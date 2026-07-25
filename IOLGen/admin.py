from django.contrib import admin
from .models import Segment


# Register models to the admin site
@admin.register(Segment)
class SegmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')  # Display ID and name in the admin list view
    search_fields = ('name',)  # Add search functionality for the name field
