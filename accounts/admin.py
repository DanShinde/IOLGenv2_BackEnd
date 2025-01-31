from django.contrib import admin
from .models import UserProfile,Info

# Register your models here.
class UserProfileAdmin(admin.ModelAdmin) :
    list_display = (
        'id', 'user', 'usertype',  'is_ac_approved', 'is_ac_cluster_create_allowed',
        'is_ac_cluster_edit_allowed', 'is_ac_cluster_delete_allowed'
    )  # Display all fields
    list_filter = ('usertype', 'is_ac_approved')

admin.site.register(UserProfile, UserProfileAdmin)


admin.site.register(Info)