from django.apps import AppConfig


class ActivityLogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'activitylog'
    verbose_name = 'Log'

    def ready(self):
        # Connects the login / logout / failed-login signal handlers
        from . import signals  # noqa: F401
