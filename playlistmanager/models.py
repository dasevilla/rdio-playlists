from django.db import models


class RdioPlaylist(models.Model):
    rdio_key = models.CharField(max_length=200)
    default = models.BooleanField()
