import hmac
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

security = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=30),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.teammate_secret_key, algorithm=ALGORITHM)


def verify_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.teammate_secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
):
    if settings.teammate_secret_key == "change-me" or not settings.teammate_secret_key:
        return None

    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    payload = verify_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
):
    """Returns user payload if authenticated, None if no auth header."""
    if credentials is None:
        return None
    return verify_token(credentials.credentials)


def verify_webhook_signature(secret: str, payload: bytes, signature: str) -> bool:
    import hashlib
    mac = hmac.new(secret.encode(), payload, hashlib.sha256)
    expected = f"sha256={mac.hexdigest()}"
    return hmac.compare_digest(expected, signature)
