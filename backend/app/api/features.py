from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.agent.proactive import (
    StandupGenerator,
    DocumentationGenerator,
    ReleaseNotesGenerator,
    TestGenerator,
)
from app.services.agent.self_extension import SelfExtension
from app.services.agent.proactive_extras import (
    SprintRetrospectiveAssistant,
    GitHygieneAutomation,
)

router = APIRouter(prefix="/features", tags=["features"])
standup = StandupGenerator()
doc_gen = DocumentationGenerator()
release_gen = ReleaseNotesGenerator()
test_gen = TestGenerator()
self_ext = SelfExtension()
retro = SprintRetrospectiveAssistant()
hygiene = GitHygieneAutomation()


from pydantic import BaseModel


class PostStandupRequest(BaseModel):
    channel: str


class DocGenRequest(BaseModel):
    module_name: str
    code_summary: str
    entities: list[dict] = []


class ArchitectureDocRequest(BaseModel):
    repo_name: str
    modules: list[dict] = []


class ReleaseNotesRequest(BaseModel):
    repo_name: str
    commits: list[dict]
    previous_tag: str | None = None


class TestGenRequest(BaseModel):
    code: str
    language: str
    function_name: str
    test_framework: str = "pytest"


class TestGapAnalysisRequest(BaseModel):
    code_summary: str
    existing_tests: list[str] = []


class SelfExtensionScanRequest(BaseModel):
    clone_path: str


# ─── Standup ──────────────────────────────────────────

@router.post("/standup")
async def generate_standup(db: AsyncSession = Depends(get_db)):
    summary = await standup.generate(db)
    return summary


@router.post("/standup/post")
async def post_standup(payload: PostStandupRequest, db: AsyncSession = Depends(get_db)):
    success = await standup.post_to_slack(db, payload.channel)
    if not success:
        raise HTTPException(status_code=400, detail="Slack not configured")
    return {"posted": True, "channel": payload.channel}


# ─── Documentation ────────────────────────────────────

@router.post("/docs/module")
async def generate_module_docs(payload: DocGenRequest):
    docs = await doc_gen.generate_module_docs(
        payload.module_name, payload.code_summary, payload.entities,
    )
    return {"docs": docs}


@router.post("/docs/architecture")
async def generate_architecture_docs(payload: ArchitectureDocRequest):
    docs = await doc_gen.generate_architecture_overview(payload.repo_name, payload.modules)
    return {"docs": docs}


# ─── Release Notes ────────────────────────────────────

@router.post("/release-notes")
async def generate_release_notes(payload: ReleaseNotesRequest):
    notes = await release_gen.generate(payload.repo_name, payload.commits, payload.previous_tag)
    return {"release_notes": notes}


# ─── Tests ────────────────────────────────────────────

@router.post("/tests/generate")
async def generate_tests(payload: TestGenRequest):
    tests = await test_gen.generate_tests(
        payload.code, payload.language, payload.function_name, payload.test_framework,
    )
    return {"tests": tests}


@router.post("/tests/gap-analysis")
async def analyze_test_gaps(payload: TestGapAnalysisRequest):
    analysis = await test_gen.analyze_gaps(payload.code_summary, payload.existing_tests)
    return analysis


class RetroRequest(BaseModel):
    sprint_name: str
    completed: list[dict] = []
    planned: list[dict] = []


class GitHygieneRequest(BaseModel):
    repo_path: str


# ─── Sprint Retrospective ───────────────────────────────

@router.post("/retro/generate")
async def generate_retrospective(payload: RetroRequest):
    summary = await retro.generate_retrospective(payload.sprint_name, payload.completed, payload.planned)
    return {"retrospective": summary}


# ─── Git Hygiene ────────────────────────────────────────

@router.post("/git-hygiene/analyze")
async def analyze_git_hygiene(payload: GitHygieneRequest):
    result = await hygiene.analyze(payload.repo_path)
    return result
