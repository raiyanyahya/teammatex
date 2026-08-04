"""Extract Knowledge-page concept cards from an onboarded repo.

The Knowledge page needs cards like the design's `auth · module · Token-based
auth with refresh rotation, integrated with company SSO · 142 refs · 24
files · @maya, @jin`. Directory paths alone can't yield that prose — the
summaries come from the LLM reading the repo's structure + contributors and
naming the concepts it sees.

This module:
  1. Pulls a compact view of the repo (file tree + per-contributor ownership
     + top language) from Neo4j.
  2. Asks the configured LLM for a strict-JSON list of concepts.
  3. Computes `files`/`refs` from the file_paths the LLM picked (refs is the
     number of `Function` graph nodes inside those files — a real signal,
     not a guess).
  4. Resolves expert handles back to actual contributor records.
  5. Upserts a row per concept into the `concepts` table.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.models.concept import Concept
from app.models.repo import Repo
from app.services.knowledge.graph import KnowledgeGraph
from app.services.llm.provider import LLMProvider

logger = get_logger(__name__)

CATS = {"module", "subsystem", "project", "concept"}
MAX_FILES_IN_PROMPT = 120
MAX_CONTRIBUTORS_IN_PROMPT = 20


class ConceptExtractor:
    def __init__(self, graph: KnowledgeGraph | None = None) -> None:
        self.graph = graph or KnowledgeGraph()

    async def extract_for_repo(self, db: AsyncSession, repo_id: str) -> list[dict]:
        """Generate + upsert concepts for one repo. Returns the persisted rows
        as plain dicts (the same shape /api/knowledge/concepts returns)."""
        repo = (await db.execute(select(Repo).where(Repo.id == repo_id))).scalar_one_or_none()
        if not repo:
            return []

        files = await self._files_for_repo(repo_id)
        contributors = await self._contributors_for_repo(repo_id)
        if not files:
            logger.info("concept_extract_skipped_empty_repo", repo_id=repo_id)
            return []

        payload = self._build_prompt(repo.local_name, files, contributors)
        raw = await LLMProvider.simple_prompt(
            system=(
                "You name the meaningful concepts that live inside a codebase. "
                "Read the file tree and contributor map you are given and return "
                "between 4 and 10 concept cards. A good concept is something a "
                "teammate would mention by name (auth, billing, queue, observability, "
                "rate-limit) — never the language or framework itself. "
                "Respond with a single JSON object matching the schema and nothing else."
            ),
            user=payload,
            temperature=0.2,
            call_type="concept_extraction",
        )
        items = self._parse_response(raw)
        if not items:
            logger.warning("concept_extract_empty_parse", repo_id=repo_id, sample=raw[:200])
            return []

        # Build a path → function-count map so refs is a real signal.
        function_counts = await self._function_counts_for_repo(repo_id)

        # Index contributors so we can resolve "maya" or "maya@x" back to a record.
        contrib_by_handle = {self._handle_for(c): c for c in contributors}
        contrib_by_email = {c["email"].lower(): c for c in contributors if c.get("email")}

        out: list[dict] = []
        model_label = "llm"  # provider doesn't echo this back through simple_prompt; keep generic.
        now = datetime.now(UTC)

        for raw_concept in items:
            name = (raw_concept.get("name") or "").strip()[:120]
            cat = (raw_concept.get("cat") or "").strip().lower()
            summary = (raw_concept.get("summary") or "").strip()
            if not name or cat not in CATS or not summary:
                continue
            file_paths = [p for p in raw_concept.get("file_paths") or [] if isinstance(p, str)]
            experts_in = raw_concept.get("experts") or []

            files_count = len(file_paths)
            refs_count = sum(function_counts.get(p, 0) for p in file_paths)

            experts = []
            for handle in experts_in[:6]:
                if not isinstance(handle, str):
                    continue
                key = handle.lstrip("@").strip().lower()
                c = contrib_by_email.get(key) or contrib_by_handle.get(key)
                if c:
                    experts.append(
                        {
                            "name": c.get("name") or key,
                            "email": c.get("email"),
                            "weight": c.get("files_owned", 0),
                        }
                    )
                else:
                    experts.append({"name": handle.lstrip("@"), "email": None, "weight": 0})

            await self._upsert(
                db, repo_id, name, cat, summary, files_count, refs_count, experts, now, model_label
            )
            out.append(
                {
                    "name": name,
                    "cat": cat,
                    "summary": summary,
                    "files": files_count,
                    "refs": refs_count,
                    "experts": experts,
                }
            )

        await db.commit()
        logger.info("concept_extract_done", repo_id=repo_id, count=len(out))
        return out

    async def extract_for_all(self, db: AsyncSession) -> dict:
        """Convenience: run for every active repo in one go. Returns a summary
        keyed by repo so the frontend can show per-repo counts."""
        repos = (
            (await db.execute(select(Repo).where(Repo.is_active == True))).scalars().all()
        )  # noqa: E712
        result: dict[str, int] = {}
        for repo in repos:
            try:
                produced = await self.extract_for_repo(db, repo.id)
                result[repo.local_name] = len(produced)
            except Exception as e:
                logger.warning("concept_extract_failed", repo=repo.local_name, error=str(e)[:200])
                result[repo.local_name] = 0
        return result

    # ─── helpers ──────────────────────────────────────────────────────

    async def _files_for_repo(self, repo_id: str) -> list[dict]:
        return await self.graph.run(
            """
            MATCH (f:File)-[:PART_OF]->(r:Repository {repo_id: $repo_id})
            WHERE NOT f.path CONTAINS 'node_modules'
              AND NOT f.path CONTAINS '__pycache__'
              AND NOT f.path CONTAINS '/vendor/'
              AND NOT f.path CONTAINS '/dist/'
              AND NOT f.path CONTAINS '/build/'
              AND NOT f.path CONTAINS '/.next/'
            RETURN f.path AS path, f.language AS language
            ORDER BY f.path
            """,
            repo_id=repo_id,
        )

    async def _contributors_for_repo(self, repo_id: str) -> list[dict]:
        return await self.graph.run(
            """
            MATCH (c:Contributor)-[:OWNS]->(f:File {repo_id: $repo_id})
            WITH c, count(DISTINCT f) AS files_owned, collect(DISTINCT f.language) AS languages
            RETURN c.name AS name, c.email AS email, files_owned,
                   [x IN languages WHERE x <> ""] AS languages
            ORDER BY files_owned DESC
            LIMIT $limit
            """,
            repo_id=repo_id,
            limit=MAX_CONTRIBUTORS_IN_PROMPT,
        )

    async def _function_counts_for_repo(self, repo_id: str) -> dict[str, int]:
        rows = await self.graph.run(
            """
            MATCH (fn:Function {repo_id: $repo_id})
            RETURN fn.file_path AS path, count(fn) AS c
            """,
            repo_id=repo_id,
        )
        return {r["path"]: int(r["c"] or 0) for r in rows if r["path"]}

    def _handle_for(self, contributor: dict) -> str:
        name = (contributor.get("name") or "").strip().lower()
        if name:
            return name.split()[0]
        email = (contributor.get("email") or "").strip().lower()
        return email.split("@")[0] if email else ""

    def _build_prompt(self, repo_name: str, files: list[dict], contributors: list[dict]) -> str:
        # Truncate the file list deterministically so prompt size stays bounded
        # on huge repos. Take a stratified sample by top-level directory so the
        # LLM still sees the shape of the tree.
        sampled = self._sample_files(files, MAX_FILES_IN_PROMPT)
        file_lines_parts: list[str] = []
        for f in sampled:
            path = f.get("path") or ""
            lang = f.get("language") or ""
            file_lines_parts.append(f"- {path} ({lang})" if lang else f"- {path}")
        file_lines = "\n".join(file_lines_parts)

        contrib_lines_parts: list[str] = []
        for c in contributors:
            handle = self._handle_for(c)
            email = c.get("email", "?")
            owned = c.get("files_owned", 0)
            line = f"- @{handle} <{email}> owns {owned} files"
            langs = (c.get("languages") or [])[:3]
            if langs:
                line += f" · langs: {', '.join(langs)}"
            contrib_lines_parts.append(line)
        contrib_lines = "\n".join(contrib_lines_parts)

        schema_hint = (
            '{"concepts": ['
            '{"name": "auth", "cat": "module", '
            '"summary": "one sentence, max ~140 chars", '
            '"file_paths": ["src/...", "..."], '
            '"experts": ["@maya", "@jin"]}'
            "]}"
        )
        rules = (
            "Rules:\n"
            "- `cat` MUST be one of: module, subsystem, project, concept.\n"
            "- module: a top-level code area (auth, billing).\n"
            "- subsystem: a cross-cutting capability (observability, CI cache).\n"
            "- project: a named in-flight effort (NATS migration, v2 rewrite).\n"
            "- concept: a recurring pattern or invariant (rate-limit, webhook idempotency).\n"
            "- Pick file_paths from the file list ONLY — never invent paths.\n"
            "- Pick experts from the contributor list ONLY — use the @handle exactly.\n"
            "- 4 to 10 concepts. Skip anything that's just framework plumbing.\n"
            "- Summaries are descriptive, not marketing copy. No emoji.\n"
        )

        return (
            f"Repository: {repo_name}\n"
            f"Total files indexed: {len(files)} (showing up to {MAX_FILES_IN_PROMPT} below)\n\n"
            f"## File tree\n{file_lines}\n\n"
            f"## Contributors (by files owned)\n{contrib_lines or '(none)'}\n\n"
            f"## Output schema\n{schema_hint}\n\n"
            f"{rules}"
        )

    def _sample_files(self, files: list[dict], cap: int) -> list[dict]:
        if len(files) <= cap:
            return files
        # Stratify by top-level dir so a repo with one giant dir doesn't crowd
        # out the smaller ones.
        groups: dict[str, list[dict]] = {}
        for f in files:
            parts = (f.get("path") or "").split("/", 1)
            key = parts[0] if parts else ""
            groups.setdefault(key, []).append(f)
        # Round-robin take.
        out: list[dict] = []
        idxs = {k: 0 for k in groups}
        while len(out) < cap:
            took_any = False
            for k, group in groups.items():
                if idxs[k] < len(group):
                    out.append(group[idxs[k]])
                    idxs[k] += 1
                    took_any = True
                    if len(out) >= cap:
                        break
            if not took_any:
                break
        return out

    def _parse_response(self, raw: str) -> list[dict]:
        """LLMs sometimes wrap JSON in ```json fences or add chatter. Strip
        those and recover the first object that parses."""
        text = (raw or "").strip()
        if "```" in text:
            chunks = text.split("```")
            for chunk in chunks:
                stripped = chunk.strip()
                if stripped.startswith("json"):
                    stripped = stripped[4:].strip()
                if stripped.startswith("{"):
                    text = stripped
                    break
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            return []
        try:
            obj = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
        items = obj.get("concepts") if isinstance(obj, dict) else None
        return items if isinstance(items, list) else []

    async def _upsert(
        self,
        db: AsyncSession,
        repo_id: str,
        name: str,
        cat: str,
        summary: str,
        files: int,
        refs: int,
        experts: list,
        now: datetime,
        model: str,
    ) -> None:
        stmt = pg_insert(Concept).values(
            repo_id=repo_id,
            name=name,
            cat=cat,
            summary=summary,
            files=files,
            refs=refs,
            experts=experts,
            generated_at=now,
            generator_model=model,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_concept_repo_name",
            set_={
                "cat": stmt.excluded.cat,
                "summary": stmt.excluded.summary,
                "files": stmt.excluded.files,
                "refs": stmt.excluded.refs,
                "experts": stmt.excluded.experts,
                "generated_at": stmt.excluded.generated_at,
                "generator_model": stmt.excluded.generator_model,
            },
        )
        await db.execute(stmt)
