"""Scope conversations by owner_id (drop unused user_id FK)

Conversations were never persisted before this change, so dropping the unused
``user_id`` FK column loses no data. They now scope by ``owner_id`` (the caller's
JWT ``sub``, a free string) to match the uploads/notepad pattern and avoid the
uuid/FK friction of the old column.

Revision ID: 0007_conversation_owner
Revises: 0006_uploads_and_notepad
Create Date: 2026-06-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_conversation_owner"
down_revision: str | None = "0006_uploads_and_notepad"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_constraint("conversations_user_id_fkey", "conversations", type_="foreignkey")
    op.drop_column("conversations", "user_id")
    op.add_column(
        "conversations",
        sa.Column("owner_id", sa.String(length=64), nullable=False, server_default=""),
    )
    op.create_index("ix_conversations_owner_id", "conversations", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_conversations_owner_id", table_name="conversations")
    op.drop_column("conversations", "owner_id")
    op.add_column(
        "conversations",
        sa.Column("user_id", sa.UUID(), nullable=True),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    op.create_foreign_key(
        "conversations_user_id_fkey", "conversations", "users", ["user_id"], ["id"]
    )
