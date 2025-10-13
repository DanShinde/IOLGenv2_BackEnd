"""
Utility functions for inventory management
"""
from django.utils import timezone
from datetime import timedelta
from .models import Item, Assignment, Dispatch, Maintenance, Alert


def generate_low_stock_alerts():
    """Generate alerts for items with low stock"""
    low_stock_items = Item.objects.filter(
        quantity__lte=models.F('min_quantity'),
        item_type='MATERIAL'
    )

    alerts_created = 0
    for item in low_stock_items:
        # Check if alert already exists and is not resolved
        existing_alert = Alert.objects.filter(
            item=item,
            alert_type='LOW_STOCK',
            is_resolved=False
        ).first()

        if not existing_alert:
            priority = 'CRITICAL' if item.is_critical else 'HIGH'
            Alert.objects.create(
                alert_type='LOW_STOCK',
                priority=priority,
                item=item,
                message=f"Low stock alert: {item.name} has {item.quantity} {item.unit} remaining (minimum: {item.min_quantity})"
            )
            alerts_created += 1

    return alerts_created


def generate_overstock_alerts():
    """Generate alerts for items with excessive stock"""
    from django.db.models import F
    overstock_items = Item.objects.filter(
        quantity__gt=F('max_quantity'),
        item_type='MATERIAL'
    )

    alerts_created = 0
    for item in overstock_items:
        # Check if alert already exists and is not resolved
        existing_alert = Alert.objects.filter(
            item=item,
            alert_type='OVERSTOCK',
            is_resolved=False
        ).first()

        if not existing_alert:
            Alert.objects.create(
                alert_type='OVERSTOCK',
                priority='LOW',
                item=item,
                message=f"Overstock alert: {item.name} has {item.quantity} {item.unit} (maximum: {item.max_quantity})"
            )
            alerts_created += 1

    return alerts_created


def generate_overdue_assignment_alerts():
    """Generate alerts for overdue assignments"""
    overdue_assignments = Assignment.objects.filter(
        return_date__isnull=True,
        expected_return_date__lt=timezone.now().date()
    )

    alerts_created = 0
    for assignment in overdue_assignments:
        # Check if alert already exists and is not resolved
        existing_alert = Alert.objects.filter(
            item=assignment.item,
            alert_type='OVERDUE_ASSIGNMENT',
            is_resolved=False
        ).first()

        if not existing_alert:
            days_overdue = (timezone.now().date() - assignment.expected_return_date).days
            priority = 'CRITICAL' if days_overdue > 7 else 'HIGH'

            Alert.objects.create(
                alert_type='OVERDUE_ASSIGNMENT',
                priority=priority,
                item=assignment.item,
                message=f"Overdue assignment: {assignment.item.name} assigned to {assignment.assigned_to.get_full_name() or assignment.assigned_to.username} is {days_overdue} days overdue"
            )
            alerts_created += 1

    return alerts_created


def generate_overdue_dispatch_alerts():
    """Generate alerts for overdue dispatches"""
    overdue_dispatches = Dispatch.objects.filter(
        return_date__isnull=True,
        expected_return_date__lt=timezone.now().date()
    )

    alerts_created = 0
    for dispatch in overdue_dispatches:
        # Check if alert already exists and is not resolved
        existing_alert = Alert.objects.filter(
            item=dispatch.item,
            alert_type='OVERDUE_DISPATCH',
            is_resolved=False
        ).first()

        if not existing_alert:
            days_overdue = (timezone.now().date() - dispatch.expected_return_date).days
            priority = 'CRITICAL' if days_overdue > 14 else 'HIGH'

            Alert.objects.create(
                alert_type='OVERDUE_DISPATCH',
                priority=priority,
                item=dispatch.item,
                message=f"Overdue dispatch: {dispatch.item.name} dispatched to {dispatch.project} is {days_overdue} days overdue"
            )
            alerts_created += 1

    return alerts_created


def generate_maintenance_due_alerts():
    """Generate alerts for upcoming and overdue maintenance"""
    # Get maintenance due in next 7 days or overdue
    upcoming_date = timezone.now().date() + timedelta(days=7)
    maintenance_items = Maintenance.objects.filter(
        status='SCHEDULED',
        scheduled_date__lte=upcoming_date
    )

    alerts_created = 0
    for maintenance in maintenance_items:
        # Check if alert already exists and is not resolved
        existing_alert = Alert.objects.filter(
            item=maintenance.item,
            alert_type='MAINTENANCE_DUE',
            is_resolved=False
        ).first()

        if not existing_alert:
            days_until = (maintenance.scheduled_date - timezone.now().date()).days

            if days_until < 0:
                priority = 'CRITICAL'
                message = f"Overdue maintenance: {maintenance.item.name} - {maintenance.get_maintenance_type_display()} was due {abs(days_until)} days ago"
            elif days_until <= 3:
                priority = 'HIGH'
                message = f"Urgent maintenance: {maintenance.item.name} - {maintenance.get_maintenance_type_display()} due in {days_until} days"
            else:
                priority = 'MEDIUM'
                message = f"Upcoming maintenance: {maintenance.item.name} - {maintenance.get_maintenance_type_display()} due in {days_until} days"

            Alert.objects.create(
                alert_type='MAINTENANCE_DUE',
                priority=priority,
                item=maintenance.item,
                message=message
            )
            alerts_created += 1

    return alerts_created


def generate_expiry_alerts():
    """Generate alerts for materials approaching expiry"""
    # Get items expiring in next 30 days or already expired
    upcoming_date = timezone.now().date() + timedelta(days=30)
    expiring_items = Item.objects.filter(
        item_type='MATERIAL',
        expiry_date__lte=upcoming_date,
        expiry_date__isnull=False
    )

    alerts_created = 0
    for item in expiring_items:
        # Check if alert already exists and is not resolved
        existing_alert = Alert.objects.filter(
            item=item,
            alert_type='EXPIRY_WARNING',
            is_resolved=False
        ).first()

        if not existing_alert:
            days_until = (item.expiry_date - timezone.now().date()).days

            if days_until < 0:
                priority = 'CRITICAL'
                message = f"Expired: {item.name} expired {abs(days_until)} days ago"
            elif days_until <= 7:
                priority = 'CRITICAL'
                message = f"Critical expiry warning: {item.name} expires in {days_until} days"
            elif days_until <= 14:
                priority = 'HIGH'
                message = f"Expiry warning: {item.name} expires in {days_until} days"
            else:
                priority = 'MEDIUM'
                message = f"Expiry notice: {item.name} expires in {days_until} days"

            Alert.objects.create(
                alert_type='EXPIRY_WARNING',
                priority=priority,
                item=item,
                message=message
            )
            alerts_created += 1

    return alerts_created


def generate_warranty_expiring_alerts():
    """Generate alerts for items with expiring warranties"""
    # Get items with warranty expiring in next 60 days
    upcoming_date = timezone.now().date() + timedelta(days=60)
    expiring_warranties = Item.objects.filter(
        warranty_expiry__lte=upcoming_date,
        warranty_expiry__gt=timezone.now().date(),
        warranty_expiry__isnull=False
    )

    alerts_created = 0
    for item in expiring_warranties:
        # Check if alert already exists and is not resolved
        existing_alert = Alert.objects.filter(
            item=item,
            alert_type='WARRANTY_EXPIRING',
            is_resolved=False
        ).first()

        if not existing_alert:
            days_until = (item.warranty_expiry - timezone.now().date()).days

            if days_until <= 30:
                priority = 'HIGH'
            else:
                priority = 'MEDIUM'

            Alert.objects.create(
                alert_type='WARRANTY_EXPIRING',
                priority=priority,
                item=item,
                message=f"Warranty expiring: {item.name} warranty expires in {days_until} days"
            )
            alerts_created += 1

    return alerts_created


def generate_all_alerts():
    """Generate all types of alerts"""
    results = {
        'low_stock': generate_low_stock_alerts(),
        'overstock': generate_overstock_alerts(),
        'overdue_assignments': generate_overdue_assignment_alerts(),
        'overdue_dispatches': generate_overdue_dispatch_alerts(),
        'maintenance_due': generate_maintenance_due_alerts(),
        'expiry_warnings': generate_expiry_alerts(),
        'warranty_expiring': generate_warranty_expiring_alerts(),
    }

    total = sum(results.values())
    return results, total


def cleanup_resolved_alerts(days_old=30):
    """Clean up old resolved alerts"""
    cutoff_date = timezone.now() - timedelta(days=days_old)
    deleted_count = Alert.objects.filter(
        is_resolved=True,
        resolved_at__lt=cutoff_date
    ).delete()[0]

    return deleted_count


def get_inventory_summary():
    """Get comprehensive inventory summary"""
    from django.db.models import Count, Sum, Q, F

    summary = {
        'total_items': Item.objects.count(),
        'total_tools': Item.objects.filter(item_type='TOOL').count(),
        'total_materials': Item.objects.filter(item_type='MATERIAL').count(),
        'available_items': Item.objects.filter(status='AVAILABLE').count(),
        'assigned_items': Item.objects.filter(status='ASSIGNED').count(),
        'dispatched_items': Item.objects.filter(status='DISPATCHED').count(),
        'maintenance_items': Item.objects.filter(status='MAINTENANCE').count(),
        'low_stock_items': Item.objects.filter(
            quantity__lte=F('min_quantity')
        ).count(),
        'critical_items': Item.objects.filter(is_critical=True).count(),
        'active_assignments': Assignment.objects.filter(return_date__isnull=True).count(),
        'overdue_assignments': Assignment.objects.filter(
            return_date__isnull=True,
            expected_return_date__lt=timezone.now().date()
        ).count(),
        'active_dispatches': Dispatch.objects.filter(return_date__isnull=True).count(),
        'overdue_dispatches': Dispatch.objects.filter(
            return_date__isnull=True,
            expected_return_date__lt=timezone.now().date()
        ).count(),
        'pending_maintenance': Maintenance.objects.filter(
            status__in=['SCHEDULED', 'IN_PROGRESS']
        ).count(),
        'overdue_maintenance': Maintenance.objects.filter(
            status='SCHEDULED',
            scheduled_date__lt=timezone.now().date()
        ).count(),
        'unresolved_alerts': Alert.objects.filter(is_resolved=False).count(),
        'critical_alerts': Alert.objects.filter(
            is_resolved=False,
            priority='CRITICAL'
        ).count(),
    }

    return summary


def calculate_total_inventory_value():
    """Calculate total current value of all items"""
    from decimal import Decimal

    items = Item.objects.filter(
        purchase_cost__isnull=False,
        purchase_date__isnull=False
    )

    total_value = Decimal('0.00')
    for item in items:
        total_value += item.current_value

    return total_value
