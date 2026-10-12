"""
KIBERone - Google Drive OAuth 2.0 Setup Utility
Этот скрипт позволяет в 1 клик авторизовать ваш Google Drive с персональной квотой аккаунта,
устраняя ошибку 'Service Accounts do not have storage quota' (storageQuotaExceeded).
"""

import sys
import io
import os
from pathlib import Path

# Fix Windows console encoding for Russian text
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"
FOLDER_ID = "10Mgxt-wQU26xs_ubKdLQEXbitPtHVkkt"
SCOPES = ["https://www.googleapis.com/auth/drive"]


def print_banner():
    print("=" * 65)
    print("  KIBERone — Подключение Google Drive через OAuth 2.0")
    print("=" * 65)
    print("Почему это нужно:")
    print("Сервисные аккаунты Google Cloud (@...iam.gserviceaccount.com)")
    print("имеют 0 МБ дискового пространства и НЕ могут создавать файлы на")
    print("личных дисках (@gmail.com). Авторизация через OAuth подключает")
    print("Google Drive от имени владельца папки с персональной квотой аккаунта!\n")


def instructions_for_credentials():
    print("[!] Файл 'credentials.json' не найден в проекте.\n")
    print("Инструкция по получению credentials.json (занимает 1 минуту):")
    print("1. Откройте Google Cloud Console:")
    print("   https://console.cloud.google.com/apis/credentials?project=kiberone-hw\n")
    print("2. Если еще не настроен экран согласия OAuth:")
    print("   Перейдите в 'OAuth consent screen' -> выберите 'External' ->")
    print("   Укажите название приложения 'KiberOne HW' и вашу почту -> Сохранить.\n")
    print("3. Нажмите '+ CREATE CREDENTIALS' (Создать учетные данные) ->")
    print("   Выберите 'OAuth client ID' (Идентификатор клиента OAuth).\n")
    print("4. Тип приложения: выберите 'Desktop app' (Приложение для ПК)")
    print("   (или 'Web application', добавив redirect URI http://localhost:8000/tutor/settings/oauth/callback).\n")
    print("5. Нажмите 'Create' и скачайте JSON-файл (кнопка 'Download JSON').\n")
    print(f"6. Переименуйте скачанный файл в 'credentials.json' и положите в:")
    print(f"   {BASE_DIR / 'credentials.json'}")
    print("   (или загрузите через страницу Настроек в браузере: http://localhost:8000/tutor/settings)\n")
    print("7. Затем снова запустите: python setup_oauth.py")
    print("=" * 65)


def run_oauth():
    print_banner()

    if not CREDENTIALS_FILE.exists():
        instructions_for_credentials()
        return False

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseUpload
    except ImportError:
        print("[x] Не установлена библиотека google_auth_oauthlib. Установите: pip install google-auth-oauthlib")
        return False

    print(f"[+] Найден {CREDENTIALS_FILE.name}! Запуск браузера для авторизации Google...")
    print("-----------------------------------------------------------------")
    print("ВАЖНЫЕ ПОДСКАЗКИ ПРИ ВХОДЕ В БРАУЗЕРЕ:")
    print("1. Если появится экран 'Google hasn't verified this app' (Приложение не проверено):")
    print("   Нажмите внизу слева: 'Advanced' (Дополнительно) ->")
    print("   'Go to KiberOne HW (unsafe)' (Перейти на страницу...) -> 'Continue' (Продолжить).")
    print("2. Если появится ошибка '403: access_denied':")
    print("   Нужно добавить вашу почту в 'Test users' (Тестовые пользователи):")
    print("   https://console.cloud.google.com/apis/credentials/consent?project=kiberone-hw")
    print("-----------------------------------------------------------------\n")

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS_FILE),
            scopes=SCOPES
        )
        creds = flow.run_local_server(port=0)

        # Save credentials to token.json
        with open(TOKEN_FILE, "w", encoding="utf-8") as token_out:
            token_out.write(creds.to_json())

        print(f"\n[OK] Токен успешно получен и сохранен в: {TOKEN_FILE.name}!")

        # Test upload
        print(f"\n[*] Выполняем проверочный тест загрузки в папку KiberOneHW (ID: {FOLDER_ID})...")
        service = build('drive', 'v3', credentials=creds)

        meta = {
            'name': '___kiberone_oauth_probe.txt',
            'parents': [FOLDER_ID]
        }
        media = MediaIoBaseUpload(
            io.BytesIO(b"KIBERone OAuth connection confirmed"),
            mimetype='text/plain'
        )

        res = service.files().create(
            body=meta,
            media_body=media,
            fields='id, name, webViewLink',
            supportsAllDrives=True
        ).execute()

        test_file_id = res.get('id')
        print(f"[OK] Проверочный файл создан на Google Drive! ID: {test_file_id}")

        # Delete probe file
        try:
            service.files().delete(fileId=test_file_id, supportsAllDrives=True).execute()
            print("[OK] Проверочный файл удален.")
        except Exception:
            pass

        print("\n" + "=" * 65)
        print("  УСПЕХ! Google Drive полностью настроен и готов к работе!")
        print("  Теперь все ДЗ и материалы будут загружаться напрямую на Google Drive.")
        print("=" * 65)
        return True

    except Exception as e:
        print(f"\n[x] Ошибка при авторизации: {e}")
        return False


if __name__ == "__main__":
    run_oauth()
