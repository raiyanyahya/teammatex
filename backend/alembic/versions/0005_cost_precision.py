"""Widen cost columns to fractional cents

Real per-call LLM costs for cheap models are sub-cent; storing them as integer
cents truncated every such cost to zero. Switch cost_log.cost_cents and
audit_log.estimated_cost_cents to numeric(14,6) so fractional cents survive.

Revision ID: 0005_cost_precision
Revises: 0004_concepts
Create Date: 2026-05-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_cost_precision"
down_revision: Union[str, None] = "0004_concepts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("cost_log", "cost_cents",
                    type_=sa.Numeric(14, 6),
                    existing_type=sa.Integer(),
                    existing_nullable=False,
                    server_default=None)
    op.alter_column("audit_log", "estimated_cost_cents",
                    type_=sa.Numeric(14, 6),
                    existing_type=sa.Integer(),
                    existing_nullable=True)


def downgrade() -> None:
    op.alter_column("cost_log", "cost_cents",
                    type_=sa.Integer(),
                    existing_type=sa.Numeric(14, 6),
                    existing_nullable=False)
    op.alter_column("audit_log", "estimated_cost_cents",
                    type_=sa.Integer(),
                    existing_type=sa.Numeric(14, 6),
                    existing_nullable=True)
