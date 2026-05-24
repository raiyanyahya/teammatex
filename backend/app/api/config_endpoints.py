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
