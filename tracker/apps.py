# tracker/apps.py

from django.apps import AppConfig

class TrackerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tracker'

    def ready(self):
        import tracker.signals  # ✅ import your signals here
