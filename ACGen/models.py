from django.db import models
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.core.cache import cache
from django.conf import settings
from django.utils.text import slugify
from django.utils.timezone import now
from pathlib import Path
import uuid
from IOLGen.models import Segment

from accounts.models import clear_info_cache


# ControlLibrary Model
class ControlLibrary(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name
    

# StandardString Model
class StandardString(models.Model):
    id = models.AutoField(primary_key=True)
    string_name = models.CharField(max_length=255, unique=True)
    string_content = models.CharField()

    def __str__(self):
        return self.string_name

# ClusterTemplate Model
class ClusterTemplate(models.Model):
    id = models.AutoField(primary_key=True)
    cluster_name = models.CharField(max_length=255, unique=True, db_index=True)
    cluster_config = models.TextField(null=True,blank=True)
    cluster_string = models.TextField(null=True, blank=True)
    cluster_path = models.CharField(max_length=512, null=True, blank=True)
    cluster_version = models.CharField(max_length=255, null=True, blank=True)
    block_type = models.CharField(max_length=255)
    uploaded_by = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.CharField(max_length=255)
    updated_at = models.DateTimeField(auto_now=True)
    segment = models.CharField(max_length=255)
    is_assignable = models.BooleanField(default=True)
    is_protected = models.BooleanField(default=False)
    dependencies = models.ManyToManyField(
        'self', 
        symmetrical=False, 
        related_name='dependent_clusters',
        help_text="Clusters that this cluster depends on.", blank=True
    )
    segment_con = models.ForeignKey(
        Segment, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
    )
    control_library = models.ForeignKey(
        ControlLibrary, on_delete=models.SET_NULL, null=True, blank=True
    )
    
    parameters_count = models.PositiveIntegerField(default=0, null=True,blank=True)  # Field to store the count
    def save(self, *args, **kwargs):
    # Store the name of the DeviceType before saving
        if self.segment_con:
            self.segment = self.segment_con.name
        super(ClusterTemplate, self).save(*args, **kwargs)
    def __str__(self):
        return self.cluster_name



# Parameter Model
class Parameter(models.Model):
    id = models.AutoField(primary_key=True)
    parameter_name = models.CharField(max_length=255)
    section = models.CharField(max_length=255)
    data_type = models.CharField(max_length=255)
    cluster = models.ForeignKey(
        ClusterTemplate, on_delete=models.CASCADE, related_name="parameters"
    )
    assignment_value = models.CharField(null=True, blank=True)
    uploaded_by = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.CharField(max_length=255)
    updated_at = models.DateTimeField(auto_now=True)
    sort_order = models.IntegerField(null=True, blank=True)
    drive_io_assignment_value = models.CharField(null=True, blank=True)

    def __str__(self):
        return self.parameter_name



class GenerationLog(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.CharField(max_length=255)
    generation_time = models.DateTimeField(auto_now_add=True)
    project_name = models.CharField(max_length=500, null=True, blank=True)
    project_file_name = models.CharField(max_length=500)
    Log_Event = models.CharField(max_length=1000, default="Done")

    def __str__(self):
        return f"Log for {self.project_name} at {self.generation_time}"


class BugReport(models.Model):
    STATUS_OPEN = "open"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_CLOSED = "closed"

    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_CLOSED, "Closed"),
    ]

    title = models.CharField(max_length=255)
    screenshot = models.ImageField(upload_to="bug_reports/screenshots/", null=True, blank=True)
    log_text = models.TextField(blank=True)
    steps_to_reproduce = models.TextField()
    application_version = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    current_status_details = models.TextField(blank=True)
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bug_reports",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"


def bug_report_attachment_upload_to(instance, filename):
    """Generate a unique, timestamped path for uploaded bug report screenshots."""
    ext = filename.split('.')[-1]
    timestamp = now().strftime('%Y%m%d_%H%M%S')
    unique_name = f"{uuid.uuid4().hex}_{timestamp}.{ext}"
    return f"bug_reports/{instance.report.id}/{unique_name}"


class BugReportAttachment(models.Model):
    report = models.ForeignKey(
        BugReport,
        related_name="attachments",
        on_delete=models.CASCADE,
    )
    image = models.ImageField(upload_to=bug_report_attachment_upload_to)
    original_name = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bug_report_attachments",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.original_name or Path(self.image.name).name


@receiver(post_delete, sender=BugReportAttachment)
def delete_bug_report_attachment_file(sender, instance, **kwargs):
    """Delete file from disk when attachment is deleted."""
    if instance.image and instance.image.storage.exists(instance.image.name):
        instance.image.delete(save=False)


@receiver(pre_save, sender=BugReportAttachment)
def auto_delete_old_file_on_change(sender, instance, **kwargs):
    """Delete old file if a new one is uploaded for same record."""
    if not instance.pk:
        return
    try:
        old_file = BugReportAttachment.objects.get(pk=instance.pk).image
    except BugReportAttachment.DoesNotExist:
        return
    new_file = instance.image
    if old_file and old_file != new_file and old_file.storage.exists(old_file.name):
        old_file.delete(save=False)


@receiver(post_delete, sender=BugReport)
def delete_bug_report_screenshot(sender, instance, **kwargs):
    if instance.screenshot:
        instance.screenshot.delete(save=False)

@receiver(post_save, sender=Parameter)
def update_parameters_count_on_save(sender, instance, created, **kwargs):
    if created:
        cluster = instance.cluster
        cluster.parameters_count = cluster.parameters.count()
        cluster.save()

@receiver(post_delete, sender=Parameter)
def update_parameters_count_on_delete(sender, instance, **kwargs):
    cluster = instance.cluster
    cluster.parameters_count = cluster.parameters.count()
    cluster.save()


@receiver([post_save, post_delete], sender=StandardString)
def update_standard_string_cache(sender, instance, **kwargs):
    """
    Clear cache when StandardString instance is created or updated or deleted.
    """
    cache_key = "standard_string_queryset"
    cache.delete(cache_key)



@receiver([post_save, post_delete], sender=ClusterTemplate)
def delete_cluster_template_cache(sender, instance, **kwargs):
    """Delete all cache keys that start with 'cluster_template:'"""
    cache_keys = cache.get('all_cache_keys', set())

    # Filter and delete relevant keys
    keys_to_delete = [key for key in cache_keys if key.startswith("cluster_template:")]
    
    for key in keys_to_delete:
        cache.delete(key)
    
    # Remove the deleted keys from tracking
    cache.set('all_cache_keys', cache_keys - set(keys_to_delete))

    return f"Deleted {len(keys_to_delete)} cache entries."



# Signal: Clear cache when an instance is deleted or updated
@receiver([post_save, post_delete], sender=Parameter)
def delete_info_cache(sender, instance, **kwargs):
    clear_info_cache("Parameter",instance.id)
    clear_info_cache("parameters:cluster_name",instance.cluster.cluster_name)
    clear_info_cache("Parameter",instance.parameter_name)

# Signal: Clear cache when an Info instance is created or updated
@receiver([post_save, post_delete], sender=ClusterTemplate)
def update_info_cache(sender, instance, **kwargs):
    clear_info_cache("ClusterTemplate",instance.id)
    clear_info_cache("ClusterTemplate",instance.cluster_name)

