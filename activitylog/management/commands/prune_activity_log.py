from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from activitylog.models import ActivityLog


class Command(BaseCommand):
    help = "Deletes activity log entries older than N days (the log grows with every page view and change)."

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=180, help='Keep this many days (default 180).')

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=options['days'])
        deleted, _ = ActivityLog.objects.filter(timestamp__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} entries older than {options['days']} days."))
