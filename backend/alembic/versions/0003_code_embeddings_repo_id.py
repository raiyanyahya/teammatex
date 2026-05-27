"""Add repo_id to code_embeddings (repo-scoped search + cleanup)

Revision ID: 0003_code_embeddings_repo_id
Revises: 0002_code_embeddings
Create Date: 2026-05-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_code_embeddings_repo_id"
down_revision: Union[str, None] = "0002_code_embeddings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable: rows written before repo-scoping have no repo_id (they predate the
    # column and their relative file_paths can't be attributed to a repo). New
    # onboarding populates it; scoped search/delete simply ignore the legacy rows.
    op.add_column("code_embeddings", sa.Column("repo_id", sa.String(36), nullable=True))
    op.create_index("idx_code_embeddings_repo", "code_embeddings", ["repo_id"])


def downgrade() -> None:
    op.drop_index("idx_code_embeddings_repo", table_name="code_embeddings")
    op.drop_column("code_embeddings", "repo_id")
