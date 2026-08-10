"""
Management command to email a digest of overdue assignments/dispatches,
low-stock materials, and expired reservations.

Run with: python manage.py notify_overdue
Intended to be scheduled (cron / Windows Task Scheduler) e.g. once a day.
"""
from django.core.management.base import BaseCommand
from inventory.utils import send_overdue_digest


class Command(BaseCommand):
    help = 'Email a digest of overdue assignments/dispatches, low stock materials, and expired reservations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be sent without actually emailing anyone',
        )
        parser.add_argument(
            '--to',
            nargs='*',
            help='Override recipient email addresses (defaults to active staff users with an email on file)',
        )

    def handle(self, *args, **options):
        context, recipients, total_issues = send_overdue_digest(
            recipient_list=options.get('to'),
            dry_run=options['dry_run'],
        )

        if total_issues == 0:
            self.stdout.write(self.style.SUCCESS('No overdue items, low stock, or expired reservations. Nothing to send.'))
            return

        self.stdout.write(f'Found {total_issues} issue(s):')
        self.stdout.write(f"  Overdue assignments:  {len(context['overdue_assignments'])}")
        self.stdout.write(f"  Overdue dispatches:   {len(context['overdue_dispatches'])}")
        self.stdout.write(f"  Low stock materials:  {len(context['low_stock_items'])}")
        self.stdout.write(f"  Expired reservations: {len(context['expired_reservations'])}")

        if options['dry_run']:
            self.stdout.write(self.style.WARNING(
                f"Dry run - would have emailed: {', '.join(recipients) if recipients else '(no recipients found)'}"
            ))
        elif not recipients:
            self.stdout.write(self.style.ERROR(
                'No recipients - no active staff user has an email address on file, and none were provided via --to.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(f"Digest emailed to: {', '.join(recipients)}"))
