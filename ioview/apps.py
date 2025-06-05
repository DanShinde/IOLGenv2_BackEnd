from django.apps import AppConfig


class IoviewConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ioview'

    def ready(self):
        import ioview.signals
