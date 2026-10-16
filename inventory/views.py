
################################################################################
# FILE 2: views.py (COMPLETE FILE - REPLACE EXISTING)
################################################################################

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Q, Sum, Count, Prefetch
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from datetime import date
import csv
import json
from .models import Item, Assignment, Dispatch, History, Reservation
from .forms import (
    ItemForm, HistoryFilterForm, ItemFilterForm, ReturnForm, ReservationForm,
    AssignForm, DispatchForm,
)
from .utils import (
    send_overdue_digest, get_active_employee_users, sync_employee_users, get_inventory_summary,
    calculate_total_inventory_value, get_reservation_summary, get_upcoming_reservations,
    get_active_dispatches, get_low_stock_items, get_return_condition_breakdown,
    build_reports_context_data,
)
from . import services
from .people import person_name
from .services import InventoryError


def _capture_next(request, fallback):
    """
    Figure out where a form should return to after it's saved or cancelled.

    - On GET (opening the form): an explicit ?next= wins, otherwise the page that
      linked here (HTTP_REFERER), otherwise `fallback`.
    - On POST (submitting the form): the hidden `next` field carries forward
      whatever was resolved when the form was opened, so it survives validation
      errors and re-renders.

    Always validated as a safe same-host redirect target to prevent open redirects.
    """
    if request.method == 'POST':
        candidate = request.POST.get('next')
    else:
        candidate = request.GET.get('next') or request.META.get('HTTP_REFERER')

    if candidate and url_has_allowed_host_and_scheme(candidate, allowed_hosts={request.get_host()}):
        return candidate
    return fallback


# ============================================================================
# PAGINATION & CACHING UTILITIES (Inspired by ACGen ViewSet)
# ============================================================================

class InventoryPaginator:
    """Custom paginator for inventory views with caching support"""
    page_size = 20
    max_page_size = 100

    @staticmethod
    def paginate_queryset(queryset, request, page_size=None):
        """Paginate queryset with custom page size from request"""
        page_size = page_size or request.GET.get('page_size', InventoryPaginator.page_size)
        try:
            page_size = min(int(page_size), InventoryPaginator.max_page_size)
        except (TypeError, ValueError):
            page_size = InventoryPaginator.page_size

        page = request.GET.get('page', 1)
        paginator = Paginator(queryset, page_size)

        try:
            paginated_data = paginator.page(page)
        except PageNotAnInteger:
            paginated_data = paginator.page(1)
        except EmptyPage:
            paginated_data = paginator.page(paginator.num_pages)

        return paginated_data, paginator


@login_required
def dashboard(request):
    """
    Optimized dashboard with caching and query optimization
    """
    # Same definitions as the list pages: single-unit items (tools, IT assets, licences,
    # other) vs stock-tracked materials, and people = the active employee roster.
    stats = {
        'tools_count': Item.objects.exclude(item_type__in=Item.STOCK_TRACKED_TYPES).count(),
        'materials_count': Item.objects.filter(item_type__in=Item.STOCK_TRACKED_TYPES).count(),
        'users_count': get_active_employee_users().count(),
    }

    # Recent assignments - optimized with select_related
    recent_assignments = Assignment.objects.filter(
        return_date__isnull=True
    ).select_related('item', 'assigned_to__skillmatrix__employee', 'assigned_by').order_by('-assignment_date')[:5]

    # Latest dispatches (tools still out and material consignments alike), newest first
    recent_dispatches = Dispatch.objects.select_related(
        'item', 'dispatched_by', 'responsible_person'
    ).order_by('-dispatch_date', '-created_at')[:5]

    # Recent history - optimized with select_related
    recent_history = History.objects.select_related(
        'item', 'user'
    ).order_by('-timestamp')[:10]

    context = {
        **stats,
        'recent_assignments': recent_assignments,
        'recent_dispatches': recent_dispatches,
        'recent_history': recent_history,
    }
    return render(request, 'inventory/dashboard.html', context)


@login_required
def item_list(request):
    """
    Optimized item list with pagination, caching, and export functionality
    """
    # Handle export requests
    if request.GET.get('export') == 'csv':
        return export_items_csv(request)

    # Get filter parameters
    form = ItemFilterForm(request.GET or None)
    filter_params = {
        'search': request.GET.get('search', ''),
        'item_type': request.GET.get('item_type', ''),
        'status': request.GET.get('status', ''),
    }

    items = _filtered_items(form)

    # Pagination
    paginated_items, paginator = InventoryPaginator.paginate_queryset(items, request)

    query = request.GET.copy()
    query.pop('page', None)
    context = {
        'items': paginated_items,
        'paginator': paginator,
        'form': form,
        'is_paginated': paginator.num_pages > 1,
        'filter_query': query.urlencode(),  # current filters, safely encoded, for page/export links
    }
    return render(request, 'inventory/item_list.html', context)


def _filtered_items(form):
    """Items matching the item-list filters (shared by the list and its CSV export)."""
    items = Item.objects.all().order_by('-created_at')
    if form.is_valid():
        if form.cleaned_data['search']:
            items = items.filter(
                Q(name__icontains=form.cleaned_data['search']) |
                Q(serial_number__icontains=form.cleaned_data['search']) |
                Q(make__icontains=form.cleaned_data['search']) |
                Q(model__icontains=form.cleaned_data['search'])
            )
        if form.cleaned_data['item_type']:
            items = items.filter(item_type=form.cleaned_data['item_type'])
        status = form.cleaned_data.get('status')
        if status == 'AVAILABLE':
            # a material with no stock left isn't available
            items = items.filter(status='AVAILABLE').exclude(item_type__in=Item.STOCK_TRACKED_TYPES, quantity=0)
        elif status:
            items = items.filter(status=status)
    return items


@login_required
def item_detail(request, pk):
    """
    Optimized item detail with prefetch_related for related objects
    """
    item = get_object_or_404(Item, pk=pk)

    # Optimized queries with select_related
    history = History.objects.filter(item=item).select_related('user').order_by('-timestamp')[:10]
    all_assignments = Assignment.objects.filter(item=item).select_related(
        'assigned_to__skillmatrix__employee', 'assigned_by'
    ).order_by('-assignment_date')
    all_dispatches = Dispatch.objects.filter(item=item).select_related(
        'dispatched_by', 'responsible_person__skillmatrix__employee'
    ).order_by('-dispatch_date')
    open_assignments = list(all_assignments.filter(return_date__isnull=True))
    open_dispatches = list(item.open_dispatches().select_related('responsible_person__skillmatrix__employee'))

    context = {
        'item': item,
        'history': history,
        'assignments': all_assignments[:5],
        'dispatches': all_dispatches[:5],
        # Who holds it right now, straight from the open records (not the status label),
        # each with its own Return button
        'open_assignments': open_assignments,
        'open_dispatches': open_dispatches,
        'active_assignment': open_assignments[0] if open_assignments else None,
        'active_dispatch': open_dispatches[0] if open_dispatches else None,
    }
    return render(request, 'inventory/item_detail.html', context)


STATUS_EXTRA_FIELD_NAMES = [
    'assigned_to', 'assignment_date', 'assignment_return_date', 'assignment_notes',
    'dispatch_project', 'dispatch_site_location', 'dispatch_responsible_person',
    'dispatch_date', 'dispatch_return_date', 'dispatch_notes', 'maintenance_notes',
]


def _apply_initial_status(item, form, request):
    """
    A brand-new item can be entered directly as already Assigned/Dispatched/Consumed/
    Under Maintenance rather than Available. This creates the same Assignment/Dispatch/
    History records that the dedicated Assign/Dispatch pages would create for an
    existing item, using the extra fields ItemForm adds for new items.
    Returns the extra history detail line to fold into the 'ADDED' record.
    """
    status = item.status
    quantity = item.quantity if item.is_stock_tracked else 1

    if status == 'ASSIGNED':
        assigned_to = form.cleaned_data['assigned_to']
        who = person_name(assigned_to)

        Assignment.objects.create(
            item=item, quantity=quantity, assigned_to=assigned_to, assigned_by=request.user,
            assignment_date=form.cleaned_data['assignment_date'],
            expected_return_date=form.cleaned_data.get('assignment_return_date'),
            notes=form.cleaned_data.get('assignment_notes', '')
        )

        if item.is_stock_tracked:
            item.quantity -= quantity
            item.status = 'AVAILABLE'
        else:
            item.location = f'With {who}'
        item.save()
        return f'Assigned to {who} at creation' + (f' ({quantity} units)' if item.is_stock_tracked else '')

    if status in ('DISPATCHED', 'CONSUMED'):
        project = form.cleaned_data['dispatch_project']
        site_location = form.cleaned_data.get('dispatch_site_location', '')
        responsible_person = form.cleaned_data['dispatch_responsible_person']
        responsible_name = person_name(responsible_person)

        Dispatch.objects.create(
            item=item, quantity=quantity, project=project, site_location=site_location,
            responsible_person=responsible_person, dispatched_by=request.user,
            dispatch_date=form.cleaned_data['dispatch_date'],
            expected_return_date=None if item.is_stock_tracked else form.cleaned_data.get('dispatch_return_date'),
            notes=form.cleaned_data.get('dispatch_notes', '')
        )

        if item.is_stock_tracked:
            item.quantity -= quantity
            item.status = 'CONSUMED'
            item.location = f'Consumed at {project}'
        else:
            item.status = 'DISPATCHED'
            item.location = f'{project} - {site_location or "N/A"}'
        item.save()
        return f'Dispatched to {project} at creation (responsible: {responsible_name})'

    if status == 'MAINTENANCE':
        return f"Under maintenance at creation - {form.cleaned_data['maintenance_notes']}"

    return None


@login_required
@permission_required('inventory.add_item', raise_exception=True)
def item_create(request):
    fallback = reverse('inventory-item-list')
    next_url = _capture_next(request, fallback)

    if request.method == 'POST':
        form = ItemForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                item = form.save(commit=False)
                item.created_by = request.user
                item.save()
                quantity_added = item.quantity  # before an initial assignment/dispatch draws it down

                extra_detail = _apply_initial_status(item, form, request)

                details = f'{item.get_item_type_display()} added to inventory with quantity {quantity_added}'
                if extra_detail:
                    details += f'. {extra_detail}'

                History.objects.create(
                    item=item,
                    action='ADDED',
                    user=request.user,
                    details=details,
                    location=item.location or 'Warehouse'
                )


            messages.success(request,
                f'Successfully added {item.name} ({item.serial_number}) to inventory!',
                extra_tags='bg-green-100 text-green-800'
            )
            return redirect(next_url)
        else:
            messages.error(request,
                'Please correct the errors below',
                extra_tags='bg-red-100 text-red-800'
            )
    else:
        form = ItemForm()

    context = {
        'form': form,
        'title': 'Add New Inventory Item',
        'next': next_url,
        'existing_item_names': Item.objects.order_by('name').values_list('name', flat=True).distinct(),
        'status_extra_field_names': STATUS_EXTRA_FIELD_NAMES,
    }
    return render(request, 'inventory/item_form.html', context)


@login_required
@permission_required('inventory.change_item', raise_exception=True)
def item_update(request, pk):
    item = get_object_or_404(Item, pk=pk)
    fallback = reverse('inventory-item-detail', kwargs={'pk': item.pk})
    next_url = _capture_next(request, fallback)

    if request.method == 'POST':
        old_status = item.status
        form = ItemForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            with transaction.atomic():
                # Re-check under a lock: the item may have been assigned since the form opened
                if Item.objects.select_for_update().get(pk=item.pk).is_out and form.cleaned_data.get('status') != old_status:
                    messages.error(request, f'{item.name} was assigned or dispatched meanwhile - its status was not changed.')
                    return redirect(next_url)
                updated_item = form.save()
                retired = updated_item.status == 'RETIRED' and old_status != 'RETIRED'
                History.objects.create(
                    item=updated_item,
                    action='RETIRED' if retired else 'UPDATED',
                    user=request.user,
                    details='Retired from service (item edit)' if retired else 'Item details updated',
                    location=updated_item.location or 'Warehouse'
                )
            messages.success(request,
                f'Successfully updated {updated_item.name}',
                extra_tags='bg-green-100 text-green-800'
            )
            return redirect(next_url)
        else:
            messages.error(request,
                'Please correct the errors below',
                extra_tags='bg-red-100 text-red-800'
            )
    else:
        form = ItemForm(instance=item)

    context = {
        'form': form,
        'title': f'Edit {item.name}',
        'item': item,
        'next': next_url,
        'existing_item_names': Item.objects.exclude(pk=item.pk).order_by('name').values_list('name', flat=True).distinct(),
        'status_extra_field_names': STATUS_EXTRA_FIELD_NAMES,
    }
    return render(request, 'inventory/item_form.html', context)






# ============================================================================
# EXPORT FUNCTIONS
# ============================================================================

@login_required
def export_items_csv(request):
    """Export items to CSV file"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="inventory_items.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Name', 'Type', 'Serial Number', 'Make', 'Model', 'Status',
        'Quantity', 'Location', 'Category', 'Purchase Date', 'Purchase Cost'
    ])

    # Same filters as item_list
    items = _filtered_items(ItemFilterForm(request.GET or None))

    for item in items:
        writer.writerow([
            item.name,
            item.get_item_type_display(),
            item.serial_number,
            item.make,
            item.model,
            item.get_status_display(),
            item.quantity,
            item.location,
            item.category,
            item.purchase_date,
            item.purchase_cost,
        ])

    return response


@login_required
def export_history_csv(request):
    """Export history to CSV file"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="inventory_history.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Timestamp', 'Item', 'Serial Number', 'Action', 'User', 'Details', 'Location'
    ])

    history = History.objects.select_related('item', 'user__skillmatrix__employee').order_by('-timestamp')
    form = HistoryFilterForm(request.GET or None)

    if form.is_valid():
        if form.cleaned_data['action']:
            history = history.filter(action=form.cleaned_data['action'])
        if form.cleaned_data['item_type']:
            history = history.filter(item__item_type=form.cleaned_data['item_type'])
        if form.cleaned_data['item']:
            history = history.filter(item=form.cleaned_data['item'])
        if form.cleaned_data['date_from']:
            history = history.filter(timestamp__date__gte=form.cleaned_data['date_from'])
        if form.cleaned_data['date_to']:
            history = history.filter(timestamp__date__lte=form.cleaned_data['date_to'])

    for record in history:
        writer.writerow([
            record.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            record.item.name,
            record.item.serial_number,
            record.get_action_display(),
            person_name(record.user) if record.user else 'N/A',
            record.details,
            record.location,
        ])

    return response


# ============================================================================
# AJAX ENDPOINTS
# ============================================================================

@login_required
@require_http_methods(["POST"])
def bulk_update_items(request):
    """Bulk update items status (staff only - retiring is the only supported bulk action;
    hard delete is intentionally not exposed here since it cascades and destroys the
    item's Assignment/Dispatch/History audit trail)"""
    if not (request.user.is_staff and request.user.has_perm('inventory.change_item')):
        return JsonResponse({'success': False, 'message': 'You do not have permission to perform this action'}, status=403)

    try:
        data = json.loads(request.body)
        item_ids = data.get('item_ids', [])
        action = data.get('action')

        if not item_ids or not action:
            return JsonResponse({'success': False, 'message': 'Missing required parameters'})

        items = Item.objects.filter(pk__in=item_ids)

        if action == 'retire':
            # One by one through the service: an item still out with someone (or at a site)
            # is refused instead of being retired with its assignment left open.
            retired, refused = 0, []
            for item in items:
                try:
                    services.retire_item(item, request.user, 'bulk retire')
                    retired += 1
                except InventoryError:
                    refused.append(item.name)
            message = f'Retired {retired} item{"s" if retired != 1 else ""}.'
            if refused:
                message += f' Not retired (still out - record the return first): {", ".join(refused)}.'
            return JsonResponse({'success': retired > 0 or not refused, 'message': message})

        return JsonResponse({'success': False, 'message': 'Invalid action'})

    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def ajax_search_items(request):
    """AJAX endpoint for real-time item search"""
    query = request.GET.get('q', '')
    item_type = request.GET.get('type', '')

    items = Item.objects.all()

    if query:
        items = items.filter(
            Q(name__icontains=query) |
            Q(serial_number__icontains=query) |
            Q(make__icontains=query) |
            Q(model__icontains=query)
        )

    if item_type:
        items = items.filter(item_type=item_type)

    items = items[:10]  # Limit to 10 results

    results = [{
        'id': item.id,
        'name': item.name,
        'serial_number': item.serial_number,
        'type': item.get_item_type_display(),
        'status': item.get_status_display(),
    } for item in items]

    return JsonResponse({'results': results})


@login_required
@permission_required('inventory.change_assignment', raise_exception=True)
def return_assignment(request, pk):
    assignment = get_object_or_404(Assignment, pk=pk, return_date__isnull=True)
    next_url = _capture_next(request, reverse('inventory-transfer-item'))

    if request.method == 'POST':
        form = ReturnForm(request.POST)
        if form.is_valid():
            returned_by = person_name(assignment.assigned_to)
            try:
                services.process_return(
                    assignment,
                    condition=form.cleaned_data['condition'],
                    return_notes=form.cleaned_data['return_notes'],
                    performed_by=request.user,
                    details_prefix=f'Returned by {returned_by}'
                )
            except InventoryError as exc:
                messages.error(request, str(exc))
                return redirect(next_url)

            messages.success(request, f'Return recorded for {assignment.item.name}.')
            return redirect(next_url)
    else:
        form = ReturnForm()

    return render(request, 'inventory/return_confirm.html', {
        'assignment': assignment,
        'return_type': 'assignment',
        'form': form,
        'next': next_url,
    })


@login_required
@permission_required('inventory.change_dispatch', raise_exception=True)
def return_dispatch(request, pk):
    # any single-unit item (tool, IT asset, licence, other) - material dispatches are consumed
    dispatch = get_object_or_404(
        Dispatch.objects.exclude(item__item_type__in=Item.STOCK_TRACKED_TYPES), pk=pk, return_date__isnull=True)
    next_url = _capture_next(request, reverse('inventory-transfer-item'))

    if request.method == 'POST':
        form = ReturnForm(request.POST)
        if form.is_valid():
            try:
                services.process_return(
                    dispatch,
                    condition=form.cleaned_data['condition'],
                    return_notes=form.cleaned_data['return_notes'],
                    performed_by=request.user,
                    details_prefix=f'Returned from {dispatch.project}'
                )
            except InventoryError as exc:
                messages.error(request, str(exc))
                return redirect(next_url)

            messages.success(request, f'Return recorded for {dispatch.item.name}.')
            return redirect(next_url)
    else:
        form = ReturnForm()

    return render(request, 'inventory/return_confirm.html', {
        'dispatch': dispatch,
        'return_type': 'dispatch',
        'form': form,
        'next': next_url,
    })


@login_required
def history_list(request):
    """
    Optimized history list with pagination and export functionality
    """
    # Handle export requests
    if request.GET.get('export') == 'csv':
        return export_history_csv(request)

    # Optimized query with select_related
    history = History.objects.select_related('item', 'user__skillmatrix__employee').order_by('-timestamp')
    form = HistoryFilterForm(request.GET or None)

    if form.is_valid():
        if form.cleaned_data['action']:
            history = history.filter(action=form.cleaned_data['action'])
        if form.cleaned_data['item_type']:
            history = history.filter(item__item_type=form.cleaned_data['item_type'])
        if form.cleaned_data['item']:
            history = history.filter(item=form.cleaned_data['item'])
        if form.cleaned_data['date_from']:
            history = history.filter(timestamp__date__gte=form.cleaned_data['date_from'])
        if form.cleaned_data['date_to']:
            history = history.filter(timestamp__date__lte=form.cleaned_data['date_to'])
        if form.cleaned_data['serial_number']:
            history = history.filter(item__serial_number__icontains=form.cleaned_data['serial_number'])
        if form.cleaned_data['user_search']:
            for word in form.cleaned_data['user_search'].split():
                history = history.filter(
                    Q(user__username__icontains=word) |
                    Q(user__first_name__icontains=word) |
                    Q(user__last_name__icontains=word) |
                    Q(user__skillmatrix__employee__name__icontains=word)
                )
        if form.cleaned_data['search']:
            history = history.filter(details__icontains=form.cleaned_data['search'])

    # Pagination
    paginated_history, paginator = InventoryPaginator.paginate_queryset(history, request, page_size=25)

    query = request.GET.copy()
    query.pop('page', None)
    context = {
        'history': paginated_history,
        'page_obj': paginated_history,   # the template's pager
        'paginator': paginator,
        'form': form,
        'is_paginated': paginator.num_pages > 1,
        'filter_query': query.urlencode(),  # keep filters on page links
    }
    return render(request, 'inventory/history_list.html', context)


@login_required
def reports(request):
    """
    Optimized reports with caching and better query aggregation
    """
    # Always built fresh: a cached copy kept showing returned items as still assigned
    cached_data = build_reports_context_data()

    context = {
        **cached_data,
        'user_assignments': [item['user'] for item in cached_data['user_assignments']],
    }

    # Add last_assignment/has_overdue back onto the user objects for the template
    for i, user in enumerate(context['user_assignments']):
        user.last_assignment = cached_data['user_assignments'][i]['last_assignment']
        user.has_overdue = cached_data['user_assignments'][i]['has_overdue']

    return render(request, 'inventory/reports.html', context)


@login_required
def export_reports_excel(request):
    """
    Everything on the Reports & Analytics page as one workbook - summary, full item
    detail, distributions with native charts, reservations, assigned items, active
    dispatches, low stock, and user assignments. Always built fresh (not from the
    5-minute reports cache) so an export always reflects the current data.
    """
    from .excel_export import build_reports_workbook

    data = build_reports_context_data()
    items = Item.objects.all().order_by('item_type', 'name').prefetch_related(
        Prefetch('assignments', queryset=Assignment.objects.filter(return_date__isnull=True)
                 .select_related('assigned_to__skillmatrix__employee'), to_attr='open_list'),
        Prefetch('dispatches', queryset=Dispatch.objects.filter(return_date__isnull=True)
                 .exclude(item__item_type__in=Item.STOCK_TRACKED_TYPES)
                 .select_related('responsible_person__skillmatrix__employee'), to_attr='open_dispatch_list'),
    )
    workbook = build_reports_workbook(data, items)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    filename = f'inventory_report_{timezone.localdate().isoformat()}.xlsx'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    workbook.save(response)
    return response


# TRANSFER SYSTEM: assign / dispatch / hub

@login_required
def transfer_item(request):
    """Hub page: quick links to Assign/Dispatch/Reserve, plus current item status lists"""
    # Available = can be handed out now (a material needs stock left)
    available_items = Item.objects.filter(status='AVAILABLE').exclude(
        item_type__in=Item.STOCK_TRACKED_TYPES, quantity=0).order_by('name')

    active_assignments = Assignment.objects.filter(
        return_date__isnull=True
    ).select_related('item', 'assigned_to__skillmatrix__employee').order_by('item__name')

    active_dispatches = get_active_dispatches().select_related(
        'responsible_person__skillmatrix__employee').order_by('item__name')

    context = {
        'available_items': available_items,
        'active_assignments': active_assignments,
        'active_dispatches': active_dispatches,
    }
    return render(request, 'inventory/transfer_hub.html', context)


@login_required
@permission_required('inventory.add_assignment', raise_exception=True)
def assign_item(request):
    next_url = _capture_next(request, reverse('inventory-transfer-item'))
    sync_employee_users()

    if request.method == 'POST':
        form = AssignForm(request.POST)
        if form.is_valid():
            item = form.cleaned_data['item']
            quantity = form.cleaned_data['quantity']
            assigned_to = form.cleaned_data['assigned_to']
            assignment_date = form.cleaned_data['assignment_date']
            expected_return_date = form.cleaned_data['expected_return_date']
            notes = form.cleaned_data['notes']
            try:
                _assignment, message = services.assign_item(
                    item, assigned_to, request.user, assignment_date,
                    expected_return_date=expected_return_date, notes=notes, quantity=quantity)
            except InventoryError as exc:
                form.add_error(None, str(exc))
                return render(request, 'inventory/assign_form.html', {'form': form, 'next': next_url})
            messages.success(request, message)
            return redirect(next_url)
    else:
        initial = {}
        item_id = request.GET.get('item')
        if item_id:
            initial['item'] = item_id
        user_id = request.GET.get('user')
        if user_id:
            initial['assigned_to'] = user_id
        form = AssignForm(initial=initial)

    return render(request, 'inventory/assign_form.html', {'form': form, 'next': next_url})


@login_required
@permission_required('inventory.add_dispatch', raise_exception=True)
def dispatch_item(request):
    next_url = _capture_next(request, reverse('inventory-transfer-item'))
    sync_employee_users()

    if request.method == 'POST':
        form = DispatchForm(request.POST)
        if form.is_valid():
            item = form.cleaned_data['item']
            project = form.cleaned_data['project']
            site_location = form.cleaned_data.get('site_location', '')
            responsible_person = form.cleaned_data['responsible_person']
            quantity = form.cleaned_data.get('quantity') or 1
            dispatch_date = form.cleaned_data['dispatch_date']
            expected_return_date = form.cleaned_data.get('expected_return_date')
            notes = form.cleaned_data['notes']
            try:
                message = services.dispatch_item(
                    item, project, site_location, responsible_person, request.user, dispatch_date,
                    expected_return_date=None if item.is_stock_tracked else expected_return_date,
                    notes=notes, quantity=quantity)
            except InventoryError as exc:
                form.add_error(None, str(exc))
                return render(request, 'inventory/dispatch_form.html', {'form': form, 'next': next_url})
            messages.success(request, message)
            return redirect(next_url)
    else:
        initial = {}
        item_id = request.GET.get('item')
        if item_id:
            initial['item'] = item_id
        form = DispatchForm(initial=initial)

    return render(request, 'inventory/dispatch_form.html', {'form': form, 'next': next_url})


# USERS

@login_required
def user_list(request):
    """
    Every active employee per Planner/skill-gap - this mirrors that shared roster
    exactly, same as the assign/dispatch/reservation dropdowns (including employees
    currently holding nothing).
    """
    sync_employee_users()
    users = get_active_employee_users().annotate(
        active_tool_count=Count(
            'tool_assignments', filter=Q(tool_assignments__return_date__isnull=True), distinct=True
        ),
        active_dispatch_count=Count(
            'responsible_dispatches',
            filter=Q(responsible_dispatches__return_date__isnull=True) & ~Q(
                responsible_dispatches__item__item_type__in=Item.STOCK_TRACKED_TYPES),
            distinct=True
        ),
    )

    context = {'users': users}
    return render(request, 'inventory/user_list.html', context)


@login_required
def user_detail(request, pk):
    sync_employee_users()
    target_user = get_object_or_404(User, pk=pk)

    active_assignments = Assignment.objects.filter(
        assigned_to=target_user, return_date__isnull=True
    ).select_related('item').order_by('item__name')

    past_assignments = Assignment.objects.filter(
        assigned_to=target_user, return_date__isnull=False
    ).select_related('item').order_by('-return_date')

    is_active_employee = get_active_employee_users().filter(pk=target_user.pk).exists()

    if request.method == 'POST':
        return assign_item(request)

    form = AssignForm(initial={'assigned_to': target_user.pk})

    context = {
        'target_user': target_user,
        'is_active_employee': is_active_employee,
        'active_assignments': active_assignments,
        'past_assignments': past_assignments,
        'form': form,
    }
    return render(request, 'inventory/user_detail.html', context)


# RESERVATIONS

@login_required
def reservation_list(request):
    reservations = Reservation.objects.select_related(
        'item', 'reserved_for', 'reserved_by'
    ).order_by('start_date')

    status_filter = request.GET.get('status', 'PENDING')
    if status_filter:
        reservations = reservations.filter(status=status_filter)

    context = {
        'reservations': reservations,
        'status_filter': status_filter,
        'reservation_status_choices': Reservation.STATUS_CHOICES,
    }
    return render(request, 'inventory/reservation_list.html', context)


@login_required
@permission_required('inventory.add_reservation', raise_exception=True)
def reservation_create(request):
    next_url = _capture_next(request, reverse('inventory-reservation-list'))
    sync_employee_users()

    if request.method == 'POST':
        form = ReservationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                reservation = form.save(commit=False)
                reservation.reserved_by = request.user
                reservation.save()

                who = person_name(reservation.reserved_for)
                History.objects.create(
                    item=reservation.item,
                    action='RESERVED',
                    user=request.user,
                    details=f'Reserved for {who} from {reservation.start_date} to {reservation.end_date}',
                    location=reservation.item.location or 'Warehouse'
                )

            messages.success(request, f'Reserved {reservation.item.name} for {who} starting {reservation.start_date}.')
            return redirect(next_url)
    else:
        initial = {}
        item_id = request.GET.get('item')
        if item_id:
            initial['item'] = item_id
        form = ReservationForm(initial=initial)

    return render(request, 'inventory/reservation_form.html', {'form': form, 'next': next_url})


@login_required
@require_http_methods(["POST"])
def reservation_cancel(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk, status='PENDING')
    # Only whoever made the booking, the person it's for, or someone allowed to manage
    # reservations can cancel it
    if request.user.pk not in (reservation.reserved_by_id, reservation.reserved_for_id) and \
            not request.user.has_perm('inventory.change_reservation'):
        messages.error(request, 'You can only cancel reservations you made or that are for you.')
        return redirect('inventory-reservation-list')
    services.cancel_reservation(reservation)
    messages.success(request, f'Cancelled reservation for {reservation.item.name}.')
    return redirect('inventory-reservation-list')


@login_required
@permission_required('inventory.add_assignment', raise_exception=True)
@require_http_methods(["POST"])
def reservation_fulfill(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk, status='PENDING')
    try:
        assignment = services.fulfill_reservation(reservation, performed_by=request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('inventory-reservation-list')

    messages.success(request, f'{assignment.item.name} assigned to {person_name(assignment.assigned_to)}.')
    return redirect('inventory-reservation-list')


# NOTIFICATIONS

@login_required
@require_http_methods(["POST"])
def send_notifications_now(request):
    """Staff-triggered, on-demand version of the notify_overdue management command"""
    if not request.user.is_staff:
        messages.error(request, 'You do not have permission to do this.')
        return redirect('inventory-reports')

    context, recipients, total_issues = send_overdue_digest()

    if total_issues == 0:
        messages.success(request, 'No overdue items, low stock, or expired reservations right now - nothing to send.')
    elif not recipients:
        messages.error(request, f'{total_issues} issue(s) found but no active staff user has an email address on file.')
    else:
        messages.success(request, f'Digest emailed to {len(recipients)} recipient(s) covering {total_issues} issue(s).')

    return redirect('inventory-reports')

