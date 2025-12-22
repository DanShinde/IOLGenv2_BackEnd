
################################################################################
# FILE 2: views.py (COMPLETE FILE - REPLACE EXISTING)
################################################################################

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Q, Sum, Count, Prefetch
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.cache import cache
from django.views.decorators.cache import cache_page
from datetime import date
import csv
import json
from .models import Item, Assignment, Dispatch, History
from .forms import ItemForm, HistoryFilterForm, UnifiedTransferForm, ItemFilterForm


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
@cache_page(60 * 5)  # Cache for 5 minutes
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
    assignments = Assignment.objects.filter(item=item).select_related(
        'assigned_to', 'assigned_by'
    ).order_by('-assignment_date')[:5]
    dispatches = Dispatch.objects.filter(item=item).select_related(
        'dispatched_by'
    ).order_by('-dispatch_date')[:5]

    context = {
        'item': item,
        'history': history,
        'assignments': assignments,
        'dispatches': dispatches,
    }
    return render(request, 'inventory/item_detail.html', context)


@login_required
def item_create(request):
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
            return redirect('inventory-item-detail', pk=item.pk)
        else:
            messages.error(request,
                'Please correct the errors below',
                extra_tags='bg-red-100 text-red-800'
            )
    else:
        form = ItemForm()

    context = {
        'form': form,
        'title': 'Add New Inventory Item'
    }
    return render(request, 'inventory/item_form.html', context)


@login_required
def item_update(request, pk):
    item = get_object_or_404(Item, pk=pk)
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
            return redirect('inventory-item-detail', pk=updated_item.pk)
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
        'item': item
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
    """Bulk update items status"""
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

        elif action == 'delete':
            count = items.count()
            items.delete()
            invalidate_cache('items_list')
            invalidate_cache('dashboard_stats')
            return JsonResponse({'success': True, 'message': f'Successfully deleted {count} items'})

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
    assignment = get_object_or_404(Assignment, pk=pk)
    if request.method == 'POST':
        assignment.return_date = date.today()
        assignment.save()
        
        item = assignment.item
        item.status = 'AVAILABLE'
        item.location = 'Warehouse'
        item.save()

        History.objects.create(
            item=item,
            action='RETURNED',
            user=request.user,
            details=f'Returned by {assignment.assigned_to.get_full_name() or assignment.assigned_to.username}',
            location='Warehouse'
        )
        
        return redirect('inventory-transfer-item')
    
    return render(request, 'inventory/return_confirm.html', {'assignment': assignment})


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


# UNIFIED TRANSFER SYSTEM

@login_required
def transfer_item(request):
    if request.method == 'POST':
        form = UnifiedTransferForm(request.POST)
        if form.is_valid():
            transfer_type = form.cleaned_data['transfer_type']
            transfer_date = form.cleaned_data['transfer_date']
            expected_return_date = form.cleaned_data['expected_return_date']
            notes = form.cleaned_data['notes']
            assigned_to = form.cleaned_data.get('assigned_to')
            
            with transaction.atomic():
                if transfer_type == 'assign':
                    assignment = form.cleaned_data.get('assignment')
                    available_item = form.cleaned_data.get('available_item')
                    
                    if assignment:
                        # Handle transfer of assigned item
                        # End current assignment
                        assignment.return_date = transfer_date
                        assignment.save()
                        
                        # Create history for return
                        History.objects.create(
                            item=assignment.item,
                            action='RETURNED',
                            user=request.user,
                            details=f'Returned by {assignment.assigned_to.get_full_name() or assignment.assigned_to.username} (Transfer)',
                            location='Warehouse'
                        )

                        # Update item location
                        assignment.item.location = f'With {assigned_to.get_full_name() or assigned_to.username}'
                        assignment.item.save()

                        # Create new assignment
                        Assignment.objects.create(
                            item=assignment.item,
                            assigned_to=assigned_to,
                            assigned_by=request.user,
                            assignment_date=transfer_date,
                            expected_return_date=expected_return_date,
                            notes=f"Transferred from {assignment.assigned_to.get_full_name() or assignment.assigned_to.username}. {notes}".strip()
                        )

                        # Create transfer history
                        History.objects.create(
                            item=assignment.item,
                            action='TRANSFERRED',
                            user=request.user,
                            details=f'Transferred from {assignment.assigned_to.get_full_name() or assignment.assigned_to.username} to {assigned_to.get_full_name() or assigned_to.username}',
                            location=f'With {assigned_to.get_full_name() or assigned_to.username}'
                        )
                        
                        messages.success(request, 
                            f'Successfully transferred {assignment.item.name} from {assignment.assigned_to.get_full_name() or assignment.assigned_to.username} to {assigned_to.get_full_name() or assigned_to.username}'
                        )
                    
                    elif available_item:
                        # Handle assignment of available item
                        # Create assignment
                        Assignment.objects.create(
                            item=available_item,
                            assigned_to=assigned_to,
                            assigned_by=request.user,
                            assignment_date=transfer_date,
                            expected_return_date=expected_return_date,
                            notes=notes
                        )
                        
                        # Update item status and location
                        available_item.status = 'ASSIGNED'
                        available_item.location = f'With {assigned_to.get_full_name() or assigned_to.username}'
                        available_item.save()

                        # Create history
                        History.objects.create(
                            item=available_item,
                            action='ASSIGNED',
                            user=request.user,
                            details=f'Assigned to {assigned_to.get_full_name() or assigned_to.username}',
                            location=f'With {assigned_to.get_full_name() or assigned_to.username}'
                        )
                        
                        messages.success(request, 
                            f'Successfully assigned {available_item.name} to {assigned_to.get_full_name() or assigned_to.username}'
                        )
                
                elif transfer_type == 'dispatch':
                    # Handle dispatch of item
                    project = form.cleaned_data['project']
                    site_location = form.cleaned_data.get('site_location', '')
                    quantity = form.cleaned_data.get('quantity', 1)

                    # Get the item (could be available or assigned)
                    item = form.cleaned_data.get('available_item')
                    if not item and form.cleaned_data.get('assignment'):
                        item = form.cleaned_data['assignment'].item

                    if item:
                        # Different logic for TOOLS vs MATERIALS
                        if item.item_type == 'MATERIAL':
                            # Materials: Reduce stock and mark as CONSUMED if quantity dispatched
                            # Create dispatch record
                            Dispatch.objects.create(
                                item=item,
                                quantity=quantity,
                                project=project,
                                site_location=site_location,
                                dispatched_by=request.user,
                                dispatch_date=transfer_date,
                                notes=notes
                            )

                            # Reduce material stock
                            item.quantity -= quantity

                            # If no stock left, mark as consumed
                            if item.quantity <= 0:
                                item.status = 'CONSUMED'
                                item.location = f'Consumed at {project}'
                            else:
                                item.location = f'Warehouse (Partially dispatched to {project})'

                            item.save()

                            # Create history
                            History.objects.create(
                                item=item,
                                action='CONSUMED',
                                user=request.user,
                                details=f'{quantity} units dispatched to {project} (Site: {site_location or "N/A"})',
                                location=f'{project} - {site_location or "N/A"}'
                            )

                            messages.success(request,
                                f'Successfully dispatched {quantity} units of {item.name} to {project}. '
                                f'Remaining stock: {item.quantity}'
                            )

                        else:  # TOOL
                            # Tools: Can be dispatched and returned
                            # If item was assigned, return it first
                            if item.status == 'ASSIGNED':
                                active_assignment = Assignment.objects.filter(item=item, return_date__isnull=True).first()
                                if active_assignment:
                                    active_assignment.return_date = transfer_date
                                    active_assignment.save()
                                    History.objects.create(
                                        item=item,
                                        action='RETURNED',
                                        user=request.user,
                                        details=f'Returned by {active_assignment.assigned_to.get_full_name() or active_assignment.assigned_to.username} (For Dispatch)',
                                        location='Warehouse'
                                    )

                            # Create dispatch record
                            Dispatch.objects.create(
                                item=item,
                                quantity=1,
                                project=project,
                                site_location=site_location,
                                dispatched_by=request.user,
                                dispatch_date=transfer_date,
                                expected_return_date=expected_return_date,
                                notes=notes
                            )

                            # Update tool status
                            item.status = 'DISPATCHED'
                            item.location = f'{project} - {site_location or "N/A"}'
                            item.save()

                            # Create history
                            History.objects.create(
                                item=item,
                                action='DISPATCHED',
                                user=request.user,
                                details=f'Dispatched to {project} (Site: {site_location or "N/A"})',
                                location=f'{project} - {site_location or "N/A"}'
                            )

                            messages.success(request,
                                f'Successfully dispatched {item.name} to {project}'
                            )
            
            return redirect('inventory-transfer-item')
    else:
        form = UnifiedTransferForm()
    
    # Get data for display
    active_assignments = Assignment.objects.filter(
        return_date__isnull=True
    ).select_related('item', 'assigned_to').order_by('item__name')
    
    available_items = Item.objects.filter(
        status='AVAILABLE'
    ).order_by('name')
    
    context = {
        'form': form,
        'active_assignments': active_assignments,
        'available_items': available_items,
    }
    return render(request, 'inventory/unified_transfer_form.html', context)



