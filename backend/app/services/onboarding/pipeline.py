from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from celery import chain, group
from structlog import get_logger

from app.workers.celery_app import celery_app

logger = get_logger(__name__)


class OnboardingStage(str, Enum):
    REPO_DISCOVERY = "repo_discovery"
    HISTORY_MINING = "history_mining"
    CODE_ANALYSIS = "code_analysis"
    PEOPLE_PROFILING = "people_profiling"
    FEATURE_EXTRACTION = "feature_extraction"
    GRAPH_BUILDING = "graph_building"
    EMBEDDING = "embedding"
    SYNTHESIS = "synthesis"
    TECH_DEBT_SCAN = "tech_debt_scan"
    STYLE_LEARNING = "style_learning"
    DEPENDENCY_SCAN = "dependency_scan"
    INTRO_REPORT = "intro_report"


STAGES = list(OnboardingStage)


def start_onboarding(repo_id: str, github_url: str, local_name: str) -> str:
    pipeline_id = str(uuid4())
    logger.info("onboarding_started", pipeline_id=pipeline_id, repo=local_name)

    task_chain = chain(
        _stage_task.s(prev_result=None, pipeline_id=pipeline_id, repo_id=repo_id, stage=OnboardingStage.REPO_DISCOVERY.value, github_url=github_url, local_name=local_name),
        _stage_task.s(pipeline_id=pipeline_id, repo_id=repo_id, stage=OnboardingStage.HISTORY_MINING.value, github_url=github_url, local_name=local_name),
        _stage_task.s(pipeline_id=pipeline_id, repo_id=repo_id, stage=OnboardingStage.CODE_ANALYSIS.value, github_url=github_url, local_name=local_name),
        _stage_task.s(pipeline_id=pipeline_id, repo_id=repo_id, stage=OnboardingStage.PEOPLE_PROFILING.value, github_url=github_url, local_name=local_name),
        _stage_task.s(pipeline_id=pipeline_id, repo_id=repo_id, stage=OnboardingStage.FEATURE_EXTRACTION.value, github_url=github_url, local_name=local_name),
        _stage_task.s(pipeline_id=pipeline_id, repo_id=repo_id, stage=OnboardingStage.GRAPH_BUILDING.value, github_url=github_url, local_name=local_name),
        _stage_task.s(pipeline_id=pipeline_id, repo_id=repo_id, stage=OnboardingStage.EMBEDDING.value, github_url=github_url, local_name=local_name),
        _stage_task.s(pipeline_id=pipeline_id, repo_id=repo_id, stage=OnboardingStage.SYNTHESIS.value, github_url=github_url, local_name=local_name),
        _stage_task.s(pipeline_id=pipeline_id, repo_id=repo_id, stage=OnboardingStage.TECH_DEBT_SCAN.value, github_url=github_url, local_name=local_name),
        _stage_task.s(pipeline_id=pipeline_id, repo_id=repo_id, stage=OnboardingStage.STYLE_LEARNING.value, github_url=github_url, local_name=local_name),
        _stage_task.s(pipeline_id=pipeline_id, repo_id=repo_id, stage=OnboardingStage.DEPENDENCY_SCAN.value, github_url=github_url, local_name=local_name),
        _stage_task.s(pipeline_id=pipeline_id, repo_id=repo_id, stage=OnboardingStage.INTRO_REPORT.value, github_url=github_url, local_name=local_name),
    )
    task_chain.apply_async()
    return pipeline_id


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def _stage_task(
    self,
    prev_result: Any = None,
    pipeline_id: str = "",
    repo_id: str = "",
    stage: str = "",
    github_url: str = "",
    local_name: str = "",
) -> dict:
    logger.info("stage_started", pipeline_id=pipeline_id, stage=stage)

    try:
        _save_stage_status(repo_id, stage, "running")
        result = _execute_stage(pipeline_id, repo_id, OnboardingStage(stage) if stage else None, prev_result, github_url, local_name)
        _save_stage_status(repo_id, stage, "completed")
        logger.info("stage_completed", pipeline_id=pipeline_id, stage=stage)
        return result
    except Exception as e:
        logger.error("stage_failed", pipeline_id=pipeline_id, stage=stage, error=str(e))
        _save_stage_status(repo_id, stage, "failed", str(e))
        raise self.retry(exc=e)


def _save_stage_status(repo_id: str, stage_name: str, status: str, error: str = None):
    from datetime import datetime, timezone
    from sqlalchemy import create_engine, select as _select
    from sqlalchemy.orm import Session
    from app.models.repo import RepoOnboardingState
    from app.config import settings as _s

    try:
        engine = create_engine(_s.database_url.replace("+asyncpg", "+psycopg2"), pool_pre_ping=True)
        with Session(engine) as db:
            result = db.execute(_select(RepoOnboardingState).where(
                RepoOnboardingState.repo_id == repo_id, RepoOnboardingState.stage == stage_name))
            row = result.scalar_one_or_none()
            now = datetime.now(timezone.utc)
            if row:
                row.status = status
                if error: row.error = error
                if status == "completed": row.completed_at = now
                elif status == "running": row.started_at = now
            else:
                db.add(RepoOnboardingState(repo_id=repo_id, stage=stage_name, status=status,
                    error=error, started_at=now if status=="running" else None,
                    completed_at=now if status=="completed" else None))
            db.commit()
        engine.dispose()
    except Exception as e:
        logger.warning("save_stage_status_failed", repo_id=repo_id, stage=stage_name, error=str(e)[:200])


def _execute_stage(
    pipeline_id: str,
    repo_id: str,
    stage: OnboardingStage,
    prev_result: Any,
    github_url: str,
    local_name: str,
) -> dict:
    import asyncio
    from app.services.onboarding.git_crawler import GitCrawler
    from app.services.onboarding.people_profiler import PeopleProfiler
    from app.services.onboarding.code_parser import CodeParser
    from app.services.onboarding.graph_builder import GraphBuilder
    from app.services.onboarding.embedding_builder import EmbeddingBuilder
    from app.services.onboarding.tech_debt_scanner import TechDebtScanner
    from app.services.onboarding.dependency_scanner import DependencyScanner
    from app.services.onboarding.feature_extractor import FeatureExtractor
    from app.services.onboarding.synthesizer import Synthesizer

    if stage == OnboardingStage.REPO_DISCOVERY:
        crawler = GitCrawler()
        info = crawler.crawl(github_url, local_name)
        return {
            "stage": stage,
            "name": info.name,
            "default_branch": info.default_branch,
            "branches": info.branches,
            "commit_count": info.commit_count,
            "contributor_count": info.contributor_count,
            "languages": info.languages,
            "total_files": info.total_files,
            "clone_path": info.clone_path,
        }

    elif stage == OnboardingStage.HISTORY_MINING:
        clone_path = _get_clone_path(prev_result)
        name = _get_repo_name(prev_result) or local_name
        return {"stage": stage, "clone_path": clone_path, "name": name, "processed": True}

    elif stage == OnboardingStage.CODE_ANALYSIS:
        parser = CodeParser()
        supported = parser.get_supported_languages()
        clone_path = _get_clone_path(prev_result)
        name = _get_repo_name(prev_result) or local_name
        return {"stage": stage, "supported_languages": supported, "clone_path": clone_path, "name": name}

    elif stage == OnboardingStage.PEOPLE_PROFILING:
        profiler = PeopleProfiler()
        clone_path = _get_clone_path(prev_result)
        name = _get_repo_name(prev_result) or local_name
        profiles = profiler.profile_repo(clone_path) if clone_path else {}
        return {"stage": stage, "contributors": len(profiles), "clone_path": clone_path, "name": name}

    elif stage == OnboardingStage.FEATURE_EXTRACTION:
        extractor = FeatureExtractor()
        clone_path = _get_clone_path(prev_result)
        name = _get_repo_name(prev_result) or local_name
        features = extractor.extract(clone_path) if clone_path else []
        return {"stage": stage, "features": len(features), "clone_path": clone_path, "name": name}

    elif stage == OnboardingStage.GRAPH_BUILDING:
        clone_path = _get_clone_path(prev_result)
        name = _get_repo_name(prev_result) or local_name
        if not clone_path:
            return {"stage": stage, "error": "No clone path", "clone_path": ""}
        result = _build_graph_sync(repo_id, name, clone_path)
        return {"stage": stage, **result, "clone_path": clone_path, "name": name}

    elif stage == OnboardingStage.EMBEDDING:
        clone_path = _get_clone_path(prev_result)
        name = _get_repo_name(prev_result) or local_name
        if not clone_path:
            return {"stage": stage, "error": "No clone path", "clone_path": ""}
        result = _build_embeddings_sync(repo_id, clone_path)
        return {"stage": stage, **result, "clone_path": clone_path, "name": name}

    elif stage == OnboardingStage.SYNTHESIS:
        clone_path = _get_clone_path(prev_result)
        name = _get_repo_name(prev_result) or local_name
        repo_name = name
        notes_count = _create_synthesis_notes_sync(repo_id, repo_name, prev_result, clone_path)
        return {"stage": stage, "notes": notes_count, "clone_path": clone_path, "name": name}

    elif stage == OnboardingStage.DEPENDENCY_SCAN:
        clone_path = _get_clone_path(prev_result)
        name = _get_repo_name(prev_result) or local_name
        scanner = DependencyScanner()
        deps = asyncio.run(scanner.scan(repo_id, clone_path))
        return {"stage": stage, "dependencies_found": len(deps), "clone_path": clone_path, "name": name}

    elif stage == OnboardingStage.TECH_DEBT_SCAN:
        clone_path = _get_clone_path(prev_result)
        name = _get_repo_name(prev_result) or local_name
        scanner = TechDebtScanner()
        items = asyncio.run(scanner.scan(repo_id, clone_path))
        return {"stage": stage, "items_found": len(items), "clone_path": clone_path, "name": name}

    elif stage == OnboardingStage.STYLE_LEARNING:
        clone_path = _get_clone_path(prev_result)
        name = _get_repo_name(prev_result) or local_name
        styles = _learn_styles(clone_path)
        return {"stage": stage, "conventions_found": len(styles), "clone_path": clone_path, "name": name, "processed": True}

    elif stage == OnboardingStage.INTRO_REPORT:
        _persist_memory_sync()
        name = _get_repo_name(prev_result) or local_name
        return {"stage": stage, "report_generated": True, "name": name}

    return {"stage": stage, "processed": True}


import asyncio


def _get_clone_path(prev_result: Any) -> str:
    if isinstance(prev_result, dict):
        path = prev_result.get("clone_path", "")
        if path:
            return path
    return f"/data/repos/{prev_result.get('name', 'unknown')}" if isinstance(prev_result, dict) else ""


def _get_repo_name(prev_result: Any) -> str | None:
    if isinstance(prev_result, dict):
        return prev_result.get("name")
    return None


def _learn_styles(clone_path: str) -> list[str]:
    from pathlib import Path as _P
    conventions: list[str] = []
    root = _P(clone_path) if clone_path else None
    if not root or not root.exists():
        return conventions

    indent_found: dict[str, int] = {}
    py_files = list(root.rglob("*.py"))[:200]
    for fp in py_files:
        try:
            first_line = fp.read_text().splitlines()[0] if fp.read_text().splitlines() else ""
            if first_line.startswith("    "):
                indent_found["spaces_4"] = indent_found.get("spaces_4", 0) + 1
            elif first_line.startswith("\t"):
                indent_found["tabs"] = indent_found.get("tabs", 0) + 1
            elif first_line.startswith("  "):
                indent_found["spaces_2"] = indent_found.get("spaces_2", 0) + 1
        except Exception:
            pass

    if indent_found:
        dominant = max(indent_found, key=indent_found.get)
        conventions.append(f"Indentation: {dominant} ({indent_found[dominant]} of {sum(indent_found.values())} files)")
    return conventions


def _build_graph_sync(repo_id: str, repo_name: str, clone_path: str) -> dict:
    from pathlib import Path
    import json, urllib.request, base64
    from app.config import settings as _s
    from app.services.knowledge.graph_ids import node_id, edge_id, EXTRACTOR_VERSION
    from app.services.knowledge.repo_manifest import RepoManifest
    from app.services.onboarding.code_parser import CodeParser

    root = Path(clone_path)
    if not root.exists():
        return {"files_processed": 0, "entities_found": 0, "relationships_created": 0}

    parser = CodeParser()
    auth = base64.b64encode(f"{_s.neo4j_user}:{_s.neo4j_password}".encode()).decode()
    statements = []
    files_processed = 0
    entities_found = 0
    relationships_created = 0

    repo_nid = node_id(repo_id, "Repository", repo_name)
    statements.append({
        "statement": "MERGE (r:Repository {id: $id}) SET r.repo_id = $repo_id, r.name = $name, r.version = $version",
        "parameters": {"id": repo_nid, "repo_id": repo_id, "name": repo_name, "version": EXTRACTOR_VERSION}
    })

    lang_map = {".py": "python", ".js": "javascript", ".ts": "typescript",
                ".tsx": "typescript", ".go": "go", ".rs": "rust", ".java": "java"}

    for file_path in root.rglob("*"):
        if not file_path.is_file() or ".git" in file_path.parts:
            continue
        files_processed += 1
        if files_processed > 500:
            break

        rel = str(file_path.relative_to(root))
        ext = file_path.suffix
        lang = lang_map.get(ext, "")
        role = RepoManifest.classify_path_role(rel)
        file_nid = node_id(repo_id, "File", rel)

        try:
            content = file_path.read_text(errors="replace")
        except Exception:
            content = ""

        statements.append({
            "statement": "MERGE (f:File {id: $id}) SET f.repo_id = $repo_id, f.path = $path, f.language = $lang, f.role = $role, f.version = $version WITH f MATCH (r:Repository {id: $repo_nid}) MERGE (f)-[:PART_OF]->(r)",
            "parameters": {"id": file_nid, "repo_id": repo_id, "path": rel, "lang": lang, "role": role, "version": EXTRACTOR_VERSION, "repo_nid": repo_nid}
        })
        entities_found += 1

        # Parse with tree-sitter for entity extraction
        analysis = parser.parse_file(str(file_path))
        if analysis:
            for entity in analysis.entities:
                if entity.kind == "function":
                    fn_nid = node_id(repo_id, "Function", rel, entity.name)
                    statements.append({
                        "statement": "MERGE (fn:Function {id: $id}) SET fn.repo_id = $repo_id, fn.file_path = $path, fn.name = $name, fn.start_line = $start, fn.end_line = $end, fn.language = $lang, fn.signature = $sig, fn.version = $v WITH fn MATCH (f:File {id: $fid}) MERGE (fn)-[:PART_OF]->(f)",
                        "parameters": {"id": fn_nid, "repo_id": repo_id, "path": rel, "name": entity.name, "start": entity.start_line, "end": entity.end_line, "lang": lang, "sig": entity.signature or "", "v": EXTRACTOR_VERSION, "fid": file_nid}
                    })
                    entities_found += 1
                elif entity.kind == "class":
                    cls_nid = node_id(repo_id, "Class", rel, entity.name)
                    statements.append({
                        "statement": "MERGE (c:Class {id: $id}) SET c.repo_id = $repo_id, c.file_path = $path, c.name = $name, c.start_line = $start, c.end_line = $end, c.language = $lang, c.version = $v WITH c MATCH (f:File {id: $fid}) MERGE (c)-[:PART_OF]->(f)",
                        "parameters": {"id": cls_nid, "repo_id": repo_id, "path": rel, "name": entity.name, "start": entity.start_line, "end": entity.end_line, "lang": lang, "v": EXTRACTOR_VERSION, "fid": file_nid}
                    })
                    entities_found += 1

            for dep in analysis.dependencies:
                if dep.kind == "imports" and dep.target:
                    for mod_name in dep.target.replace("import ", "").replace("from ", "").split(","):
                        clean = mod_name.strip().strip("\"'").split()[0].lstrip(".")
                        if clean and not clean.startswith("."):
                            mod_nid = node_id(repo_id, "Module", clean)
                            statements.append({
                                "statement": "MERGE (m:Module {id: $id}) SET m.repo_id = $repo_id, m.name = $name, m.version = $v WITH m MATCH (r:Repository {id: $rnid}) MERGE (m)-[:PART_OF]->(r)",
                                "parameters": {"id": mod_nid, "repo_id": repo_id, "name": clean, "v": EXTRACTOR_VERSION, "rnid": repo_nid}
                            })
                            relationships_created += 1
                elif dep.kind == "calls" and dep.target:
                    caller_nid = node_id(repo_id, "Function", rel, dep.source or "")
                    statements.append({
                        "statement": "MATCH (a:Function {id: $cid}) MERGE (b:Function {repo_id: $repo_id, name: $cname}) MERGE (a)-[r:CALLS]->(b) SET r.version = $v",
                        "parameters": {"cid": caller_nid, "repo_id": repo_id, "cname": dep.target, "v": EXTRACTOR_VERSION}
                    })
                    relationships_created += 1

    # Ownership edges: the primary contributor per file (the one with the most
    # commits to it) becomes its OWNS owner, so find_owner / "who should review
    # this?" returns data. Files must already be MERGE'd above (they come first
    # in the statement list, hence in earlier batches), so the OWNS MATCH lands.
    try:
        from app.services.onboarding.people_profiler import PeopleProfiler
        profiles = PeopleProfiler().profile_repo(clone_path)
        for prof in profiles.values():
            if not prof.owned_files:
                continue
            contrib_nid = node_id("", "Contributor", prof.email)
            statements.append({
                "statement": "MERGE (c:Contributor {id: $id}) SET c.email = $email, c.name = $name, c.version = $v",
                "parameters": {"id": contrib_nid, "email": prof.email, "name": prof.name, "v": EXTRACTOR_VERSION}
            })
            for owned in prof.owned_files:
                owned_fid = node_id(repo_id, "File", owned)
                statements.append({
                    "statement": "MATCH (c:Contributor {id: $cid}) MATCH (f:File {id: $fid}) MERGE (c)-[o:OWNS]->(f) SET o.weight = $w, o.version = $v",
                    "parameters": {"cid": contrib_nid, "fid": owned_fid, "w": prof.commit_count, "v": EXTRACTOR_VERSION}
                })
                relationships_created += 1
    except Exception as e:
        logger.warning("ownership_build_failed", repo=repo_name, error=str(e)[:100])

    for i in range(0, len(statements), 100):
        batch = statements[i:i+100]
        try:
            data = json.dumps({"statements": batch}).encode()
            host = _s.neo4j_uri.replace("bolt://", "").split(":")[0]
            req = urllib.request.Request(f"http://{host}:7474/db/neo4j/tx/commit", data=data,
                headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"})
            urllib.request.urlopen(req, timeout=60)
        except Exception as e:
            logger.warning("neo4j_batch_failed", repo=repo_name, error=str(e)[:100])

    return {"files_processed": files_processed, "entities_found": entities_found, "relationships_created": relationships_created}


def _build_embeddings_sync(repo_id: str, clone_path: str) -> dict:
    from pathlib import Path
    from sqlalchemy import create_engine, text as sqla_text
    from app.config import settings as _s
    from app.services.knowledge.chunker import CodeChunker
    import hashlib

    root = Path(clone_path)
    if not root.exists():
        return {"files_scanned": 0, "chunks_created": 0, "chunks_stored": 0}

    try:
        from sentence_transformers import SentenceTransformer
        from app.services.knowledge.embedding_schema import reconcile_embeddings_dim

        engine = create_engine(_s.database_url.replace("+asyncpg", "+psycopg2"), pool_pre_ping=True)

        # Load the model first so the table dimension matches what it actually
        # emits (local all-MiniLM = 384, OpenAI = 1536). A mismatch makes every
        # pgvector insert fail with "expected N dimensions".
        model = SentenceTransformer(_s.embedding_model)
        dim = model.get_sentence_embedding_dimension() or len(model.encode(["x"])[0])
        chunker = CodeChunker()

        # Create the table at the right dimension, and reconcile an existing
        # table that was created with the wrong one (embeddings are regenerable).
        with engine.begin() as conn:
            conn.execute(sqla_text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(sqla_text(f"""
            CREATE TABLE IF NOT EXISTS code_embeddings (
                id VARCHAR(32) PRIMARY KEY,
                text TEXT NOT NULL,
                embedding vector({dim}),
                file_path VARCHAR(1024) NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                entity_type VARCHAR(50),
                language VARCHAR(50),
                entity_name VARCHAR(255)
            )
            """))
            action = reconcile_embeddings_dim(conn, dim)
        if action == "fixed":
            logger.warning("embeddings_table_dim_reset", repo=repo_id, dim=dim)

        files_scanned = 0
        chunks_stored = 0
        lang_map = {".py": "python", ".js": "javascript", ".ts": "typescript",
                    ".tsx": "typescript", ".go": "go", ".rs": "rust", ".java": "java"}
        all_chunks = []

        for file_path in root.rglob("*"):
            if not file_path.is_file() or ".git" in file_path.parts:
                continue
            if files_scanned >= 5000:
                break

            ext = file_path.suffix.lower()
            lang = lang_map.get(ext)
            if not lang:
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if not content.strip():
                continue

            chunks = chunker.chunk_file(content, str(file_path.relative_to(root)), lang)
            all_chunks.extend(chunks)
            files_scanned += 1

        insert_errors: list[str] = []
        if all_chunks:
            texts = [c.text for c in all_chunks]
            vectors = model.encode(texts, show_progress_bar=False).tolist()

            # One savepoint per row: a single bad row no longer poisons the whole
            # transaction (the old code shared one transaction + swallowed every
            # error, so one failure silently lost the entire batch).
            with engine.connect() as conn:
                with conn.begin():
                    for chunk, vector in zip(all_chunks, vectors):
                        # Identify a chunk by repo + path + span + its text. Paths are
                        # repo-relative (two repos can share src/index.js) and the
                        # chunker can emit several windows for one entity span, so
                        # anything coarser silently overwrites distinct chunks; the
                        # text keeps windows distinct while a re-onboard of unchanged
                        # code stays idempotent.
                        chunk_id = hashlib.md5(
                            f"{repo_id}:{chunk.file_path}:{chunk.start_line}:{chunk.end_line}:{chunk.text}".encode()
                        ).hexdigest()
                        vector_str = "[" + ",".join(str(v) for v in vector) + "]"
                        try:
                            with conn.begin_nested():
                                conn.execute(sqla_text(
                                    "INSERT INTO code_embeddings (id, text, embedding, file_path, start_line, end_line, entity_type, language, entity_name) "
                                    "VALUES (:id, :text, CAST(:emb AS vector), :fp, :sl, :el, :et, :la, :en) "
                                    "ON CONFLICT (id) DO UPDATE SET embedding = EXCLUDED.embedding, text = EXCLUDED.text"
                                ), {"id": chunk_id, "text": chunk.text, "emb": vector_str, "fp": chunk.file_path,
                                    "sl": chunk.start_line, "el": chunk.end_line, "et": chunk.entity_type,
                                    "la": chunk.language, "en": chunk.entity_name})
                            chunks_stored += 1
                        except Exception as e:
                            if len(insert_errors) < 3:
                                insert_errors.append(f"{type(e).__name__}: {str(e)[:160]}")

        if insert_errors:
            logger.error("embedding_insert_errors", repo=repo_id, stored=chunks_stored,
                         total=len(all_chunks), samples=insert_errors)

        engine.dispose()
        return {"files_scanned": files_scanned, "chunks_created": len(all_chunks), "chunks_stored": chunks_stored}
    except Exception as e:
        logger.error("embedding_build_failed", repo=repo_id, error=str(e)[:200])
        return {"files_scanned": 0, "chunks_created": 0, "chunks_stored": 0, "error": str(e)[:200]}


def _persist_memory_sync():
    try:
        from sqlalchemy import create_engine, text
        from app.config import settings as _s
        import json
        engine = create_engine(_s.database_url.replace("+asyncpg", "+psycopg2"), pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM app_config WHERE key = 'memory_state'"))
            conn.execute(text("INSERT INTO app_config (key, value) VALUES ('memory_state', :val)"),
                         {"val": json.dumps({"preferences": {}, "conventions": ["Onboarding complete"], "episodic": []})})
            conn.commit()
        engine.dispose()
    except Exception as e:
        logger.warning("persist_memory_failed", error=str(e)[:200])


def _create_synthesis_notes_sync(repo_id: str, repo_name: str, prev_result: dict, clone_path: str) -> int:
    from pathlib import Path
    from sqlalchemy import create_engine, text
    from app.config import settings as _s
    import uuid

    if not clone_path or not Path(clone_path).exists():
        return 0

    notes = []
    root = Path(clone_path)
    all_files = [f for f in root.rglob("*") if f.is_file() and ".git" not in f.parts]
    py_count = sum(1 for f in all_files if f.suffix == ".py")
    total = len(all_files)

    langs: dict[str, int] = {}
    for f in all_files:
        ext = f.suffix or "noext"
        langs[ext] = langs.get(ext, 0) + 1
    top_langs = sorted(langs.items(), key=lambda x: x[1], reverse=True)[:5]
    lang_str = ", ".join(f"{e}({c})" for e, c in top_langs)

    notes.append((
        f"Architecture — {repo_name}",
        f"# {repo_name}\n\n- **Files**: {total}\n- **Python**: {py_count}\n- **Languages**: {lang_str}",
        repo_id,
    ))

    key_files = [(f, f.stat().st_size) for f in all_files if f.stat().st_size > 200][:15]
    if key_files:
        notes.append((
            f"Key Files — {repo_name}",
            "## Key Files\n\n" + "\n".join(f"- `{str(f.relative_to(root))}` ({s}B)" for f, s in sorted(key_files, key=lambda x: x[1], reverse=True)),
            repo_id,
        ))

    try:
        engine = create_engine(_s.database_url.replace("+asyncpg", "+psycopg2"), pool_pre_ping=True)
        with engine.connect() as conn:
            for title, content, eid in notes:
                nid = str(uuid.uuid4())
                conn.execute(text(
                    "INSERT INTO notes (id, title, content, entity_type, entity_id, created_at, updated_at) "
                    "VALUES (:id, :t, :c, 'repo', :e, NOW(), NOW())"
                ), {"id": nid, "t": title, "c": content, "e": eid})
            conn.commit()
        engine.dispose()
        return len(notes)
    except Exception as e:
        logger.warning("synthesis_notes_failed", repo=repo_name, error=str(e)[:200])
        return 0
