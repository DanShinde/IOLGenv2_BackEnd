from django.contrib import admin

from .models import TestVaultProject, ReportSession


@admin.register(TestVaultProject)
class TestVaultProjectAdmin(admin.ModelAdmin):
    list_display = ('project_code', 'customer_name', 'zone_name', 'testing_phase', 'prepared_by', 'updated_at')
    list_filter = ('testing_phase', 'validator_type')
    search_fields = ('tracker_project__code', 'tracker_project__customer_name', 'zone_name')
    autocomplete_fields = ('tracker_project', 'prepared_by', 'validator_employee')


@admin.register(ReportSession)
class ReportSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'created_at', 'updated_at')
