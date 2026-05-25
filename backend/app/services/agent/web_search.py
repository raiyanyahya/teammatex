"""Real web search for the agent (the old web_search tool was a dead stub).

Pluggable by environment, zero-config by default:

- ``TAVILY_API_KEY`` set  → Tavily (best quality)
- ``BRAVE_API_KEY``  set  → Brave Search API
- otherwise               → DuckDuckGo via the ``ddgs`` library (no key)

All backends are normalized to ``[{"title", "url", "snippet"}]`` so the agent
sees one consistent shape regardless of provider.
"""

from __future__ import annotations

import asyncio
import os

from structlog import get_logger

logger = get_logger(__name__)


def select_search_provider(env=None) -> str:
    env = env if env is not None else os.environ
    if env.get("TAVILY_API_KEY"):
        return "tavily"
    if env.get("BRAVE_API_KEY"):
        return "brave"
    return "duckduckgo"


def normalize_results(provider: str, raw) -> list[dict]:
    """Map a provider's raw payload to the standard result shape."""
    if provider == "tavily":
        items = (raw or {}).get("results", []) or []
        return [{"title": r.get("title", ""), "url": r.get("url", ""),
                 "snippet": r.get("content", "")} for r in items]
    if provider == "brave":
        items = ((raw or {}).get("web") or {}).get("results", []) or []
        return [{"title": r.get("title", ""), "url": r.get("url", ""),
                 "snippet": r.get("description", "")} for r in items]
    # duckduckgo
    items = raw or []
    return [{"title": r.get("title", ""),
             "url": r.get("href") or r.get("url", ""),
             "snippet": r.get("body", "")} for r in items]


# --- backend fetchers --------------------------------------------------------


def _fetch_duckduckgo(query: str, max_results: int):
    try:
        from ddgs import DDGS
    except ImportError:  # older package name
        from duckduckgo_search import DDGS
    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results))


async def _fetch_tavily(query: str, max_results: int, api_key: str):
    import httpx
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query,
                  "max_results": max_results, "include_answer": False},
        )
        resp.raise_for_status()
        return resp.json()


async def _fetch_brave(query: str, max_results: int, api_key: str):
    import httpx
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": max_results},
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()


async def web_search(query: str, max_results: int = 5) -> dict:
    """Search the web and return ``{"provider", "results": [...]}``."""
    provider = select_search_provider()
    try:
        if provider == "tavily":
            raw = await _fetch_tavily(query, max_results, os.environ["TAVILY_API_KEY"])
        elif provider == "brave":
            raw = await _fetch_brave(query, max_results, os.environ["BRAVE_API_KEY"])
        else:
            loop = asyncio.get_running_loop()
            raw = await loop.run_in_executor(
                None, lambda: _fetch_duckduckgo(query, max_results)
            )
        results = normalize_results(provider, raw)[:max_results]
        return {"provider": provider, "results": results}
    except Exception as e:
        logger.warning("web_search_failed", provider=provider, error=str(e)[:200])
        return {"provider": provider, "results": [], "error": str(e)[:200]}
