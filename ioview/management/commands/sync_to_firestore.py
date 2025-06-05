import os
import firebase_admin
from firebase_admin import credentials, firestore
from ioview.models import IOVProject, Tag
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        cred_path = os.path.join(BASE_DIR, "firebase", "ioview-firebase-adminsdk.json")

        # ✅ Initialize only if not already initialized
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)

        db = firestore.client()

        for project in IOVProject.objects.all():
            proj_ref = db.collection("projects").document(str(project.id))
            proj_ref.set({
                "name": project.name,
                "plc_endpoint": project.plc_endpoint
            })

            tags = Tag.objects.filter(project=project)
            for tag in tags:
                proj_ref.collection("tags").document(str(tag.id)).set({
                    "name": tag.name,
                    "address": tag.address,
                    "type": tag.type,
                    "panel_number": tag.panel_number,
                    "location": tag.location,
                    "order": tag.order
                })
