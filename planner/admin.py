from django.contrib import admin
from .models import ProjectType, Segment, Category, Holiday, Project, Activity, GeneralSettings, CapacitySettings, EffortBracket, SalesForecast, Leave
from import_export.admin import ImportExportModelAdmin

class ProjectTypeAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('segment', 'category', 'engineer_involvement', 'team_lead_involvement', 'manager_involvement')
    search_fields = ('segment__name', 'category__name')
    list_filter = ('segment', 'category')

class SegmentAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

class CategoryAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

class HolidayAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('date', 'description')
    search_fields = ('description',)
    list_filter = ('date',)

class ProjectAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('project_id', 'customer_name', 'segment', 'team_lead', 'tracker_project')
    search_fields = ('project_id', 'customer_name', 'tracker_project__code')
    list_filter = ('segment', 'team_lead')
    raw_id_fields = ('tracker_project',)
    readonly_fields = ('get_tracker_link',)

    def get_tracker_link(self, obj):
        """Display a clickable link to the tracker project if connected."""
        if obj.tracker_project:
            from django.utils.html import format_html
            return format_html(
                '<a href="/admin/tracker/project/{}/change/" target="_blank">{}</a>',
                obj.tracker_project.id,
                obj.tracker_project.code
            )
        return "-"
    get_tracker_link.short_description = "Tracker Project Link"

class ActivityAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('project', 'activity_name', 'assignee', 'start_date', 'duration', 'end_date')
    search_fields = ('activity_name', 'project__project_id')
    list_filter = ('project', 'assignee', 'start_date')

class GeneralSettingsAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('working_hours_per_day',)

class CapacitySettingsAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('designation', 'monthly_meeting_hours', 'monthly_leave_hours', 'efficiency_loss_factor')
    search_fields = ('designation',)
    list_filter = ('designation',)

class EffortBracketAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('project_type', 'project_value', 'effort_days')
    search_fields = ('project_type__segment__name', 'project_type__category__name')
    list_filter = ('project_type',)

class SalesForecastAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('opportunity', 'total_amount', 'probability', 'segment', 'category', 'start_date', 'end_date')
    search_fields = ('opportunity', 'segment', 'category')
    list_filter = ('segment', 'category', 'probability')

class LeaveAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('employee', 'start_date', 'end_date', 'reason')
    search_fields = ('employee__name', 'reason')
    list_filter = ('start_date', 'end_date')
    raw_id_fields = ('employee',)

admin.site.register(ProjectType, ProjectTypeAdmin)
admin.site.register(Segment, SegmentAdmin)
admin.site.register(Category, CategoryAdmin)
admin.site.register(Holiday, HolidayAdmin)
admin.site.register(Project, ProjectAdmin)
admin.site.register(Activity, ActivityAdmin)
admin.site.register(GeneralSettings, GeneralSettingsAdmin)
admin.site.register(CapacitySettings, CapacitySettingsAdmin)
admin.site.register(EffortBracket, EffortBracketAdmin)
admin.site.register(SalesForecast, SalesForecastAdmin)
admin.site.register(Leave, LeaveAdmin)
