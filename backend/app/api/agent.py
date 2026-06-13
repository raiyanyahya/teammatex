import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_user
from app.db.session import get_db
from app.services.agent.attachments import build_attached_message
from app.services.agent.conversations_service import get_or_create, save_message
from app.services.agent.runtime import agent_runtime

router = APIRouter(prefix="/agent", tags=["agent"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    repo_id: str | None = None
    conversation_id: str | None = None
    upload_id: str | None = None
    history: list[dict] | None = None


class PlanRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=5000)
    repo_id: str | None = None


class CodeGenRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=5000)
    language: str = Field(..., min_length=1, max_length=50)
    repo_id: str | None = None
    context_files: dict[str, str] | None = None


class ValidateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50000)
    file_path: str = "generated.py"


class ToolExecuteRequest(BaseModel):
    tool_name: str = Field(..., min_length=1, max_length=100)
    arguments: dict
    repo_id: str | None = None
    # Side-effecting tools (write_file, run_command, create_pr, …) are flagged
    # requires_confirmation. The caller must pass confirm=true to run them, so the
    # human-in-the-loop is enforced server-side, not just in the UI.
    confirm: bool = False


class ReviewRequest(BaseModel):
    summary: str = Field(..., min_length=1, max_length=5000)
    files: list[str] = Field(default_factory=list, max_length=100)
    diff: str = Field(..., max_length=50000)


# ─── Chat (Streaming) ────────────────────────────────────

def _capture_text(raw: str, parts: list[str]) -> None:
    """Pull the assistant's final text out of the SSE chunk(s) so we can persist
    it. The loop emits the answer as ``{"type": "text", ...}`` events."""
    for line in raw.splitlines():
        if not line.startswith("data: "):
            continue
        body = line[6:]
        if body == "[DONE]":
            continue
        try:
            data = json.loads(body)
        except ValueError:
            continue
        if data.get("type") == "text":
            parts.append(data.get("content", ""))


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    user: dict = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    owner = str(user.get("sub") or "anonymous")
    # Inject any attached file as context for the LLM, but persist the user's
    # original message (not the augmented blob).
    augmented = await build_attached_message(db, payload.upload_id, owner, payload.message)
    convo = await get_or_create(db, owner, payload.conversation_id, payload.message)
    convo_id = convo.id
    await save_message(db, convo_id, "user", payload.message)
    await db.commit()

    async def stream():
        yield f"data: {json.dumps({'type': 'conversation', 'id': convo_id})}\n\n"
        parts: list[str] = []
        async for event in agent_runtime.chat(db, augmented, payload.repo_id, payload.history):
            _capture_text(event, parts)
            yield event
        if parts:
            await save_message(db, convo_id, "assistant", "".join(parts))
            await db.commit()
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


# ─── Plan ────────────────────────────────────────────────

@router.post("/plan")
async def plan_task(payload: PlanRequest, db: AsyncSession = Depends(get_db)):
    plan = await agent_runtime.plan_task(payload.task, payload.repo_id, db)
    return {"task": payload.task, "plan": plan}


# ─── Code Generation ─────────────────────────────────────

@router.post("/generate-code")
async def generate_code(payload: CodeGenRequest):
    code = await agent_runtime.generate_code(
        payload.task, payload.language, payload.context_files,
    )
    return {"language": payload.language, "code": code}


# ─── Validate Code ───────────────────────────────────────

@router.post("/validate")
async def validate_code(payload: ValidateRequest):
    passed, message = await agent_runtime.validate_code(payload.code, payload.file_path)
    return {"passed": passed, "message": message}


# ─── Self Review ─────────────────────────────────────────

@router.post("/review")
async def self_review(payload: ReviewRequest):
    result = await agent_runtime.self_review(
        payload.summary, payload.files, payload.diff,
    )
    return {"review": result}


# ─── Execute Tool ────────────────────────────────────────

@router.post("/tool")
async def execute_tool(payload: ToolExecuteRequest, db: AsyncSession = Depends(get_db)):
    from app.services.agent.runtime import AgentContext

    tool = agent_runtime.tools.get_all().get(payload.tool_name)
    if tool is not None and tool.requires_confirmation and not payload.confirm:
        raise HTTPException(
            status_code=403,
            detail=f"Tool '{payload.tool_name}' makes changes and requires confirmation; resend with confirm=true.",
        )

    ctx = AgentContext(repo_id=payload.repo_id, db=db)
    result = await agent_runtime.execute_tool(ctx, payload.tool_name, payload.arguments)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ─── List Tools ──────────────────────────────────────────

@router.get("/tools")
async def list_tools():
    tools = agent_runtime.tools.get_all()
    return {
        "tools": [
            {"name": name, "description": t.description, "category": t.category,
             "requires_confirmation": t.requires_confirmation}
            for name, t in tools.items()
        ]
    }
