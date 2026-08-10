"""
Shared business logic for state-changing inventory actions.

These functions carry the actual rules (what happens to an Item's status/location,
what gets written to History) and are called from both the HTML views and the REST
API, so the two surfaces can never drift apart on what a "return" or a "fulfilled
reservation" actually does.
"""
from datetime import date

from django.db import transaction

from .models import Assignment, History, RETURN_CONDITION_CHOICES, resolve_return_status
from .utils import get_active_employee_users

RETURN_CONDITION_LABELS = dict(RETURN_CONDITION_CHOICES)


def process_return(target, condition, return_notes, performed_by, details_prefix):
    """
    Shared by Assignment and Dispatch returns: sets return_date/condition/notes on
    `target` (an Assignment or Dispatch instance), moves the item to the right
    status/location based on condition, and logs History.

    Returns the updated Item.
    """
    new_status, location, history_action = resolve_return_status(condition)

    with transaction.atomic():
        target.return_date = date.today()
        target.return_condition = condition
        target.return_notes = return_notes
        target.save()

        item = target.item
        item.status = new_status
        item.location = location
        item.save()

        details = f'{details_prefix} - Condition: {RETURN_CONDITION_LABELS[condition]}'
        if return_notes:
            details += f'. {return_notes}'

        History.objects.create(
            item=item,
            action=history_action,
            user=performed_by,
            details=details,
            location=location
        )

    return item


def fulfill_reservation(reservation, performed_by):
    """Convert a PENDING reservation into a real Assignment. Raises ValueError if it can't be fulfilled."""
    if reservation.status != 'PENDING':
        raise ValueError('This reservation is no longer pending.')

    item = reservation.item
    if item.status != 'AVAILABLE':
        raise ValueError(f'{item.name} is not currently available (status: {item.get_status_display()}).')

    who = reservation.reserved_for.get_full_name() or reservation.reserved_for.username

    if not get_active_employee_users().filter(pk=reservation.reserved_for_id).exists():
        raise ValueError(f'{who} is no longer an active employee, so this reservation cannot be fulfilled.')

    with transaction.atomic():
        assignment = Assignment.objects.create(
            item=item,
            assigned_to=reservation.reserved_for,
            assigned_by=performed_by,
            assignment_date=date.today(),
            expected_return_date=reservation.end_date,
            notes=f'Fulfilled from reservation. {reservation.notes}'.strip()
        )

        item.status = 'ASSIGNED'
        item.location = f'With {who}'
        item.save()

        reservation.status = 'FULFILLED'
        reservation.fulfilled_assignment = assignment
        reservation.save()

        History.objects.create(
            item=item,
            action='ASSIGNED',
            user=performed_by,
            details=f'Reservation fulfilled - assigned to {who}',
            location=item.location
        )

    return assignment


def cancel_reservation(reservation):
    """Cancel a PENDING reservation. Raises ValueError if it isn't pending."""
    if reservation.status != 'PENDING':
        raise ValueError('This reservation is no longer pending.')
    reservation.status = 'CANCELLED'
    reservation.save()
