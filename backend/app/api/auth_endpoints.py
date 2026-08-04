from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AUTH_COOKIE, require_admin
from app.db.session import get_db
from app.models.user import User
from app.utils.auth import (
    create_token,
    decode_token,
    first_run_check,
    hash_password,
    verify_password,
)
from app.utils.ratelimit import SlidingWindowLimiter

router = APIRouter(prefix="/auth", tags=["auth"])

# 30 days, matching the JWT exp in app.utils.auth.create_token.
_COOKIE_MAX_AGE = 30 * 24 * 3600

# Throttle failed logins: per-account is the strict guarantee (5 bad tries per
# 15 min); the per-source-IP net is looser because behind a proxy many users
# share one peer IP. Successful logins clear the counters.
_login_email_limiter = SlidingWindowLimiter(max_events=5, window_seconds=900)
_login_ip_limiter = SlidingWindowLimiter(max_events=50, window_seconds=900)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _set_auth_cookie(response: Response, token: str) -> None:
    """Set the session token as an HttpOnly cookie so the browser sends it on
    every same-origin API call automatically. SameSite=Lax blocks the cookie on
    cross-site POSTs (CSRF mitigation). The Secure flag is controlled by
    settings.cookie_secure: off by default so plain-http localhost works, but set
    COOKIE_SECURE=true in production so the session cookie never leaves over http."""
    from app.config import settings

    response.set_cookie(
        AUTH_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=_COOKIE_MAX_AGE,
        path="/",
    )


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str = Field(min_length=8)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class FirstRunResponse(BaseModel):
    is_first_run: bool
    default_password: str | None = None
    message: str


@router.get("/first-run", response_model=FirstRunResponse)
async def check_first_run(db: AsyncSession = Depends(get_db)):
    is_first, password = await first_run_check(db)
    if is_first and password:
        return FirstRunResponse(
            is_first_run=True,
            default_password=password,
            message="Default admin created. Use the password above to log in. Change it immediately.",
        )
    return FirstRunResponse(
        is_first_run=False,
        message="Setup already completed.",
    )


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    email_key = f"email:{payload.email.lower()}"
    ip_key = f"ip:{_client_ip(request)}"
    if _login_email_limiter.is_blocked(email_key) or _login_ip_limiter.is_blocked(ip_key):
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Try again in a few minutes.",
        )

    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password or ""):
        _login_email_limiter.record(email_key)
        _login_ip_limiter.record(ip_key)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    _login_email_limiter.reset(email_key)
    _login_ip_limiter.reset(ip_key)
    token = create_token(str(user.id), user.email)
    _set_auth_cookie(response, token)

    return {
        "token": token,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "github_username": user.github_username,
        },
    }


@router.post("/register", status_code=201)
async def register(
    payload: RegisterRequest,
    _admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # Admin-only: open, unauthenticated registration would let anyone create an
    # account and then drive the agent (shell, plugin install, secret reads).
    # The first-run bootstrap creates the initial admin; admins invite the rest.
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=payload.email,
        name=payload.name,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
        },
    }


@router.post("/logout")
async def logout(response: Response):
    """Clear the auth cookie. The client also drops its localStorage token."""
    response.delete_cookie(AUTH_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")

    payload = decode_token(auth_header[7:])
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "github_username": user.github_username,
    }


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")

    token_data = decode_token(auth_header[7:])
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == token_data["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(payload.current_password, user.hashed_password or ""):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    user.hashed_password = hash_password(payload.new_password)
    await db.commit()

    return {"message": "Password changed successfully"}
