from firebase_admin import auth, firestore
from django.contrib.auth import get_user_model
from .firebase.firebase_init import default_app  # Ensure Firebase is initialized
from ioview.models import UserAccess

User = get_user_model()
db = firestore.client()

def sync_user_to_firebase(user):
    """Ensure the user exists in Firebase Auth"""
    try:
        # Try to update if user exists
        auth.update_user(
            uid=str(user.id),
            email=user.email,
            display_name=f"{user.first_name} {user.last_name}",
        )
        print(f"✔ Updated Firebase user: {user.email}")
    except auth.UserNotFoundError:
        # Create if user doesn't exist
        auth.create_user(
            uid=str(user.id),
            email=user.email,
            password="TempPass123!",  # Firebase requires a password
            display_name=f"{user.first_name} {user.last_name}",
        )
        print(f"✔ Created Firebase user: {user.email}")

def push_user_access_to_firestore(user):
    """Push allowed projects and username to Firestore"""
    try:
        access = UserAccess.objects.get(email=user.email)
        db.collection("users").document(str(user.id)).set({
            "email": user.email,
            "username": user.username,
            "allowed_projects": [str(p.id) for p in access.allowed_projects.all()],
        })
        print(f"✔ Access pushed to Firestore for {user.username}")
    except UserAccess.DoesNotExist:
        print(f"⚠ No UserAccess found for: {user.email}")
