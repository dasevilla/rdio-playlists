from django.contrib import admin

from playlistmanager.models import RdioPlaylist


class RdioPlaylistAdmin(admin.ModelAdmin):
    list_display = ('id', 'rdio_key', 'default')
    list_filter = ('default',)


admin.site.register(RdioPlaylist, RdioPlaylistAdmin)
