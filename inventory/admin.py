from django.contrib import admin
from .models import Item, Assignment, Dispatch, History

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'serial_number', 'item_type', 'status', 'quantity', 'location')
    list_filter = ('item_type', 'status', 'category')
    search_fields = ('name', 'serial_number', 'make', 'model')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('item', 'assigned_to', 'assignment_date', 'return_date')
    list_filter = ('assignment_date',)
    search_fields = ('item__name', 'assigned_to__username')
    raw_id_fields = ('item', 'assigned_to', 'assigned_by')

@admin.register(Dispatch)
class DispatchAdmin(admin.ModelAdmin):
    list_display = ('item', 'quantity', 'project', 'dispatch_date')
    list_filter = ('dispatch_date', 'project')
    search_fields = ('item__name', 'project')

@admin.register(History)
class HistoryAdmin(admin.ModelAdmin):
    list_display = ('item', 'action', 'user', 'timestamp')
    list_filter = ('action', 'timestamp')
    search_fields = ('item__name', 'user__username')
    readonly_fields = ('timestamp',)