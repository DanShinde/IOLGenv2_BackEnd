"""
Utility functions for inventory management
"""
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.db.models import Count, F, Prefetch, Q, Sum, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from .models import Item, Assignment, Dispatch, Reservation, ProvisionedUser, RETURN_CONDITION_CHOICES


def _generate_unique_username(base):
    from django.utils.text import slugify

    base = slugify(base).replace('-', '.') or 'employee'
    username = base
    suffix = 1
    while User.objects.filter(username=username).exists():
        suffix += 1
        username = f'{base}{suffix}'
    return username


def _create_placeholder_user(employee):
    """
    A login-disabled (unusable password) User for an employee who has no account of
    their own yet, so they can still be picked by name in inventory's dropdowns.
    Name fields are populated from Employee so `get_full_name()` shows correctly
    everywhere the app already displays "who" (matching every other user reference).
    """
    parts = employee.name.split()
    user = User(
        username=_generate_unique_username(employee.name),
        first_name=parts[0] if parts else employee.name,
        last_name=' '.join(parts[1:]) if len(parts) > 1 else '',
        email=employee.email or '',
        is_active=True,
    )
    user.set_unusable_password()
    user.save()
    ProvisionedUser.objects.create(user=user)
    return user


def _sync_missing_employee_logins():
    """
    Every active employee needs a linked login to be selectable in inventory's
    assign/dispatch/reservation dropdowns, but linking one (gap_analysis's "Linked
    Login" field) is a manual, easy-to-forget step owned by another app. Rather than
    silently showing a shrinking subset of Planner/skill-gap's shared employee list,
    self-heal here: for every active employee with no linked login, try to find an
    existing matching account first, and only create a new (login-disabled) one if
    truly none exists. Cheap no-op once everyone's linked.
    """
    from employees.models import Employee
    from gap_analysis.models import SkillMatrix, find_matching_user

    unlinked = Employee.objects.filter(is_active=True).exclude(
        skill_matrix__user__isnull=False
    )
    for employee in unlinked:
        sm, _ = SkillMatrix.objects.get_or_create(employee=employee)
        if sm.user_id:
            continue
        user = find_matching_user(employee.name) or _create_placeholder_user(employee)
        sm.user = user
        sm.save(update_fields=['user'])


def _sync_user_active_status():
    """
    Keep User.is_active aligned with the Planner/skill-gap employee roster: anyone
    linked to a currently-active employee gets their login enabled; everyone else
    (never an employee, or an employee who's since left) gets it disabled. This is
    deliberately project-wide, not inventory-scoped, because auth.User itself is
    shared by every app in this project - there's no such thing as "inactive in
    inventory only".

    Hard safety rail: superuser accounts are NEVER auto-deactivated here, no matter
    what. This function runs unattended (including in production) every time the
    active-employee list is read, so it must be structurally incapable of locking
    out platform administration - that's not a decision an automated sync gets to
    make, even if the superuser isn't in the employee roster.
    """
    active_employee_user_ids = list(
        User.objects.filter(
            skillmatrix__isnull=False, skillmatrix__employee__is_active=True
        ).values_list('id', flat=True)
    )

    User.objects.filter(
        is_superuser=False, is_active=False, id__in=active_employee_user_ids
    ).update(is_active=True)

    User.objects.filter(is_superuser=False, is_active=True).exclude(
        id__in=active_employee_user_ids
    ).update(is_active=False)


def preview_employee_sync():
    """
    Read-only preview of exactly what sync_employee_users() would change, without
    changing anything - for reviewing before it runs somewhere real (production).
    """
    from employees.models import Employee

    employees_needing_login = list(
        Employee.objects.filter(is_active=True).exclude(skill_matrix__user__isnull=False)
    )

    active_employee_user_ids = set(
        User.objects.filter(
            skillmatrix__isnull=False, skillmatrix__employee__is_active=True
        ).values_list('id', flat=True)
    )

    return {
        'employees_needing_login': employees_needing_login,
        'users_to_activate': list(
            User.objects.filter(is_superuser=False, is_active=False, id__in=active_employee_user_ids)
        ),
        'users_to_deactivate': list(
            User.objects.filter(is_superuser=False, is_active=True).exclude(id__in=active_employee_user_ids)
        ),
        'protected_superusers': list(
            User.objects.filter(is_superuser=True).exclude(id__in=active_employee_user_ids)
        ),
    }


def sync_employee_users():
    """
    Full sync: link every active employee to a login (creating a placeholder if
    truly none exists), then align is_active for every user in the project with
    the current employee roster. Safe to call repeatedly (idempotent) - this is
    what the `sync_employee_users` management command runs, and what the
    assign/dispatch/reservation views call explicitly before reading
    get_active_employee_users() (see that function's docstring).
    """
    _sync_missing_employee_logins()
    _sync_user_active_status()


def get_active_employee_users():
    """
    Users who are currently active employees, for populating "who can this tool be
    given to" dropdowns (assign/transfer, dispatch responsible person, reservations)
    and the Users list page.

    "Active employee" here means employees.Employee.is_active=True - the same signal
    Planner treats as canonical for "currently employed" (as opposed to
    gap_analysis.SkillMatrix.status, which tracks a separate skill-review state like
    "on_leave" that doesn't mean someone has left).

    Deliberately read-only - does NOT call sync_employee_users() itself, so a request that
    just reads this (a form/serializer binding its dropdown queryset, a DRF list/retrieve)
    never silently writes to auth.User as a side effect. Callers that need the roster
    freshly synced before reading it (the assign/dispatch/reservation views, on GET) call
    sync_employee_users() explicitly first; otherwise the roster reflects whatever the last
    sync (management command / scheduled job) left it as.
    """
    return User.objects.filter(
        is_active=True,
        skillmatrix__isnull=False,
        skillmatrix__employee__is_active=True,
    ).distinct().order_by('username')


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


def get_reservation_summary():
    """Reservation counts by status, for the reports page"""
    counts = Reservation.objects.aggregate(
        pending=Count('id', filter=Q(status='PENDING')),
        fulfilled=Count('id', filter=Q(status='FULFILLED')),
        cancelled=Count('id', filter=Q(status='CANCELLED')),
    )
    counts['expired'] = get_expired_reservations().count()
    counts['total'] = Reservation.objects.count()
    return counts


def get_upcoming_reservations(days=30):
    """PENDING reservations whose window overlaps the next N days"""
    today = timezone.now().date()
    return Reservation.objects.filter(
        status='PENDING',
        start_date__lte=today + timedelta(days=days),
        end_date__gte=today,
    ).select_related('item', 'reserved_for').order_by('start_date')


def get_active_dispatches():
    """Tools currently out at a project (materials are consumed immediately, never 'active')"""
    return Dispatch.objects.filter(
        return_date__isnull=True, item__item_type='TOOL'
    ).select_related('item', 'responsible_person').order_by('dispatch_date')


def get_return_condition_breakdown():
    """How tools have come back across every assignment/dispatch return, by condition"""
    breakdown = {choice[0]: 0 for choice in RETURN_CONDITION_CHOICES}
    for row in Assignment.objects.exclude(return_condition='').values('return_condition').annotate(count=Count('id')):
        breakdown[row['return_condition']] += row['count']
    for row in Dispatch.objects.exclude(return_condition='').values('return_condition').annotate(count=Count('id')):
        breakdown[row['return_condition']] += row['count']
    return breakdown


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
        'maintenance_items': Item.objects.filter(status='MAINTENANCE').count(),
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


def build_reports_context_data():
    """
    Every number shown on the Reports & Analytics page, gathered in one place so the
    HTML view (cached) and the Excel export (always fresh) can never show different
    figures - both call this and nothing else for their data.
    """
    inventory_summary = list(Item.objects.values('item_type').annotate(
        total=Count('id'),
        available=Count('id', filter=Q(status='AVAILABLE')),
        assigned=Count('id', filter=Q(status='ASSIGNED')),
        dispatched=Count('id', filter=Q(status='DISPATCHED')),
        maintenance=Count('id', filter=Q(status='MAINTENANCE')),
        consumed=Count('id', filter=Q(status='CONSUMED')),
        retired=Count('id', filter=Q(status='RETIRED')),
    ))

    user_assignments_qs = User.objects.filter(
        tool_assignments__return_date__isnull=True
    ).prefetch_related(
        Prefetch('tool_assignments',
                queryset=Assignment.objects.filter(return_date__isnull=True).select_related('item').order_by('-assignment_date'))
    ).annotate(
        tool_count=Count('tool_assignments', filter=Q(tool_assignments__return_date__isnull=True))
    ).filter(tool_count__gt=0).order_by('-tool_count')

    user_assignments = []
    for user in user_assignments_qs:
        active = list(user.tool_assignments.all())
        user_assignments.append({
            'user': user,
            'tool_count': user.tool_count,
            'last_assignment': active[0] if active else None,
            'has_overdue': any(a.is_overdue for a in active),
        })

    assigned_items = list(
        Assignment.objects.filter(return_date__isnull=True)
        .select_related('item', 'assigned_to').order_by('assignment_date')
    )

    return {
        'inventory_summary': inventory_summary,
        'user_assignments': user_assignments,
        'total_value': calculate_total_inventory_value(),
        'summary_counts': get_inventory_summary(),
        'reservation_summary': get_reservation_summary(),
        'upcoming_reservations': list(get_upcoming_reservations()),
        'assigned_items': assigned_items,
        'active_dispatches': list(get_active_dispatches()),
        'low_stock_items': list(get_low_stock_items()),
        'return_condition_breakdown': get_return_condition_breakdown(),
    }
