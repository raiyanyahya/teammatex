from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.models.base import Base
from app.services.knowledge.embedding_schema import expected_dim

try:
    from pgvector.sqlalchemy import Vector

    _HAS_PGVECTOR = True
except ImportError:
    Vector = None  # type: ignore
    _HAS_PGVECTOR = False

_EMBED_DIM = expected_dim(settings.embedding_provider)


class CodeEmbedding(Base):
    __tablename__ = "code_embeddings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    repo_id: Mapped[str | None] = mapped_column(String(36), index=True)
    text: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str] = mapped_column(String(1024))
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    language: Mapped[str | None] = mapped_column(String(50))
    entity_name: Mapped[str | None] = mapped_column(String(255))

    if _HAS_PGVECTOR:
        embedding = mapped_column(Vector(_EMBED_DIM))  # type: ignore
