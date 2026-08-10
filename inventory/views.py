
################################################################################
# FILE 2: views.py (COMPLETE FILE - REPLACE EXISTING)
################################################################################

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Q, Sum, Count, Prefetch
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.cache import cache
from django.utils.http import url_has_allowed_host_and_scheme
import csv
import json
from .models import Item, Assignment, Dispatch, History, Reservation
from .forms import (
    ItemForm, HistoryFilterForm, ItemFilterForm, ReturnForm, ReservationForm,
    AssignForm, DispatchForm,
)
from .utils import send_overdue_digest
from . import services


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


def get_cache_key(prefix, **filters):
    """Generate cache key based on filter parameters with versioning"""
    filter_parts = []
    for key, value in sorted(filters.items()):
        if value is not None and value != '':
            filter_parts.append(f"{key}:{value}")

    filter_string = "_".join(filter_parts) if filter_parts else "all"
    version = cache.get(f"{prefix}_version", 0)
    return f"{prefix}:v{version}:{filter_string}"


def invalidate_cache(prefix):
    """Invalidate all cache for a given prefix by incrementing version"""
    cache_version_key = f"{prefix}_version"
    current_version = cache.get(cache_version_key, 0)
    cache.set(cache_version_key, current_version + 1, None)  # Never expires


@login_required
def dashboard(request):
    """
    Optimized dashboard with caching and query optimization
    """
    # Get summary data for dashboard
    cache_key = get_cache_key('dashboard_stats', user_id=request.user.id)
    cached_stats = cache.get(cache_key)

    if not cached_stats:
        tools_count = Item.objects.filter(item_type='TOOL').count()
        materials_count = Item.objects.filter(item_type='MATERIAL').count()
        users_count = User.objects.filter(is_active=True).count()
        cached_stats = {
            'tools_count': tools_count,
            'materials_count': materials_count,
            'users_count': users_count,
        }
        cache.set(cache_key, cached_stats, 300)  # 5 minutes

    # Recent assignments - optimized with select_related
    recent_assignments = Assignment.objects.filter(
        return_date__isnull=True
    ).select_related('item', 'assigned_to', 'assigned_by').order_by('-assignment_date')[:5]

    # Recent dispatches - optimized with select_related
    recent_dispatches = Dispatch.objects.filter(
        return_date__isnull=True
    ).select_related('item', 'dispatched_by').order_by('-dispatch_date')[:5]

    # Recent history - optimized with select_related
    recent_history = History.objects.select_related(
        'item', 'user'
    ).order_by('-timestamp')[:10]

    context = {
        **cached_stats,
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

    # Try to get cached IDs
    cache_key = get_cache_key('items_list', **filter_params)
    cached_ids = cache.get(cache_key)

    # Base queryset
    items = Item.objects.all().order_by('-created_at')

    if cached_ids is not None:
        # Use cached IDs to filter queryset
        items = items.filter(pk__in=cached_ids)
    else:
        # Apply filters
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
            if form.cleaned_data.get('status'):
                items = items.filter(status=form.cleaned_data['status'])

        # Cache the filtered IDs
        cache.set(cache_key, list(items.values_list('id', flat=True)), 300)  # 5 minutes

    # Pagination
    paginated_items, paginator = InventoryPaginator.paginate_queryset(items, request)

    context = {
        'items': paginated_items,
        'paginator': paginator,
        'form': form,
        'is_paginated': paginator.num_pages > 1,
    }
    return render(request, 'inventory/item_list.html', context)


@login_required
def item_detail(request, pk):
    """
    Optimized item detail with prefetch_related for related objects
    """
    item = get_object_or_404(Item, pk=pk)

    # Optimized queries with select_related
    history = History.objects.filter(item=item).select_related('user').order_by('-timestamp')[:10]
    all_assignments = Assignment.objects.filter(item=item).select_related(
        'assigned_to', 'assigned_by'
    ).order_by('-assignment_date')
    all_dispatches = Dispatch.objects.filter(item=item).select_related(
        'dispatched_by'
    ).order_by('-dispatch_date')

    context = {
        'item': item,
        'history': history,
        'assignments': all_assignments[:5],
        'dispatches': all_dispatches[:5],
        'active_assignment': all_assignments.filter(return_date__isnull=True).first(),
        'active_dispatch': all_dispatches.filter(return_date__isnull=True).first(),
    }
    return render(request, 'inventory/item_detail.html', context)


@login_required
def item_create(request):
    fallback = reverse('inventory-item-list')
    next_url = _capture_next(request, fallback)

    if request.method == 'POST':
        form = ItemForm(request.POST, request.FILES)
        if form.is_valid():
            item = form.save()
            # Set created_by
            item.created_by = request.user
            item.save()

            # Invalidate caches
            invalidate_cache('items_list')
            invalidate_cache('dashboard_stats')

            # Create history record
            History.objects.create(
                item=item,
                action='ADDED',
                user=request.user,
                details=f'{item.get_item_type_display()} added to inventory with quantity {item.quantity}',
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
    }
    return render(request, 'inventory/item_form.html', context)


@login_required
def item_update(request, pk):
    item = get_object_or_404(Item, pk=pk)
    fallback = reverse('inventory-item-detail', kwargs={'pk': item.pk})
    next_url = _capture_next(request, fallback)

    if request.method == 'POST':
        form = ItemForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            updated_item = form.save()

            # Invalidate caches
            invalidate_cache('items_list')
            invalidate_cache('dashboard_stats')

            # Create history record
            History.objects.create(
                item=updated_item,
                action='UPDATED',
                user=request.user,
                details=f'Item details updated',
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

    # Apply same filters as item_list
    items = Item.objects.all().order_by('-created_at')
    form = ItemFilterForm(request.GET or None)

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
        if form.cleaned_data.get('status'):
            items = items.filter(status=form.cleaned_data['status'])

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

    history = History.objects.select_related('item', 'user').order_by('-timestamp')
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
            record.user.get_full_name() if record.user else 'N/A',
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
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'You do not have permission to perform this action'}, status=403)

    try:
        data = json.loads(request.body)
        item_ids = data.get('item_ids', [])
        action = data.get('action')

        if not item_ids or not action:
            return JsonResponse({'success': False, 'message': 'Missing required parameters'})

        items = Item.objects.filter(pk__in=item_ids)

        if action == 'retire':
            items.update(status='RETIRED')
            invalidate_cache('items_list')
            invalidate_cache('dashboard_stats')
            return JsonResponse({'success': True, 'message': f'Successfully retired {len(item_ids)} items'})

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
def return_assignment(request, pk):
    assignment = get_object_or_404(Assignment, pk=pk, return_date__isnull=True)
    next_url = _capture_next(request, reverse('inventory-transfer-item'))

    if request.method == 'POST':
        form = ReturnForm(request.POST)
        if form.is_valid():
            returned_by = assignment.assigned_to.get_full_name() or assignment.assigned_to.username
            services.process_return(
                assignment,
                condition=form.cleaned_data['condition'],
                return_notes=form.cleaned_data['return_notes'],
                performed_by=request.user,
                details_prefix=f'Returned by {returned_by}'
            )

            invalidate_cache('items_list')
            invalidate_cache('dashboard_stats')
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
def return_dispatch(request, pk):
    dispatch = get_object_or_404(Dispatch, pk=pk, return_date__isnull=True, item__item_type='TOOL')
    next_url = _capture_next(request, reverse('inventory-transfer-item'))

    if request.method == 'POST':
        form = ReturnForm(request.POST)
        if form.is_valid():
            services.process_return(
                dispatch,
                condition=form.cleaned_data['condition'],
                return_notes=form.cleaned_data['return_notes'],
                performed_by=request.user,
                details_prefix=f'Returned from {dispatch.project}'
            )

            invalidate_cache('items_list')
            invalidate_cache('dashboard_stats')
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
    history = History.objects.select_related('item', 'user').order_by('-timestamp')
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
            history = history.filter(
                Q(user__username__icontains=form.cleaned_data['user_search']) |
                Q(user__first_name__icontains=form.cleaned_data['user_search']) |
                Q(user__last_name__icontains=form.cleaned_data['user_search'])
            )
        if form.cleaned_data['search']:
            history = history.filter(details__icontains=form.cleaned_data['search'])

    # Pagination
    paginated_history, paginator = InventoryPaginator.paginate_queryset(history, request, page_size=25)

    context = {
        'history': paginated_history,
        'paginator': paginator,
        'form': form,
        'is_paginated': paginator.num_pages > 1,
    }
    return render(request, 'inventory/history_list.html', context)


@login_required
def reports(request):
    """
    Optimized reports with caching and better query aggregation
    """
    # Cache reports data
    cache_key = get_cache_key('reports_data')
    cached_data = cache.get(cache_key)

    if not cached_data:
        # Inventory summary
        inventory_summary = list(Item.objects.values('item_type').annotate(
            total=Count('id'),
            available=Count('id', filter=Q(status='AVAILABLE')),
            assigned=Count('id', filter=Q(status='ASSIGNED')),
            dispatched=Count('id', filter=Q(status='DISPATCHED'))
        ))

        # Category distribution with percentage
        total_items = Item.objects.count()
        category_distribution = list(Item.objects.values('category').annotate(
            count=Count('id')
        ).order_by('-count'))

        # Add percentage to each category
        for category in category_distribution:
            category['percentage'] = (category['count'] / total_items * 100) if total_items > 0 else 0

        # User assignments with prefetch
        user_assignments = User.objects.filter(
            tool_assignments__return_date__isnull=True
        ).prefetch_related(
            Prefetch('tool_assignments',
                    queryset=Assignment.objects.filter(return_date__isnull=True).order_by('-assignment_date'))
        ).annotate(
            tool_count=Count('tool_assignments', filter=Q(tool_assignments__return_date__isnull=True))
        ).filter(tool_count__gt=0).order_by('-tool_count')

        # Add last assignment to each user
        user_list = []
        for user in user_assignments:
            last_assignment = user.tool_assignments.first()
            user_list.append({
                'user': user,
                'tool_count': user.tool_count,
                'last_assignment': last_assignment
            })

        cached_data = {
            'inventory_summary': inventory_summary,
            'category_distribution': category_distribution,
            'user_assignments': user_list,
            'total_items': total_items,
        }
        cache.set(cache_key, cached_data, 300)  # Cache for 5 minutes

    context = {
        **cached_data,
        'inventory_summary': cached_data['inventory_summary'],
        'category_distribution': cached_data['category_distribution'],
        'user_assignments': [item['user'] for item in cached_data['user_assignments']],
    }

    # Add last_assignment to user objects for template
    for i, user in enumerate(context['user_assignments']):
        user.last_assignment = cached_data['user_assignments'][i]['last_assignment']

    return render(request, 'inventory/reports.html', context)


# TRANSFER SYSTEM: assign / dispatch / hub

@login_required
def transfer_item(request):
    """Hub page: quick links to Assign/Dispatch/Reserve, plus current item status lists"""
    available_items = Item.objects.filter(status='AVAILABLE').order_by('name')

    active_assignments = Assignment.objects.filter(
        return_date__isnull=True
    ).select_related('item', 'assigned_to').order_by('item__name')

    active_dispatches = Dispatch.objects.filter(
        return_date__isnull=True, item__item_type='TOOL'
    ).select_related('item').order_by('item__name')

    context = {
        'available_items': available_items,
        'active_assignments': active_assignments,
        'active_dispatches': active_dispatches,
    }
    return render(request, 'inventory/transfer_hub.html', context)


@login_required
def assign_item(request):
    next_url = _capture_next(request, reverse('inventory-transfer-item'))

    if request.method == 'POST':
        form = AssignForm(request.POST)
        if form.is_valid():
            item = form.cleaned_data['item']
            assigned_to = form.cleaned_data['assigned_to']
            assignment_date = form.cleaned_data['assignment_date']
            expected_return_date = form.cleaned_data['expected_return_date']
            notes = form.cleaned_data['notes']
            who = assigned_to.get_full_name() or assigned_to.username

            with transaction.atomic():
                if item.status == 'ASSIGNED':
                    active_assignment = item.assignments.filter(return_date__isnull=True).first()
                    prev_who = active_assignment.assigned_to.get_full_name() or active_assignment.assigned_to.username
                    active_assignment.return_date = assignment_date
                    active_assignment.save()

                    History.objects.create(
                        item=item, action='RETURNED', user=request.user,
                        details=f'Returned by {prev_who} (Transfer)', location='Warehouse'
                    )

                    Assignment.objects.create(
                        item=item, assigned_to=assigned_to, assigned_by=request.user,
                        assignment_date=assignment_date, expected_return_date=expected_return_date,
                        notes=f'Transferred from {prev_who}. {notes}'.strip()
                    )

                    item.status = 'ASSIGNED'
                    item.location = f'With {who}'
                    item.save()

                    History.objects.create(
                        item=item, action='TRANSFERRED', user=request.user,
                        details=f'Transferred from {prev_who} to {who}', location=item.location
                    )
                    messages.success(request, f'Transferred {item.name} from {prev_who} to {who}.')
                else:
                    Assignment.objects.create(
                        item=item, assigned_to=assigned_to, assigned_by=request.user,
                        assignment_date=assignment_date, expected_return_date=expected_return_date,
                        notes=notes
                    )
                    item.status = 'ASSIGNED'
                    item.location = f'With {who}'
                    item.save()

                    History.objects.create(
                        item=item, action='ASSIGNED', user=request.user,
                        details=f'Assigned to {who}', location=item.location
                    )
                    messages.success(request, f'Assigned {item.name} to {who}.')

            invalidate_cache('items_list')
            invalidate_cache('dashboard_stats')
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
def dispatch_item(request):
    next_url = _capture_next(request, reverse('inventory-transfer-item'))

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

            with transaction.atomic():
                if item.item_type == 'MATERIAL':
                    Dispatch.objects.create(
                        item=item, quantity=quantity, project=project, site_location=site_location,
                        responsible_person=responsible_person,
                        dispatched_by=request.user, dispatch_date=dispatch_date, notes=notes
                    )

                    item.quantity -= quantity
                    if item.quantity <= 0:
                        item.status = 'CONSUMED'
                        item.location = f'Consumed at {project}'
                    else:
                        item.location = f'Warehouse (Partially dispatched to {project})'
                    item.save()

                    History.objects.create(
                        item=item, action='CONSUMED', user=request.user,
                        details=f'{quantity} units dispatched to {project} (Site: {site_location or "N/A"}) - '
                                f'received by {responsible_person}',
                        location=f'{project} - {site_location or "N/A"}'
                    )
                    messages.success(
                        request,
                        f'Dispatched {quantity} units of {item.name} to {project}. Remaining stock: {item.quantity}'
                    )
                else:  # TOOL
                    if item.status == 'ASSIGNED':
                        active_assignment = Assignment.objects.filter(item=item, return_date__isnull=True).first()
                        if active_assignment:
                            who = active_assignment.assigned_to.get_full_name() or active_assignment.assigned_to.username
                            active_assignment.return_date = dispatch_date
                            active_assignment.save()
                            History.objects.create(
                                item=item, action='RETURNED', user=request.user,
                                details=f'Returned by {who} (For Dispatch)', location='Warehouse'
                            )

                    Dispatch.objects.create(
                        item=item, quantity=1, project=project, site_location=site_location,
                        responsible_person=responsible_person,
                        dispatched_by=request.user, dispatch_date=dispatch_date,
                        expected_return_date=expected_return_date, notes=notes
                    )

                    item.status = 'DISPATCHED'
                    item.location = f'{project} - {site_location or "N/A"}'
                    item.save()

                    History.objects.create(
                        item=item, action='DISPATCHED', user=request.user,
                        details=f'Dispatched to {project} (Site: {site_location or "N/A"}) - '
                                f'responsible person: {responsible_person}',
                        location=item.location
                    )
                    messages.success(request, f'Dispatched {item.name} to {project} (responsible: {responsible_person}).')

            invalidate_cache('items_list')
            invalidate_cache('dashboard_stats')
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
    users = User.objects.filter(is_active=True).annotate(
        active_tool_count=Count('tool_assignments', filter=Q(tool_assignments__return_date__isnull=True))
    ).order_by('username')

    context = {'users': users}
    return render(request, 'inventory/user_list.html', context)


@login_required
def user_detail(request, pk):
    target_user = get_object_or_404(User, pk=pk)

    active_assignments = Assignment.objects.filter(
        assigned_to=target_user, return_date__isnull=True
    ).select_related('item').order_by('item__name')

    past_assignments = Assignment.objects.filter(
        assigned_to=target_user, return_date__isnull=False
    ).select_related('item').order_by('-return_date')

    if request.method == 'POST':
        return assign_item(request)

    form = AssignForm(initial={'assigned_to': target_user.pk})

    context = {
        'target_user': target_user,
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
def reservation_create(request):
    next_url = _capture_next(request, reverse('inventory-reservation-list'))

    if request.method == 'POST':
        form = ReservationForm(request.POST)
        if form.is_valid():
            reservation = form.save(commit=False)
            reservation.reserved_by = request.user
            reservation.save()

            who = reservation.reserved_for.get_full_name() or reservation.reserved_for.username
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
    services.cancel_reservation(reservation)
    messages.success(request, f'Cancelled reservation for {reservation.item.name}.')
    return redirect('inventory-reservation-list')


@login_required
@require_http_methods(["POST"])
def reservation_fulfill(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk, status='PENDING')
    try:
        assignment = services.fulfill_reservation(reservation, performed_by=request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('inventory-reservation-list')

    invalidate_cache('items_list')
    invalidate_cache('dashboard_stats')
    who = assignment.assigned_to.get_full_name() or assignment.assigned_to.username
    messages.success(request, f'{assignment.item.name} assigned to {who}.')
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

