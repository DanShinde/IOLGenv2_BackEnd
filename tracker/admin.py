from django.contrib import admin
from .models import Project, Stage,trackerSegment, Pace  
from import_export.admin import ImportExportModelAdmin



@admin.register(Project)
class ModuleAdmin(ImportExportModelAdmin, admin.ModelAdmin):

    # ✅ Add pace_contact to the display list
    list_display = ('id', 'code', 'customer_name', 'value', 'so_punch_date', 'segment_con', 'pace')
    search_fields = ('code', 'customer_name', 'segment_con__name', 'pace__name') # ✅ Add pace_contact to search
    list_filter = ('segment_con', 'pace',) # ✅ Add pace_contact to filter



@admin.register(Stage)
class ModuleAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('id', 'name', 'project', 'planned_date', 'actual_date', 'status')
    search_fields = ('name', 'project__code')
    # list_filter = ('status')


@admin.register(trackerSegment)
class SegmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')  # Display ID and name in the admin list view

    search_fields = ('name',)  # Add search functionality for the name field

@admin.register(Pace)
class PaceAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)    

