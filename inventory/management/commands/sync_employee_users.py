"""
Management command to sync inventory's notion of "who can be assigned tools" with
the shared Planner/skill-gap employee roster.

Run with: python manage.py sync_employee_users --dry-run   (preview only, no changes)
          python manage.py sync_employee_users              (applies the changes)

Intended to be run explicitly right after deploying to a new environment (including
production) - ALWAYS run --dry-run first there and review the "Users that would be
DEACTIVATED" list before applying, since this sync sets User.is_active=False
project-wide for anyone not linked to a currently-active employee. That's exactly
what you want for genuine non-employee accounts, but any environment can have real
people using other apps (Tracker, ACGen, ...) under accounts that were never linked
to an Employee record - dry-run is how you catch that before anyone loses access.

Safe to run repeatedly (idempotent). This is the same sync that also runs
automatically on every read of the active-employee list (e.g. opening the Assign
form) - the explicit command exists so you can review it deliberately instead of
letting it fire silently on whatever request happens to hit it first.
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from inventory.utils import sync_employee_users, get_active_employee_users, preview_employee_sync


class Command(BaseCommand):
    help = 'Link every active employee to a login and align User.is_active with the Planner/skill-gap employee roster'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show exactly what would change without changing anything',
        )

    def handle(self, *args, **options):
        if options['dry_run']:
            preview = preview_employee_sync()

            self.stdout.write(self.style.WARNING('DRY RUN - nothing has been changed\n'))

            self.stdout.write(f"Employees needing a new placeholder login: {len(preview['employees_needing_login'])}")
            for e in preview['employees_needing_login']:
                self.stdout.write(f'  + {e.name}')

            self.stdout.write(f"\nUsers that would be ACTIVATED: {len(preview['users_to_activate'])}")
            for u in preview['users_to_activate']:
                self.stdout.write(f'  + {u.username} ({u.get_full_name()})')

            self.stdout.write(self.style.ERROR(f"\nUsers that would be DEACTIVATED: {len(preview['users_to_deactivate'])}"))
            for u in preview['users_to_deactivate']:
                self.stdout.write(f'  - {u.username} ({u.get_full_name()}) [staff={u.is_staff}]')

            self.stdout.write(f"\nSuperusers protected (not employee-linked, will stay active regardless): {len(preview['protected_superusers'])}")
            for u in preview['protected_superusers']:
                self.stdout.write(f'  ! {u.username} ({u.get_full_name()})')

            self.stdout.write(self.style.WARNING(
                '\nReview the DEACTIVATED list carefully. Re-run without --dry-run to apply.'
            ))
            return

        before_active = set(User.objects.filter(is_active=True).values_list('id', flat=True))

        sync_employee_users()

        after_active = set(User.objects.filter(is_active=True).values_list('id', flat=True))
        activated = after_active - before_active
        deactivated = before_active - after_active

        self.stdout.write(self.style.SUCCESS(f'Active employees now linked to a login: {get_active_employee_users().count()}'))
        self.stdout.write(f'Users activated: {len(activated)}')
        for u in User.objects.filter(id__in=activated):
            self.stdout.write(f'  + {u.username} ({u.get_full_name()})')
        self.stdout.write(f'Users deactivated: {len(deactivated)}')
        for u in User.objects.filter(id__in=deactivated):
            self.stdout.write(f'  - {u.username} ({u.get_full_name()})')
