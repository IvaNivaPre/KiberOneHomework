"""
KIBERone - Скрипт первичной инициализации аккаунта администратора.

Использование:
1. Интерактивный режим:
   python init_admin.py

2. Передача параметров через аргументы командной строки:
   python init_admin.py --username admin --password secretpassword --name "Иванова Анна"
"""

import sys
import argparse
import getpass
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from app.database import engine, Base, SessionLocal
from app.models import User
from app.auth import hash_password


def init_administrator(username: str, password: str, full_name: str):
    # Ensure tables are created
    Base.metadata.create_all(bind=engine)
    
    clean_username = username.strip().lower()
    clean_name = full_name.strip()
    
    if not clean_username:
        print("[ОШИБКА] Логин администратора не может быть пустым.")
        return False
        
    if not password or len(password.strip()) < 4:
        print("[ОШИБКА] Пароль должен содержать не менее 4 символов.")
        return False

    db = SessionLocal()
    try:
        existing_user = db.query(User).filter(User.username == clean_username).first()
        if existing_user:
            existing_user.password_hash = hash_password(password.strip())
            existing_user.plain_password = password.strip()
            existing_user.full_name = clean_name or existing_user.full_name
            existing_user.role = "admin"
            db.commit()
            print("--------------------------------------------------")
            print("[УСПЕХ] Существующий аккаунт обновлен до Администратора.")
            print(f"Логин: {clean_username}")
            print(f"ФИО:   {existing_user.full_name}")
            print(f"Роль:  admin")
            print("--------------------------------------------------")
        else:
            new_admin = User(
                username=clean_username,
                password_hash=hash_password(password.strip()),
                plain_password=password.strip(),
                full_name=clean_name or "Администратор KIBERone",
                role="admin"
            )
            db.add(new_admin)
            db.commit()
            print("--------------------------------------------------")
            print("[УСПЕХ] Аккаунт администратора успешно создан!")
            print(f"Логин: {clean_username}")
            print(f"ФИО:   {new_admin.full_name}")
            print(f"Роль:  admin")
            print("--------------------------------------------------")
            
        print("Теперь администратор может войти в систему по адресу:")
        print("http://localhost:8000/login")
        print("и добавлять преподавателей, группы и учеников через веб-интерфейс.")
        return True
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Первичная инициализация администратора KIBERone")
    parser.add_argument("--username", "-u", type=str, help="Логин администратора (например: admin)")
    parser.add_argument("--password", "-p", type=str, help="Пароль администратора")
    parser.add_argument("--name", "-n", type=str, help="ФИО администратора")

    args = parser.parse_args()

    # If parameters passed via flags
    if args.username and args.password:
        name = args.name or "Администратор KIBERone"
        init_administrator(args.username, args.password, name)
        return

    # Interactive mode
    print("==================================================")
    print("  KIBERone — Первичная инициализация Администратора")
    print("==================================================")
    print("Этот скрипт создает главную учетную запись администратора.")
    print("Через этот аккаунт администратор сможет настраивать школу,")
    print("добавлять преподавателей, группы и учеников.\n")

    default_username = "admin"
    username_input = input(f"Введите логин администратора [{default_username}]: ").strip()
    username = username_input if username_input else default_username

    default_name = "Администратор KIBERone"
    name_input = input(f"Введите ФИО администратора [{default_name}]: ").strip()
    full_name = name_input if name_input else default_name

    while True:
        try:
            password = getpass.getpass("Введите пароль для входа: ").strip()
        except Exception:
            password = input("Введите пароль для входа: ").strip()

        if not password or len(password) < 4:
            print("[!] Пароль должен быть не короче 4 символов. Попробуйте снова.")
            continue

        try:
            confirm = getpass.getpass("Подтвердите пароль: ").strip()
        except Exception:
            confirm = input("Подтвердите пароль: ").strip()

        if password != confirm:
            print("[!] Пароли не совпадают. Попробуйте снова.\n")
            continue
        break

    init_administrator(username, password, full_name)


if __name__ == "__main__":
    main()
