import os
import io
import uuid
import json
import hashlib
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from fastapi import UploadFile

from app.config import (
    UPLOAD_DIR,
    BASE_DIR,
    GDRIVE_SERVICE_ACCOUNT_FILE,
    GDRIVE_OAUTH_CREDENTIALS_FILE,
    GDRIVE_FOLDER_ID,
    GDRIVE_SERVICE_ACCOUNT_EMAIL
)

logger = logging.getLogger(__name__)

# Try to import Google Drive libraries
try:
    from google.oauth2 import service_account
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    GOOGLE_LIBS_AVAILABLE = True
except ImportError:
    GOOGLE_LIBS_AVAILABLE = False


class StorageService:
    def __init__(self):
        self.drive_service = None
        self.storage_mode = "local"  # 'gdrive' or 'local'
        self.auth_type = "none"      # 'oauth', 'service_account', or 'none'
        self.init_error = None
        self.last_upload_error = None
        self.last_upload_status = None
        
        # Deduplication cache and statistics
        self.cache_file = BASE_DIR / ".cache_dedup.json"
        self._cache = {}
        self._stats = {"files_deduplicated": 0, "bytes_saved": 0}
        self._load_cache()

        self._initialize_gdrive()

    def _load_cache(self):
        """Loads persistent deduplication cache from disk."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._cache = data.get("cache", {})
                    self._stats = data.get("stats", {"files_deduplicated": 0, "bytes_saved": 0})
            except Exception as e:
                logger.warning(f"Could not load dedup cache: {e}")
                self._cache = {}
                self._stats = {"files_deduplicated": 0, "bytes_saved": 0}

    def _save_cache(self):
        """Saves deduplication cache and savings statistics to disk."""
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump({"cache": self._cache, "stats": self._stats}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Could not save dedup cache: {e}")

    def reload(self):
        """Re-initializes the Google Drive client."""
        self.drive_service = None
        self.storage_mode = "local"
        self.auth_type = "none"
        self.init_error = None
        self.last_upload_error = None
        self._initialize_gdrive()

    def _initialize_gdrive(self):
        """
        Attempts to initialize Google Drive API.
        Priority 1: OAuth User Token (token.json) - has user quota on personal drives!
        Priority 2: Service Account (service_account.json) - works with Workspace Shared Drives.
        Fallback: Local storage in /uploads.
        """
        if not GOOGLE_LIBS_AVAILABLE:
            self.storage_mode = "local"
            self.init_error = "Google API библиотеки не установлены"
            return

        # 1. PRIORITY: Check for authorized user OAuth token (token.json)
        token_path = Path(BASE_DIR) / "token.json"
        if not token_path.exists():
            oauth_path = Path(GDRIVE_OAUTH_CREDENTIALS_FILE)
            if oauth_path.parent:
                alt_token = oauth_path.parent / "token.json"
                if alt_token.exists():
                    token_path = alt_token

        if token_path.exists():
            try:
                credentials = Credentials.from_authorized_user_file(
                    str(token_path),
                    scopes=['https://www.googleapis.com/auth/drive']
                )
                if credentials and credentials.expired and credentials.refresh_token:
                    logger.info("Refreshing expired Google Drive OAuth token...")
                    credentials.refresh(Request())
                    with open(token_path, "w", encoding="utf-8") as f:
                        f.write(credentials.to_json())

                self.drive_service = build('drive', 'v3', credentials=credentials)
                self.storage_mode = "gdrive"
                self.auth_type = "oauth"
                self.init_error = None
                logger.info(f"Google Drive OAuth initialized successfully from {token_path}")
                return
            except Exception as e:
                self.init_error = f"Ошибка инициализации OAuth token: {str(e)}"
                logger.warning(self.init_error)

        # 2. Check for Service Account key (service_account.json)
        sa_path = Path(GDRIVE_SERVICE_ACCOUNT_FILE)
        if sa_path.exists():
            try:
                scopes = [
                    'https://www.googleapis.com/auth/drive.file',
                    'https://www.googleapis.com/auth/drive'
                ]
                credentials = service_account.Credentials.from_service_account_file(
                    str(sa_path), scopes=scopes
                )
                self.drive_service = build('drive', 'v3', credentials=credentials)
                self.storage_mode = "gdrive"
                self.auth_type = "service_account"
                self.init_error = None
                logger.info(f"Google Drive service account initialized from {sa_path}")
                return
            except Exception as e:
                self.init_error = f"Ошибка инициализации Service Account: {str(e)}"
                logger.warning(self.init_error)

        # Fallback to local
        self.storage_mode = "local"
        self.auth_type = "none"
        if not self.init_error:
            self.init_error = "Ключ Google Drive пока не настроен. Активен локальный режим."

    def test_upload(self) -> Dict[str, Any]:
        """
        Runs a diagnostic probe on the configured Google Drive folder.
        Attempts to read folder info, create a 1-byte probe file, and delete it.
        """
        if not self.drive_service:
            return {
                "success": False,
                "error_type": "NOT_CONNECTED",
                "message": self.init_error or "Google Drive API не инициализирован"
            }

        folder_id = GDRIVE_FOLDER_ID.strip()
        try:
            # 1. Check folder read access
            folder = self.drive_service.files().get(
                fileId=folder_id,
                fields='id, name, capabilities, owners',
                supportsAllDrives=True
            ).execute()
            folder_name = folder.get('name', 'KiberOneHW')
            owners = folder.get('owners', [])
            owner_email = owners[0].get('emailAddress') if owners else "Google Workspace"

            # 2. Verify write and delete access
            probe_content = b"KIBERone drive connection verified"
            media = MediaIoBaseUpload(io.BytesIO(probe_content), mimetype='text/plain', resumable=False)
            file_metadata = {
                'name': '___kiberone_connection_check.txt',
                'parents': [folder_id]
            }

            res = self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink',
                supportsAllDrives=True
            ).execute()

            probe_file_id = res.get('id')

            # 3. Clean up probe file
            try:
                self.drive_service.files().delete(fileId=probe_file_id, supportsAllDrives=True).execute()
            except Exception as del_err:
                logger.warning(f"Could not delete probe file {probe_file_id}: {del_err}")

            self.last_upload_error = None
            return {
                "success": True,
                "folder_name": folder_name,
                "folder_id": folder_id,
                "owner_email": owner_email,
                "auth_type": self.auth_type,
                "message": f"Тест успешен! Папка '{folder_name}' доступна для прямой загрузки файлов."
            }

        except Exception as e:
            err_str = str(e)
            self.last_upload_error = err_str
            logger.error(f"Google Drive diagnostic test failed: {err_str}")

            if "storageQuotaExceeded" in err_str:
                return {
                    "success": False,
                    "error_type": "QUOTA_EXCEEDED",
                    "folder_id": folder_id,
                    "auth_type": self.auth_type,
                    "message": (
                        "Ошибка квоты Google Drive (storageQuotaExceeded): "
                        "Сервисные аккаунты Google Cloud (@...iam.gserviceaccount.com) имеют квоту 0 байт на личных дисках (@gmail.com). "
                        "Для обычного Google Drive загружайте файлы от имени владельца через OAuth 2.0 (token.json), "
                        "либо используйте 'Общий диск' Google Workspace."
                    ),
                    "raw_error": err_str
                }

            return {
                "success": False,
                "error_type": "API_ERROR",
                "folder_id": folder_id,
                "auth_type": self.auth_type,
                "message": f"Ошибка Google Drive API: {err_str}",
                "raw_error": err_str
            }

    def get_status(self) -> Dict[str, Any]:
        """Returns the current storage configuration, detailed status, and deduplication metrics."""
        token_path = Path(BASE_DIR) / "token.json"
        sa_path = Path(GDRIVE_SERVICE_ACCOUNT_FILE)
        oauth_client_path = Path(GDRIVE_OAUTH_CREDENTIALS_FILE)

        return {
            "mode": self.storage_mode,
            "is_gdrive": self.storage_mode == "gdrive",
            "auth_type": self.auth_type,
            "has_token": token_path.exists(),
            "service_account_exists": sa_path.exists(),
            "oauth_client_exists": oauth_client_path.exists(),
            "service_account_email": GDRIVE_SERVICE_ACCOUNT_EMAIL,
            "status_message": (
                "Google Drive подключен через OAuth (квота аккаунта активна)" if self.auth_type == "oauth"
                else "Google Drive подключен через Service Account (квота 0 байт на личных дисках)" if self.auth_type == "service_account"
                else self.init_error or "Локальный режим"
            ),
            "folder_id": GDRIVE_FOLDER_ID or "10Mgxt-wQU26xs_ubKdLQEXbitPtHVkkt",
            "last_upload_error": self.last_upload_error,
            "dedup_stats": {
                "files_deduplicated": self._stats.get("files_deduplicated", 0),
                "bytes_saved": self._stats.get("bytes_saved", 0),
                "cache_entries": len(self._cache),
                "enabled": True
            }
        }

    async def upload_file(self, upload_file: UploadFile) -> Dict[str, Any]:
        """
        Uploads a file with smart Google Drive deduplication.
        If an identical file (by MD5 hash) already exists in the target folder or cache,
        the existing file link is reused immediately. This prevents duplication,
        saves storage quota, and provides instant response.
        """
        content = await upload_file.read()
        file_size = len(content)
        original_filename = upload_file.filename or "file"
        content_md5 = hashlib.md5(content).hexdigest()

        # 1. OPTIMIZATION: Check local persistent deduplication cache
        if content_md5 in self._cache:
            cached_entry = dict(self._cache[content_md5])
            self._stats["files_deduplicated"] += 1
            self._stats["bytes_saved"] += file_size
            self._save_cache()
            logger.info(
                f"[Deduplication] Instant hit for '{original_filename}' (MD5: {content_md5}). "
                f"Reusing {cached_entry.get('storage_type')} file {cached_entry.get('file_id')}. Saved {file_size} bytes."
            )
            cached_entry["deduplicated"] = True
            cached_entry["file_name"] = original_filename
            return cached_entry

        # 2. Check directly on Google Drive by appProperties (md5) in target folder
        folder_id = GDRIVE_FOLDER_ID.strip()
        if self.storage_mode == "gdrive" and self.drive_service and folder_id:
            try:
                query = f"'{folder_id}' in parents and appProperties has {{ key='md5' and value='{content_md5}' }} and trashed = false"
                res = self.drive_service.files().list(
                    q=query,
                    fields="files(id, name, webViewLink, webContentLink, size)",
                    supportsAllDrives=True
                ).execute()
                existing_files = res.get("files", [])
                if existing_files:
                    ex = existing_files[0]
                    file_id = ex.get("id")
                    web_view_link = ex.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"
                    download_url = ex.get("webContentLink") or web_view_link
                    
                    entry = {
                        "storage_type": "gdrive",
                        "file_id": file_id,
                        "file_name": original_filename,
                        "file_size": int(ex.get("size") or file_size),
                        "file_url": web_view_link,
                        "download_url": download_url,
                        "deduplicated": True
                    }
                    self._cache[content_md5] = entry
                    self._stats["files_deduplicated"] += 1
                    self._stats["bytes_saved"] += file_size
                    self._save_cache()
                    logger.info(
                        f"[Google Drive Cloud Deduplication] Found existing file on Drive (ID: {file_id}, MD5: {content_md5}). "
                        f"Reused! Saved {file_size} bytes."
                    )
                    return entry
            except Exception as search_err:
                logger.warning(f"Google Drive deduplication search error (continuing with upload): {search_err}")

        # 3. New file: Upload to Google Drive
        if self.storage_mode == "gdrive" and self.drive_service:
            try:
                file_metadata = {
                    'name': f"KIBERone_{original_filename}",
                    'appProperties': {'md5': content_md5}
                }
                if folder_id:
                    file_metadata['parents'] = [folder_id]

                media = MediaIoBaseUpload(
                    io.BytesIO(content),
                    mimetype=upload_file.content_type or 'application/octet-stream',
                    resumable=True
                )

                g_file = self.drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id, name, webViewLink, webContentLink, md5Checksum',
                    supportsAllDrives=True
                ).execute()

                file_id = g_file.get('id')
                
                # Make file readable to anyone with link (public read for students/tutors)
                try:
                    self.drive_service.permissions().create(
                        fileId=file_id,
                        body={'type': 'anyone', 'role': 'reader'},
                        fields='id',
                        supportsAllDrives=True
                    ).execute()
                except Exception as perm_err:
                    logger.warning(f"Could not set public permission on Drive file {file_id}: {perm_err}")

                web_view_link = g_file.get('webViewLink') or f"https://drive.google.com/file/d/{file_id}/view"
                download_url = g_file.get('webContentLink') or web_view_link
                
                entry = {
                    "storage_type": "gdrive",
                    "file_id": file_id,
                    "file_name": original_filename,
                    "file_size": file_size,
                    "file_url": web_view_link,
                    "download_url": download_url,
                    "deduplicated": False
                }

                # Store in dedup cache
                self._cache[content_md5] = entry
                self._save_cache()

                self.last_upload_status = {"success": True, "file_id": file_id}
                self.last_upload_error = None

                logger.info(f"Successfully uploaded {original_filename} to Google Drive (ID: {file_id}, MD5: {content_md5})")
                return entry

            except Exception as e:
                self.last_upload_error = str(e)
                logger.error(f"Google Drive upload failed, falling back to local: {e}")

        # 4. Local storage fallback (also deduplicated locally)
        safe_prefix = uuid.uuid4().hex[:8]
        safe_name = f"{safe_prefix}_{original_filename.replace(' ', '_')}"
        local_path = UPLOAD_DIR / safe_name
        
        with open(local_path, "wb") as f:
            f.write(content)

        entry = {
            "storage_type": "local",
            "file_id": safe_name,
            "file_name": original_filename,
            "file_size": file_size,
            "file_url": f"/uploads/{safe_name}",
            "download_url": f"/uploads/{safe_name}",
            "deduplicated": False,
            "warning": f"Сохранено локально: {self.last_upload_error}" if self.last_upload_error else None
        }
        self._cache[content_md5] = entry
        self._save_cache()

        logger.info(f"Saved {original_filename} to local storage fallback at {local_path}")
        return entry


# Singleton storage instance
storage_service = StorageService()
