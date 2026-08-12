from django.contrib import admin

from .models import Activity, ComplexityLevel, ModuleActivityTime, ModuleType, Project, ProjectModule, Segment


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ('name', 'display_order')
    search_fields = ('name',)


@admin.register(Segment)
class SegmentAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(ModuleType)
class ModuleTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'has_configured_times')
    search_fields = ('name',)


@admin.register(ModuleActivityTime)
class ModuleActivityTimeAdmin(admin.ModelAdmin):
    list_display = ('segment', 'module_type', 'activity', 'minutes', 'batch_count', 'batch_minutes')
    list_filter = ('segment', 'module_type', 'activity')


@admin.register(ComplexityLevel)
class ComplexityLevelAdmin(admin.ModelAdmin):
    list_display = ('name', 'multiplier', 'display_order')


class ProjectModuleInline(admin.TabularInline):
    model = ProjectModule
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'customer', 'complexity', 'created_by', 'updated_at')
    list_filter = ('complexity',)
    search_fields = ('name', 'customer')
    inlines = [ProjectModuleInline]
