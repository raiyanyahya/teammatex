from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.task import Task

router = APIRouter(prefix="/tasks", tags=["tasks"])

# The board columns the Tasks page renders. New tasks land in "todo"; drag-drop
# moves a task by PATCHing its status to one of these.
VALID_STATUSES = {"todo", "doing", "review", "done"}


class TaskCreate(BaseModel):
    # title maps to a varchar(500) column; bound it at the edge so an overlong
    # value is a 422, not a database 500.
    title: str = Field(min_length=1, max_length=500)
    status: str = "todo"
    priority: str | None = None
    assignee: str | None = None
    description: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    status: str | None = None
    priority: str | None = None
    assignee: str | None = None
    description: str | None = None


class TaskResponse(BaseModel):
    id: str
    title: str
    status: str
    priority: str | None = None
    assignee: str | None = None
    description: str | None = None
    created_at: str | None = None


def _to_response(t: Task) -> TaskResponse:
    return TaskResponse(
        id=str(t.id),
        title=t.title,
        status=t.status,
        priority=t.priority,
        assignee=t.assigned_to,
        description=t.description,
        created_at=str(t.created_at) if t.created_at else None,
    )


@router.get("", response_model=list[TaskResponse])
async def list_tasks(limit: int = 200, db: AsyncSession = Depends(get_db)):
    rows = (
        (
            await db.execute(
                select(Task).order_by(Task.created_at.desc()).limit(max(1, min(limit, 500)))
            )
        )
        .scalars()
        .all()
    )
    return [_to_response(t) for t in rows]


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(payload: TaskCreate, db: AsyncSession = Depends(get_db)):
    # Reject an unknown status (422) rather than silently coercing it — same
    # contract as PATCH.
    if payload.status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status: {payload.status}")
    task = Task(
        title=payload.title,
        status=payload.status,
        priority=payload.priority,
        assigned_to=payload.assignee,
        description=payload.description,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return _to_response(task)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(task_id: str, payload: TaskUpdate, db: AsyncSession = Depends(get_db)):
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if payload.title is not None:
        task.title = payload.title
    if payload.status is not None:
        if payload.status not in VALID_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid status: {payload.status}")
        task.status = payload.status
    if payload.priority is not None:
        task.priority = payload.priority
    if payload.assignee is not None:
        task.assigned_to = payload.assignee
    if payload.description is not None:
        task.description = payload.description

    await db.commit()
    await db.refresh(task)
    return _to_response(task)


@router.delete("/{task_id}")
async def delete_task(task_id: str, db: AsyncSession = Depends(get_db)):
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.delete(task)
    await db.commit()
    return {"deleted": True, "task_id": task_id}
