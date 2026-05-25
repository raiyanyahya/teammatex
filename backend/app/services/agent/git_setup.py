"""Self-healing git + gh configuration, run at API startup.

The container ships ``gh`` and ``git`` but no identity or auth. This sets a git
identity and authenticates ``gh`` from whatever token is available (env, the DB
``github_token`` row, or an existing clone's token-embedded remote) so the
teammate can branch/commit/push/PR on every boot — including after a rebuild —
with no manual steps.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from structlog import get_logger

logger = get_logger(__name__)

GIT_NAME = "TeammateX"
GIT_EMAIL = "teammate@teammatex.local"


def resolve_github_token(env_token=None, db_value=None, remote_url=None):
    """First available of: env token, DB app_config value, remote URL token."""
    if env_token:
        return env_token
    if db_value:
        data = json.loads(db_value) if isinstance(db_value, str) else db_value
        if isinstance(data, dict) and data.get("token"):
            return data["token"]
    if remote_url:
        m = re.search(r"x-access-token:([^@]+)@", remote_url)
        if m:
            return m.group(1)
    return None


def _run(cmd: str, stdin: str | None = None):
    return subprocess.run(cmd, shell=True, input=stdin, capture_output=True,
                          text=True, timeout=30)


def _find_remote_token() -> str | None:
    repos = Path("/data/repos")
    if not repos.exists():
        return None
    for d in repos.iterdir():
        if (d / ".git").exists():
            r = _run(f'git -C "{d}" remote get-url origin')
            if r.returncode == 0 and "x-access-token:" in r.stdout:
                return r.stdout.strip()
    return None


_gh_ready = False


def _gh_authenticated() -> bool:
    return _run("gh auth status").returncode == 0


async def ensure_git_and_gh(db=None) -> bool:
    """Set git identity and authenticate gh from any available token.

    Returns True if gh ends up authenticated. Idempotent and cheap to re-call:
    skips the login if gh is already authed.
    """
    _run(f'git config --global user.name "{GIT_NAME}"')
    _run(f'git config --global user.email "{GIT_EMAIL}"')
    _run('git config --global init.defaultBranch main')

    if _run("which gh").returncode != 0:
        logger.info("gh_setup_skipped", reason="gh not installed")
        return False
    if _gh_authenticated():
        return True

    env_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    db_value = None
    if db is not None and not env_token:
        try:
            from sqlalchemy import select
            from app.models.app_config import AppConfig
            res = await db.execute(select(AppConfig).where(AppConfig.key == "github_token"))
            row = res.scalar_one_or_none()
            db_value = row.value if row else None
        except Exception:
            pass
    remote_url = None if (env_token or db_value) else _find_remote_token()

    token = resolve_github_token(env_token, db_value, remote_url)
    if not token:
        logger.info("gh_setup_skipped", reason="no token found")
        return False
    login = _run("gh auth login --with-token", stdin=token)
    _run("gh auth setup-git")
    ok = login.returncode == 0
    logger.info("gh_configured", login_ok=ok)
    return ok


async def ensure_gh_ready(db=None) -> bool:
    """Self-healing entry point for the chat path: authenticate gh on the first
    request after a token is added, without needing an API restart."""
    global _gh_ready
    if _gh_ready:
        return True
    _gh_ready = await ensure_git_and_gh(db)
    return _gh_ready
