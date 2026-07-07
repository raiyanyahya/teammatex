from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class User(Base, UUIDMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(1024))
    github_username: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Only admins can create other accounts and manage plugins. The first-run
    # bootstrap user is an admin; everyone else defaults to non-admin.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    hashed_password: Mapped[str | None] = mapped_column(String(255))
