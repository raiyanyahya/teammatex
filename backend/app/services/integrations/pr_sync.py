"""Ingest GitHub pull requests into the local `prs` table.

Pull requests are a GitHub-platform concept and do not exist in the cloned git
repo, so the onboarding pipeline (which only does `git clone` + static analysis)
never captured them — leaving the `prs` table empty and every repo's open-PR
count stuck at 0 on the dashboard. This module fetches open PRs from the GitHub
REST API and reconciles them into `prs`, idempotently, so the counts are real.

Kept fully synchronous (httpx.Client + a SQLAlchemy Session) so it is trivially
testable and runnable as a one-off backfill. The async poll loop calls it from a
worker thread (see app.services.agent.auto_sync).
"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from structlog import get_logger

from app.models.app_config import AppConfig
from app.models.pr import PR

logger = get_logger(__name__)

GITHUB_API = "https://api.github.com"
_OPEN = "open"
# Hard ceiling on pagination so a misbehaving API that never returns a short or
# empty page can't spin the fetch loop forever. 50 pages × 100 = 5000 open PRs,
# far beyond any real repo.
MAX_PAGES = 50


def github_token(db) -> str | None:
    """The GitHub token saved in Settings (same key the org-import flow uses)."""
    row = db.execute(select(AppConfig).where(AppConfig.key == "github_token")).scalar_one_or_none()
    if row and row.value:
        return row.value.get("token") or None
    return None


def owner_repo(github_url: str) -> str | None:
    """`https://github.com/owner/name(.git)` -> `owner/name`; None for org-only URLs."""
    path = urlparse(github_url or "").path.strip("/")
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        return None
    owner, name = parts[0], parts[1]
    if name.endswith(".git"):
        name = name[:-4]
    return f"{owner}/{name}"


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)


def fetch_open_prs(
    full_name: str, token: str | None, client: httpx.Client | None = None
) -> list[dict]:
    """All open PRs for `owner/name`, following pagination (100/page)."""
    own_client = client is None
    if own_client:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        client = httpx.Client(base_url=GITHUB_API, headers=headers, timeout=30)
    try:
        out: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            resp = client.get(
                f"/repos/{full_name}/pulls",
                params={"state": _OPEN, "per_page": 100, "page": page},
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            out.extend(batch)
            if len(batch) < 100:
                break
        return out
    finally:
        if own_client:
            client.close()


def reconcile_prs(db, repo_id: str, gh_prs: list[dict]) -> dict:
    """Upsert the fetched open PRs and close DB rows that are no longer open.

    Agent-authored PRs (those linked to a task) are never auto-closed — they are
    tracked by the agent's own workflow, not by this external snapshot.
    """
    existing = {
        p.github_pr_number: p
        for p in db.execute(select(PR).where(PR.repo_id == repo_id)).scalars().all()
        if p.github_pr_number is not None
    }
    seen: set[int] = set()
    added = updated = 0

    for gh in gh_prs:
        number = gh.get("number")
        if number is None:
            continue
        seen.add(number)
        title = (gh.get("title") or "")[:500]
        branch = ((gh.get("head") or {}).get("ref") or "")[:255]

        pr = existing.get(number)
        if pr is None:
            db.add(
                PR(
                    repo_id=repo_id,
                    github_pr_number=number,
                    title=title,
                    branch=branch,
                    status=_OPEN,
                    created_at=_parse_dt(gh.get("created_at")),
                )
            )
            added += 1
        else:
            changed = False
            if pr.status != _OPEN:
                pr.status = _OPEN
                changed = True
            if pr.title != title:
                pr.title = title
                changed = True
            if changed:
                updated += 1

    closed = 0
    for number, pr in existing.items():
        if number in seen:
            continue
        if pr.task_id is not None:  # agent-owned — leave it alone
            continue
        if pr.status not in ("merged", "closed"):
            pr.status = "closed"
            closed += 1

    db.commit()
    return {"added": added, "updated": updated, "closed": closed, "open": len(seen)}


def sync_repo_prs(db, repo, token: str | None = None, client: httpx.Client | None = None) -> dict:
    """Fetch + reconcile open PRs for one repo. Returns a small summary dict."""
    full = owner_repo(repo.github_url)
    if not full:
        return {"status": "bad_url", "repo": getattr(repo, "local_name", "?")}
    token = token or github_token(db)
    gh_prs = fetch_open_prs(full, token, client=client)
    result = reconcile_prs(db, str(repo.id), gh_prs)
    result["repo"] = getattr(repo, "local_name", full)
    return result


def sync_repo_prs_by_id(repo_id: str) -> dict:
    """Refresh one repo's PRs in a fresh session — safe to call from a worker
    thread (the poll loop's ORM objects are detached from their session)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.config import settings
    from app.models.repo import Repo

    engine = create_engine(
        settings.database_url.replace("+asyncpg", "+psycopg2"), pool_pre_ping=True
    )
    try:
        with Session(engine) as db:
            repo = db.get(Repo, repo_id)
            if not repo:
                return {"status": "unknown_repo", "repo_id": repo_id}
            return sync_repo_prs(db, repo)
    finally:
        engine.dispose()


def sync_all_prs() -> dict:
    """Backfill/refresh PRs for every active repo. Manages its own DB session."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.config import settings
    from app.models.repo import Repo

    engine = create_engine(
        settings.database_url.replace("+asyncpg", "+psycopg2"), pool_pre_ping=True
    )
    totals = {"repos": 0, "added": 0, "updated": 0, "closed": 0, "open": 0, "errors": 0}
    try:
        with Session(engine) as db:
            token = github_token(db)
            repos = (
                db.execute(select(Repo).where(Repo.is_active == True)).scalars().all()
            )  # noqa: E712
            for repo in repos:
                totals["repos"] += 1
                try:
                    r = sync_repo_prs(db, repo, token=token)
                    for k in ("added", "updated", "closed", "open"):
                        totals[k] += r.get(k, 0)
                except Exception as e:
                    totals["errors"] += 1
                    db.rollback()
                    logger.warning("pr_sync_repo_failed", repo=repo.local_name, error=str(e)[:160])
    finally:
        engine.dispose()
    logger.info("pr_sync_complete", **totals)
    return totals
