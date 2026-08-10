"""
Utility functions for inventory management
"""
from decimal import Decimal
from django.db.models import F, Sum, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from .models import Item, Assignment, Dispatch, Reservation


def get_low_stock_items():
    """Materials whose stock has fallen to or below their reorder threshold"""
    return Item.objects.filter(item_type='MATERIAL', quantity__lte=F('min_quantity'))


def get_overdue_assignments():
    """Active tool assignments past their expected return date"""
    return Assignment.objects.filter(
        return_date__isnull=True,
        expected_return_date__lt=timezone.now().date()
    ).select_related('item', 'assigned_to')


def get_overdue_dispatches():
    """Active tool dispatches past their expected return date (materials are never returned)"""
    return Dispatch.objects.filter(
        return_date__isnull=True,
        expected_return_date__lt=timezone.now().date()
    ).exclude(item__item_type='MATERIAL').select_related('item')


def get_expired_reservations():
    """Pending reservations whose window passed without being fulfilled"""
    return Reservation.objects.filter(
        status='PENDING',
        end_date__lt=timezone.now().date()
    ).select_related('item', 'reserved_for')


def build_overdue_digest_context():
    return {
        'overdue_assignments': list(get_overdue_assignments()),
        'overdue_dispatches': list(get_overdue_dispatches()),
        'low_stock_items': list(get_low_stock_items()),
        'expired_reservations': list(get_expired_reservations()),
        'today': timezone.now().date(),
    }


def send_overdue_digest(recipient_list=None, dry_run=False):
    """
    Build a digest of overdue assignments/dispatches, low-stock materials, and expired
    reservations, and email it to `recipient_list` (defaults to active staff users with
    an email address on file).

    Returns (context, recipient_list, total_issues). Nothing is sent if there are no
    issues, no recipients, or dry_run is True - callers can inspect the return value to
    report what would have happened.
    """
    from django.contrib.auth.models import User
    from django.core.mail import send_mail
    from django.template.loader import render_to_string

    context = build_overdue_digest_context()
    total_issues = (
        len(context['overdue_assignments']) +
        len(context['overdue_dispatches']) +
        len(context['low_stock_items']) +
        len(context['expired_reservations'])
    )

    if recipient_list is None:
        recipient_list = list(
            User.objects.filter(is_staff=True, is_active=True)
            .exclude(email='').values_list('email', flat=True)
        )

    if total_issues == 0 or not recipient_list or dry_run:
        return context, recipient_list, total_issues

    html_message = render_to_string('inventory/email/overdue_digest.html', context)
    send_mail(
        subject=f'Inventory Alert: {total_issues} issue(s) need attention',
        message='',
        from_email=None,
        recipient_list=recipient_list,
        html_message=html_message,
        fail_silently=False,
    )
    return context, recipient_list, total_issues


def get_inventory_summary():
    """Get comprehensive inventory summary"""
    return {
        'total_items': Item.objects.count(),
        'total_tools': Item.objects.filter(item_type='TOOL').count(),
        'total_materials': Item.objects.filter(item_type='MATERIAL').count(),
        'available_items': Item.objects.filter(status='AVAILABLE').count(),
        'assigned_items': Item.objects.filter(status='ASSIGNED').count(),
        'dispatched_items': Item.objects.filter(status='DISPATCHED').count(),
        'consumed_items': Item.objects.filter(status='CONSUMED').count(),
        'retired_items': Item.objects.filter(status='RETIRED').count(),
        'low_stock_items': get_low_stock_items().count(),
        'active_assignments': Assignment.objects.filter(return_date__isnull=True).count(),
        'overdue_assignments': get_overdue_assignments().count(),
        'active_dispatches': Dispatch.objects.filter(return_date__isnull=True, item__item_type='TOOL').count(),
        'overdue_dispatches': get_overdue_dispatches().count(),
    }


def calculate_total_inventory_value():
    """Total purchase value currently held: sum(purchase_cost * quantity) across all items"""
    total = Item.objects.filter(purchase_cost__isnull=False).aggregate(
        total=Coalesce(
            Sum(F('purchase_cost') * F('quantity'), output_field=DecimalField(max_digits=14, decimal_places=2)),
            Decimal('0.00')
        )
    )['total']
    return total
