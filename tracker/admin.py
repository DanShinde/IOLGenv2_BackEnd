from django.contrib import admin
from django.db.models import Count
from .models import Project, Stage, trackerSegment, ContactPerson, ProjectComment, DelayReasonTag
from import_export.admin import ImportExportModelAdmin



@admin.register(Project)
class ProjectAdmin(ImportExportModelAdmin, admin.ModelAdmin):

    list_display = ('id', 'code', 'customer_name', 'value', 'so_punch_date', 'segment_con', 'team_lead')
    search_fields = ('code', 'customer_name', 'segment_con__name', 'team_lead__name')
    list_filter = ('segment_con', 'team_lead',)



@admin.register(Stage)
class StageAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('id', 'name', 'project', 'planned_date', 'actual_date', 'status', 'completion_percentage')
    search_fields = ('name', 'project__code')
    list_filter = ('status',)


@admin.register(trackerSegment)
class SegmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')  # Display ID and name in the admin list view

    search_fields = ('name',)  # Add search functionality for the name field

# ✅ Register the ContactPerson model
@admin.register(ContactPerson)
class ContactPersonAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'email')
    search_fields = ('first_name', 'last_name', 'email', 'name')
    fields = ('first_name', 'last_name', 'email') # 'name' is hidden and auto-calculated

@admin.register(DelayReasonTag)
class DelayReasonTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'used_in_stages', 'created_at')
    search_fields = ('name',)
    ordering = ('name',)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_stage_count=Count('stage_delays'))

    @admin.display(description='Used in stages', ordering='_stage_count')
    def used_in_stages(self, obj):
        return obj._stage_count

@admin.register(ProjectComment)
class ProjectCommentAdmin(admin.ModelAdmin):
    list_display = ('project', 'added_by', 'text', 'created_at')
    search_fields = ('project__code', 'added_by__username', 'text')