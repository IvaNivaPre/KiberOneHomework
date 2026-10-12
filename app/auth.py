import os
import hmac
import hashlib
import json
import base64
import time
from typing import Optional
from fastapi import Request, HTTPException, status, Depends
from sqlalchemy.orm import Session
from app.config import SECRET_KEY, COOKIE_NAME
from app.database import get_db
from app.models import User

# --- Password Hashing with PBKDF2 ---

def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with a random salt."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    salt_b64 = base64.b64encode(salt).decode("ascii")
    dk_b64 = base64.b64encode(dk).decode("ascii")
    return f"pbkdf2:sha256:100000${salt_b64}${dk_b64}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against stored hash."""
    try:
        parts = hashed_password.split("$")
        if len(parts) != 3:
            return False
        salt = base64.b64decode(parts[1])
        expected_dk = base64.b64decode(parts[2])
        actual_dk = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, 100_000)
        return hmac.compare_digest(expected_dk, actual_dk)
    except Exception:
        return False


# --- Token Management (Signed JSON Token) ---

def create_access_token(user_id: int, username: str, role: str, expires_in_days: int = 7) -> str:
    """Creates an HMAC-signed token stored securely in cookies."""
    exp = int(time.time()) + (expires_in_days * 86400)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "exp": exp
    }
    payload_json = json.dumps(payload, separators=(',', ':'))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode('utf-8')).decode('ascii').rstrip('=')
    
    signature = hmac.new(
        SECRET_KEY.encode('utf-8'),
        payload_b64.encode('utf-8'),
        hashlib.sha256
    ).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode('ascii').rstrip('=')
    
    return f"{payload_b64}.{sig_b64}"


def decode_access_token(token: str) -> Optional[dict]:
    """Verifies token HMAC signature and expiration."""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, sig_b64 = parts
        
        # Verify HMAC
        expected_sig = hmac.new(
            SECRET_KEY.encode('utf-8'),
            payload_b64.encode('utf-8'),
            hashlib.sha256
        ).digest()
        
        # Add padding back for urlsafe_b64decode
        sig_padding = 4 - (len(sig_b64) % 4)
        if sig_padding != 4:
            sig_b64 += "=" * sig_padding
            
        actual_sig = base64.urlsafe_b64decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
            
        # Decode JSON payload
        p_padding = 4 - (len(payload_b64) % 4)
        if p_padding != 4:
            payload_b64 += "=" * p_padding
            
        payload_json = base64.urlsafe_b64decode(payload_b64).decode('utf-8')
        payload = json.loads(payload_json)
        
        # Check expiry
        if payload.get("exp", 0) < time.time():
            return None
            
        return payload
    except Exception:
        return None


# --- FastAPI User Dependencies ---

def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """Get current user from cookie, returning None if not authenticated."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    data = decode_access_token(token)
    if not data or "sub" not in data:
        return None
    user = db.query(User).filter(User.id == data["sub"]).first()
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Requires authentication. Redirects or raises 401."""
    user = get_current_user_optional(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Необходима авторизация",
            headers={"Location": "/login"}
        )
    return user


def require_tutor(current_user: User = Depends(get_current_user)) -> User:
    """Requires 'tutor' or 'admin' role."""
    if current_user.role not in ["tutor", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ разрешен только тьюторам и администраторам"
        )
    return current_user


def require_student(current_user: User = Depends(get_current_user)) -> User:
    """Requires 'student' role."""
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ разрешен только ученикам"
        )
    return current_user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Requires 'admin' role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ разрешен только администратору"
        )
    return current_user

