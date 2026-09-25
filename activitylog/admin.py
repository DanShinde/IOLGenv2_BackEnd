from django.contrib import admin

from .models import ActivityLog


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    """Read-only: the log is a record, not something to edit. Only superusers may delete
    rows (or use the prune_activity_log command to trim old ones)."""
    list_display = ('timestamp', 'username', 'event', 'app', 'description', 'status_code', 'ip_address')
    list_filter = ('event', 'app')
    search_fields = ('username', 'description', 'path')
    date_hierarchy = 'timestamp'
    list_per_page = 100

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
