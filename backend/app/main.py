from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from structlog import get_logger

from app.api.router import api_router
from app.config import settings

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_secret_key()
    try:
        from app.db.neo4j import get_neo4j_manager

        await get_neo4j_manager().verify_connectivity()
        logger.info("neo4j_connected")
        from app.services.knowledge.graph import KnowledgeGraph

        await KnowledgeGraph().ensure_schema()
        logger.info("neo4j_schema_ready")
    except Exception as e:
        logger.warning("neo4j_unavailable", error=str(e))

    try:
        import app.db.session as _session
        from app.services.agent.git_setup import ensure_git_and_gh

        _session._init_engine()
        async with _session.async_session_factory() as _db:
            await ensure_git_and_gh(_db)
        logger.info("git_gh_ready")
    except Exception as e:
        logger.warning("git_gh_setup_failed", error=str(e))

    try:
        from app.services.agent.auto_sync import auto_sync

        await auto_sync.start_polling(settings.auto_sync_poll_interval_minutes)
        logger.info(
            "auto_sync_polling_configured",
            webhook=settings.auto_sync_webhook_enabled,
            polling_min=settings.auto_sync_poll_interval_minutes,
        )
    except Exception as e:
        logger.warning("auto_sync_start_failed", error=str(e))

    yield
    try:
        from app.services.agent.auto_sync import auto_sync

        await auto_sync.stop()
    except Exception:
        pass
    try:
        from app.db.neo4j import get_neo4j_manager

        await get_neo4j_manager().close()
    except Exception as e:
        logger.debug("neo4j_close_error", error=str(e))
    try:
        from app.services.integrations.base import IntegrationRegistry

        for attr in ("_scm", "_pm", "_chat"):
            provider = getattr(IntegrationRegistry, attr, None)
            if provider and hasattr(provider, "close"):
                await provider.close()
    except Exception as e:
        logger.debug("provider_close_error", error=str(e))


app = FastAPI(
    title="TeammateX",
    description="AI teammate that learns your codebase and works alongside your team",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

if settings.prometheus_enabled:
    try:
        import hmac

        from fastapi import HTTPException, Request, Response
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
        from prometheus_fastapi_instrumentator import Instrumentator

        # Collect metrics, but do NOT use .expose() — that mounts an
        # unauthenticated /metrics. Serve it ourselves behind a token so it
        # isn't world-readable (it leaks endpoint inventory + traffic volume).
        Instrumentator().instrument(app)

        if settings.metrics_token:

            @app.get("/metrics", include_in_schema=False)
            def metrics(request: Request):
                auth = request.headers.get("Authorization", "")
                provided = (
                    auth[7:]
                    if auth.startswith("Bearer ")
                    else request.query_params.get("token", "")
                )
                if not hmac.compare_digest(provided, settings.metrics_token):
                    raise HTTPException(status_code=401, detail="Unauthorized")
                return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

        else:
            logger.info(
                "metrics_endpoint_disabled", reason="set TEAMMATEX_METRICS_TOKEN to enable /metrics"
            )
    except ImportError:
        pass
