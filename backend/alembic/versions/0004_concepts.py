"""Add concepts table for LLM-extracted Knowledge cards

Revision ID: 0004_concepts
Revises: 0003_code_embeddings_repo_id
Create Date: 2026-05-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_concepts"
down_revision: str | None = "0003_code_embeddings_repo_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "concepts",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("repo_id", sa.UUID(), sa.ForeignKey("repos.id"), nullable=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("cat", sa.String(20), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("files", sa.Integer, nullable=False, server_default="0"),
        sa.Column("refs", sa.Integer, nullable=False, server_default="0"),
        sa.Column("experts", sa.JSON, nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generator_model", sa.String(120), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("repo_id", "name", name="uq_concept_repo_name"),
    )
    op.create_index("idx_concepts_repo", "concepts", ["repo_id"])
    op.create_index("idx_concepts_cat", "concepts", ["cat"])


def downgrade() -> None:
    op.drop_index("idx_concepts_cat", table_name="concepts")
    op.drop_index("idx_concepts_repo", table_name="concepts")
    op.drop_table("concepts")
