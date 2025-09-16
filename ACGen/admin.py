from django.contrib import admin
from .models import ClusterTemplate, Parameter, StandardString, GenerationLog, ControlLibrary
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
        'id', 'user', 'generation_time', 'project_name', 'project_file_name'
    )  
    # Display all fields
    search_fields = ('user','project_name','project_file_name')  # Optional: Allows searching by cluster_name
    list_filter = ('user', 'project_name')

admin.site.register(GenerationLog, GenerationLogAdmin)

