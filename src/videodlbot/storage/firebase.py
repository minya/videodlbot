import logging
from datetime import datetime
from typing import Any, TypedDict

import firebase_admin
from firebase_admin import credentials, storage

from ..config import settings

logger = logging.getLogger(__name__)

firebase_app: firebase_admin.App | None = None


class FileInfo(TypedDict):
    name: str
    title: str
    size: int
    created: datetime | None
    updated: datetime | None
    url: str
    user_id: str | None


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


def upload_to_firebase(file_path: str, filename: str, title: str | None = None, user_id: str | None = None) -> str | None:
    if not firebase_app:
        logger.error("Firebase not initialized")
        return None

    try:
        bucket = storage.bucket()
        blob = bucket.blob(f"videos/{filename}")

        logger.info(f"Uploading {file_path} to Firebase Storage as {filename}")

        metadata: dict[str, str] = {}
        if title:
            metadata['title'] = title
        if user_id:
            metadata['user_id'] = user_id
        if metadata:
            blob.metadata = metadata

        blob.upload_from_filename(file_path)

        blob.make_public()

        download_url: str = blob.public_url
        logger.info(f"File uploaded successfully. Download URL: {download_url}")
        return download_url

    except Exception as e:
        logger.error(f"Error uploading to Firebase: {e}")
        return None


def list_firebase_files(user_id: str | None = None, is_admin: bool = False) -> list[FileInfo] | None:
    """List files in the Firebase Storage videos folder.

    If user_id is provided and is_admin is False, only files belonging to that user are returned.
    If is_admin is True, all files are returned.
    """
    if not firebase_app:
        logger.error("Firebase not initialized")
        return None

    try:
        bucket = storage.bucket()
        blobs: Any = bucket.list_blobs(prefix="videos/")

        files: list[FileInfo] = []
        for blob in blobs:
            # Skip directory markers and files with no actual content
            name: str = blob.name
            if name.endswith('/') or blob.size == 0:
                continue

            # Only include actual video files
            filename: str = name.replace('videos/', '')
            if not filename:
                continue

            # Reload blob to get metadata
            blob.reload()

            # Get metadata fields
            title: str | None = None
            file_user_id: str | None = None
            blob_metadata: dict[str, str] | None = blob.metadata
            if blob_metadata:
                title = blob_metadata.get('title')
                file_user_id = blob_metadata.get('user_id')

            # Filter by user_id unless admin
            if user_id and not is_admin and file_user_id != user_id:
                continue

            files.append({
                'name': name,
                'title': title or filename,
                'size': int(blob.size),
                'created': blob.time_created,
                'updated': blob.updated,
                'url': str(blob.public_url),
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
