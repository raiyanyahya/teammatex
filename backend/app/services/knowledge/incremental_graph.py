import contextlib
import json
from pathlib import Path
from typing import Any

from structlog import get_logger

from app.services.knowledge.graph import KnowledgeGraph
from app.services.knowledge.graph_ids import EXTRACTOR_VERSION, node_id
from app.services.knowledge.repo_manifest import RepoManifest
from app.services.onboarding.code_parser import CodeParser

logger = get_logger(__name__)

MANIFEST_PREFIX = "manifest::"

# Skip line-counting files larger than this (binary/minified blobs); the line
# count would be meaningless and the read wasteful.
_MAX_LINE_COUNT_BYTES = 2 * 1024 * 1024


def _count_lines(path: Path) -> int:
    """Best-effort line count for a source file, 0 on any error or oversized/
    binary file. Populates File.lines so per-file size data in the graph is real
    rather than always 0."""
    try:
        if not path.is_file() or path.stat().st_size > _MAX_LINE_COUNT_BYTES:
            return 0
        with path.open("rb") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


class IncrementalGraphUpdater:
    def __init__(self, clone_path: str, repo_id: str, repo_name: str):
        self.clone_path = clone_path
        self.repo_id = repo_id
        self.repo_name = repo_name
        self.manifest = RepoManifest(clone_path)
        self.graph = KnowledgeGraph()
        self.parser = CodeParser()
        self._auth: str | None = None

    def _neo4j_auth(self) -> str:
        if self._auth is None:
            import base64

            from app.config import settings

            self._auth = base64.b64encode(
                f"{settings.neo4j_user}:{settings.neo4j_password}".encode()
            ).decode()
        return self._auth

    async def full_sync(self) -> dict:
        manifest = self.manifest.scan()
        await self.graph.ensure_repo_node(self.repo_id, self.repo_name)
        await self._store_manifest(manifest)

        root = Path(self.clone_path)
        processed = 0
        entities = 0
        rels = 0

        for file_path in root.rglob("*"):
            if (
                not file_path.is_file()
                or ".git" in file_path.parts
                or "node_modules" in file_path.parts
            ):
                continue
            if processed >= 500:
                break
            processed += 1
            rel = str(file_path.relative_to(root))
            lang_map = {
                ".py": "python",
                ".js": "javascript",
                ".ts": "typescript",
                ".go": "go",
                ".rs": "rust",
                ".java": "java",
            }
            lang = lang_map.get(file_path.suffix, "")

            file_nid = node_id(self.repo_id, "File", rel)
            role = RepoManifest.classify_path_role(rel)
            info = manifest.get(rel, {})
            sha = info.get("sha256", "")
            size_val = info.get("size", 0)

            try:
                await self._run_cypher(
                    """
                MERGE (f:File {id: $id})
                SET f.repo_id = $repo_id, f.path = $path, f.language = $lang,
                    f.sha256 = $sha, f.size = $size, f.role = $role,
                    f.lines = $lines, f.version = $version
                WITH f
                MATCH (r:Repository {id: $repo_nid})
                MERGE (f)-[:PART_OF]->(r)
                """,
                    id=file_nid,
                    repo_id=self.repo_id,
                    path=rel,
                    lang=lang,
                    sha=sha,
                    size=size_val,
                    role=role,
                    lines=_count_lines(file_path),
                    version=EXTRACTOR_VERSION,
                    repo_nid=node_id(self.repo_id, "Repository", self.repo_name),
                )
            except Exception as e:
                logger.debug("file_node_failed", path=rel, error=str(e)[:100])

        return {
            "files_processed": processed,
            "entities_found": entities,
            "relationships_created": rels,
        }

    async def incremental_sync(self) -> dict:
        stored = await self._load_manifest()
        if not stored:
            return await self.full_sync()

        diff = self.manifest.diff(stored)
        total_changes = len(diff["added"]) + len(diff["changed"]) + len(diff["removed"])

        if total_changes == 0:
            return {"status": "up_to_date", "changes": 0}

        changed_files = diff["added"] + diff["changed"]

        for rel in diff["removed"]:
            file_nid = node_id(self.repo_id, "File", rel)
            with contextlib.suppress(Exception):
                await self._run_cypher("MATCH (f:File {id: $id}) DETACH DELETE f", id=file_nid)

        current = self.manifest.scan()
        for rel in changed_files[:200]:
            file_path = Path(self.clone_path) / rel
            if not file_path.exists():
                continue
            info = current.get(rel, {})
            lang_map = {
                ".py": "python",
                ".js": "javascript",
                ".ts": "typescript",
                ".go": "go",
                ".rs": "rust",
                ".java": "java",
            }
            lang = lang_map.get(file_path.suffix, "")
            role = RepoManifest.classify_path_role(rel)
            file_nid = node_id(self.repo_id, "File", rel)

            try:
                await self._run_cypher(
                    """
                MERGE (f:File {id: $id})
                SET f.repo_id = $repo_id, f.path = $path, f.language = $lang,
                    f.sha256 = $sha, f.size = $size, f.role = $role,
                    f.lines = $lines, f.version = $version
                WITH f
                MATCH (r:Repository {id: $repo_nid})
                MERGE (f)-[:PART_OF]->(r)
                """,
                    id=file_nid,
                    repo_id=self.repo_id,
                    path=rel,
                    lang=lang,
                    sha=info.get("sha256", ""),
                    size=info.get("size", 0),
                    role=role,
                    lines=_count_lines(file_path),
                    version=EXTRACTOR_VERSION,
                    repo_nid=node_id(self.repo_id, "Repository", self.repo_name),
                )
            except Exception as e:
                logger.debug("incr_file_failed", path=rel, error=str(e)[:100])

        await self._store_manifest(current)

        return {
            "status": "updated",
            "changes": total_changes,
            "added": len(diff["added"]),
            "changed": len(diff["changed"]),
            "removed": len(diff["removed"]),
            # Filename lists (consumers like auto_sync record which files moved).
            "added_files": diff["added"],
            "changed_files": diff["changed"],
            "removed_files": diff["removed"],
        }

    async def _store_manifest(self, manifest: dict):
        key = f"{MANIFEST_PREFIX}{self.repo_id}"
        with contextlib.suppress(Exception):
            await self._run_cypher(
                """
            MERGE (m:Manifest {key: $key})
            SET m.data = $data, m.updated_at = datetime()
            """,
                key=key,
                data=json.dumps(manifest),
            )

    async def _load_manifest(self) -> dict[str, dict[str, Any]]:
        key = f"{MANIFEST_PREFIX}{self.repo_id}"
        try:
            records = await self._run_cypher(
                """
            MATCH (m:Manifest {key: $key}) RETURN m.data AS data
            """,
                key=key,
            )
            if records and records[0].get("data"):
                data = records[0]["data"]
                return json.loads(data) if isinstance(data, str) else data
        except Exception:
            pass
        return {}

    async def _run_cypher(self, query: str, **params):
        from app.db.neo4j import get_neo4j_manager

        async with get_neo4j_manager().session() as session:
            result = await session.run(query, **params)
            return [dict(r) async for r in result]


class ImportCentrality:
    def __init__(self, repo_id: str):
        self.repo_id = repo_id

    async def compute_centrality(self) -> dict[str, int]:
        records = await self._run(
            """
        MATCH (f:File {repo_id: $repo_id})
        OPTIONAL MATCH (f)<-[r:PART_OF]-(other:Function)
        RETURN f.path AS file, f.id AS id, coalesce(count(other), 0) AS in_degree
        ORDER BY in_degree DESC
        LIMIT 100
        """,
            repo_id=self.repo_id,
        )
        centrality: dict[str, int] = {}
        for r in records:
            centrality[r["file"]] = r["in_degree"]
        return centrality

    async def rank_files(self, query_results: list[dict], repo_id: str) -> list[dict]:
        centrality = await self.compute_centrality()
        max_deg = max(centrality.values()) if centrality else 1

        for result in query_results:
            file_path = result.get("file_path", "")
            if file_path in centrality:
                in_deg = centrality[file_path]
                boost = min(0.15, (in_deg / max(max_deg, 1)) * 0.15)
                original = result.get("similarity", result.get("score", 0.5))
                result["similarity"] = round(min(1.0, original + boost), 4)
                result["centrality"] = in_deg
                result["centrality_boost"] = round(boost, 4)
        return query_results

    async def _run(self, query: str, **params):
        from app.db.neo4j import get_neo4j_manager

        async with get_neo4j_manager().session() as session:
            result = await session.run(query, **params)
            return [dict(r) async for r in result]
