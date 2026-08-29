import base64, hashlib
from datetime import datetime, timedelta, timezone
from cryptography.fernet import Fernet
from jose import jwt, JWTError
from fastapi import HTTPException, Header
from .config import settings

ALGO = "HS256"

def _fernet():
    if settings.token_encryption_key:
        key = settings.token_encryption_key.encode()
    else:
        digest = hashlib.sha256(settings.secret_key.encode()).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)

def encrypt_token(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()

def decrypt_token(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()

def create_access_token(username: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode({"sub": username, "exp": exp}, settings.secret_key, algorithm=ALGO)

def current_user(authorization: str = Header(default="")) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Not authenticated")
    token = authorization[7:]
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGO])
        return payload.get("sub") or "admin"
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")
