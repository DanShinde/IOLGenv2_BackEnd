from django.contrib import admin
from .models import UserProfile,Info
from import_export.admin import ImportExportModelAdmin

# Register your models here.
class UserProfileAdmin(ImportExportModelAdmin,admin.ModelAdmin) :
    list_display = (
        'id', 'user', 'usertype',  'is_ac_approved', 'is_ac_cluster_create_allowed',
        'is_ac_cluster_edit_allowed', 'is_ac_cluster_delete_allowed'
    )  # Display all fields
    list_filter = ('usertype', 'is_ac_approved')
    search_fields = ('user',)

admin.site.register(UserProfile, UserProfileAdmin)

class InfosAdmin(ImportExportModelAdmin, admin.ModelAdmin) :
    list_display = (
        'id', 'key', 'value'
    )  # Display all fields
    search_fields = ('key',)
    
admin.site.register(Info, InfosAdmin)