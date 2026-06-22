"""
app/routers/files.py

文件管理接口（operator/admin）：
  GET    /api/files                       — 当前用户文件列表（分页）
  POST   /api/files                       — 上传文件到 OSS（产生 oss_call_logs）
  GET    /api/files/{file_id}/download-url — 生成 OSS 签名下载 URL
  DELETE /api/files/{file_id}             — 软删除 + 清理 OSS 对象

OSS 对象键命名规范：uploads/{user_id}/{yyyymmdd}/{uuid}.{ext}
文件大小限制：50MB（_MAX_UPLOAD_BYTES）
"""
import math
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File as FileParam, HTTPException, Request, UploadFile
from sqlalchemy import select, update

from app.adapters import oss as oss_adapter
from app.core.database import AsyncSessionLocal
from app.core.response import ApiResponse, ErrorCode, error_response, success_response
from app.middlewares.auth import require_password_changed
from app.models.file import File
from app.models.log import OperationLog
from app.models.user import User

router = APIRouter()

_PAGE_SIZE_ALLOWED = {10, 20, 50}
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


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
        "oss_key": f.oss_key,
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


def _build_oss_key(user_id: int, filename: str) -> str:
    """生成 OSS 对象键：uploads/{user_id}/{yyyymmdd}/{uuid}.{ext}"""
    yyyymmdd = datetime.now(timezone.utc).strftime("%Y%m%d")
    ext = os.path.splitext(filename)[1].lstrip(".").lower() or "bin"
    return f"uploads/{user_id}/{yyyymmdd}/{uuid.uuid4().hex}.{ext}"


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
# POST /api/files  (operator — 上传到 OSS)
# ---------------------------------------------------------------------------

@router.post("/files", response_model=ApiResponse)
async def upload_file_to_oss(
    request: Request,
    file: UploadFile = FileParam(...),
    current_user: User = Depends(require_password_changed),
):
    """
    上传文件到 OSS。

    - 限制：单文件 <= 50MB
    - OSS 对象键：uploads/{user_id}/{yyyymmdd}/{uuid}.{ext}
    - 失败：OSS 调用失败时 raise HTTPException 500（不写 files 表）
    - 成功：files 表写一条记录 + OperationLog + oss_call_logs（由 adapter 写）
    """
    # 流式读取 + 大小校验（避免一次性加载到内存）
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)  # 64KB 块
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail={"code": "FILE_TOO_LARGE", "message": f"文件超过 50MB 限制"},
            )
        chunks.append(chunk)
    content = b"".join(chunks)

    if total == 0:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "文件内容为空"},
        )

    filename = file.filename or "unnamed"
    content_type = file.content_type or "application/octet-stream"
    file_type = os.path.splitext(filename)[1].lstrip(".").lower() or None
    oss_key = _build_oss_key(current_user.id, filename)

    # OSS 上传（adapter 内部写 oss_call_logs + commit）
    async with AsyncSessionLocal() as session:
        try:
            await oss_adapter.upload_file(
                oss_key=oss_key,
                content=content,
                content_type=content_type,
                db=session,
                user_id=current_user.id,
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail={"code": "OSS_UPLOAD_FAILED", "message": f"OSS 上传失败: {str(e)[:200]}"},
            )

    # 写 files 表 + OperationLog（新事务）
    async with AsyncSessionLocal() as session:
        new_file = File(
            filename=filename,
            file_type=file_type,
            file_size=total,
            oss_key=oss_key,
            content_type=content_type,
            created_by=current_user.id,
        )
        session.add(new_file)
        await session.flush()
        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="upload_file",
            target_type="file",
            target_id=new_file.id,
            detail={"filename": filename, "oss_key": oss_key, "size": total},
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent"),
        ))
        await session.commit()
        await session.refresh(new_file)

    return success_response(data=_file_to_dict(new_file), message="上传成功")


# ---------------------------------------------------------------------------
# GET /api/files/{file_id}/download-url  (operator — own only, real OSS URL)
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

    # 调 OSS adapter 生成签名 URL（adapter 内部写 oss_call_logs + commit）
    async with AsyncSessionLocal() as session:
        try:
            download_url = await oss_adapter.get_download_url(
                oss_key=file.oss_key,
                db=session,
                user_id=current_user.id,
            )
        except Exception as e:
            return error_response(
                ErrorCode.EXTERNAL_SERVICE_ERROR,
                f"OSS 生成下载链接失败: {str(e)[:200]}",
            )

    return success_response(data={
        "file_id": file_id,
        "file_name": file.filename,
        "download_url": download_url,
        "expires_in": 3600,
    })


# ---------------------------------------------------------------------------
# DELETE /api/files/{file_id}  (operator — soft delete + OSS 清理)
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

        oss_key_to_delete = file.oss_key
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
            detail={"oss_key": oss_key_to_delete},
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent"),
        ))
        await session.commit()

    # OSS 对象清理（失败不阻塞软删除，但写日志）
    async with AsyncSessionLocal() as session:
        try:
            await oss_adapter.delete_file(
                oss_key=oss_key_to_delete,
                db=session,
                user_id=current_user.id,
            )
        except Exception:
            # OSS 删除失败不影响软删除结果（已软删），仅日志记录失败
            pass

    return success_response(data=None, message="文件已删除")
