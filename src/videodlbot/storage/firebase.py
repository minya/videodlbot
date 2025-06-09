import logging
from typing import Optional
import firebase_admin
from firebase_admin import credentials, storage

from ..config import settings

logger = logging.getLogger(__name__)

firebase_app = None

def initialize_firebase() -> None:
    global firebase_app
    if settings.FIREBASE_CREDENTIALS_PATH and settings.FIREBASE_STORAGE_BUCKET:
        try:
            cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
            firebase_app = firebase_admin.initialize_app(cred, {
                'storageBucket': settings.FIREBASE_STORAGE_BUCKET
            })
            logger.info("Firebase initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize Firebase: {e}")
    else:
        logger.warning("Firebase credentials or bucket not configured")


def upload_to_firebase(file_path: str, filename: str) -> Optional[str]:
    if not firebase_app:
        logger.error("Firebase not initialized")
        return None
    
    try:
        bucket = storage.bucket()
        blob = bucket.blob(f"videos/{filename}")
        
        logger.info(f"Uploading {file_path} to Firebase Storage as {filename}")
        blob.upload_from_filename(file_path)
        
        blob.make_public()
        
        download_url = blob.public_url
        logger.info(f"File uploaded successfully. Download URL: {download_url}")
        return download_url
        
    except Exception as e:
        logger.error(f"Error uploading to Firebase: {e}")
        return None