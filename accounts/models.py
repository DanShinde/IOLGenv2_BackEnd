from django.contrib.auth.models import User
from django.db import models
from IOLGen.models import Segment

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
