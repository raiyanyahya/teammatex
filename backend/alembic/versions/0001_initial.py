"""Initial schema — all tables

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("avatar_url", sa.String(1024), nullable=True),
        sa.Column("github_username", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "app_config",
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )

    op.create_table(
        "permissions",
        sa.Column("capability", sa.String(50), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("capability"),
    )

    op.create_table(
        "integrations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("credentials_encrypted", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("webhook_secret", sa.String(255), nullable=True),
        sa.Column("config", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider"),
    )

    op.create_table(
        "trust_level",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column("level_name", sa.String(50), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_by", sa.String(255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("level BETWEEN 0 AND 4", name="ck_trust_level_range"),
    )

    op.create_table(
        "trust_metrics",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pr_merge_rate", sa.Float(), nullable=True, server_default=sa.text("0.0")),
        sa.Column("pr_iteration_avg", sa.Float(), nullable=True, server_default=sa.text("0.0")),
        sa.Column("feedback_score", sa.Float(), nullable=True, server_default=sa.text("0.0")),
        sa.Column("question_quality", sa.Float(), nullable=True, server_default=sa.text("0.0")),
        sa.Column("test_pass_rate", sa.Float(), nullable=True, server_default=sa.text("0.0")),
        sa.Column("task_completion_rate", sa.Float(), nullable=True, server_default=sa.text("0.0")),
        sa.Column("overall_score", sa.Float(), nullable=True, server_default=sa.text("0.0")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "api_registry",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("allowed_methods", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("allowed_paths", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("rate_limit_per_hour", sa.Integer(), nullable=True),
        sa.Column("requires_approval", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("added_by", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=True, server_default=sa.text("'active'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "repos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("github_url", sa.String(1024), nullable=False),
        sa.Column("local_name", sa.String(255), nullable=False),
        sa.Column("default_branch", sa.String(255), nullable=True, server_default=sa.text("'main'")),
        sa.Column("language_stats", postgresql.JSONB(), nullable=True),
        sa.Column("clone_path", sa.String(1024), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "repo_onboarding_state",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("repo_id", sa.UUID(), nullable=False),
        sa.Column("stage", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=True, server_default=sa.text("'pending'")),
        sa.Column("progress", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_repo_onboarding_state_repo_id", "repo_onboarding_state", ["repo_id"])

    op.create_table(
        "tech_debt_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("repo_id", sa.UUID(), nullable=False),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=True, server_default=sa.text("'medium'")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=True, server_default=sa.text("'open'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tech_debt_items_repo_id", "tech_debt_items", ["repo_id"])

    op.create_table(
        "dependency_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("repo_id", sa.UUID(), nullable=False),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dependency_snapshots_repo_id", "dependency_snapshots", ["repo_id"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("source_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(50), nullable=True, server_default=sa.text("'open'")),
        sa.Column("priority", sa.String(20), nullable=True),
        sa.Column("assigned_to", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "prs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=True),
        sa.Column("repo_id", sa.UUID(), nullable=False),
        sa.Column("github_pr_number", sa.Integer(), nullable=True),
        sa.Column("branch", sa.String(255), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("status", sa.String(50), nullable=True, server_default=sa.text("'open'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prs_task_id", "prs", ["task_id"])
    op.create_index("ix_prs_repo_id", "prs", ["repo_id"])

    op.create_table(
        "blocked_tasks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=True, server_default=sa.text("'pending'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_by", sa.UUID(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["answered_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_blocked_tasks_task_id", "blocked_tasks", ["task_id"])

    op.create_table(
        "conversations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])

    op.create_table(
        "notes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", sa.String(255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("llm_calls", sa.Integer(), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_cents", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "feedback",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("pr_id", sa.UUID(), nullable=True),
        sa.Column("rating", sa.String(50), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["pr_id"], ["prs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "cost_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("call_type", sa.String(50), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column("tokens_out", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column("cost_cents", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("cost_log")
    op.drop_table("feedback")
    op.drop_table("audit_log")
    op.drop_table("notes")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("blocked_tasks")
    op.drop_table("prs")
    op.drop_table("tasks")
    op.drop_table("dependency_snapshots")
    op.drop_table("tech_debt_items")
    op.drop_table("repo_onboarding_state")
    op.drop_table("repos")
    op.drop_table("api_registry")
    op.drop_table("trust_metrics")
    op.drop_table("trust_level")
    op.drop_table("integrations")
    op.drop_table("permissions")
    op.drop_table("app_config")
    op.drop_table("users")
