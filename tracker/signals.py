# tracker/signals.py

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import Stage, StageRemark, StageHistory

def clear_project_cache(instance):
    if hasattr(instance, 'project'):
        project_id = instance.project.id
    elif hasattr(instance, 'stage'):
        project_id = instance.stage.project.id
    else:
        return
    cache_key = f'project_detail_{project_id}'
    cache.delete(cache_key)

@receiver(post_save, sender=Stage)
@receiver(post_delete, sender=Stage)
@receiver(post_save, sender=StageRemark)
@receiver(post_delete, sender=StageRemark)
@receiver(post_save, sender=StageHistory)
@receiver(post_delete, sender=StageHistory)
def invalidate_project_cache(sender, instance, **kwargs):
    clear_project_cache(instance)
