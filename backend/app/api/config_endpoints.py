from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.app_config import AppConfig

router = APIRouter(prefix="/config", tags=["config"])


class ConfigSetRequest(BaseModel):
    key: str
    value: dict


class TokenVerifyRequest(BaseModel):
    token: str | None = None


@router.post("/github_token/verify")
async def verify_github_token_endpoint(
    payload: TokenVerifyRequest, db: AsyncSession = Depends(get_db),
):
    """Verify a GitHub token (the supplied one, or the stored one if omitted)
    and report whether it can push — so the user isn't surprised by a 403 on PR.
    """
    from app.services.agent.git_setup import verify_github_token

    token = (payload.token or "").strip()
    if not token:
        result = await db.execute(select(AppConfig).where(AppConfig.key == "github_token"))
        row = result.scalar_one_or_none()
        if row and row.value:
            val = row.value
            token = (val.get("token") if isinstance(val, dict) else val) or ""
    return await verify_github_token(token)


@router.get("/{key}")
async def get_config(key: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AppConfig).where(AppConfig.key == key))
    row = result.scalar_one_or_none()
    if not row:
        return {"key": key, "value": None}
    return {"key": key, "value": row.value}


@router.put("/{key}")
async def set_config(key: str, payload: ConfigSetRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AppConfig).where(AppConfig.key == key))
    row = result.scalar_one_or_none()

    if row:
        row.value = payload.value
    else:
        row = AppConfig(key=key, value=payload.value)
        db.add(row)

    await db.commit()
    return {"key": key, "saved": True}


@router.get("/llm/providers")
async def list_llm_providers(db: AsyncSession = Depends(get_db)):
    """Recommended providers/models so the UI can offer a stronger-model upgrade.
    DeepSeek is the cheap default; Claude/GPT give higher tool-calling reliability.
    """
    from app.services.llm.provider import RECOMMENDED_MODELS

    result = await db.execute(select(AppConfig).where(AppConfig.key == "llm_config"))
    row = result.scalar_one_or_none()
    active = row.value if row else None
    return {
        "providers": RECOMMENDED_MODELS,
        "default_provider": "deepseek",
        "active": {"provider": active.get("provider"), "model": active.get("model")} if isinstance(active, dict) else None,
    }


@router.get("")
async def get_all_config(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AppConfig))
    rows = result.scalars().all()
    return {"config": {r.key: r.value for r in rows}}


@router.delete("/{key}")
async def delete_config(key: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AppConfig).where(AppConfig.key == key))
    row = result.scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()
    return {"key": key, "deleted": True}
