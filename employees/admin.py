from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from .models import Employee


class EmployeeAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('name', 'designation', 'is_active', 'last_working_day', 'email', 'phone', 'join_date')
    search_fields = ('name', 'designation', 'email')
    list_filter = ('designation', 'is_active')

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'designation', 'is_active', 'last_working_day'),
            'description': 'When unticking "Active Status", set the last working day '
                           '(left blank, today is used). Ticking it again clears the date.',
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
