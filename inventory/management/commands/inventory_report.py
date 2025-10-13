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
        self.stdout.write(self.style.HTTP_INFO('\n📦 INVENTORY OVERVIEW'))
        self.stdout.write('-' * 70)
        self.stdout.write(f'  Total Items:              {summary["total_items"]}')
        self.stdout.write(f'  Tools:                    {summary["total_tools"]}')
        self.stdout.write(f'  Materials:                {summary["total_materials"]}')
        self.stdout.write(f'  Total Current Value:      ${total_value:,.2f}')

        # Status Breakdown
        self.stdout.write(self.style.HTTP_INFO('\n📊 STATUS BREAKDOWN'))
        self.stdout.write('-' * 70)
        self.stdout.write(f'  Available:                {summary["available_items"]}')
        self.stdout.write(f'  Assigned:                 {summary["assigned_items"]}')
        self.stdout.write(f'  Dispatched:               {summary["dispatched_items"]}')
        self.stdout.write(f'  Under Maintenance:        {summary["maintenance_items"]}')

        # Stock Alerts
        self.stdout.write(self.style.HTTP_INFO('\n⚠️  STOCK ALERTS'))
        self.stdout.write('-' * 70)
        if summary["low_stock_items"] > 0:
            self.stdout.write(
                self.style.ERROR(f'  Low Stock Items:          {summary["low_stock_items"]} ⚠️')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'  Low Stock Items:          {summary["low_stock_items"]} ✓')
            )

        if summary["critical_items"] > 0:
            self.stdout.write(f'  Critical Items:           {summary["critical_items"]}')

        # Assignments
        self.stdout.write(self.style.HTTP_INFO('\n👥 ASSIGNMENTS'))
        self.stdout.write('-' * 70)
        self.stdout.write(f'  Active Assignments:       {summary["active_assignments"]}')
        if summary["overdue_assignments"] > 0:
            self.stdout.write(
                self.style.ERROR(f'  Overdue Assignments:      {summary["overdue_assignments"]} ⚠️')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'  Overdue Assignments:      {summary["overdue_assignments"]} ✓')
            )

        # Dispatches
        self.stdout.write(self.style.HTTP_INFO('\n🚚 DISPATCHES'))
        self.stdout.write('-' * 70)
        self.stdout.write(f'  Active Dispatches:        {summary["active_dispatches"]}')
        if summary["overdue_dispatches"] > 0:
            self.stdout.write(
                self.style.ERROR(f'  Overdue Dispatches:       {summary["overdue_dispatches"]} ⚠️')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'  Overdue Dispatches:       {summary["overdue_dispatches"]} ✓')
            )

        # Maintenance
        self.stdout.write(self.style.HTTP_INFO('\n🔧 MAINTENANCE'))
        self.stdout.write('-' * 70)
        self.stdout.write(f'  Pending Maintenance:      {summary["pending_maintenance"]}')
        if summary["overdue_maintenance"] > 0:
            self.stdout.write(
                self.style.ERROR(f'  Overdue Maintenance:      {summary["overdue_maintenance"]} ⚠️')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'  Overdue Maintenance:      {summary["overdue_maintenance"]} ✓')
            )

        # Alerts
        self.stdout.write(self.style.HTTP_INFO('\n🔔 SYSTEM ALERTS'))
        self.stdout.write('-' * 70)
        self.stdout.write(f'  Unresolved Alerts:        {summary["unresolved_alerts"]}')
        if summary["critical_alerts"] > 0:
            self.stdout.write(
                self.style.ERROR(f'  Critical Alerts:          {summary["critical_alerts"]} ⚠️')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'  Critical Alerts:          {summary["critical_alerts"]} ✓')
            )

        # Summary
        self.stdout.write(self.style.WARNING(f'\n{"="*70}'))

        issues = (
            summary["low_stock_items"] +
            summary["overdue_assignments"] +
            summary["overdue_dispatches"] +
            summary["overdue_maintenance"] +
            summary["critical_alerts"]
        )

        if issues == 0:
            self.stdout.write(
                self.style.SUCCESS('✓ No critical issues found! Inventory is in good shape.\n')
            )
        else:
            self.stdout.write(
                self.style.ERROR(f'⚠️  {issues} issues require attention!\n')
            )

        self.stdout.write(self.style.WARNING(f'{"="*70}\n'))
