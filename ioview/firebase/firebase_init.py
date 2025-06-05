import os
import firebase_admin
from firebase_admin import credentials

# Get the full path to the JSON file relative to this file's location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CRED_PATH = os.path.join(BASE_DIR, 'ioview-firebase-adminsdk.json')

cred = credentials.Certificate(CRED_PATH)
default_app = firebase_admin.initialize_app(cred)
