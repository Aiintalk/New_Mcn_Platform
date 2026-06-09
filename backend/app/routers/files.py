import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, update

from app.core.database import AsyncSessionLocal
from app.core.response import ApiResponse, ErrorCode, error_response, success_response
from app.middlewares.auth import require_password_changed
from app.models.file import File
from app.models.log import OperationLog
from app.models.user import User

router = APIRouter()

_PAGE_SIZE_ALLOWED = {10, 20, 50}


def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _file_to_dict(f: File) -> dict:
    return {
        "id": f.id,
        "filename": f.filename,
        "file_type": f.file_type,
        "file_size": f.file_size,
        "content_type": f.content_type,
        "output_id": f.output_id,
        "task_id": f.task_id,
        "created_by": f.created_by,
        "created_at": _ts(f.created_at),
    }


def _pagination(total: int, page: int, page_size: int) -> dict:
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": math.ceil(total / page_size) if page_size else 1,
    }


# ---------------------------------------------------------------------------
# GET /api/files  (operator — own files, deleted_at IS NULL)
# ---------------------------------------------------------------------------

@router.get("/files", response_model=ApiResponse)
async def list_files(
    page: int = 1,
    page_size: int = 20,
    output_id: int = 0,
    current_user: User = Depends(require_password_changed),
):
    if page_size not in _PAGE_SIZE_ALLOWED:
        page_size = 20

    async with AsyncSessionLocal() as session:
        q = select(File).where(
            File.created_by == current_user.id,
            File.deleted_at.is_(None),
        )
        if output_id:
            q = q.where(File.output_id == output_id)

        total = len((await session.execute(q)).scalars().all())
        rows = (await session.execute(
            q.order_by(File.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()

    return success_response(data={
        "items": [_file_to_dict(f) for f in rows],
        "pagination": _pagination(total, page, page_size),
    })


# ---------------------------------------------------------------------------
# GET /api/files/{file_id}/download-url  (operator — own only, mock URL)
# ---------------------------------------------------------------------------

@router.get("/files/{file_id}/download-url", response_model=ApiResponse)
async def get_download_url(
    file_id: int,
    current_user: User = Depends(require_password_changed),
):
    async with AsyncSessionLocal() as session:
        file = (await session.execute(
            select(File).where(File.id == file_id, File.deleted_at.is_(None))
        )).scalar_one_or_none()

    if file is None or file.created_by != current_user.id:
        return error_response(ErrorCode.PERMISSION_DENIED, "无权限访问")

    mock_url = f"https://mock-oss.example.com/files/{file.oss_key}?token=mock"
    return success_response(data={
        "file_id": file_id,
        "file_name": file.filename,
        "download_url": mock_url,
        "expires_in": 3600,
    })


# ---------------------------------------------------------------------------
# DELETE /api/files/{file_id}  (operator — soft delete own only)
# ---------------------------------------------------------------------------

@router.delete("/files/{file_id}", response_model=ApiResponse)
async def delete_file(
    file_id: int,
    request: Request,
    current_user: User = Depends(require_password_changed),
):
    async with AsyncSessionLocal() as session:
        file = (await session.execute(
            select(File).where(File.id == file_id, File.deleted_at.is_(None))
        )).scalar_one_or_none()

        if file is None or file.created_by != current_user.id:
            return error_response(ErrorCode.PERMISSION_DENIED, "无权限访问")

        now = datetime.now(tz=timezone.utc)
        await session.execute(
            update(File).where(File.id == file_id).values(deleted_at=now)
        )
        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="delete_file",
            target_type="file",
            target_id=file_id,
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent"),
        ))
        await session.commit()

    return success_response(data=None, message="文件已删除")
