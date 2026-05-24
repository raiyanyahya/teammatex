import http.client
import json
import urllib.parse

from fastapi import APIRouter

router = APIRouter(prefix="/logs", tags=["logs"])

CONTAINERS = {
    "api": "teammatex-api-1",
    "worker": "teammatex-worker-1",
    "frontend": "teammatex-frontend-1",
    "postgres": "teammatex-postgres-1",
    "neo4j": "teammatex-neo4j-1",
    "redis": "teammatex-redis-1",
}


@router.get("/{service}")
async def get_logs(service: str):
    container = CONTAINERS.get(service)
    if not container:
        return f"Unknown service: {service}"

    try:
        conn = http.client.HTTPConnection("localhost")
        conn.sock = __import__("socket").socket(__import__("socket").AF_UNIX, __import__("socket").SOCK_STREAM)
        conn.sock.connect("/var/run/docker.sock")
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
    except FileNotFoundError:
        return "Docker socket not available. Logs can only be viewed from the host: docker compose logs -f"
    except Exception as e:
        return f"Error: {e}"
