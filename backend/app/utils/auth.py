import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime, timedelta

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
        "exp": datetime.now(UTC) + timedelta(days=30),
        "iat": datetime.now(UTC),
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
        is_admin=True,
    )
    db.add(admin)
    await db.commit()

    # Never print the password: container logs are commonly shipped to
    # aggregation where any operator/service could read them. Write it to an
    # owner-only file (0600) instead and log just a pointer. The API's
    # first-run response still returns it once for the initial login.
    cred_path = os.getenv("FIRST_RUN_CRED_PATH", "/data/first-run-admin-password")
    written_to: str | None = None
    try:
        # O_CREAT with mode 0o600 so the file is never briefly world-readable;
        # chmod as well in case it already existed from a prior aborted run.
        fd = os.open(cred_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(password + "\n")
        os.chmod(cred_path, 0o600)
        written_to = cred_path
    except OSError:
        written_to = None

    print(f"\n{'='*50}")
    print("  TeammateX first run")
    print("  Default admin created:")
    print("  Email:    admin@teammatex.local")
    if written_to:
        print(f"  Password written to: {written_to} (mode 0600)")
        print(f"  Retrieve it with:    docker compose exec api cat {written_to}")
    else:
        print("  Password: fetch it from the first-run API response (/api/auth/first-run).")
    print("  Change this password after logging in, then delete the file above.")
    print(f"{'='*50}\n")

    return True, password
