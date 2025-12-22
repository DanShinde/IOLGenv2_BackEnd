from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from .models import Employee


class EmployeeAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('name', 'designation', 'is_active', 'email', 'phone', 'join_date')
    search_fields = ('name', 'designation', 'email')
    list_filter = ('designation', 'is_active')

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'designation', 'is_active')
        }),
        ('Contact Information', {
            'fields': ('email', 'phone'),
            'classes': ('collapse',)
        }),
        ('Employment Details', {
            'fields': ('join_date',),
            'classes': ('collapse',)
        }),
    )


admin.site.register(Employee, EmployeeAdmin)
