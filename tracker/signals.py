# tracker/signals.py

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
# ✅ Import the new ProjectUpdate model
from .models import Stage, StageRemark, StageHistory, ProjectUpdate

def clear_project_cache(instance):
    # This helper function doesn't need to change
    if hasattr(instance, 'project') and instance.project:
        project_id = instance.project.id
    elif hasattr(instance, 'stage'):
        project_id = instance.stage.project.id
    else:
        return
    cache_key = f'project_detail_{project_id}'
    cache.delete(cache_key)

# Add the new ProjectUpdate model to the list of senders
@receiver(post_save, sender=Stage)
@receiver(post_delete, sender=Stage)
@receiver(post_save, sender=StageRemark)
@receiver(post_delete, sender=StageRemark)
@receiver(post_save, sender=StageHistory)
@receiver(post_delete, sender=StageHistory)
@receiver(post_save, sender=ProjectUpdate)      
@receiver(post_delete, sender=ProjectUpdate)    
def invalidate_project_cache(sender, instance, **kwargs):
    clear_project_cache(instance)