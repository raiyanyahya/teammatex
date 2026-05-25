import asyncio
from structlog import get_logger

from app.services.knowledge.graph import KnowledgeGraph

logger = get_logger(__name__)


class BlameTracer:
    def __init__(self):
        self.graph = KnowledgeGraph()

    async def trace(
        self, repo_id: str, repo_name: str, entity_name: str,
        file_path: str | None = None, clone_path: str = "",
    ) -> dict:
        candidates: list[dict] = []

        blame_entries = await self._get_blame(file_path, clone_path) if file_path else []

        callers = await self.graph.find_dependents(repo_id, entity_name)
        callees = await self.graph.find_dependencies(repo_id, entity_name)

        candidates.append({
            "source": "call_graph",
            "related": len(callers) + len(callees),
            "detail": f"{len(callers)} callers, {len(callees)} dependencies",
        })

        if blame_entries:
            recent = blame_entries[:5]
            unique_authors = {b.get("author") for b in recent if b.get("author")}
            candidates.append({
                "source": "git_blame",
                "recent_changes": recent,
                "unique_authors": len(unique_authors),
                "detail": f"{len(recent)} recent changes by {len(unique_authors)} authors",
            })

        owner = await self.graph.find_owner(repo_id, file_path) if file_path else None
        if owner:
            candidates.append({
                "source": "ownership",
                "owner": owner,
                "detail": f"Primary owner: {owner.get('name', 'unknown')} ({owner.get('weight', 0):.0f} commits)",
            })

        return {
            "entity": entity_name,
            "file": file_path,
            "repo": repo_name,
            "total_sources": len(candidates),
            "candidates": candidates,
            "summary": self._build_summary(candidates, entity_name),
        }

    async def _get_blame(self, file_path: str, clone_path: str) -> list[dict]:
        if not clone_path or not file_path:
            return []
        try:
            import subprocess
            loop = asyncio.get_running_loop()
            def _run():
                result = subprocess.run(
                    ["git", "blame", "-L", "1,100", file_path],
                    capture_output=True, text=True, cwd=clone_path, timeout=10,
                )
                return result.stdout
            output = await loop.run_in_executor(None, _run)
            entries = []
            for line in output.splitlines()[:10]:
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    entries.append({
                        "commit": parts[0][:8],
                        "author": parts[1] if len(parts) > 1 else "unknown",
                    })
            return entries
        except Exception:
            return []

    def _build_summary(self, candidates: list[dict], entity_name: str) -> str:
        if not candidates:
            return f"No trace data found for '{entity_name}'."
        parts = []
        for c in candidates:
            parts.append(c.get("detail", ""))
        return f"{entity_name}: " + " | ".join(parts)


blame_tracer = BlameTracer()
