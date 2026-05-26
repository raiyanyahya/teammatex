from typing import Any, Optional

from neo4j import AsyncSession
from structlog import get_logger

from app.db.neo4j import get_neo4j_manager
from app.services.knowledge.graph_ids import node_id, edge_id, EXTRACTOR_VERSION

logger = get_logger(__name__)


class KnowledgeGraph:
    """Operations on the Neo4j knowledge graph."""

    NODE_TYPES = [
        "Repository", "File", "Module", "Class", "Function",
        "Contributor", "Feature", "PR", "Commit", "Ticket", "Note", "Conversation",
    ]

    RELATIONSHIP_TYPES = [
        "DEPENDS_ON", "CALLS", "IMPLEMENTS", "EXTENDS", "OWNS",
        "PART_OF", "IMPACTS", "RELATES_TO", "REVIEWED_BY", "AUTHORED_BY",
        "KNOWS_ABOUT", "MENTIONS",
    ]

    async def create_node(
        self,
        labels: list[str],
        properties: dict[str, Any],
    ) -> dict | None:
        label_str = ":".join(labels)
        props_str = ", ".join(f"{k}: ${k}" for k in properties)
        query = f"CREATE (n:{label_str} {{{props_str}}}) RETURN n {{.*}} as node"
        async with get_neo4j_manager().session() as session:
            result = await session.run(query, **properties)
            record = await result.single()
            return dict(record["node"]) if record else None

    async def create_relationship(
        self,
        from_node_query: str,
        from_params: dict,
        to_node_query: str,
        to_params: dict,
        rel_type: str,
        rel_properties: dict[str, Any] | None = None,
    ) -> bool:
        rel_props = rel_properties or {}
        rel_str = f":{rel_type}"
        if rel_props:
            props = ", ".join(f"{k}: ${k}" for k in rel_props)
            rel_str = f":{rel_type} {{{props}}}"

        query = f"""
        MATCH (a {{{from_node_query}}})
        MATCH (b {{{to_node_query}}})
        CREATE (a)-[r{rel_str}]->(b)
        RETURN r
        """
        params = {**from_params, **to_params, **(rel_props or {})}
        async with get_neo4j_manager().session() as session:
            result = await session.run(query, **params)
            return await result.single() is not None

    async def ensure_repo_node(self, repo_id: str, repo_name: str) -> None:
        repo_nid = node_id(repo_id, "Repository", repo_name)
        await self.run("""
        MERGE (r:Repository {id: $id})
        SET r.repo_id = $repo_id, r.name = $name, r.version = $version
        """, id=repo_nid, repo_id=repo_id, name=repo_name, version=EXTRACTOR_VERSION)

    async def ensure_file_node(
        self, repo_id: str, file_path: str, language: str, lines: int
    ) -> None:
        file_nid = node_id(repo_id, "File", file_path)
        repo_nid = node_id(repo_id, "Repository", self._resolve_repo_name(repo_id))
        await self.run("""
        MERGE (f:File {id: $id})
        SET f.repo_id = $repo_id, f.path = $path, f.language = $language, f.lines = $lines, f.version = $version
        WITH f
        MATCH (r:Repository {id: $repo_nid})
        MERGE (f)-[:PART_OF]->(r)
        """, id=file_nid, repo_id=repo_id, path=file_path, language=language, lines=lines, version=EXTRACTOR_VERSION,
             repo_nid=repo_nid)

    async def ensure_function_node(
        self,
        repo_id: str,
        file_path: str,
        name: str,
        start_line: int,
        end_line: int,
        language: str,
        signature: str | None = None,
    ) -> None:
        fn_nid = node_id(repo_id, "Function", file_path, name)
        file_nid = node_id(repo_id, "File", file_path)
        await self.run("""
        MERGE (fn:Function {id: $id})
        SET fn.repo_id = $repo_id, fn.file_path = $file_path, fn.name = $name,
            fn.start_line = $start_line, fn.end_line = $end_line,
            fn.language = $language, fn.signature = $signature, fn.version = $version
        WITH fn
        MATCH (f:File {id: $file_nid})
        MERGE (fn)-[:PART_OF]->(f)
        """, id=fn_nid, repo_id=repo_id, file_path=file_path, name=name,
             start_line=start_line, end_line=end_line,
             language=language, signature=signature, version=EXTRACTOR_VERSION,
             file_nid=file_nid)

    async def ensure_class_node(
        self,
        repo_id: str,
        file_path: str,
        name: str,
        start_line: int,
        end_line: int,
        language: str,
    ) -> None:
        cls_nid = node_id(repo_id, "Class", file_path, name)
        file_nid = node_id(repo_id, "File", file_path)
        await self.run("""
        MERGE (c:Class {id: $id})
        SET c.repo_id = $repo_id, c.file_path = $file_path, c.name = $name,
            c.start_line = $start_line, c.end_line = $end_line,
            c.language = $language, c.version = $version
        WITH c
        MATCH (f:File {id: $file_nid})
        MERGE (c)-[:PART_OF]->(f)
        """, id=cls_nid, repo_id=repo_id, file_path=file_path, name=name,
             start_line=start_line, end_line=end_line, language=language,
             version=EXTRACTOR_VERSION, file_nid=file_nid)

    async def ensure_module_node(self, repo_id: str, name: str) -> None:
        mod_nid = node_id(repo_id, "Module", name)
        repo_nid = node_id(repo_id, "Repository", self._resolve_repo_name(repo_id))
        await self.run("""
        MERGE (m:Module {id: $id})
        SET m.repo_id = $repo_id, m.name = $name, m.version = $version
        WITH m
        MATCH (r:Repository {id: $repo_nid})
        MERGE (m)-[:PART_OF]->(r)
        """, id=mod_nid, repo_id=repo_id, name=name, version=EXTRACTOR_VERSION,
             repo_nid=repo_nid)

    async def ensure_contributor_node(self, email: str, name: str) -> None:
        # Key the node on email only; name can vary between commits, and
        # add_ownership keys the same way, so the OWNS MATCH must agree.
        contrib_nid = node_id("", "Contributor", email)
        await self.run("""
        MERGE (c:Contributor {id: $id})
        SET c.email = $email, c.name = $name, c.version = $version
        """, id=contrib_nid, email=email, name=name, version=EXTRACTOR_VERSION)

    async def add_call_relationship(
        self,
        repo_id: str,
        caller_file: str,
        caller_name: str,
        caller_start: int,
        callee_name: str,
    ) -> None:
        caller_nid = node_id(repo_id, "Function", caller_file, caller_name)
        await self.run("""
        MATCH (a:Function {id: $caller_nid})
        MERGE (b:Function {repo_id: $repo_id, name: $callee_name})
        MERGE (a)-[r:CALLS]->(b)
        SET r.version = $version
        """, caller_nid=caller_nid, repo_id=repo_id, callee_name=callee_name,
             version=EXTRACTOR_VERSION)

    async def add_ownership(
        self, email: str, repo_id: str, file_path: str, weight: float = 1.0
    ) -> None:
        file_nid = node_id(repo_id, "File", file_path)
        contrib_nid = node_id("", "Contributor", email)
        rel_eid = edge_id(repo_id, "OWNS", contrib_nid, file_nid)
        await self.run("""
        MATCH (c:Contributor {id: $contrib_nid})
        MATCH (f:File {id: $file_nid})
        MERGE (c)-[o:OWNS]->(f)
        SET o.id = $rel_eid, o.weight = coalesce(o.weight, 0) + $weight, o.version = $version
        """, contrib_nid=contrib_nid, file_nid=file_nid, rel_eid=rel_eid,
             weight=weight, version=EXTRACTOR_VERSION)

    async def find_owner(self, repo_id: str, file_path: str) -> dict | None:
        # Accept a repo id OR name (the agent works with names), like the other
        # graph tools — File nodes are keyed by the canonical repo_id.
        canonical = await self._resolve_repo_id(repo_id) or repo_id
        file_nid = node_id(canonical, "File", file_path)
        record = await self.run_single("""
        MATCH (c:Contributor)-[o:OWNS]->(f:File {id: $file_nid})
        RETURN c.name AS name, c.email AS email, o.weight AS weight
        ORDER BY o.weight DESC
        LIMIT 1
        """, file_nid=file_nid)
        return record

    async def find_dependents(self, repo_id: str, entity_name: str) -> list[dict]:
        """Functions that call `entity_name`. Scoped to a repo (id or name) when
        one resolves, else across all onboarded repos."""
        canonical = await self._resolve_repo_id(repo_id)
        callee = "{repo_id: $repo_id, name: $name}" if canonical else "{name: $name}"
        return await self.run(f"""
        MATCH (a:Function)-[:CALLS]->(b:Function {callee})
        RETURN a.file_path AS file, a.name AS caller, a.start_line AS line, a.repo_id AS repo_id
        LIMIT 50
        """, repo_id=canonical, name=entity_name)

    async def find_dependencies(self, repo_id: str, entity_name: str) -> list[dict]:
        """Functions that `entity_name` calls. Scoped to a repo (id or name) when
        one resolves, else across all onboarded repos."""
        canonical = await self._resolve_repo_id(repo_id)
        caller = "{repo_id: $repo_id, name: $name}" if canonical else "{name: $name}"
        return await self.run(f"""
        MATCH (a:Function {caller})-[:CALLS]->(b:Function)
        RETURN b.file_path AS file, b.name AS callee, b.language AS language
        LIMIT 50
        """, repo_id=canonical, name=entity_name)

    async def _resolve_repo_id(self, value: str) -> str | None:
        """Map a repo_id OR a human repo name to the canonical repo_id stored on
        graph nodes. The agent often passes a repo's local name (e.g. 'kit-fork')
        while nodes carry the UUID; without this, queries match nothing."""
        if not value:
            return None
        rec = await self.run_single("""
        MATCH (r:Repository)
        WHERE r.repo_id = $v OR r.name = $v
        RETURN r.repo_id AS repo_id
        LIMIT 1
        """, v=value)
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
        return await self.run(f"""
        MATCH (f:File)
        {where}
        OPTIONAL MATCH (fn:Function)-[:PART_OF]->(f)
        RETURN f.repo_id AS repo_id, f.path AS file, f.language AS language,
               f.role AS role, count(fn) AS function_count
        ORDER BY function_count DESC, file ASC
        LIMIT 40
        """, repo_id=canonical)

    async def get_module_graph(self, repo_id: str) -> dict:
        nodes = await self.run("""
        MATCH (m:Module {repo_id: $repo_id})
        OPTIONAL MATCH (m)<-[:PART_OF]-(f:File)
        RETURN m.name AS name, "Module" AS type, count(f) AS weight
        """, repo_id=repo_id)

        edges = await self.run("""
        MATCH (a:Module {repo_id: $repo_id})<-[:PART_OF]-(:File)<-[:PART_OF]-(:Function)-[:CALLS]->
              (:Function)-[:PART_OF]->(:File)-[:PART_OF]->(b:Module {repo_id: $repo_id})
        WHERE a.name < b.name
        RETURN a.name AS source, b.name AS target, count(*) AS weight
        """, repo_id=repo_id)

        return {"nodes": nodes, "edges": edges}

    async def create_note_node(self, note_id: str, title: str, entity_id: str | None = None) -> None:
        await self.run("""
        CREATE (n:Note {id: $id, title: $title})
        """, id=note_id, title=title)

    async def link_note_to_entity(self, note_id: str, entity_type: str, entity_params: dict) -> None:
        match_clause = "{" + ", ".join(f"{k}: ${k}" for k in entity_params) + "}"
        query = f"""
        MATCH (n:Note {{id: $note_id}})
        MATCH (e:{entity_type} {match_clause})
        MERGE (n)-[:KNOWS_ABOUT]->(e)
        """
        await self.run(query, note_id=note_id, **entity_params)

    async def search_graph(self, query: str, limit: int = 20) -> list[dict]:
        return await self.run("""
        MATCH (n)
        WHERE any(label IN labels(n) WHERE label IN ['Function', 'Class', 'Module', 'File', 'Feature'])
        AND (n.name CONTAINS $query OR n.title CONTAINS $query OR n.path CONTAINS $query)
        RETURN labels(n)[0] AS type, n {.*} AS properties
        LIMIT $limit
        """, query=query, limit=limit)

    def _resolve_repo_name(self, repo_id: str) -> str:
        return repo_id

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
