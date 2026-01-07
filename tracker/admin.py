from django.contrib import admin
from .models import Project, Stage, trackerSegment, ContactPerson, ProjectComment
from import_export.admin import ImportExportModelAdmin



@admin.register(Project)
class ModuleAdmin(ImportExportModelAdmin, admin.ModelAdmin):

    list_display = ('id', 'code', 'customer_name', 'value', 'so_punch_date', 'segment_con', 'team_lead')
    search_fields = ('code', 'customer_name', 'segment_con__name', 'team_lead__name')
    list_filter = ('segment_con', 'team_lead',)



@admin.register(Stage)
class ModuleAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('id', 'name', 'project', 'planned_date', 'actual_date', 'status', 'completion_percentage')
    search_fields = ('name', 'project__code')
    # list_filter = ('status')


@admin.register(trackerSegment)
class SegmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')  # Display ID and name in the admin list view

    search_fields = ('name',)  # Add search functionality for the name field

# ✅ Register the ContactPerson model
@admin.register(ContactPerson)
class ContactPersonAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)

@admin.register(ProjectComment)
class ProjectCommentAdmin(admin.ModelAdmin):
    list_display = ('project', 'added_by', 'text', 'created_at')
    search_fields = ('project__code', 'added_by__username', 'text')