import logging
import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django_twilio.decorators import twilio_view
from requests_oauthlib import OAuth2
from social.apps.django_app.utils import load_strategy
from twilio.twiml import Response
import requests
import sendgrid

from playlistmanager.models import RdioPlaylist


OAUTH2_RESOURCE_URL = 'https://www.rdio.com/api/1/'


def get_rdio_social():
    # TODO: Better user selection
    user = User.objects.get(pk=1)
    social = user.social_auth.filter(provider='rdio-oauth2')[0]
    return social


def refresh_token():
    strategy = load_strategy(backend='rdio-oauth2')
    logging.info('Using the refresh token')
    social = get_rdio_social()
    social.refresh_token(strategy=strategy)


def rdio_oauth2_auth():
    social = get_rdio_social()
    access_token = social.extra_data['access_token']
    return OAuth2(token={
      'access_token': access_token,
      'token_type': 'bearer'
    })


def rdio_request(method, params):
    params['method'] = method
    r = requests.post(OAUTH2_RESOURCE_URL, auth=rdio_oauth2_auth(), data=params)
    return r


def rdio_request_with_refresh(method, params):
    r = rdio_request(method, params)

    # Try refreshing the token
    if r.status_code == 401:
        refresh_token()
        r = rdio_request(method, params)

    return r


def rdio_track_from_text(query):
    """
    Returns a track object
    """
    r = rdio_request_with_refresh('search', {
        'types': 'track',
        'query': query
    })

    # TODO: Handle token refresh
    r.raise_for_status()

    payload = r.json()
    search_results = payload['result']
    if search_results['number_results'] == 0:
        return None

    return search_results['results'][0]


def add_track_to_playlist(playlist_key, track_key):
    """
    Returns a playlist object
    """
    r = rdio_request_with_refresh('addToPlaylist', {
        'playlist': playlist_key,
        'tracks': track_key
    })

    r.raise_for_status()

    payload = r.json()
    return payload['result']


def build_email_body(rdio_playlist, rdio_track):
    email_body = '"%s" by "%s" added to "%s". Listen here: %s' % (
        rdio_track['name'],
        rdio_track['artist'],
        rdio_playlist['name'],
        rdio_playlist['shortUrl'],
    )

    email_body += '\n\n'

    email_body += 'Get started with the Rdio API at %s' % (
        'http://www.rdio.com/developers/'
    )

    return email_body


def query_to_playlist(playlist_id, query):
    try:
        playlist = RdioPlaylist.objects.get(id=playlist_id)
    except ValueError:
        logging.warn('Invalid playlist ID: %s', playlist_id)
        return None
    except RdioPlaylist.DoesNotExist:
        logging.warn('Unknown playlist ID: %s', playlist_id)
        return None

    rdio_track = rdio_track_from_text(query)

    if rdio_track is None:
        logging.warn('%s cannot by found on Rdio' % query)
        return None

    rdio_playlist = add_track_to_playlist(playlist.rdio_key, rdio_track['key'])

    return rdio_playlist, rdio_track


@csrf_exempt
def sendgrid_add(request):
    playlist_id, _ = request.POST['to'].split('@')
    query = request.POST['subject']
    if len(query) == 0:
        query = request.POST['text']

    rdio_objs = query_to_playlist(playlist_id, query)
    if rdio_objs is None:
        return HttpResponse(status=200)

    rdio_playlist, rdio_track = rdio_objs

    envelope = json.loads(request.POST['envelope'])

    email_body = build_email_body(rdio_playlist, rdio_track)
    message = sendgrid.Mail(
        to=envelope['from'],
        subject='Re: %s' % request.POST['subject'],
        text=email_body,
        from_email=envelope['to'],
        from_name='Rdio API',
        reply_to='developersupport@rd.io'
    )

    sg = sendgrid.SendGridClient(
        settings.SENDGRID_USERNAME,
        settings.SENDGRID_PASSWORD,
        raise_errors=True
    )

    try:
        sg.send(message)
    except sendgrid.SendGridClientError as e:
        logging.exception(e)
    except sendgrid.SendGridServerError as e:
        logging.exception(e)

    return HttpResponse(status=200)


def build_sms_body(rdio_playlist, rdio_track):
    sms_body = '"%s" by "%s" added to %s' % (
        rdio_track['name'],
        rdio_track['artist'],
        rdio_playlist['shortUrl'],
    )

    sms_body += '\n\n'

    sms_body += 'Build your own app: %s' % (
        'http://www.rdio.com/developers/'
    )

    return sms_body


@twilio_view
def twilio_add(request):
    # TODO: Query the proper playlist
    playlist_id = RdioPlaylist.objects.get(default=True).id
    query = request.POST['Body']

    rdio_objs = query_to_playlist(playlist_id, query)
    if rdio_objs is None:
        return HttpResponse(status=200)

    rdio_playlist, rdio_track = rdio_objs

    sms_body = build_sms_body(rdio_playlist, rdio_track)

    r = Response()
    r.message(sms_body)
    return r


@login_required
def add_playlist(request):
    if request.method == 'POST':
        r = rdio_request_with_refresh('createPlaylist', {
            'name': request.POST['title'],
            'description': '',
            'tracks': '',
        })
        rdio_playlist = r.json()['result']

        RdioPlaylist.objects.filter(default=True).update(default=False)

        playlist = RdioPlaylist.objects.create(
            rdio_key=rdio_playlist['key'],
            default=True
        )
        playlist.save()

    return render(request, 'add-playlist.html')
