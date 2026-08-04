from django.apps import AppConfig


class GapAnalysisConfig(AppConfig):
    name = 'gap_analysis'

    def ready(self):
        from . import signals  # noqa: F401
