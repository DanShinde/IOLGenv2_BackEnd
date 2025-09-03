from django.contrib import admin
from .models import Project, Stage,trackerSegment
from import_export.admin import ImportExportModelAdmin



@admin.register(Project)
class ModuleAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    # Corrected: Removed the old 'segment' field from the display.
    list_display = ('id', 'code', 'customer_name', 'value', 'so_punch_date', 'segment_con')
    # Corrected: Changed search to use the 'name' from the related 'segment_con' model.
    search_fields = ('code', 'customer_name', 'segment_con__name')
    # Corrected: Also updated the commented-out filter for future use.
    # list_filter = ('segment_con',)


@admin.register(Stage)
class ModuleAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('id', 'name', 'project', 'planned_date', 'actual_date', 'status')
    search_fields = ('name', 'project__code')
    # list_filter = ('status')


@admin.register(trackerSegment)
class SegmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')  # Display ID and name in the admin list view
    search_fields = ('name',)  # Add search functionality for the name field