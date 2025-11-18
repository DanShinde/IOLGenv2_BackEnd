from django.contrib import admin
from .models import BugReport, ClusterTemplate, Parameter, StandardString, GenerationLog, ControlLibrary, BugReportAttachment
from import_export.admin import ImportExportModelAdmin

# Register your models here.
# admin.site.register(ClusterTemplate)
# admin.site.register(Parameter)
admin.site.register(StandardString)

# Register ClusterTemplate model
class ClusterTemplateAdmin(ImportExportModelAdmin,admin.ModelAdmin) :
    list_display = (
        'id', 'cluster_name', 'block_type', 'uploaded_by', 'uploaded_at',
        'updated_by', 'updated_at', 'control_library', 'parameters_count'
    )  # Display all fields
    search_fields = ('cluster_name',)  # Optional: Allows searching by cluster_name
    list_filter = ('segment', 'control_library','block_type' , 'uploaded_by')

    def change_view(self, request, object_id, form_url='', extra_context=None):
        try:
            return super().change_view(request, object_id, form_url, extra_context)
        except Exception as e:
            import traceback
            print("\n--- ADMIN CHANGE_VIEW EXCEPTION ---")
            traceback.print_exc()
            raise

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user.username
        if not change:
            obj.uploaded_by = request.user.username
        super().save_model(request, obj, form, change)



admin.site.register(ClusterTemplate, ClusterTemplateAdmin)


 
@admin.register(ControlLibrary)
class SegmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')  # Display ID and name in the admin list view
    search_fields = ('name',)  # Add search functionality for the name field
    



# Register Parameter model
class ParameterAdmin(ImportExportModelAdmin,admin.ModelAdmin):
    list_display = (
        'id', 'parameter_name', 'section', 'data_type', 'cluster', 'assignment_value', 'uploaded_by',
        'uploaded_at', 'updated_by', 'updated_at', 'sort_order', 'drive_io_assignment_value'
    )  # Display all fields
    search_fields = ('parameter_name',)  # Optional: Allows searching by parameter_name
    list_filter = ('cluster', 'data_type', 'section' )  # Optional: Allows filtering by cluster and data_type

admin.site.register(Parameter, ParameterAdmin)


class GenerationLogAdmin(ImportExportModelAdmin,admin.ModelAdmin) :
    list_display = (
        'id', 'user', 'generation_time',  'Log_Event',  'project_name', 'project_file_name'
    )  
    # Display all fields
    search_fields = ('user','project_name','project_file_name')  # Optional: Allows searching by cluster_name
    list_filter = ('user', 'project_name',  'Log_Event')

admin.site.register(GenerationLog, GenerationLogAdmin)


class BugReportAttachmentInline(admin.TabularInline):
    model = BugReportAttachment
    extra = 0
    fields = ("original_name", "image", "uploaded_by", "uploaded_at")
    readonly_fields = ("uploaded_by", "uploaded_at")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# Register BugReport model
class BugReportAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    inlines = [BugReportAttachmentInline]
    list_display = (
        'id',
        'title',
        'status',
        'application_version',
        'reported_by',
        'created_at',
        'updated_at',
    )
    search_fields = ('title', 'steps_to_reproduce', 'reported_by__username')  # Allows searching by title, steps, and the reporter's username
    list_filter = ('status', 'application_version', 'reported_by')
    readonly_fields = ('created_at', 'updated_at') # Good practice to make auto-fields read-only

admin.site.register(BugReport, BugReportAdmin)