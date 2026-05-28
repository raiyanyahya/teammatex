import time

from fastapi import APIRouter

from app.api.auth_endpoints import router as auth_router
from app.api.repos import router as repos_router
from app.api.knowledge import router as knowledge_router
from app.api.agent import router as agent_router
from app.api.integrations import router as integrations_router
from app.api.webhooks import router as webhooks_router
from app.api.api_registry import router as api_registry_router
from app.api.plugins import router as plugins_router
from app.api.features import router as features_router
from app.api.config_endpoints import router as config_router
from app.api.permissions import router as permissions_router

from app.api.logs_endpoint import router as logs_router
from app.api.reporting import router as reports_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(repos_router)
api_router.include_router(knowledge_router)
api_router.include_router(agent_router)
api_router.include_router(integrations_router)
api_router.include_router(webhooks_router)
api_router.include_router(api_registry_router)
api_router.include_router(plugins_router)
api_router.include_router(features_router)
api_router.include_router(config_router)
api_router.include_router(permissions_router)
api_router.include_router(logs_router)
api_router.include_router(reports_router)

_API_STARTED_AT = time.monotonic()


@api_router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "teammatex-api",
        "uptime_seconds": int(time.monotonic() - _API_STARTED_AT),
    }
