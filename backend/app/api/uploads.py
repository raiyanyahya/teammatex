"""Per-user file uploads — store only, no execution.

Bytes are written to the uploads_data volume under a generated UUID name (the
original filename is never used as a path component, so it can't traverse), and
the metadata row is scoped to the uploader's JWT ``sub``. Downloads are
owner-only and always served as attachments so an uploaded HTML/SVG can't run
as stored XSS.
"""

import os
import uuid as _uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.api.deps import require_user
from app.db.session import get_db
from app.models.upload import Upload

logger = get_logger(__name__)
router = APIRouter(prefix="/uploads", tags=["uploads"])

UPLOAD_ROOT = Path(os.getenv("UPLOAD_DIR", "/data/uploads"))
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


def _owner(user: dict) -> str:
    return str(user.get("sub") or "anonymous")


def _serialize(u: Upload) -> dict:
    return {
        "id": u.id,
        "filename": u.filename,
        "content_type": u.content_type,
        "size_bytes": u.size_bytes,
        "created_at": str(u.created_at) if u.created_at else None,
    }


async def _owned(upload_id: str, owner: str, db: AsyncSession) -> Upload:
    # A malformed (non-UUID) id has no row; 404 rather than letting the typed
    # column query raise a 500 on the bad cast.
    try:
        _uuid.UUID(upload_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    up = (
        await db.execute(select(Upload).where(Upload.id == upload_id, Upload.owner_id == owner))
    ).scalar_one_or_none()
    if up is None:
        raise HTTPException(status_code=404, detail="Not found")
    return up


@router.get("")
async def list_uploads(user: dict = Depends(require_user), db: AsyncSession = Depends(get_db)):
    rows = (
        (
            await db.execute(
                select(Upload)
                .where(Upload.owner_id == _owner(user))
                .order_by(Upload.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_serialize(u) for u in rows]


@router.post("", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    user: dict = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    owner = _owner(user)
    # Read in chunks with a hard cap so an oversized upload can't be buffered
    # whole into memory before we reject it.
    data = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
            )
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    owner_dir = UPLOAD_ROOT / owner
    owner_dir.mkdir(parents=True, exist_ok=True)
    stored_path = owner_dir / _uuid.uuid4().hex
    stored_path.write_bytes(bytes(data))

    up = Upload(
        owner_id=owner,
        filename=(file.filename or "upload")[:512],
        content_type=file.content_type,
        size_bytes=len(data),
        stored_path=str(stored_path),
    )
    db.add(up)
    await db.commit()
    await db.refresh(up)
    return _serialize(up)


@router.get("/{upload_id}/download")
async def download_upload(
    upload_id: str,
    user: dict = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    up = await _owned(upload_id, _owner(user), db)
    if not os.path.exists(up.stored_path):
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(
        up.stored_path,
        media_type="application/octet-stream",
        filename=up.filename,
        content_disposition_type="attachment",
    )


@router.delete("/{upload_id}", status_code=204)
async def delete_upload(
    upload_id: str,
    user: dict = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    up = await _owned(upload_id, _owner(user), db)
    try:
        if os.path.exists(up.stored_path):
            os.remove(up.stored_path)
    except OSError as e:
        logger.warning("upload_file_delete_failed", id=upload_id, error=str(e)[:120])
    await db.delete(up)
    await db.commit()
