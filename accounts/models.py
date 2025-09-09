from django.contrib.auth.models import User
from django.db import models
from IOLGen.models import Segment
from django.db.models.signals import post_save, post_delete, post_init
from django.dispatch import receiver
from django.core.cache import cache, caches

def print_all_cache():
    try:
        # Get Redis client
        redis_client = cache._cache.get_client(1)
        
        # Get all keys
        all_keys = redis_client.keys('*')
        
        print(f"Found {len(all_keys)} cache entries:")
        for key in all_keys:
            if isinstance(key, bytes):
                key = key.decode('utf-8')
            
            value = cache.get(key)
            print(f"Key: {key}")
            print(f"Value: {value}")
            print("-" * 50)
            
    except Exception as e:
        print(f"Error accessing Redis cache: {e}")
        
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
    is_tracker = models.BooleanField(default=False, help_text="Is this user a tracker?")
    def __str__(self):
        return f"{self.user.username}'s Profile - {self.get_usertype_display()}"




class Info(models.Model):
    id = models.AutoField(primary_key=True)
    key = models.CharField(max_length=255)
    value = models.TextField()

    def __str__(self):
        return f"{self.key}: {self.value}"


# Function to clear cache when an Info object is created, updated, or deleted
def clear_info_cache(prefix,id):
    cache_key = f"{prefix}_{id}"
    cache.delete(cache_key)
    cache.delete(f"{prefix}:{id}")
    # try:
    #     cacher = caches['default']  # or whatever cache alias you use
    #     keys = list(cacher._cache.keys())
    #     # print(keys)
    # except Exception as e:
    #     print(f"Error accessing cache keys: {e}")


# Signal: Clear cache when an Info instance is created or updated or deleted
@receiver([post_save,post_delete], sender=Info)
def update_info_cache(sender, instance, **kwargs):
    clear_info_cache("info",instance.id)


@receiver(post_save, sender=User)
def create_new_user_profile(sender, instance, created, **kwargs):
    if created:  # This ensures the signal runs only when a new User is created
        UserProfile.objects.create(
            user=instance, 
            usertype=UserTypeEnum.USER, 
            is_ac_approved=False, 
            is_ac_cluster_create_allowed=False, 
            is_ac_cluster_edit_allowed=False, 
            is_ac_cluster_delete_allowed=False
        )



