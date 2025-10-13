"""
Management command to generate inventory alerts
Run with: python manage.py generate_alerts
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from inventory.utils import generate_all_alerts, cleanup_resolved_alerts


class Command(BaseCommand):
    help = 'Generate alerts for low stock, overdue items, maintenance, etc.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Clean up old resolved alerts (>30 days)',
        )
        parser.add_argument(
            '--cleanup-days',
            type=int,
            default=30,
            help='Number of days to keep resolved alerts (default: 30)',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING(
            f'\n{"="*60}\n'
            f'Generating Inventory Alerts - {timezone.now()}\n'
            f'{"="*60}\n'
        ))

        # Generate all alerts
        results, total = generate_all_alerts()

        # Display results
        self.stdout.write('\nAlert Generation Results:')
        self.stdout.write('-' * 60)

        for alert_type, count in results.items():
            if count > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'  ✓ {alert_type.replace("_", " ").title()}: {count} alerts created')
                )
            else:
                self.stdout.write(
                    f'  - {alert_type.replace("_", " ").title()}: No new alerts'
                )

        self.stdout.write('-' * 60)
        self.stdout.write(
            self.style.SUCCESS(f'\nTotal: {total} alerts generated\n')
        )

        # Cleanup old alerts if requested
        if options['cleanup']:
            days = options['cleanup_days']
            self.stdout.write(f'\nCleaning up resolved alerts older than {days} days...')
            deleted_count = cleanup_resolved_alerts(days_old=days)
            self.stdout.write(
                self.style.SUCCESS(f'  ✓ Deleted {deleted_count} old resolved alerts\n')
            )

        self.stdout.write(
            self.style.SUCCESS(f'{"="*60}\n✓ Alert generation completed successfully!\n{"="*60}\n')
        )
