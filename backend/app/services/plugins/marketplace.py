from dataclasses import dataclass

import httpx
from structlog import get_logger

logger = get_logger(__name__)


@dataclass
class MarketplacePlugin:
    name: str
    version: str
    description: str
    author: str
    rating: float = 0.0
    installs: int = 0
    verified: bool = False
    homepage: str = ""
    package_name: str = ""


class PluginMarketplace:
    MARKETPLACE_URL = "https://marketplace.teammatex.dev"
    _cache: dict[str, MarketplacePlugin] = {}
    _cache_ttl = 3600

    async def search(self, query: str = "", limit: int = 20) -> list[MarketplacePlugin]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.MARKETPLACE_URL}/api/v1/plugins",
                    params={"q": query, "limit": limit},
                )
                response.raise_for_status()
                plugins = response.json()
                return [
                    MarketplacePlugin(
                        name=p["name"],
                        version=p["version"],
                        description=p.get("description", ""),
                        author=p.get("author", ""),
                        rating=p.get("rating", 0.0),
                        installs=p.get("installs", 0),
                        verified=p.get("verified", False),
                        homepage=p.get("homepage", ""),
                        package_name=p.get("package_name", p["name"]),
                    )
                    for p in plugins
                ]
        except Exception as e:
            logger.warning("marketplace_unreachable", error=str(e))
            return []

    async def get_plugin(self, name: str) -> MarketplacePlugin | None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.MARKETPLACE_URL}/api/v1/plugins/{name}")
                response.raise_for_status()
                p = response.json()
                return MarketplacePlugin(
                    name=p["name"],
                    version=p["version"],
                    description=p.get("description", ""),
                    author=p.get("author", ""),
                    rating=p.get("rating", 0.0),
                    installs=p.get("installs", 0),
                    verified=p.get("verified", False),
                    homepage=p.get("homepage", ""),
                    package_name=p.get("package_name", p["name"]),
                )
        except Exception as e:
            logger.warning("marketplace_plugin_fetch_failed", name=name, error=str(e))
            return None

    async def install(self, package_name: str) -> bool:
        try:
            import subprocess
            result = subprocess.run(
                ["pip", "install", package_name],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                logger.info("plugin_installed", package=package_name)
                return True
            else:
                logger.error("plugin_install_failed", package=package_name, stderr=result.stderr[:500])
                return False
        except Exception as e:
            logger.error("plugin_install_error", package=package_name, error=str(e))
            return False


marketplace = PluginMarketplace()
