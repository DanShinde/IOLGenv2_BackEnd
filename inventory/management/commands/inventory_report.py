"""
Management command to generate inventory summary report
Run with: python manage.py inventory_report
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from inventory.utils import get_inventory_summary, calculate_total_inventory_value


class Command(BaseCommand):
    help = 'Generate comprehensive inventory summary report'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING(
            f'\n{"="*70}\n'
            f'INVENTORY SUMMARY REPORT\n'
            f'Generated: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}\n'
            f'{"="*70}\n'
        ))

        summary = get_inventory_summary()
        total_value = calculate_total_inventory_value()

        # Inventory Overview
        self.stdout.write(self.style.HTTP_INFO('\nINVENTORY OVERVIEW'))
        self.stdout.write('-' * 70)
        self.stdout.write(f'  Total Items:              {summary["total_items"]}')
        self.stdout.write(f'  Tools:                    {summary["total_tools"]}')
        self.stdout.write(f'  Materials:                {summary["total_materials"]}')
        self.stdout.write(f'  Total Purchase Value:     ${total_value:,.2f}')

        # Status Breakdown
        self.stdout.write(self.style.HTTP_INFO('\nSTATUS BREAKDOWN'))
        self.stdout.write('-' * 70)
        self.stdout.write(f'  Available:                {summary["available_items"]}')
        self.stdout.write(f'  Assigned:                 {summary["assigned_items"]}')
        self.stdout.write(f'  Dispatched:               {summary["dispatched_items"]}')
        self.stdout.write(f'  Consumed:                 {summary["consumed_items"]}')
        self.stdout.write(f'  Retired:                  {summary["retired_items"]}')

        # Stock
        self.stdout.write(self.style.HTTP_INFO('\nSTOCK'))
        self.stdout.write('-' * 70)
        if summary["low_stock_items"] > 0:
            self.stdout.write(
                self.style.ERROR(f'  Low Stock Materials:      {summary["low_stock_items"]}')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'  Low Stock Materials:      {summary["low_stock_items"]}')
            )

        # Assignments
        self.stdout.write(self.style.HTTP_INFO('\nASSIGNMENTS'))
        self.stdout.write('-' * 70)
        self.stdout.write(f'  Active Assignments:       {summary["active_assignments"]}')
        if summary["overdue_assignments"] > 0:
            self.stdout.write(
                self.style.ERROR(f'  Overdue Assignments:      {summary["overdue_assignments"]}')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'  Overdue Assignments:      {summary["overdue_assignments"]}')
            )

        # Dispatches
        self.stdout.write(self.style.HTTP_INFO('\nDISPATCHES'))
        self.stdout.write('-' * 70)
        self.stdout.write(f'  Active Dispatches:        {summary["active_dispatches"]}')
        if summary["overdue_dispatches"] > 0:
            self.stdout.write(
                self.style.ERROR(f'  Overdue Dispatches:       {summary["overdue_dispatches"]}')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'  Overdue Dispatches:       {summary["overdue_dispatches"]}')
            )

        # Summary
        self.stdout.write(self.style.WARNING(f'\n{"="*70}'))

        issues = (
            summary["low_stock_items"] +
            summary["overdue_assignments"] +
            summary["overdue_dispatches"]
        )

        if issues == 0:
            self.stdout.write(
                self.style.SUCCESS('No issues found. Inventory is in good shape.\n')
            )
        else:
            self.stdout.write(
                self.style.ERROR(f'{issues} issue(s) require attention.\n')
            )

        self.stdout.write(self.style.WARNING(f'{"="*70}\n'))
