import json
from datetime import datetime, timezone, timedelta
from structlog import get_logger

logger = get_logger(__name__)


class DigestGenerator:
    def __init__(self):
        pass

    def generate_weekly(self, db_engine_url: str) -> dict:
        from sqlalchemy import create_engine, text
        engine = create_engine(db_engine_url.replace("+asyncpg", "+psycopg2"), pool_pre_ping=True)
        try:
            week_ago = datetime.now(timezone.utc) - timedelta(days=7)
            digest = {"week_ending": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "sections": []}

            with engine.connect() as conn:
                # Audit activity
                result = conn.execute(text(
                    "SELECT action, count(*) FROM audit_log WHERE completed_at > :since GROUP BY action ORDER BY count DESC LIMIT 10"
                ), {"since": week_ago})
                actions = [{"action": r[0], "count": r[1]} for r in result]
                if actions:
                    digest["sections"].append({"title": "Actions This Week", "data": actions})

                # Repo onboarding status
                result = conn.execute(text(
                    "SELECT r.local_name, COUNT(ros.stage) AS completed, "
                    "COUNT(ros.stage) FILTER (WHERE ros.status = 'failed') AS failed "
                    "FROM repos r JOIN repo_onboarding_state ros ON ros.repo_id = r.id "
                    "WHERE r.is_active = TRUE GROUP BY r.local_name"
                ))
                repos_data = [{"repo": r[0], "stages_completed": r[1], "stages_failed": r[2]} for r in result]
                if repos_data:
                    digest["sections"].append({"title": "Repo Status", "data": repos_data})

                # Total cost
                result = conn.execute(text(
                    "SELECT coalesce(sum(cost_cents), 0), coalesce(sum(tokens_in + tokens_out), 0) "
                    "FROM cost_log WHERE date >= :since"
                ), {"since": week_ago.date()})
                cost_row = result.fetchone()
                if cost_row and cost_row[0]:
                    digest["sections"].append({
                        "title": "LLM Usage",
                        "data": {"total_cost_cents": int(cost_row[0]), "total_tokens": int(cost_row[1])},
                    })

                # Notes created recently
                result = conn.execute(text(
                    "SELECT title, substr(content, 1, 200) AS preview FROM notes WHERE created_at > :since ORDER BY created_at DESC LIMIT 10"
                ), {"since": week_ago})
                notes = [{"title": r[0], "preview": r[1]} for r in result]
                if notes:
                    digest["sections"].append({"title": "Knowledge Notes", "data": notes})

            digest["section_count"] = len(digest["sections"])
            return digest
        finally:
            engine.dispose()

    def format_markdown(self, digest: dict) -> str:
        lines = [f"# TeammateX Weekly Digest — {digest.get('week_ending', '')}", ""]
        for section in digest.get("sections", []):
            lines.append(f"## {section['title']}")
            data = section["data"]
            if isinstance(data, list):
                for item in data[:10]:
                    if isinstance(item, dict):
                        parts = ", ".join(f"{k}: {v}" for k, v in item.items())
                        lines.append(f"- {parts}")
                    else:
                        lines.append(f"- {item}")
            elif isinstance(data, dict):
                for k, v in data.items():
                    lines.append(f"- **{k}**: {v}")
            lines.append("")
        return "\n".join(lines)


digest_generator = DigestGenerator()
