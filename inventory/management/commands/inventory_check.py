"""
Read-only consistency check of inventory data: lists every item whose status disagrees
with its open assignment/dispatch records (the cause of "available but assigned to
someone" and "assigned but shows available"), plus other records that need a person to
decide what really happened. It never changes anything.

Run with: python manage.py inventory_check
"""
from django.core.management.base import BaseCommand
from django.db.models import Count, F, Q
from django.utils import timezone

from inventory.models import Item, Assignment, Dispatch, Reservation
from inventory.people import person_name


class Command(BaseCommand):
    help = 'List inventory records whose status and assignments disagree (read-only)'

    def handle(self, *args, **options):
        single = Item.objects.exclude(item_type__in=Item.STOCK_TRACKED_TYPES)
        open_a = Assignment.objects.filter(return_date__isnull=True).select_related('assigned_to', 'item')
        open_d = Dispatch.objects.filter(return_date__isnull=True).exclude(item__item_type__in=Item.STOCK_TRACKED_TYPES)
        holders = {}
        for a in open_a:
            holders.setdefault(a.item_id, []).append(person_name(a.assigned_to))
        dispatched = set(open_d.values_list('item_id', flat=True))
        problems = 0

        def section(title, rows, fix):
            nonlocal problems
            rows = list(rows)
            if not rows:
                return
            problems += len(rows)
            self.stdout.write(self.style.WARNING(f'\n{title} ({len(rows)})'))
            for line in rows:
                self.stdout.write(f'  - {line}')
            self.stdout.write(f'    What to do: {fix}')

        label = lambda i: f'#{i.pk} {i.name} [{i.serial_number}] status={i.get_status_display()}'
        section('Still with someone, but status says otherwise',
                [f'{label(i)} | with {", ".join(holders[i.pk])}'
                 for i in single.filter(pk__in=holders).exclude(status='ASSIGNED')],
                'Open the item page and press Return next to their name. If they really still have it, '
                'then Assign it to them again (this records it properly).')
        section('Status says Assigned, but nobody holds it',
                [label(i) for i in single.filter(status='ASSIGNED').exclude(pk__in=holders)],
                'Find out who has it and Assign it to them, or set it Available via Edit.')
        section('Held by more than one person at once',
                [f'{label(i)} | with {", ".join(holders[i.pk])}' for i in single if len(holders.get(i.pk, [])) > 1],
                'On the item page, press Return next to everyone who no longer has it.')
        section('Out at a site, but status says otherwise',
                [label(i) for i in single.filter(pk__in=dispatched).exclude(status='DISPATCHED')],
                'Return the dispatch from the item page if it is back, otherwise ask a developer to set the status.')
        section('Status says Dispatched, but no open dispatch',
                [label(i) for i in single.filter(status='DISPATCHED').exclude(pk__in=dispatched)],
                'Dispatch it again with the right project, or set it Available via Edit.')
        section('Materials marked Available with no stock left',
                [label(i) for i in Item.objects.filter(item_type__in=Item.STOCK_TRACKED_TYPES, status='AVAILABLE', quantity=0)],
                'Restock via Edit (quantity), or leave it: lists now treat it as unavailable.')
        section('Returned before they were handed out',
                [f'{a.item.name} -> {person_name(a.assigned_to)}: out {a.assignment_date}, back {a.return_date}'
                 for a in Assignment.objects.filter(return_date__lt=F('assignment_date')).select_related('item', 'assigned_to')],
                'Ask a developer to correct the dates (admin no longer allows editing them).')
        section('Pending reservations whose dates have passed',
                [f'{r.item.name} for {person_name(r.reserved_for)}: {r.start_date} to {r.end_date}'
                 for r in Reservation.objects.filter(status='PENDING', end_date__lt=timezone.localdate()).select_related('item', 'reserved_for')],
                'Cancel them on the Reservations page.')
        section('Overdue (still out after the expected return date)',
                [f'{a.item.name} -> {person_name(a.assigned_to)}, due {a.expected_return_date}'
                 for a in open_a.filter(expected_return_date__lt=timezone.localdate())],
                'Chase the holder, or record the return.')

        if problems:
            self.stdout.write(self.style.ERROR(f'\n{problems} record(s) need attention. Nothing was changed.'))
        else:
            self.stdout.write(self.style.SUCCESS('All inventory records are consistent.'))
