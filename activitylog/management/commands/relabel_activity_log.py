from types import SimpleNamespace

from django.core.management.base import BaseCommand

from activitylog.models import ActivityLog
from activitylog.services import denied_title, describe, full_name_for

E = ActivityLog.Event


class Command(BaseCommand):
    help = ("Rewrites entries logged before readable titles existed, e.g. \"Project Detail "
            "(project_id=37)\" -> \"Opened project\" + \"Project AD-2451\". Records are named "
            "as they are today; old and new values can't be recovered for past changes.")

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show what would change without saving.')

    def handle(self, *args, **options):
        # Entries with no full name or record name predate the new format.
        entries = ActivityLog.objects.filter(full_name='', target='').select_related('user')
        updated = 0
        for entry in entries.iterator():
            title, target = entry.description, entry.target
            if entry.event in (E.VIEW, E.ACTION, E.DOWNLOAD, E.DENIED) and entry.path:
                request = SimpleNamespace(path_info=entry.path, method=entry.method or 'GET', resolver_match=None)
                title, target = describe(request)
                if entry.event == E.DENIED:
                    title = denied_title(title)
            full_name = full_name_for(entry.user, entry.username)[:150]
            if (title, target, full_name) == (entry.description, entry.target, entry.full_name):
                continue
            updated += 1
            if options['dry_run']:
                self.stdout.write(f"{entry.pk}: {entry.description!r} -> {title!r} | {target!r} | {full_name!r}")
                continue
            entry.description, entry.target, entry.full_name = title[:255], target[:255], full_name
            entry.save(update_fields=['description', 'target', 'full_name'])
        verb = 'Would update' if options['dry_run'] else 'Updated'
        self.stdout.write(self.style.SUCCESS(f"{verb} {updated} entries."))
