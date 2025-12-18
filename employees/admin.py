from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from .models import Employee


class EmployeeAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('name', 'designation', 'is_active', 'tracker_pace', 'email', 'phone', 'join_date')
    search_fields = ('name', 'designation', 'email')
    list_filter = ('designation', 'is_active')
    raw_id_fields = ('tracker_pace',)
    readonly_fields = ('get_tracker_link',)

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'designation', 'is_active')
        }),
        ('Contact Information', {
            'fields': ('email', 'phone'),
            'classes': ('collapse',)
        }),
        ('Employment Details', {
            'fields': ('join_date',),
            'classes': ('collapse',)
        }),
        ('Tracker Integration', {
            'fields': ('tracker_pace', 'get_tracker_link'),
            'classes': ('collapse',)
        }),
    )

    def get_tracker_link(self, obj):
        """Display a clickable link to the tracker Pace if connected."""
        if obj.tracker_pace:
            from django.utils.html import format_html
            return format_html(
                '<a href="/admin/tracker/pace/{}/change/" target="_blank">{}</a>',
                obj.tracker_pace.id,
                obj.tracker_pace.name
            )
        return "-"
    get_tracker_link.short_description = "Tracker PACe Link"


admin.site.register(Employee, EmployeeAdmin)
