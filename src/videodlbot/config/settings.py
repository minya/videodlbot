import os
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()

BYTES_MB = 1048576


class Settings:
    BOT_TOKEN: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    
    _MAX_FILE_SIZE_STR = os.getenv('MAX_FILE_SIZE', '')
    MAX_FILE_SIZE: int = int(_MAX_FILE_SIZE_STR) * BYTES_MB if _MAX_FILE_SIZE_STR else 500 * BYTES_MB
    MAX_TELEGRAM_FILE_SIZE: int = 50 * BYTES_MB
    
    DEBUG_MODE: bool = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
    ALLOWED_USERS: List[str] = os.getenv('ALLOWED_USERS', '').split(',')
    
    COOKIE_FILE: Optional[str] = '.secrets/cookies.txt' if os.path.exists('.secrets/cookies.txt') else None
    
    FIREBASE_CREDENTIALS_PATH: Optional[str] = os.getenv('FIREBASE_CREDENTIALS_PATH')
    FIREBASE_STORAGE_BUCKET: Optional[str] = os.getenv('FIREBASE_STORAGE_BUCKET')


settings = Settings()