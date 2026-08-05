import re
from dataclasses import dataclass
from urllib.parse import quote

import httpx
from structlog import get_logger

logger = get_logger(__name__)

# A bare PyPI distribution name, optionally pinned with ==<version>. This is
# deliberately strict: it rejects VCS/URL/path specs like
# "git+https://evil/x.git", local dirs, and pip option injection ("--index-url
# http://evil"), any of which would let `pip install` fetch and execute
# arbitrary attacker code (setup.py / import time).
_PACKAGE_SPEC_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}(==[A-Za-z0-9][A-Za-z0-9.+!_-]{0,63})?$"
)


def is_valid_package_spec(name: str) -> bool:
    return bool(_PACKAGE_SPEC_RE.fullmatch((name or "").strip()))


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
        # `name` is interpolated into the request path, so a value like
        # "../../secret" or "..%2f@evil" could otherwise redirect the call to a
        # different path or host (SSRF). Restrict it to a plain package name and
        # percent-encode it so no character can escape this single path segment.
        if not is_valid_package_spec(name):
            logger.warning("marketplace_plugin_name_rejected", name=(name or "")[:120])
            return None
        safe_name = quote(name.strip(), safe="")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.MARKETPLACE_URL}/api/v1/plugins/{safe_name}")
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
        # Reject anything that isn't a plain PyPI name/version. Without this a
        # caller could pass a git+https URL or a local path and get RCE via the
        # installed package's setup.py.
        if not is_valid_package_spec(package_name):
            logger.warning("plugin_install_rejected", package=package_name[:120])
            return False
        try:
            import subprocess

            result = subprocess.run(
                # "--" stops pip from treating a crafted name as an option flag.
                ["pip", "install", "--no-input", "--disable-pip-version-check", "--", package_name],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                logger.info("plugin_installed", package=package_name)
                return True
            else:
                logger.error(
                    "plugin_install_failed", package=package_name, stderr=result.stderr[:500]
                )
                return False
        except Exception as e:
            logger.error("plugin_install_error", package=package_name, error=str(e))
            return False


marketplace = PluginMarketplace()
