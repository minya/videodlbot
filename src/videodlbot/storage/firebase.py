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


def upload_to_firebase(file_path: str, filename: str, title: Optional[str] = None, user_id: Optional[str] = None) -> Optional[str]:
    if not firebase_app:
        logger.error("Firebase not initialized")
        return None

    try:
        bucket = storage.bucket()
        blob = bucket.blob(f"videos/{filename}")

        logger.info(f"Uploading {file_path} to Firebase Storage as {filename}")

        metadata = {}
        if title:
            metadata['title'] = title
        if user_id:
            metadata['user_id'] = user_id
        if metadata:
            blob.metadata = metadata

        blob.upload_from_filename(file_path)

        blob.make_public()

        download_url = blob.public_url
        logger.info(f"File uploaded successfully. Download URL: {download_url}")
        return download_url

    except Exception as e:
        logger.error(f"Error uploading to Firebase: {e}")
        return None


def list_firebase_files(user_id: Optional[str] = None, is_admin: bool = False) -> Optional[list]:
    """List files in the Firebase Storage videos folder.

    If user_id is provided and is_admin is False, only files belonging to that user are returned.
    If is_admin is True, all files are returned.
    """
    if not firebase_app:
        logger.error("Firebase not initialized")
        return None

    try:
        bucket = storage.bucket()
        blobs = bucket.list_blobs(prefix="videos/")

        files = []
        for blob in blobs:
            # Skip directory markers and files with no actual content
            if blob.name.endswith('/') or blob.size == 0:
                continue

            # Only include actual video files
            filename = blob.name.replace('videos/', '')
            if not filename:
                continue

            # Reload blob to get metadata
            blob.reload()

            # Get metadata fields
            title = None
            file_user_id = None
            if blob.metadata:
                title = blob.metadata.get('title')
                file_user_id = blob.metadata.get('user_id')

            # Filter by user_id unless admin
            if user_id and not is_admin and file_user_id != user_id:
                continue

            files.append({
                'name': blob.name,
                'title': title or filename,
                'size': blob.size,
                'created': blob.time_created,
                'updated': blob.updated,
                'url': blob.public_url,
                'user_id': file_user_id,
            })

        logger.info(f"Found {len(files)} files in Firebase Storage")
        return files

    except Exception as e:
        logger.error(f"Error listing Firebase files: {e}")
        return None


def delete_firebase_file(filename: str) -> bool:
    """Delete a file from Firebase Storage."""
    if not firebase_app:
        logger.error("Firebase not initialized")
        return False

    try:
        bucket = storage.bucket()
        blob = bucket.blob(filename)

        if not blob.exists():
            logger.warning(f"File {filename} does not exist in Firebase Storage")
            return False

        blob.delete()
        logger.info(f"File {filename} deleted successfully from Firebase Storage")
        return True

    except Exception as e:
        logger.error(f"Error deleting Firebase file: {e}")
        return False