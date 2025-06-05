from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .firebase_users import sync_user_to_firebase, push_user_access_to_firestore

User = get_user_model()

@receiver(post_save, sender=User)
def sync_user_on_create_or_update(sender, instance, **kwargs):
    sync_user_to_firebase(instance)
    push_user_access_to_firestore(instance)
