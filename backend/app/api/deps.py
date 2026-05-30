"""Shared FastAPI dependencies — the API auth gate.

Every data/mutation router depends on `require_user`, so an unauthenticated
caller gets 401 instead of free read/write/delete access. Auth travels as an
HttpOnly `tmx_token` cookie (set at login, sent automatically by the browser on
same-origin calls) or, for programmatic clients, an `Authorization: Bearer <jwt>`
header. Both carry the same JWT minted by app.utils.auth.create_token.
"""
from fastapi import HTTPException, Request

from app.config import settings
from app.utils.auth import decode_token

AUTH_COOKIE = "tmx_token"


async def require_user(request: Request) -> dict:
    """Authenticate via the tmx_token cookie or a Bearer header; 401 otherwise.
    Returns the decoded JWT payload (``sub``/``email``)."""
    # Only bypass when auth is entirely unconfigured (no signing key at all).
    # We do NOT bypass on the "change-me" default: the gate must still enforce so
    # an operator running on the default isn't silently wide open — that weak key
    # is a separate hardening issue (set a strong TEAMMATEX_SECRET_KEY).
    if not settings.teammate_secret_key:
        return {"sub": "anonymous"}

    token = request.cookies.get(AUTH_COOKIE)
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):  # explicit header wins over the cookie
        token = auth[7:]

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload
