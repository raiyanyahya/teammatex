"""Builds the "you already know everything local" context block injected into
the agent's system prompt.

The old code listed DB repos and pointed the model at ``/data/repos/<local_name>``
— but those names didn't always match the directories on disk (and there was a
bogus ``blockstacks`` org row with no clone at all), so the agent groped around
with failed ``list_directory`` calls. Here the on-disk directories are the
source of truth; DB rows only enrich them with language/branch metadata.
"""

from __future__ import annotations

REPOS_ROOT = "/data/repos"


def reconcile_repos(db_repos, disk_names) -> list[dict]:
    """Repos that actually exist on disk, enriched with DB metadata when present.

    ``db_repos``: list of dicts with local_name/language/default_branch/github_url.
    ``disk_names``: set of directory names present under /data/repos.
    """
    by_name = {r.get("local_name"): r for r in db_repos}
    out = []
    for name in sorted(disk_names):
        meta = by_name.get(name, {})
        out.append(
            {
                "name": name,
                "path": f"{REPOS_ROOT}/{name}",
                "language": meta.get("language") or "unknown",
                "default_branch": meta.get("default_branch") or "main",
                "github_url": meta.get("github_url") or "",
                "entries": [],
            }
        )
    return out


def format_environment_block(repos: list[dict]) -> str:
    if not repos:
        return (
            "## Local environment\n"
            "There are currently no repositories cloned under "
            f"{REPOS_ROOT}/. Ask the user to onboard one first."
        )
    lines = [
        "## Local environment",
        f"{len(repos)} repository(ies) are cloned and ready under {REPOS_ROOT}/:",
        "",
    ]
    for r in repos:
        lines.append(
            f"- **{r['name']}** — `{r['path']}` "
            f"(lang: {r['language']}, default branch: {r['default_branch']})"
        )
        if r.get("github_url"):
            lines.append(f"  - remote: {r['github_url']}")
        if r.get("entries"):
            lines.append("  - top level: " + ", ".join(r["entries"]))
    return "\n".join(lines)


async def build_environment_context(db, repos_root: str = REPOS_ROOT) -> str:
    """Scan disk + DB and render the environment block (IO wrapper)."""
    from pathlib import Path

    root = Path(repos_root)
    disk_names = (
        {p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")}
        if root.exists()
        else set()
    )

    db_repos: list[dict] = []
    try:
        from sqlalchemy import select

        from app.models.repo import Repo

        result = await db.execute(select(Repo).where(Repo.is_active == True))  # noqa: E712
        for r in result.scalars().all():
            db_repos.append(
                {
                    "local_name": r.local_name,
                    "language": getattr(r, "language", None),
                    "default_branch": r.default_branch,
                    "github_url": r.github_url,
                }
            )
    except Exception:
        pass

    repos = reconcile_repos(db_repos, disk_names)
    for rp in repos:
        try:
            rp["entries"] = sorted(
                p.name for p in Path(rp["path"]).iterdir() if not p.name.startswith(".")
            )[:25]
        except Exception:
            rp["entries"] = []
    return format_environment_block(repos)
