from django.conf.urls import patterns, url

urlpatterns = patterns('',
    url(r'^add-playlist/$', 'playlistmanager.views.add_playlist', name='add-playlist'),
    url(r'^sendgrid/$', 'playlistmanager.views.sendgrid_add', name='sendgrid-add'),
    url(r'^twilio/$', 'playlistmanager.views.twilio_add', name='twilio-add'),
)
