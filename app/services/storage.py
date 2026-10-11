import os
import io
import uuid
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from fastapi import UploadFile

from app.config import (
    UPLOAD_DIR,
    GDRIVE_SERVICE_ACCOUNT_FILE,
    GDRIVE_OAUTH_CREDENTIALS_FILE,
    GDRIVE_FOLDER_ID
)

logger = logging.getLogger(__name__)

# Try to import Google Drive libraries
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    GOOGLE_LIBS_AVAILABLE = True
except ImportError:
    GOOGLE_LIBS_AVAILABLE = False


class StorageService:
    def __init__(self):
        self.drive_service = None
        self.storage_mode = "local"  # 'gdrive' or 'local'
        self.init_error = None
        self._initialize_gdrive()

    def _initialize_gdrive(self):
        """Attempts to initialize Google Drive API using service account or credentials."""
        if not GOOGLE_LIBS_AVAILABLE:
            self.storage_mode = "local"
            self.init_error = "Google API библиотеки не установлены"
            return

        sa_path = Path(GDRIVE_SERVICE_ACCOUNT_FILE)
        if sa_path.exists():
            try:
                scopes = ['https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/drive']
                credentials = service_account.Credentials.from_service_account_file(
                    str(sa_path), scopes=scopes
                )
                self.drive_service = build('drive', 'v3', credentials=credentials)
                self.storage_mode = "gdrive"
                self.init_error = None
                logger.info(f"Google Drive service account initialized from {sa_path}")
                return
            except Exception as e:
                self.init_error = f"Ошибка инициализации Service Account: {str(e)}"
                logger.warning(self.init_error)

        oauth_path = Path(GDRIVE_OAUTH_CREDENTIALS_FILE)
        if oauth_path.exists():
            try:
                # If oauth credentials file exists, try basic load if token exists
                token_file = sa_path.parent / "token.json"
                if token_file.exists():
                    from google.oauth2.credentials import Credentials
                    credentials = Credentials.from_authorized_user_file(str(token_file))
                    self.drive_service = build('drive', 'v3', credentials=credentials)
                    self.storage_mode = "gdrive"
                    self.init_error = None
                    logger.info("Google Drive OAuth token initialized")
                    return
            except Exception as e:
                self.init_error = f"Ошибка инициализации OAuth: {str(e)}"
                logger.warning(self.init_error)

        # Fallback to local
        self.storage_mode = "local"
        if not self.init_error:
            self.init_error = "Файл учетных данных Google Drive (service_account.json) не найден. Включен локальный режим хранения."

    def get_status(self) -> Dict[str, Any]:
        """Returns the current storage configuration and status."""
        return {
            "mode": self.storage_mode,
            "is_gdrive": self.storage_mode == "gdrive",
            "service_account_exists": Path(GDRIVE_SERVICE_ACCOUNT_FILE).exists(),
            "oauth_exists": Path(GDRIVE_OAUTH_CREDENTIALS_FILE).exists(),
            "status_message": "Google Drive подключен и активен" if self.storage_mode == "gdrive" else self.init_error or "Локальный режим",
            "folder_id": GDRIVE_FOLDER_ID or "Корень диска (Root)"
        }

    async def upload_file(self, upload_file: UploadFile) -> Dict[str, Any]:
        """
        Uploads a file to Google Drive if configured, otherwise saves locally.
        Returns dict with file_id, file_name, file_url, file_size, storage_type.
        """
        content = await upload_file.read()
        file_size = len(content)
        original_filename = upload_file.filename or "file"

        # If Google Drive is active, try upload to Drive
        if self.storage_mode == "gdrive" and self.drive_service:
            try:
                file_metadata = {
                    'name': f"KiberOne_{original_filename}",
                }
                if GDRIVE_FOLDER_ID.strip():
                    file_metadata['parents'] = [GDRIVE_FOLDER_ID.strip()]

                media = MediaIoBaseUpload(
                    io.BytesIO(content),
                    mimetype=upload_file.content_type or 'application/octet-stream',
                    resumable=True
                )

                g_file = self.drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id, name, webViewLink, webContentLink'
                ).execute()

                file_id = g_file.get('id')
                
                # Make file readable to anyone with link (public read for students/tutors)
                try:
                    self.drive_service.permissions().create(
                        fileId=file_id,
                        body={'type': 'anyone', 'role': 'reader'},
                        fields='id'
                    ).execute()
                except Exception as perm_err:
                    logger.warning(f"Could not set public permission on Drive file {file_id}: {perm_err}")

                web_view_link = g_file.get('webViewLink') or f"https://drive.google.com/file/d/{file_id}/view"
                
                return {
                    "storage_type": "gdrive",
                    "file_id": file_id,
                    "file_name": original_filename,
                    "file_size": file_size,
                    "file_url": web_view_link,
                    "download_url": g_file.get('webContentLink') or web_view_link
                }
            except Exception as e:
                logger.error(f"Google Drive upload failed, falling back to local: {e}")
                # Fallback to local below

        # Local storage fallback
        safe_prefix = uuid.uuid4().hex[:8]
        safe_name = f"{safe_prefix}_{original_filename.replace(' ', '_')}"
        local_path = UPLOAD_DIR / safe_name
        
        with open(local_path, "wb") as f:
            f.write(content)

        return {
            "storage_type": "local",
            "file_id": safe_name,
            "file_name": original_filename,
            "file_size": file_size,
            "file_url": f"/uploads/{safe_name}",
            "download_url": f"/uploads/{safe_name}"
        }


# Singleton storage instance
storage_service = StorageService()
