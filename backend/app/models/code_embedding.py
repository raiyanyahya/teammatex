from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

try:
    from pgvector.sqlalchemy import Vector
    _HAS_PGVECTOR = True
except ImportError:
    Vector = None  # type: ignore
    _HAS_PGVECTOR = False


class CodeEmbedding(Base):
    __tablename__ = "code_embeddings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str] = mapped_column(String(1024))
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    language: Mapped[str | None] = mapped_column(String(50))
    entity_name: Mapped[str | None] = mapped_column(String(255))

    if _HAS_PGVECTOR:
        embedding = mapped_column(Vector(1536))  # type: ignore
