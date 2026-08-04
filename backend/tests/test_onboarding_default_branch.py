"""Onboarding persists the *detected* default branch back to the repo row.

Repos are created with the model default ("main") before the clone exists; the
REPO_DISCOVERY stage detects the real branch and must write it back, or auto-sync
(which pulls default_branch) silently targets a nonexistent branch.
"""

import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401 — register every table on Base.metadata
from app.config import settings
from app.models.base import Base
from app.models.repo import Repo
from app.services.onboarding.pipeline import _save_repo_default_branch


def _engine():
    return create_engine(settings.database_url.replace("+asyncpg", "+psycopg2"), pool_pre_ping=True)


def test_save_repo_default_branch_updates_row():
    eng = _engine()
    Base.metadata.create_all(eng)  # idempotent; ensure the repos table exists
    rid = None
    try:
        with Session(eng) as db:
            repo = Repo(
                github_url=f"https://github.com/x/{uuid.uuid4().hex}.git", local_name="dbtest"
            )
            db.add(repo)
            db.commit()
            rid = repo.id
            assert repo.default_branch == "main"  # the model default the bug left in place

        _save_repo_default_branch(rid, "master")

        with Session(eng) as db:
            repo = db.execute(select(Repo).where(Repo.id == rid)).scalar_one()
            assert repo.default_branch == "master"
    finally:
        if rid:
            with Session(eng) as db:
                r = db.get(Repo, rid)
                if r:
                    db.delete(r)
                    db.commit()
        eng.dispose()


def test_save_repo_default_branch_noop_on_empty():
    # Missing repo_id or empty branch must be a clean no-op, never a raise.
    _save_repo_default_branch("", "master")
    _save_repo_default_branch(str(uuid.uuid4()), "")
