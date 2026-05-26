"""Add code_embeddings table for pgvector

Revision ID: 0002_code_embeddings
Revises: 0001_initial
Create Date: 2026-05-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from app.config import settings
from app.services.knowledge.embedding_schema import expected_dim

# Match the dimension the configured embedding model emits (local=384, openai=1536).
# Hardcoding 1536 silently broke the local default; the onboarding pipeline also
# self-corrects an existing table whose dimension drifts from the active model.
_EMBED_DIM = expected_dim(settings.embedding_provider)


revision: str = "0002_code_embeddings"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "code_embeddings",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(_EMBED_DIM)),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(50)),
        sa.Column("language", sa.String(50)),
        sa.Column("entity_name", sa.String(255)),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("idx_code_embeddings_file", "code_embeddings", ["file_path"])
    op.create_index("idx_code_embeddings_entity", "code_embeddings", ["entity_type", "language"])


def downgrade() -> None:
    op.drop_table("code_embeddings")
