"""Add uploads + notepad tables

Per-user file uploads (metadata; bytes live on the uploads_data volume) and a
single always-saved scratchpad per user.

Revision ID: 0006_uploads_and_notepad
Revises: 0005_cost_precision
Create Date: 2026-06-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_uploads_and_notepad"
down_revision: str | None = "0005_cost_precision"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "uploads",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("stored_path", sa.String(length=1024), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_uploads_owner_id", "uploads", ["owner_id"])

    op.create_table(
        "notepad",
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("owner_id"),
    )


def downgrade() -> None:
    op.drop_table("notepad")
    op.drop_index("ix_uploads_owner_id", table_name="uploads")
    op.drop_table("uploads")
