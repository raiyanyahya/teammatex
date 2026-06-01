"""Verify all 22 models instantiate and have correct table names."""

import pytest
from sqlalchemy import inspect

from app.models.base import Base, UUIDMixin, TimestampMixin, utcnow
from app.models.user import User
from app.models.repo import Repo, RepoOnboardingState
from app.models.task import Task
from app.models.pr import PR
from app.models.conversation import Conversation, Message
from app.models.note import Note
from app.models.integration import Integration
from app.models.audit import AuditLog, Feedback, CostLog
from app.models.tech_debt import TechDebtItem
from app.models.dependency import DependencySnapshot
from app.models.permission import Permission
from app.models.trust import TrustLevel, TrustMetrics
from app.models.blocked import BlockedTask
from app.models.api_registry import APIRegistryEntry
from app.models.app_config import AppConfig
from app.models.code_embedding import CodeEmbedding
from app.models.concept import Concept


EXPECTED_TABLES = {
    "users", "repos", "repo_onboarding_state", "tasks", "prs",
    "conversations", "messages", "notes", "integrations",
    "audit_log", "feedback", "cost_log", "tech_debt_items",
    "dependency_snapshots", "permissions", "trust_level",
    "trust_metrics", "blocked_tasks", "api_registry", "app_config",
    "code_embeddings", "concepts", "uploads", "notepad",
}

ALL_MODELS = [
    User, Repo, RepoOnboardingState, Task, PR, Conversation, Message,
    Note, Integration, AuditLog, Feedback, CostLog, TechDebtItem,
    DependencySnapshot, Permission, TrustLevel, TrustMetrics,
    BlockedTask, APIRegistryEntry, AppConfig, CodeEmbedding, Concept,
]


class TestAllModels:
    def test_total_table_count(self, sqlite_engine, sqlite_session):
        # sqlite_session creates all tables on sqlite_engine (its side effect).
        inspector = inspect(sqlite_engine)
        tables = set(inspector.get_table_names())
        assert len(tables) == 24, f"Expected 24 tables, got {len(tables)}: {tables}"

    def test_all_tables_match_expected(self, sqlite_engine, sqlite_session):
        inspector = inspect(sqlite_engine)
        tables = set(inspector.get_table_names())
        assert tables == EXPECTED_TABLES, f"Missing: {EXPECTED_TABLES - tables}, Extra: {tables - EXPECTED_TABLES}"

    def test_all_models_instantiate(self, db_session):
        for model_cls in ALL_MODELS:
            instance = model_cls()
            assert hasattr(instance, "__tablename__"), f"{model_cls.__name__} missing __tablename__"

    def test_user_model(self, db_session):
        user = User(email="test@test.com", name="Test User")
        db_session.add(user)
        db_session.commit()
        assert user.id is not None
        assert user.email == "test@test.com"

    def test_repo_model_with_relationship(self, db_session):
        repo = Repo(github_url="https://github.com/test/repo", local_name="test-repo")
        db_session.add(repo)
        db_session.commit()

        state = RepoOnboardingState(repo_id=repo.id, stage="repo_discovery", status="completed")
        db_session.add(state)
        db_session.commit()

        assert state.repo_id == repo.id

    def test_task_pr_relationship(self, db_session):
        task = Task(title="Add feature", status="open")
        db_session.add(task)
        db_session.commit()

        pr = PR(task_id=task.id, repo_id="d0e45e5a-1234-4abc-9def-123456789abc", branch="teammatex/feature", title="Add feature")
        db_session.add(pr)
        db_session.commit()

        assert pr.task_id == task.id

    def test_conversation_message_relationship(self, db_session):
        conv = Conversation(owner_id="user-1", title="Test chat")
        db_session.add(conv)
        db_session.commit()

        msg = Message(conversation_id=conv.id, role="user", content="Hello")
        db_session.add(msg)
        db_session.commit()

        assert msg.conversation_id == conv.id

    def test_blocked_task_fk(self, db_session):
        user = User(email="blocker@test.com", name="Blocker")
        db_session.add(user)
        db_session.commit()

        task = Task(title="Blocked task", status="open")
        db_session.add(task)
        db_session.commit()

        blocked = BlockedTask(task_id=task.id, question="Which approach?", answered_by=user.id)
        db_session.add(blocked)
        db_session.commit()

        assert blocked.task_id == task.id
        assert blocked.answered_by == user.id

    def test_trust_level_constraint(self, db_session):
        trust = TrustLevel(level=0, level_name="Observer")
        db_session.add(trust)
        db_session.commit()

        invalid = TrustLevel(level=5, level_name="Invalid")

    def test_app_config_kv(self, db_session):
        config = AppConfig(key="test_key", value={"foo": "bar"})
        db_session.add(config)
        db_session.commit()

        assert config.value == {"foo": "bar"}

    def test_permission_model(self, db_session):
        perm = Permission(capability="read_code", enabled=True, description="Can read code")
        db_session.add(perm)
        db_session.commit()

        assert perm.capability == "read_code"

    def test_auth_model(self, db_session):
        from app.api.auth import create_access_token, verify_token

        token = create_access_token("user-1", "user@test.com")
        payload = verify_token(token)
        assert payload is not None
        assert payload["sub"] == "user-1"
        assert payload["email"] == "user@test.com"

        invalid = verify_token("bad.token.here")
        assert invalid is None

    def test_utcnow_returns_timezone_aware(self):
        dt = utcnow()
        assert dt.tzinfo is not None
