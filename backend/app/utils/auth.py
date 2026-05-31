import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select

from app.config import settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    return f"{salt}${pw_hash}"


def verify_password(plain: str, hashed: str) -> bool:
    if "$" not in hashed:
        return False
    salt, pw_hash = hashed.split("$", 1)
    computed = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), 100000).hex()
    return hmac.compare_digest(computed, pw_hash)


def create_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=30),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.teammate_secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.teammate_secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


def generate_default_password(length: int = 16) -> str:
    return secrets.token_urlsafe(length)


async def first_run_check(db) -> tuple[bool, str | None]:
    """Check if this is the first run. Returns (is_first_run, default_password)."""
    from app.models.user import User
    result = await db.execute(select(User).limit(1))
    existing = result.scalar_one_or_none()
    if existing:
        return False, None

    password = generate_default_password()
    admin = User(
        email="admin@teammatex.local",
        name="Admin",
        hashed_password=hash_password(password),
    )
    db.add(admin)
    await db.commit()

    print(f"\n{'='*50}")
    print(f"  TeammateX first run")
    print(f"  Default admin created:")
    print(f"  Email:    admin@teammatex.local")
    print(f"  Password: {password}")
    print(f"  Change this password after logging in.")
    print(f"{'='*50}\n")

    return True, password
