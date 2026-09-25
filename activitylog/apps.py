from django.apps import AppConfig


class ActivityLogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'activitylog'
    verbose_name = 'Log'

    def ready(self):
        # Connects the login / logout / failed-login handlers and the record-change tracking
        from . import changes, signals  # noqa: F401
