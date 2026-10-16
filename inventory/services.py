"""
Shared business logic for state-changing inventory actions.

Every action that moves an item (assign, transfer, dispatch, return, retire, fulfil a
reservation) goes through here, from both the HTML views and the REST API, so an item's
status, its open Assignment/Dispatch rows and its History can never drift apart.

Each function locks the item row (select_for_update) inside a transaction and re-checks
the item's state under the lock, so two people acting on the same item at the same
moment (or a double-clicked submit) can't both succeed. Problems are raised as
InventoryError with a message fit to show the user.
"""
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Item, Assignment, Dispatch, History, RETURN_CONDITION_CHOICES, resolve_return_status
from .people import person_name
from .utils import get_active_employee_users, sync_employee_users

RETURN_CONDITION_LABELS = dict(RETURN_CONDITION_CHOICES)


class InventoryError(ValueError):
    """An action that can't be carried out in the item's current state."""


def _locked(item):
    return Item.objects.select_for_update().get(pk=item.pk)


def _close_open_assignments(item, close_date, user, reason):
    """Close every open assignment of a single-unit item (normally at most one; more can
    exist only in data damaged before this was enforced). Returns the holders' names."""
    names = []
    for a in item.assignments.select_for_update().filter(return_date__isnull=True).select_related('assigned_to'):
        a.return_date = max(close_date, a.assignment_date)
        a.return_condition = a.return_condition or 'GOOD'
        a.save(update_fields=['return_date', 'return_condition'])
        names.append(person_name(a.assigned_to))
        History.objects.create(item=item, action='RETURNED', user=user,
                               details=f'Returned by {names[-1]} ({reason})', location=item.location)
    return names


def assign_item(item, assigned_to, performed_by, assignment_date, expected_return_date=None, notes='', quantity=1):
    """Assign (or, for a single-unit item someone already has, transfer) an item.
    Returns (assignment, message)."""
    who = person_name(assigned_to)
    with transaction.atomic():
        item = _locked(item)
        if item.is_stock_tracked:
            if item.status != 'AVAILABLE' or quantity > item.quantity:
                raise InventoryError(f'Only {item.quantity} units of {item.name} are in stock.')
            assignment = Assignment.objects.create(
                item=item, quantity=quantity, assigned_to=assigned_to, assigned_by=performed_by,
                assignment_date=assignment_date, expected_return_date=expected_return_date, notes=notes)
            Item.objects.filter(pk=item.pk).update(quantity=F('quantity') - quantity)
            item.refresh_from_db()
            History.objects.create(item=item, action='ASSIGNED', user=performed_by,
                                   details=f'{quantity} units assigned to {who}', location=item.location or 'Warehouse')
            return assignment, f'Assigned {quantity} units of {item.name} to {who}. Remaining stock: {item.quantity}'

        if item.open_dispatches().exists() or item.status not in ('AVAILABLE', 'ASSIGNED'):
            raise InventoryError(f'{item.name} is {item.get_status_display().lower()} and cannot be assigned right now.')
        current = list(item.open_assignments().select_related('assigned_to'))
        if any(a.assigned_to_id == assigned_to.pk for a in current) and len(current) == 1:
            raise InventoryError(f'{item.name} is already assigned to {who}.')
        latest_start = max((a.assignment_date for a in current), default=None)
        if latest_start and assignment_date < latest_start:
            raise InventoryError(f'The transfer date cannot be before {latest_start:%d %b %Y}, '
                                 f'when the current holder received {item.name}.')

        prev = _close_open_assignments(item, assignment_date, performed_by, 'Transfer')
        assignment = Assignment.objects.create(
            item=item, assigned_to=assigned_to, assigned_by=performed_by,
            assignment_date=assignment_date, expected_return_date=expected_return_date,
            notes=(f'Transferred from {", ".join(prev)}. {notes}' if prev else notes).strip())
        item.status = 'ASSIGNED'
        item.location = f'With {who}'
        item.save(update_fields=['status', 'location', 'updated_at'])
        if prev:
            History.objects.create(item=item, action='TRANSFERRED', user=performed_by,
                                   details=f'Transferred from {", ".join(prev)} to {who}', location=item.location)
            return assignment, f'Transferred {item.name} from {", ".join(prev)} to {who}.'
        History.objects.create(item=item, action='ASSIGNED', user=performed_by,
                               details=f'Assigned to {who}', location=item.location)
        return assignment, f'Assigned {item.name} to {who}.'


def dispatch_item(item, project, site_location, responsible_person, performed_by, dispatch_date,
                  expected_return_date=None, notes='', quantity=1):
    """Send an item to a project site. Materials are consumed; single-unit items stay
    out until returned (anyone holding it is treated as handing it over). Returns a message."""
    responsible = person_name(responsible_person)
    site = site_location or 'N/A'
    with transaction.atomic():
        item = _locked(item)
        if item.is_stock_tracked:
            if item.status != 'AVAILABLE' or quantity > item.quantity:
                raise InventoryError(f'Cannot dispatch {quantity} units. Only {item.quantity} available.')
            Dispatch.objects.create(item=item, quantity=quantity, project=project, site_location=site_location,
                                    responsible_person=responsible_person, dispatched_by=performed_by,
                                    dispatch_date=dispatch_date, notes=notes)
            Item.objects.filter(pk=item.pk).update(quantity=F('quantity') - quantity)
            item.refresh_from_db()
            if item.quantity <= 0:
                item.status = 'CONSUMED'
                item.location = f'Consumed at {project}'
            else:
                item.location = f'Warehouse (Partially dispatched to {project})'
            item.save(update_fields=['status', 'location', 'updated_at'])
            History.objects.create(item=item, action='CONSUMED', user=performed_by,
                                   details=f'{quantity} units dispatched to {project} (Site: {site}) - received by {responsible}',
                                   location=f'{project} - {site}')
            return f'Dispatched {quantity} units of {item.name} to {project}. Remaining stock: {item.quantity}'

        if item.open_dispatches().exists() or item.status not in ('AVAILABLE', 'ASSIGNED'):
            raise InventoryError(f'{item.name} is {item.get_status_display().lower()} and cannot be dispatched right now.')
        _close_open_assignments(item, dispatch_date, performed_by, 'For Dispatch')
        Dispatch.objects.create(item=item, quantity=1, project=project, site_location=site_location,
                                responsible_person=responsible_person, dispatched_by=performed_by,
                                dispatch_date=dispatch_date, expected_return_date=expected_return_date, notes=notes)
        item.status = 'DISPATCHED'
        item.location = f'{project} - {site}'
        item.save(update_fields=['status', 'location', 'updated_at'])
        History.objects.create(item=item, action='DISPATCHED', user=performed_by,
                               details=f'Dispatched to {project} (Site: {site}) - responsible person: {responsible}',
                               location=item.location)
        return f'Dispatched {item.name} to {project} (responsible: {responsible}).'


def process_return(target, condition, return_notes, performed_by, details_prefix):
    """
    Shared by Assignment and Dispatch returns: closes `target` (an Assignment or
    Dispatch), moves the item to the right status/location based on condition, and logs
    History. A single-unit item's status only changes when nothing else still holds it.

    Returns the updated Item.
    """
    new_status, location, history_action = resolve_return_status(condition)
    model = type(target)

    with transaction.atomic():
        item = _locked(target.item)
        target = model.objects.select_for_update().get(pk=target.pk)
        if target.return_date is not None:
            raise InventoryError('This has already been returned.')
        started = target.dispatch_date if isinstance(target, Dispatch) else target.assignment_date
        target.return_date = max(timezone.localdate(), started)  # never before it went out
        target.return_condition = condition
        target.return_notes = return_notes
        target.save()

        details = f'{details_prefix} - Condition: {RETURN_CONDITION_LABELS[condition]}'
        if return_notes:
            details += f'. {return_notes}'

        if isinstance(target, Assignment) and item.is_stock_tracked:
            # Only a good-condition return puts the units back into stock; damaged or lost
            # units are written off (the material itself stays in service).
            if condition == 'GOOD':
                Item.objects.filter(pk=item.pk).update(quantity=F('quantity') + target.quantity)
                item.refresh_from_db()
                if item.status == 'CONSUMED' and item.quantity > 0:
                    item.status = 'AVAILABLE'
                    item.save(update_fields=['status', 'updated_at'])
            else:
                details += f' ({target.quantity} units written off, not returned to stock)'
            history_action = 'RETURNED'
            location = item.location or 'Warehouse'
        elif item.is_out:
            # Someone else still has it (data from before transfers closed every holder):
            # leave the item where it is.
            location = item.location
            details += ' (item still out with another holder; status unchanged)'
        elif item.status in ('ASSIGNED', 'DISPATCHED'):
            item.status = new_status
            item.location = location
            item.save(update_fields=['status', 'location', 'updated_at'])
        else:
            # e.g. an item retired while it was still out: record the return, don't revive it
            location = item.location
            details += f' (item is {item.get_status_display().lower()}; status unchanged)'

        History.objects.create(item=item, action=history_action, user=performed_by, details=details, location=location)

    return item


def retire_item(item, performed_by, reason=''):
    """Retire a single item. Refused while it is still out with someone or at a site."""
    with transaction.atomic():
        item = _locked(item)
        if item.status == 'RETIRED':
            return item
        if item.is_out or item.open_assignments().exists():
            raise InventoryError(f'{item.name} is still out (assigned or dispatched). Record its return first.')
        item.status = 'RETIRED'
        item.save(update_fields=['status', 'updated_at'])
        History.objects.create(item=item, action='RETIRED', user=performed_by,
                               details=f'Retired from service{": " + reason if reason else ""}', location=item.location)
    return item


def fulfill_reservation(reservation, performed_by):
    """Convert a PENDING reservation into a real Assignment. Raises InventoryError if it can't be fulfilled."""
    if reservation.status != 'PENDING':
        raise InventoryError('This reservation is no longer pending.')

    who = person_name(reservation.reserved_for)
    sync_employee_users()
    if not get_active_employee_users().filter(pk=reservation.reserved_for_id).exists():
        raise InventoryError(f'{who} is no longer an active employee, so this reservation cannot be fulfilled.')

    with transaction.atomic():
        reservation = type(reservation).objects.select_for_update().get(pk=reservation.pk)
        if reservation.status != 'PENDING':
            raise InventoryError('This reservation is no longer pending.')
        item = _locked(reservation.item)
        if item.status != 'AVAILABLE' or item.is_out:
            raise InventoryError(f'{item.name} is not currently available (status: {item.get_status_display()}).')

        assignment = Assignment.objects.create(
            item=item, assigned_to=reservation.reserved_for, assigned_by=performed_by,
            assignment_date=timezone.localdate(), expected_return_date=reservation.end_date,
            notes=f'Fulfilled from reservation. {reservation.notes}'.strip())
        item.status = 'ASSIGNED'
        item.location = f'With {who}'
        item.save(update_fields=['status', 'location', 'updated_at'])

        reservation.status = 'FULFILLED'
        reservation.fulfilled_assignment = assignment
        reservation.save()

        History.objects.create(item=item, action='ASSIGNED', user=performed_by,
                               details=f'Reservation fulfilled - assigned to {who}', location=item.location)
    return assignment


def cancel_reservation(reservation):
    """Cancel a PENDING reservation. Raises InventoryError if it isn't pending."""
    if reservation.status != 'PENDING':
        raise InventoryError('This reservation is no longer pending.')
    reservation.status = 'CANCELLED'
    reservation.save()
