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
        CREATE = 'CREATE', 'Created'
        UPDATE = 'UPDATE', 'Changed'
        DELETE = 'DELETE', 'Deleted'
        # A change request whose saved records couldn't be followed (or saved none).
        ACTION = 'ACTION', 'Other action'
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
    full_name = models.CharField(max_length=150, blank=True)
    event = models.CharField(max_length=20, choices=Event.choices, db_index=True)
    app = models.CharField(max_length=50, blank=True, db_index=True)
    # What happened, in words: "Planned date changed", "Project created".
    description = models.CharField(max_length=255, blank=True)
    # The record it happened to, named when the entry is written so a later rename or
    # delete doesn't change the log: "Stage AD-2451 - FAT".
    target = models.CharField(max_length=255, blank=True)
    # Every record the request saved: [{model, object, action, fields: [{field, old, new}]}]
    changes = models.JSONField(default=list, blank=True)
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

    CHANGE_EVENTS = (Event.CREATE, Event.UPDATE, Event.DELETE, Event.ACTION)

    @property
    def person_name(self):
        """First and last name; entries written before full_name existed fall back to the
        account's current name."""
        if self.full_name:
            return self.full_name
        if self.user_id and self.user:
            return self.user.get_full_name().strip()
        return ''

    def changes_text(self):
        """One line for the Excel export: "Planned date: 12 Oct 2026 -> 19 Oct 2026; ..."."""
        parts = []
        for record in self.changes or []:
            if record.get('action') == 'more':
                parts.append(f"and {record.get('count')} more records")
                continue
            for f in record.get('fields', []):
                parts.append(f"{f['field']}: {f['old']} -> {f['new']}")
            if record is not self.changes[0] and record.get('action') in ('create', 'delete'):
                parts.append(f"{record['object']} {record['action']}d")
        return '; '.join(parts)

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.username or '-'} {self.event} {self.description}"
