"""Add users.is_admin and gate privileged actions to admins

Registration and plugin management are admin-only (see app.api.deps.require_admin).
New column defaults to false. The bootstrap admin (admin@teammatex.local) is
promoted so existing single-admin deployments keep working; if that row is
absent, one existing user is promoted so a deployment is never left with no
admin. (The users table has no created_at, so the fallback orders by id.)

Revision ID: 0008_user_is_admin
Revises: 0007_conversation_owner
Create Date: 2026-07-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_user_is_admin"
down_revision: Union[str, None] = "0007_conversation_owner"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
    )
    # Promote the bootstrap admin so an existing deployment isn't locked out of
    # registration/plugin management after this migration.
    op.execute(
        "UPDATE users SET is_admin = true WHERE email = 'admin@teammatex.local'"
    )
    # Fallback: if there's no bootstrap admin but users exist, promote one so
    # there is always at least one admin. (No created_at column, so order by id.)
    op.execute(
        """
        UPDATE users SET is_admin = true
        WHERE id = (
            SELECT id FROM users
            WHERE is_admin = false
            ORDER BY id ASC
            LIMIT 1
        )
        AND NOT EXISTS (SELECT 1 FROM users WHERE is_admin = true)
        """
    )


def downgrade() -> None:
    op.drop_column("users", "is_admin")
