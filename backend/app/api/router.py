import time

from fastapi import APIRouter, Depends

from app.api.agent import router as agent_router
from app.api.api_registry import router as api_registry_router
from app.api.auth_endpoints import router as auth_router
from app.api.config_endpoints import router as config_router
from app.api.conversations import router as conversations_router
from app.api.deps import require_user
from app.api.features import router as features_router
from app.api.integrations import router as integrations_router
from app.api.knowledge import router as knowledge_router
from app.api.logs_endpoint import router as logs_router
from app.api.notepad import router as notepad_router
from app.api.permissions import router as permissions_router
from app.api.plugins import router as plugins_router
from app.api.reporting import router as reports_router
from app.api.repos import router as repos_router
from app.api.tasks import router as tasks_router
from app.api.uploads import router as uploads_router
from app.api.webhooks import router as webhooks_router

api_router = APIRouter()

# Open routers: login/setup must be reachable before auth, and webhooks
# authenticate themselves via signature verification (callers are GitHub/Slack,
# not a logged-in user). /health (below) is also public for container probes.
api_router.include_router(auth_router)
api_router.include_router(webhooks_router)

# Everything else requires an authenticated user (tmx_token cookie or Bearer).
_auth = [Depends(require_user)]
api_router.include_router(repos_router, dependencies=_auth)
api_router.include_router(knowledge_router, dependencies=_auth)
api_router.include_router(agent_router, dependencies=_auth)
api_router.include_router(integrations_router, dependencies=_auth)
api_router.include_router(api_registry_router, dependencies=_auth)
api_router.include_router(plugins_router, dependencies=_auth)
api_router.include_router(features_router, dependencies=_auth)
api_router.include_router(config_router, dependencies=_auth)
api_router.include_router(permissions_router, dependencies=_auth)
api_router.include_router(tasks_router, dependencies=_auth)
api_router.include_router(uploads_router, dependencies=_auth)
api_router.include_router(notepad_router, dependencies=_auth)
api_router.include_router(conversations_router, dependencies=_auth)
api_router.include_router(logs_router, dependencies=_auth)
api_router.include_router(reports_router, dependencies=_auth)

_API_STARTED_AT = time.monotonic()


@api_router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "teammatex-api",
        "uptime_seconds": int(time.monotonic() - _API_STARTED_AT),
    }
