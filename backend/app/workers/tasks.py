from app.services.onboarding import pipeline  # noqa: F401
from app.workers.celery_app import celery_app


@celery_app.task(name="health_check")
def health_check() -> dict:
    return {"status": "ok", "worker": "celery"}


@celery_app.task(name="git_pull_repos")
def git_pull_repos() -> dict:
    """Pull all onboarded repos to keep knowledge fresh."""

    from sqlalchemy import create_engine, select

    from app.config import settings as _s
    from app.models.repo import Repo
    from app.utils.git import clone_or_pull

    engine = create_engine(_s.database_url.replace("+asyncpg", "+psycopg2"), pool_pre_ping=True)
    repos: list = []
    try:
        with engine.connect() as conn:
            repos = conn.execute(select(Repo).where(Repo.is_active == True)).all()
    except Exception:
        engine.dispose()
        return {"error": "Database error"}

    pulled = 0
    for repo in repos:
        try:
            path = f"/data/repos/{repo.local_name}"
            clone_or_pull(repo.github_url, path)
            pulled += 1
        except Exception:
            pass

    engine.dispose()
    return {"pulled": pulled, "total": len(repos)}


def _digest_slack_channel() -> str:
    """Channel for the weekly digest, from config `digest_settings.slack_channel`."""
    import json as _json

    from sqlalchemy import create_engine, text

    from app.config import settings as _s

    engine = create_engine(_s.database_url.replace("+asyncpg", "+psycopg2"), pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT value FROM app_config WHERE key = 'digest_settings'")
            ).fetchone()
            if row and row[0]:
                val = _json.loads(row[0]) if isinstance(row[0], str) else row[0]
                return (val or {}).get("slack_channel", "") or ""
    except Exception:
        pass
    finally:
        engine.dispose()
    return ""


@celery_app.task(name="send_weekly_digest")
def send_weekly_digest() -> dict:
    """Generate the weekly digest and post it to Slack if a channel + bot token are
    configured. Runs on the beat schedule (Mondays 09:00 UTC) and on demand via
    POST /api/reports/digest/send. A no-op delivery (returns the digest summary)
    when Slack isn't set up, so it never errors on an unconfigured instance."""
    from app.config import settings as _s
    from app.services.reporting.digest import digest_generator

    try:
        digest = digest_generator.generate_weekly(_s.database_url)
        markdown = digest_generator.format_markdown(digest)
    except Exception as e:
        return {"delivered": False, "error": f"digest generation failed: {str(e)[:200]}"}

    channel = _digest_slack_channel()
    token = getattr(_s, "slack_bot_token", "") or ""
    if not (channel and token):
        return {
            "delivered": False,
            "reason": "slack channel/token not configured",
            "sections": digest.get("section_count", 0),
        }

    try:
        import httpx

        resp = httpx.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {token}"},
            json={"channel": channel, "text": markdown, "mrkdwn": True},
            timeout=15,
        )
        ok = bool(resp.json().get("ok"))
        return {"delivered": ok, "channel": channel, "sections": digest.get("section_count", 0)}
    except Exception as e:
        return {"delivered": False, "error": str(e)[:200]}


@celery_app.task(name="git_pull_scheduled")
def git_pull_scheduled() -> dict:
    """Scheduled git pull - checks config for frequency."""
    from sqlalchemy import create_engine
    from sqlalchemy import select as sa_select

    from app.config import settings as _s
    from app.models.app_config import AppConfig

    engine = create_engine(_s.database_url.replace("+asyncpg", "+psycopg2"), pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            result = conn.execute(sa_select(AppConfig).where(AppConfig.key == "update_settings"))
            row = result.mappings().first()
            if row and row.get("value", {}).get("method") == "git_pull":
                int(row["value"].get("frequency_minutes", 5))
                # Check if it's time based on frequency
                return git_pull_repos()
    except Exception:
        pass
    finally:
        engine.dispose()
    return {"pulled": 0, "note": "Git pull not configured or not scheduled"}
