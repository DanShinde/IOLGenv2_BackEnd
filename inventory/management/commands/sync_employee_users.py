"""
Management command that links every active employee (the shared Planner/skill-gap
roster) to a login, so they can be picked in inventory's assign / dispatch /
reservation dropdowns.

Run with: python manage.py sync_employee_users --dry-run   (preview only, no changes)
          python manage.py sync_employee_users              (applies the changes)

It never activates or deactivates accounts: User.is_active is set only by
administrators in Django admin. Safe to run repeatedly (idempotent). The same sync
also runs when the Assign / Dispatch / Reservation pages are opened.
"""
from django.core.management.base import BaseCommand

from inventory.utils import sync_employee_users, get_active_employee_users, preview_employee_sync


class Command(BaseCommand):
    help = 'Link every active employee to a login so they appear in inventory dropdowns'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show exactly what would change without changing anything',
        )

    def handle(self, *args, **options):
        if options['dry_run']:
            preview = preview_employee_sync()
            self.stdout.write(self.style.WARNING('DRY RUN - nothing has been changed
'))
            self.stdout.write(f"Employees needing a new placeholder login: {len(preview['employees_needing_login'])}")
            for e in preview['employees_needing_login']:
                self.stdout.write(f'  + {e.name}')
            self.stdout.write('
Re-run without --dry-run to apply.')
            return

        sync_employee_users()
        self.stdout.write(self.style.SUCCESS(f'Active employees now linked to a login: {get_active_employee_users().count()}'))
