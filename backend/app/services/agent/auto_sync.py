import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from structlog import get_logger

logger = get_logger(__name__)


class AutoSyncEngine:
    _instance: Optional["AutoSyncEngine"] = None
    _task: Optional[asyncio.Task] = None

    def __init__(self):
        self._running = False
        self._last_poll: dict[str, datetime] = {}

    @classmethod
    def get(cls) -> "AutoSyncEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def start_polling(self, interval_minutes: int = 15):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop(interval_minutes))
        logger.info("auto_sync_polling_started", interval_minutes=interval_minutes)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _poll_loop(self, interval_minutes: int):
        while self._running:
            try:
                await self._poll_all_repos()
            except Exception as e:
                logger.error("auto_sync_poll_failed", error=str(e)[:200])
            await asyncio.sleep(interval_minutes * 60)

    async def _poll_all_repos(self):
        from sqlalchemy import create_engine, select as _select
        from app.config import settings as _s
        from app.models.repo import Repo
        from app.services.knowledge.repo_manifest import RepoManifest
        from app.services.knowledge.incremental_graph import IncrementalGraphUpdater

        engine = create_engine(_s.database_url.replace("+asyncpg", "+psycopg2"), pool_pre_ping=True)
        try:
            from sqlalchemy.orm import Session
            with Session(engine) as db:
                repos = db.execute(_select(Repo).where(Repo.is_active == True)).scalars().all()
        finally:
            engine.dispose()

        for repo in repos:
            try:
                await self._sync_repo(repo)
            except Exception as e:
                logger.warning("auto_sync_repo_failed", repo=repo.local_name, error=str(e)[:100])

    async def _sync_repo(self, repo) -> dict:
        import asyncio
        from pathlib import Path
        from app.services.knowledge.repo_manifest import RepoManifest
        from app.services.knowledge.incremental_graph import IncrementalGraphUpdater

        # Pull requests live in the GitHub API, not the cloned git repo, so they
        # are synced independently of (and before) the clone-dependent graph sync.
        try:
            from app.services.integrations.pr_sync import sync_repo_prs_by_id
            pr_result = await asyncio.to_thread(sync_repo_prs_by_id, str(repo.id))
            if pr_result.get("added") or pr_result.get("closed"):
                logger.info("auto_sync_prs_updated", repo=repo.local_name,
                            added=pr_result.get("added", 0), closed=pr_result.get("closed", 0),
                            open=pr_result.get("open", 0))
        except Exception as e:
            logger.warning("auto_sync_pr_failed", repo=repo.local_name, error=str(e)[:120])

        clone_path = f"/data/repos/{repo.local_name}"
        if not Path(clone_path).exists():
            return {"status": "no_clone"}

        updater = IncrementalGraphUpdater(clone_path, str(repo.id), repo.local_name)
        result = await updater.incremental_sync()

        if result.get("changes", 0) > 0:
            logger.info(
                "auto_sync_changes_detected",
                repo=repo.local_name,
                added=result.get("added", 0),
                changed=result.get("changed", 0),
                removed=result.get("removed", 0),
            )
            await self._notify_changes(repo.local_name, result)

        self._last_poll[repo.local_name] = datetime.now(timezone.utc)
        return result

    async def handle_webhook_push(self, repo_name: str) -> dict:
        from sqlalchemy import create_engine, select as _select
        from app.config import settings as _s
        from app.models.repo import Repo
        from app.utils.git import clone_or_pull, read_file_from_bare

        engine = create_engine(_s.database_url.replace("+asyncpg", "+psycopg2"), pool_pre_ping=True)
        try:
            from sqlalchemy.orm import Session
            with Session(engine) as db:
                repo = db.execute(_select(Repo).where(Repo.local_name == repo_name)).scalar_one_or_none()
                if not repo:
                    return {"status": "unknown_repo"}
                repo_id = str(repo.id)
                github_url = repo.github_url or ""
        finally:
            engine.dispose()

        clone_path = f"/data/repos/{repo.local_name}"
        if Path(clone_path).exists():
            clone_or_pull(github_url, clone_path, getattr(repo, "default_branch", "main") or "main")

        return await self._sync_repo(repo)

    async def _notify_changes(self, repo_name: str, result: dict):
        # Record what changed into the teammate's memory. (There is no
        # `proactive_agent` notification channel — that import was dead and made
        # this whole method raise ImportError on every detected change.)
        from app.services.agent.memory import memory_manager

        added = result.get("added", [])
        changed = result.get("changed", [])
        removed = result.get("removed", [])

        if added:
            memory_manager.remember(
                f"new_files_{repo_name}",
                f"New files added to {repo_name}: {', '.join(added[:10])}",
                "feedback", importance=0.7,
            )
        if changed:
            memory_manager.remember(
                f"changed_files_{repo_name}",
                f"Files modified in {repo_name}: {', '.join(changed[:10])}",
                "feedback", importance=0.8,
            )
        if removed:
            memory_manager.remember(
                f"removed_files_{repo_name}",
                f"Files removed from {repo_name}: {', '.join(removed[:10])}",
                "feedback", importance=0.6,
            )

        total = len(added) + len(changed) + len(removed)
        if total > 0:
            logger.info("auto_sync_changes_recorded", repo=repo_name,
                        added=len(added), changed=len(changed), removed=len(removed))


auto_sync = AutoSyncEngine.get()
