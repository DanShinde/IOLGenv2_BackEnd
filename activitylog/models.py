from django.conf import settings
from django.db import models
from django.utils import timezone


class ActivityLog(models.Model):
    """One entry per thing a person did in AutoVerse: signing in or out, opening a page,
    changing data, downloading a file, or being refused access. Written by the
    middleware and the auth signals (see middleware.py / signals.py), never by views."""

    class Event(models.TextChoices):
        LOGIN = 'LOGIN', 'Login'
        LOGOUT = 'LOGOUT', 'Logout'
        LOGIN_FAILED = 'LOGIN_FAILED', 'Failed login'
        VIEW = 'VIEW', 'Page view'
        ACTION = 'ACTION', 'Action'
        DOWNLOAD = 'DOWNLOAD', 'Download'
        DENIED = 'DENIED', 'Access denied'

    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='activity_logs',
    )
    # Kept alongside the FK so the entry still names the person after the account is
    # deleted, and so failed logins (no account, or a mistyped name) are recorded too.
    username = models.CharField(max_length=150, blank=True, db_index=True)
    event = models.CharField(max_length=20, choices=Event.choices, db_index=True)
    app = models.CharField(max_length=50, blank=True, db_index=True)
    description = models.CharField(max_length=255, blank=True)
    path = models.CharField(max_length=500, blank=True)
    method = models.CharField(max_length=10, blank=True)
    view_name = models.CharField(max_length=150, blank=True)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['username', 'timestamp']),
            models.Index(fields=['app', 'timestamp']),
        ]
        verbose_name = 'activity log entry'
        verbose_name_plural = 'activity log'

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.username or '-'} {self.event} {self.description}"
