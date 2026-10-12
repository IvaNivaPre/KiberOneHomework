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
GDRIVE_SERVICE_ACCOUNT_EMAIL = "kiberone@kiberone-hw.iam.gserviceaccount.com"
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID", "10Mgxt-wQU26xs_ubKdLQEXbitPtHVkkt")
GDRIVE_SERVICE_ACCOUNT_FILE = os.getenv(
    "GDRIVE_SERVICE_ACCOUNT_FILE", str(BASE_DIR / "service_account.json")
)
GDRIVE_OAUTH_CREDENTIALS_FILE = os.getenv(
    "GDRIVE_OAUTH_CREDENTIALS_FILE", str(BASE_DIR / "credentials.json")
)

# Contacts with tutor (default fallbacks for Telegram, Phone, Email, MAX, WhatsApp)
TUTOR_CONTACTS = {
    "phone": os.getenv("TUTOR_PHONE", "+7 (495) 120-10-10"),
    "telegram": os.getenv("TUTOR_TELEGRAM", "https://t.me/kiberone_moscow"),
    "telegram_handle": os.getenv("TUTOR_TELEGRAM_HANDLE", "@kiberone_moscow"),
    "email": os.getenv("TUTOR_EMAIL", "info@kiber-one.com"),
    "whatsapp": os.getenv("TUTOR_WHATSAPP", "https://wa.me/74951201010"),
    "max": os.getenv("TUTOR_MAX", "https://max.kiber-one.com")
}

# Local upload directory fallback / staging
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
