import asyncio
from datetime import datetime, timezone

from structlog import get_logger

logger = get_logger(__name__)


async def log_cost(
    provider: str,
    model: str,
    call_type: str,
    tokens_in: int,
    tokens_out: int,
    cost_cents: float,
) -> None:
    try:
        from sqlalchemy import create_engine, text
        from app.config import settings

        engine = create_engine(
            settings.database_url.replace("+asyncpg", "+psycopg2"),
            pool_pre_ping=True,
        )
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _sync_log_cost, engine, provider, model, call_type, tokens_in, tokens_out, cost_cents)
    except Exception:
        pass


def _sync_log_cost(engine, provider, model, call_type, tokens_in, tokens_out, cost_cents):
    from sqlalchemy import text
    import uuid
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO cost_log (id, date, provider, model, call_type, tokens_in, tokens_out, cost_cents) "
                    "VALUES (:id, :date, :provider, :model, :call_type, :tokens_in, :tokens_out, :cost_cents)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "date": datetime.now(timezone.utc).date(),
                    "provider": provider,
                    "model": model,
                    "call_type": call_type,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "cost_cents": cost_cents,
                },
            )
            conn.commit()
    except Exception:
        pass
    finally:
        try:
            engine.dispose()
        except Exception:
            pass


async def log_audit(
    action: str,
    entity_type: str = "",
    entity_id: str = "",
    summary: str = "",
    llm_calls: int = 0,
    tokens_used: int = 0,
    cost_cents: float = 0,
    status: str = "success",
) -> None:
    try:
        from sqlalchemy import create_engine, text
        from app.config import settings

        engine = create_engine(
            settings.database_url.replace("+asyncpg", "+psycopg2"),
            pool_pre_ping=True,
        )
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, _sync_log_audit, engine, action, entity_type, entity_id,
            summary, llm_calls, tokens_used, cost_cents, status,
        )
    except Exception:
        pass


def _sync_log_audit(engine, action, entity_type, entity_id, summary, llm_calls, tokens_used, cost_cents, status):
    from sqlalchemy import text
    import uuid
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO audit_log (id, action, entity_type, entity_id, summary, llm_calls, tokens_used, estimated_cost_cents, started_at, completed_at, status) "
                    "VALUES (:id, :action, :entity_type, :entity_id, :summary, :llm_calls, :tokens_used, :cost, :started, :completed, :status)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "action": action,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "summary": summary,
                    "llm_calls": llm_calls,
                    "tokens_used": tokens_used,
                    "cost": cost_cents,
                    "started": datetime.now(timezone.utc),
                    "completed": datetime.now(timezone.utc),
                    "status": status,
                },
            )
            conn.commit()
    except Exception:
        pass
    finally:
        try:
            engine.dispose()
        except Exception:
            pass
