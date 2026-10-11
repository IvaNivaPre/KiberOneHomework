import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Database configuration
DATABASE_URL = f"sqlite:///{BASE_DIR / 'kiberone.db'}"

# Application security
SECRET_KEY = os.getenv("SECRET_KEY", "kiberone-super-secret-key-2026-homework-platform")
ALGORITHM = "HS256"
COOKIE_NAME = "kiberone_session"

# Google Drive Configuration
# You can place service_account.json or credentials.json in BASE_DIR or specify a path
GDRIVE_SERVICE_ACCOUNT_FILE = os.getenv(
    "GDRIVE_SERVICE_ACCOUNT_FILE", str(BASE_DIR / "service_account.json")
)
GDRIVE_OAUTH_CREDENTIALS_FILE = os.getenv(
    "GDRIVE_OAUTH_CREDENTIALS_FILE", str(BASE_DIR / "credentials.json")
)
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID", "")  # Optional target root folder in Google Drive

# Local upload directory fallback / staging
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
