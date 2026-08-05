import http.client
import os

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from structlog import get_logger

from app.api.deps import require_admin

logger = get_logger(__name__)

# Container logs (api, worker, postgres, neo4j, redis) routinely carry
# connection strings, tracebacks with request data, and other operational
# secrets, so this is an admin-only view — not merely authenticated.
router = APIRouter(prefix="/logs", tags=["logs"], dependencies=[Depends(require_admin)])

CONTAINERS = {
    "api": "teammatex-api-1",
    "worker": "teammatex-worker-1",
    "frontend": "teammatex-frontend-1",
    "postgres": "teammatex-postgres-1",
    "neo4j": "teammatex-neo4j-1",
    "redis": "teammatex-redis-1",
}

# We reach the Docker API through the read-only docker-socket-proxy over TCP, NOT
# a bind-mounted /var/run/docker.sock. The proxy only permits read GET calls on
# /containers, so this endpoint can fetch logs while the api container has no
# direct, writable handle on the host Docker daemon to escape through.
DOCKER_PROXY_HOST = os.getenv("DOCKER_PROXY_HOST", "docker-socket-proxy")
DOCKER_PROXY_PORT = int(os.getenv("DOCKER_PROXY_PORT", "2375"))


# PlainTextResponse so the body is the raw log text with real newlines. The
# default JSONResponse would wrap it in quotes and escape every newline to a
# literal \n, collapsing the whole log into one line in the Logs UI (which
# splits on newlines) and breaking the level filters.
@router.get("/{service}", response_class=PlainTextResponse)
async def get_logs(service: str):
    container = CONTAINERS.get(service)
    if not container:
        return f"Unknown service: {service}"

    try:
        conn = http.client.HTTPConnection(DOCKER_PROXY_HOST, DOCKER_PROXY_PORT, timeout=5)
        conn.request("GET", f"/containers/{container}/logs?stdout=1&stderr=1&tail=300")
        response = conn.getresponse()
        data = response.read()
        # Strip Docker multiplexing headers (8 bytes per frame: stream-type + 3 padding + 4 size)
        cleaned = ""
        i = 0
        while i < len(data):
            if i + 8 > len(data):
                break
            size = int.from_bytes(data[i + 4 : i + 8], "big")
            cleaned += data[i + 8 : i + 8 + size].decode("utf-8", errors="replace")
            i += 8 + size
        conn.close()
        return cleaned or "No logs"
    except (ConnectionRefusedError, OSError) as e:
        # Keep the underlying error in the server log; don't echo it to the client.
        logger.warning("logs_proxy_unavailable", service=service, error=str(e))
        return (
            "Log proxy unavailable. The docker-socket-proxy service must be running; "
            "logs can also be viewed from the host: docker compose logs -f"
        )
    except Exception as e:
        logger.error("logs_fetch_failed", service=service, error=str(e))
        return "Error retrieving logs. See the server log for details."
