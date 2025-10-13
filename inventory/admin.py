from django.contrib import admin
from django.utils.html import format_html
from .models import Item, Assignment, Dispatch, History


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'serial_number', 'item_type', 'status_badge',
        'quantity', 'location', 'current_location_display', 'needs_reorder_badge'
    )
    list_filter = ('item_type', 'status', 'category', 'created_at')
    search_fields = ('name', 'serial_number', 'make', 'model', 'description', 'remarks')
    readonly_fields = ('created_at', 'updated_at', 'current_location_display')

    fieldsets = (
        ('Basic Information', {
            'fields': ('item_type', 'name', 'make', 'model', 'serial_number', 'description', 'image')
        }),
        ('Purchase Information', {
            'fields': ('purchase_date', 'purchase_cost')
        }),
        ('Stock & Location', {
            'fields': ('quantity', 'min_quantity', 'location', 'category', 'status')
        }),
        ('Remarks & Notes', {
            'fields': ('remarks',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at', 'current_location_display'),
            'classes': ('collapse',)
        }),
    )

    def status_badge(self, obj):
        colors = {
            'AVAILABLE': 'green',
            'ASSIGNED': 'blue',
            'DISPATCHED': 'orange',
            'CONSUMED': 'gray',
            'RETIRED': 'red',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def needs_reorder_badge(self, obj):
        if obj.item_type == 'MATERIAL' and obj.needs_reorder:
            return format_html(
                '<span style="background-color: red; color: white; padding: 3px 10px; border-radius: 3px;">LOW STOCK</span>'
            )
        elif obj.item_type == 'MATERIAL':
            return format_html(
                '<span style="background-color: green; color: white; padding: 3px 10px; border-radius: 3px;">OK</span>'
            )
        return '-'
    needs_reorder_badge.short_description = 'Stock Level'


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = (
        'item', 'assigned_to', 'assigned_by', 'assignment_date',
        'expected_return_date', 'return_date', 'status_badge'
    )
    list_filter = ('assignment_date', 'return_date')
    search_fields = (
        'item__name', 'item__serial_number',
        'assigned_to__username', 'assigned_to__first_name', 'assigned_to__last_name'
    )
    date_hierarchy = 'assignment_date'

    def status_badge(self, obj):
        if obj.is_overdue:
            return format_html(
                '<span style="background-color: red; color: white; padding: 3px 10px; border-radius: 3px;">OVERDUE ({} days)</span>',
                obj.days_overdue
            )
        elif obj.is_active():
            return format_html(
                '<span style="background-color: green; color: white; padding: 3px 10px; border-radius: 3px;">ACTIVE</span>'
            )
        return format_html(
            '<span style="background-color: gray; color: white; padding: 3px 10px; border-radius: 3px;">RETURNED</span>'
        )
    status_badge.short_description = 'Status'


@admin.register(Dispatch)
class DispatchAdmin(admin.ModelAdmin):
    list_display = (
        'item', 'quantity', 'project', 'site_location',
        'dispatch_date', 'expected_return_date', 'status_badge'
    )
    list_filter = ('dispatch_date', 'project', 'return_date')
    search_fields = ('item__name', 'item__serial_number', 'project', 'site_location')
    date_hierarchy = 'dispatch_date'

    def status_badge(self, obj):
        if obj.item.item_type == 'MATERIAL':
            return format_html(
                '<span style="background-color: gray; color: white; padding: 3px 10px; border-radius: 3px;">CONSUMED</span>'
            )
        elif obj.is_overdue:
            return format_html(
                '<span style="background-color: red; color: white; padding: 3px 10px; border-radius: 3px;">OVERDUE ({} days)</span>',
                obj.days_overdue
            )
        elif obj.is_active():
            return format_html(
                '<span style="background-color: green; color: white; padding: 3px 10px; border-radius: 3px;">ACTIVE</span>'
            )
        return format_html(
            '<span style="background-color: gray; color: white; padding: 3px 10px; border-radius: 3px;">RETURNED</span>'
        )
    status_badge.short_description = 'Status'


@admin.register(History)
class HistoryAdmin(admin.ModelAdmin):
    list_display = ('item', 'action', 'user', 'location', 'timestamp', 'details_short')
    list_filter = ('action', 'timestamp')
    search_fields = ('item__name', 'item__serial_number', 'user__username', 'details', 'location')
    readonly_fields = ('timestamp',)
    date_hierarchy = 'timestamp'

    def details_short(self, obj):
        return obj.details[:100] + '...' if len(obj.details) > 100 else obj.details
    details_short.short_description = 'Details'
