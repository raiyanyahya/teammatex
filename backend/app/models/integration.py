from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class Integration(Base, UUIDMixin):
    __tablename__ = "integrations"

    provider: Mapped[str] = mapped_column(String(50), unique=True)
    credentials_encrypted: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    webhook_secret: Mapped[str | None] = mapped_column(String(255))
    config: Mapped[dict | None] = mapped_column(JSON)
