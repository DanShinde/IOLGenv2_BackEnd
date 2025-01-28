from django.contrib import admin
from .models import ClusterTemplate, Parameter, StandardString
from import_export.admin import ImportExportModelAdmin

# Register your models here.
# admin.site.register(ClusterTemplate)
# admin.site.register(Parameter)
admin.site.register(StandardString)

# Register ClusterTemplate model
class ClusterTemplateAdmin(ImportExportModelAdmin,admin.ModelAdmin) :
    list_display = (
        'id', 'cluster_name', 'cluster_string', 'block_type', 'uploaded_by', 'uploaded_at',
        'updated_by', 'updated_at', 'segment', 'parameters_count'
    )  # Display all fields
    search_fields = ('cluster_name',)  # Optional: Allows searching by cluster_name

admin.site.register(ClusterTemplate, ClusterTemplateAdmin)


# Register Parameter model
class ParameterAdmin(ImportExportModelAdmin,admin.ModelAdmin):
    list_display = (
        'id', 'parameter_name', 'section', 'data_type', 'cluster', 'assignment_value', 'uploaded_by',
        'uploaded_at', 'updated_by', 'updated_at', 'sort_order', 'drive_io_assignment_value'
    )  # Display all fields
    search_fields = ('parameter_name',)  # Optional: Allows searching by parameter_name
    list_filter = ('cluster', 'data_type', 'section' )  # Optional: Allows filtering by cluster and data_type

admin.site.register(Parameter, ParameterAdmin)