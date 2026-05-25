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
    import asyncio
    from pathlib import Path
    from app.services.onboarding.graph_builder import GraphBuilder

    root = Path(clone_path)
    if not root.exists():
        return {"files_processed": 0, "entities_found": 0, "relationships_created": 0}

    try:
        builder = GraphBuilder()
        result = asyncio.run(builder.build(repo_id, repo_name, clone_path))
        return result
    except Exception as e:
        logger.error("graph_build_failed", repo=repo_name, error=str(e)[:200])
        return {"files_processed": 0, "entities_found": 0, "relationships_created": 0, "error": str(e)[:200]}


def _build_embeddings_sync(repo_id: str, clone_path: str) -> dict:
    import asyncio
    from pathlib import Path
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from app.config import settings as _s
    from app.services.onboarding.embedding_builder import EmbeddingBuilder

    root = Path(clone_path)
    if not root.exists():
        return {"files_scanned": 0, "chunks_created": 0, "chunks_stored": 0}

    async_engine = None
    try:
        async_engine = create_async_engine(_s.database_url, pool_pre_ping=True)
        async_session = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

        async def _run():
            async with async_session() as db:
                builder = EmbeddingBuilder()
                return await builder.build(db, clone_path, repo_id)

        result = asyncio.run(_run())
        return result
    except Exception as e:
        logger.error("embedding_build_failed", repo=repo_id, error=str(e)[:200])
        return {"files_scanned": 0, "chunks_created": 0, "chunks_stored": 0, "error": str(e)[:200]}
    finally:
        if async_engine:
            asyncio.run(async_engine.dispose())


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
