import re
from typing import Any

from structlog import get_logger

from app.db.neo4j import get_neo4j_manager
from app.services.knowledge.graph_ids import EXTRACTOR_VERSION, edge_id, node_id

logger = get_logger(__name__)

# Cypher has no bind parameters for labels, relationship types, or property
# *names* — they can only be interpolated into the query string. So anything
# interpolated must be a bare identifier; otherwise a value like
# "Note) DETACH DELETE n //" is injection. Neo4j identifiers are letters, digits,
# and underscores (not starting with a digit).
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(value: str, kind: str) -> str:
    if not isinstance(value, str) or not _IDENT_RE.fullmatch(value):
        raise ValueError(f"unsafe Cypher {kind}: {value!r}")
    return value


class KnowledgeGraph:
    """Operations on the Neo4j knowledge graph."""

    NODE_TYPES = [
        "Repository",
        "File",
        "Module",
        "Class",
        "Function",
        "Contributor",
        "Feature",
        "PR",
        "Commit",
        "Ticket",
        "Note",
        "Conversation",
    ]

    RELATIONSHIP_TYPES = [
        "DEPENDS_ON",
        "CALLS",
        "IMPLEMENTS",
        "EXTENDS",
        "OWNS",
        "PART_OF",
        "IMPACTS",
        "RELATES_TO",
        "REVIEWED_BY",
        "AUTHORED_BY",
        "KNOWS_ABOUT",
        "MENTIONS",
    ]

    async def ensure_repo_node(self, repo_id: str, repo_name: str) -> None:
        repo_nid = node_id(repo_id, "Repository", repo_name)
        await self.run(
            """
        MERGE (r:Repository {id: $id})
        SET r.repo_id = $repo_id, r.name = $name, r.version = $version
        """,
            id=repo_nid,
            repo_id=repo_id,
            name=repo_name,
            version=EXTRACTOR_VERSION,
        )

    async def ensure_file_node(
        self, repo_id: str, file_path: str, language: str, lines: int
    ) -> None:
        file_nid = node_id(repo_id, "File", file_path)
        # Match the repo by its repo_id property: the Repository node id is
        # hashed from the repo *name* (see ensure_repo_node), which isn't
        # recoverable from repo_id alone.
        await self.run(
            """
        MERGE (f:File {id: $id})
        SET f.repo_id = $repo_id, f.path = $path, f.language = $language, f.lines = $lines, f.version = $version
        WITH f
        MATCH (r:Repository {repo_id: $repo_id})
        MERGE (f)-[:PART_OF]->(r)
        """,
            id=file_nid,
            repo_id=repo_id,
            path=file_path,
            language=language,
            lines=lines,
            version=EXTRACTOR_VERSION,
        )

    async def ensure_contributor_node(self, email: str, name: str) -> None:
        # Key the node on email only; name can vary between commits, and
        # add_ownership keys the same way, so the OWNS MATCH must agree.
        contrib_nid = node_id("", "Contributor", email)
        await self.run(
            """
        MERGE (c:Contributor {id: $id})
        SET c.email = $email, c.name = $name, c.version = $version
        """,
            id=contrib_nid,
            email=email,
            name=name,
            version=EXTRACTOR_VERSION,
        )

    async def ensure_schema(self) -> None:
        """Heal and guard the contributor identity model. The onboarding pipeline
        MERGEs Contributor nodes by id, but without a uniqueness constraint MERGE
        isn't atomic, so concurrent workers leave several nodes sharing one id —
        which is what makes the Team page show duplicates. We first collapse any
        existing same-id duplicates (re-pointing their OWNS edges onto a single
        survivor), then add the constraint that stops them from recurring. Order
        matters: the constraint can't be created while duplicates still exist.
        Best-effort and idempotent — safe to run on every startup."""
        # 1. Merge same-id duplicates: keep the first node, move every other
        #    node's owned files onto it, then delete the extras.
        await self.run(
            """
        MATCH (c:Contributor)
        WITH c.id AS id, collect(c) AS nodes
        WHERE size(nodes) > 1
        WITH nodes[0] AS keep, nodes[1..] AS dups
        UNWIND dups AS dup
        OPTIONAL MATCH (dup)-[o:OWNS]->(f:File)
        FOREACH (_ IN CASE WHEN f IS NULL THEN [] ELSE [1] END |
            MERGE (keep)-[ko:OWNS]->(f)
            SET ko.weight = CASE
                WHEN ko.weight IS NULL THEN o.weight
                WHEN o.weight IS NULL THEN ko.weight
                ELSE ko.weight + o.weight END)
        WITH DISTINCT dup
        DETACH DELETE dup
        """
        )
        # 2. Now that ids are unique, install the constraint so MERGE becomes
        #    atomic and the duplicates can never come back.
        await self.run(
            """
        CREATE CONSTRAINT contributor_id_unique IF NOT EXISTS
        FOR (c:Contributor) REQUIRE c.id IS UNIQUE
        """
        )

    async def add_ownership(
        self, email: str, repo_id: str, file_path: str, weight: float = 1.0
    ) -> None:
        file_nid = node_id(repo_id, "File", file_path)
        contrib_nid = node_id("", "Contributor", email)
        rel_eid = edge_id(repo_id, "OWNS", contrib_nid, file_nid)
        await self.run(
            """
        MATCH (c:Contributor {id: $contrib_nid})
        MATCH (f:File {id: $file_nid})
        MERGE (c)-[o:OWNS]->(f)
        SET o.id = $rel_eid, o.weight = coalesce(o.weight, 0) + $weight, o.version = $version
        """,
            contrib_nid=contrib_nid,
            file_nid=file_nid,
            rel_eid=rel_eid,
            weight=weight,
            version=EXTRACTOR_VERSION,
        )

    async def find_owner(self, repo_id: str, file_path: str) -> dict | None:
        # Accept a repo id OR name (the agent works with names), like the other
        # graph tools — File nodes are keyed by the canonical repo_id.
        canonical = await self._resolve_repo_id(repo_id) or repo_id
        file_nid = node_id(canonical, "File", file_path)
        record = await self.run_single(
            """
        MATCH (c:Contributor)-[o:OWNS]->(f:File {id: $file_nid})
        RETURN c.name AS name, c.email AS email, o.weight AS weight
        ORDER BY o.weight DESC
        LIMIT 1
        """,
            file_nid=file_nid,
        )
        return record

    async def find_dependents(self, repo_id: str, entity_name: str) -> list[dict]:
        """Functions that call `entity_name`. Scoped to a repo (id or name) when
        one resolves, else across all onboarded repos."""
        canonical = await self._resolve_repo_id(repo_id)
        callee = "{repo_id: $repo_id, name: $name}" if canonical else "{name: $name}"
        return await self.run(
            f"""
        MATCH (a:Function)-[:CALLS]->(b:Function {callee})
        RETURN a.file_path AS file, a.name AS caller, a.start_line AS line, a.repo_id AS repo_id
        LIMIT 50
        """,
            repo_id=canonical,
            name=entity_name,
        )

    async def find_dependencies(self, repo_id: str, entity_name: str) -> list[dict]:
        """Functions that `entity_name` calls. Scoped to a repo (id or name) when
        one resolves, else across all onboarded repos."""
        canonical = await self._resolve_repo_id(repo_id)
        caller = "{repo_id: $repo_id, name: $name}" if canonical else "{name: $name}"
        return await self.run(
            f"""
        MATCH (a:Function {caller})-[:CALLS]->(b:Function)
        RETURN b.file_path AS file, b.name AS callee, b.language AS language
        LIMIT 50
        """,
            repo_id=canonical,
            name=entity_name,
        )

    async def _resolve_repo_id(self, value: str) -> str | None:
        """Map a repo_id OR a human repo name to the canonical repo_id stored on
        graph nodes. The agent often passes a repo's local name (e.g. 'kit-fork')
        while nodes carry the UUID; without this, queries match nothing."""
        if not value:
            return None
        rec = await self.run_single(
            """
        MATCH (r:Repository)
        WHERE r.repo_id = $v OR r.name = $v
        RETURN r.repo_id AS repo_id
        LIMIT 1
        """,
            v=value,
        )
        return rec["repo_id"] if rec else value

    async def get_architecture(self, repo_id: str = "") -> list[dict]:
        """Architecture overview: files with their function counts. Scoped to one
        repo when a repo_id/name resolves, otherwise across all onboarded repos.

        The builder attaches Files and Modules to the Repository (not File->Module),
        so the old `(File)-[:PART_OF]->(Module)` traversal always returned zero
        counts; this queries the topology that actually exists.
        """
        canonical = await self._resolve_repo_id(repo_id)
        where = "WHERE f.repo_id = $repo_id" if canonical else ""
        return await self.run(
            f"""
        MATCH (f:File)
        {where}
        OPTIONAL MATCH (fn:Function)-[:PART_OF]->(f)
        RETURN f.repo_id AS repo_id, f.path AS file, f.language AS language,
               f.role AS role, count(fn) AS function_count
        ORDER BY function_count DESC, file ASC
        LIMIT 40
        """,
            repo_id=canonical,
        )

    async def get_module_graph(self, repo_id: str) -> dict:
        nodes = await self.run(
            """
        MATCH (m:Module {repo_id: $repo_id})
        OPTIONAL MATCH (m)<-[:PART_OF]-(f:File)
        RETURN m.name AS name, "Module" AS type, count(f) AS weight
        """,
            repo_id=repo_id,
        )

        edges = await self.run(
            """
        MATCH (a:Module {repo_id: $repo_id})<-[:PART_OF]-(:File)<-[:PART_OF]-(:Function)-[:CALLS]->
              (:Function)-[:PART_OF]->(:File)-[:PART_OF]->(b:Module {repo_id: $repo_id})
        WHERE a.name < b.name
        RETURN a.name AS source, b.name AS target, count(*) AS weight
        """,
            repo_id=repo_id,
        )

        return {"nodes": nodes, "edges": edges}

    async def get_stats(self) -> dict:
        """Counts of code-knowledge nodes across all onboarded repos. The dashboard
        hero sentence shows `concepts` as a single number — the sum of the
        structural code-knowledge node types (File + Module + Function + Class)."""
        record = await self.run_single(
            """
        OPTIONAL MATCH (f:File) WITH count(f) AS files
        OPTIONAL MATCH (m:Module) WITH files, count(m) AS modules
        OPTIONAL MATCH (fn:Function) WITH files, modules, count(fn) AS functions
        OPTIONAL MATCH (c:Class) WITH files, modules, functions, count(c) AS classes
        RETURN files, modules, functions, classes
        """
        )
        files = (record or {}).get("files", 0) or 0
        modules = (record or {}).get("modules", 0) or 0
        functions = (record or {}).get("functions", 0) or 0
        classes = (record or {}).get("classes", 0) or 0
        return {
            "files": files,
            "modules": modules,
            "functions": functions,
            "classes": classes,
            "concepts": files + modules + functions + classes,
        }

    async def list_contributors(self, limit: int = 100) -> list[dict]:
        """Everyone the graph profiles, with the ownership footprint built from
        commit history: how many files each owns, across which repos and
        languages. `collect`/`count` skip nulls, so a contributor with no OWNS
        edges still appears with files_owned=0 and empty repos/languages.

        Identities are collapsed to one row per person: the onboarding pipeline
        can leave several Contributor nodes for the same human — identical-id
        duplicates (concurrent MERGE with no uniqueness constraint) and the same
        person committing under multiple git emails. We group by a person key
        (their name when present, else email) and count each owned file once
        across all of that person's nodes, so the Team page shows no dupes and
        no inflated file totals."""
        return await self.run(
            """
        MATCH (c:Contributor)
        WITH c, coalesce(
                 CASE WHEN trim(c.name) = '' THEN null ELSE trim(c.name) END,
                 c.email
             ) AS person_key
        OPTIONAL MATCH (c)-[:OWNS]->(f:File)
        OPTIONAL MATCH (r:Repository {repo_id: f.repo_id})
        WITH person_key,
             head(collect(DISTINCT c.name)) AS name,
             head(collect(DISTINCT c.email)) AS email,
             count(DISTINCT f) AS files_owned,
             collect(DISTINCT r.name) AS repos,
             collect(DISTINCT f.language) AS languages
        RETURN name, email, files_owned,
               [x IN repos WHERE x <> ""] AS repos,
               [x IN languages WHERE x <> ""] AS languages
        ORDER BY files_owned DESC, name ASC
        LIMIT $limit
        """,
            limit=limit,
        )

    async def create_note_node(
        self, note_id: str, title: str, entity_id: str | None = None
    ) -> None:
        await self.run(
            """
        CREATE (n:Note {id: $id, title: $title})
        """,
            id=note_id,
            title=title,
        )

    async def search_graph(self, query: str, limit: int = 20) -> list[dict]:
        return await self.run(
            """
        MATCH (n)
        WHERE any(label IN labels(n) WHERE label IN ['Function', 'Class', 'Module', 'File', 'Feature'])
        AND (n.name CONTAINS $query OR n.title CONTAINS $query OR n.path CONTAINS $query)
        RETURN labels(n)[0] AS type, n {.*} AS properties
        LIMIT $limit
        """,
            query=query,
            limit=limit,
        )

    async def run(self, cql: str, **params: Any) -> list[dict]:
        async with get_neo4j_manager().session() as session:
            # Pass params as the `parameters` dict, not **kwargs: the driver's
            # session.run(query, ...) reserves the name `query`, so a cypher param
            # named $query (e.g. search_graph) otherwise collides with it.
            result = await session.run(cql, parameters=params)
            return [dict(r) async for r in result]

    async def run_single(self, cql: str, **params: Any) -> dict | None:
        async with get_neo4j_manager().session() as session:
            result = await session.run(cql, parameters=params)
            record = await result.single()
            return dict(record) if record else None
