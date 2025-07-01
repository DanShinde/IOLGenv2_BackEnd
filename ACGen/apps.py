from django.apps import AppConfig


class AcgenConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ACGen'

    # def ready(self):
    #     from .apscheduler import start  # Import your scheduler function
    #     start()