from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from IOLGen.models import Segment

from accounts.models import clear_info_cache

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
    cluster_name = models.CharField(max_length=255, unique=True)
    cluster_config = models.TextField(null=True,blank=True)
    cluster_string = models.CharField(null=True, blank=True)
    block_type = models.CharField(max_length=255)
    uploaded_by = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.CharField(max_length=255)
    updated_at = models.DateTimeField(auto_now=True)
    segment = models.CharField(max_length=255)
    segment_con = models.ForeignKey(
        Segment, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
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
    clear_info_cache("Parameter",instance.parameter_name)

# Signal: Clear cache when an Info instance is created or updated
@receiver([post_save, post_delete], sender=ClusterTemplate)
def update_info_cache(sender, instance, **kwargs):
    clear_info_cache("ClusterTemplate",instance.id)
    clear_info_cache("ClusterTemplate",instance.cluster_name)

