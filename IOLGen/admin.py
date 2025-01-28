from django.contrib import admin
from .models import Segment, PLC, IODevice, Project, Module, IOList, Signal, ProjectReport
from import_export.admin import ImportExportModelAdmin

# Register models to the admin site
@admin.register(Segment)
class SegmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')  # Display ID and name in the admin list view
    search_fields = ('name',)  # Add search functionality for the name field

@admin.register(PLC)
class PLCAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)

@admin.register(IODevice)
class IODeviceAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)

@admin.register(Project)
class ProjectAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('id', 'name', 'created_by', 'created_at', 'isFreeze')
    search_fields = ('name', 'created_by')
    list_filter = ('isFreeze', 'created_at')  # Add filtering options
    readonly_fields = ('created_at', 'updated_at')  # Make created_at and updated_at read-only


@admin.register(Module)
class ModuleAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('id', 'module', 'created_by', 'created_at')
    search_fields = ('module', 'created_by')
    list_filter = ('created_at',)

@admin.register(IOList)
class IOListAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('id', 'name', 'equipment_code', 'panel_number', 'created_by')
    search_fields = ('name', 'equipment_code', 'panel_number', 'created_by')
    list_filter = ('panel_number', 'created_at')

@admin.register(Signal)
class SignalAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('id', 'module', 'equipment_code', 'code', 'signal_type', 'segment', 'location', 'created_by', 'created_at', 'updated_at')
    search_fields = ('equipment_code', 'code')
    list_filter = ('signal_type', 'location', 'created_at' , 'module__module')

@admin.register(ProjectReport)
class ProjectReportAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('id', 'project', 'updated_by', 'created_at')
    search_fields = ('project__name', 'updated_by')
    list_filter = ('created_at',)
