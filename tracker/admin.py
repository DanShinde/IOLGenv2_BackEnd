from django.contrib import admin
from .models import Project, Stage,trackerSegment
from import_export.admin import ImportExportModelAdmin



@admin.register(Project)
class ModuleAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('id', 'code', 'customer_name', 'value', 'so_punch_date', 'segment', 'segment_con')
    search_fields = ('code', 'customer_name', 'segment')
    # list_filter = ('segment')


@admin.register(Stage)
class ModuleAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('id', 'name', 'project', 'planned_date', 'actual_date', 'status')
    search_fields = ('name', 'project__code')
    # list_filter = ('status')


admin.register(trackerSegment)
    

