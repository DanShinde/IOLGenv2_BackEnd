from django.contrib.auth.models import User
from django.db import models
from IOLGen.models import Segment
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache


class UserTypeEnum(models.TextChoices):
    USER = "USER", "User"
    ADMIN = "ADMIN", "Admin"
    MANAGER = "MANAGER", "Manager"

# User Profile Model (Extending User)
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    usertype = models.CharField(
        max_length=10,
        choices=UserTypeEnum.choices,
        default=UserTypeEnum.USER,  # Default user type
    )
    segments = models.ManyToManyField(Segment, blank=True)  # Many-to-Many for segments
    is_ac_approved = models.BooleanField(default=False)
    is_ac_cluster_create_allowed = models.BooleanField(default=False)
    is_ac_cluster_edit_allowed = models.BooleanField(default=False)
    is_ac_cluster_delete_allowed = models.BooleanField(default=False)
    allowed_clusters = models.ManyToManyField(
        'ACGen.ClusterTemplate',  # Reference using 'app_label.ModelName'
        related_name='allowed_users',
        blank=True,
        help_text="Clusters allowed for this user."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s Profile - {self.get_usertype_display()}"




class Info(models.Model):
    key = models.CharField(max_length=255)
    value = models.TextField()

    def __str__(self):
        return f"{self.key}: {self.value}"


# Function to clear cache when an Info object is created, updated, or deleted
def clear_info_cache(prefix,key):
    cache_key = f"{prefix}_{key}"
    cache.delete(cache_key)

# Signal: Clear cache when an Info instance is created or updated
@receiver(post_save, sender=Info)
def update_info_cache(sender, instance, **kwargs):
    clear_info_cache("info",instance.key)

# Signal: Clear cache when an Info instance is deleted
@receiver(post_delete, sender=Info)
def delete_info_cache(sender, instance, **kwargs):
    clear_info_cache("info",instance.key)