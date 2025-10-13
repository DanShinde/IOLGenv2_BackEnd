
################################################################################
# FILE 2: views.py (COMPLETE FILE - REPLACE EXISTING)
################################################################################

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Q, Sum, Count
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db import transaction
from datetime import date
from .models import Item, Assignment, Dispatch, History
from .forms import ItemForm, HistoryFilterForm, UnifiedTransferForm, ItemFilterForm


@login_required
def dashboard(request):
    # Get summary data for dashboard
    tools_count = Item.objects.filter(item_type='TOOL').count()
    materials_count = Item.objects.filter(item_type='MATERIAL').count()
    users_count = User.objects.filter(is_active=True).count()
    
    # Recent assignments
    recent_assignments = Assignment.objects.filter(
        return_date__isnull=True
    ).order_by('-assignment_date')[:5]
    
    # Recent dispatches
    recent_dispatches = Dispatch.objects.filter(
        return_date__isnull=True
    ).order_by('-dispatch_date')[:5]
    
    # Recent history
    recent_history = History.objects.all().order_by('-timestamp')[:10]
    
    context = {
        'tools_count': tools_count,
        'materials_count': materials_count,
        'users_count': users_count,
        'recent_assignments': recent_assignments,
        'recent_dispatches': recent_dispatches,
        'recent_history': recent_history,
    }
    return render(request, 'inventory/dashboard.html', context)


@login_required
def item_list(request):
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
    
    context = {
        'items': items,
        'form': form,
    }
    return render(request, 'inventory/item_list.html', context)


@login_required
def item_detail(request, pk):
    item = get_object_or_404(Item, pk=pk)
    history = History.objects.filter(item=item).order_by('-timestamp')[:10]
    assignments = Assignment.objects.filter(item=item).order_by('-assignment_date')[:5]
    dispatches = Dispatch.objects.filter(item=item).order_by('-dispatch_date')[:5]
    
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
    history = History.objects.all().order_by('-timestamp')
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
    
    context = {
        'history': history,
        'form': form,
    }
    return render(request, 'inventory/history_list.html', context)


@login_required
def reports(request):
    # Inventory summary
    inventory_summary = Item.objects.values('item_type').annotate(
        total=Count('id'),
        available=Count('id', filter=Q(status='AVAILABLE')),
        assigned=Count('id', filter=Q(status='ASSIGNED')),
        dispatched=Count('id', filter=Q(status='DISPATCHED'))
    )
    
    # Category distribution
    category_distribution = Item.objects.values('category').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # User assignments
    user_assignments = User.objects.filter(
        tool_assignments__return_date__isnull=True
    ).annotate(
        tool_count=Count('tool_assignments')
    ).order_by('-tool_count')
    
    context = {
        'inventory_summary': inventory_summary,
        'category_distribution': category_distribution,
        'user_assignments': user_assignments,
    }
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



