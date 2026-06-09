import math

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.response import ApiResponse, success_response
from app.middlewares.auth import require_admin
from app.models.log import ExternalServiceLog, OperationLog
from app.models.user import User

router = APIRouter()

_PAGE_SIZE_ALLOWED = {10, 20, 50}


def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


def _pagination(total: int, page: int, page_size: int) -> dict:
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": math.ceil(total / page_size) if page_size else 1,
    }


# ---------------------------------------------------------------------------
# GET /api/admin/logs/operation
# ---------------------------------------------------------------------------

@router.get("/admin/logs/operation", response_model=ApiResponse)
async def admin_operation_logs(
    page: int = 1,
    page_size: int = 20,
    user_id: int = 0,
    action: str = "",
    current_user: User = Depends(require_admin),
):
    if page_size not in _PAGE_SIZE_ALLOWED:
        page_size = 20

    async with AsyncSessionLocal() as session:
        q = select(OperationLog)
        if user_id:
            q = q.where(OperationLog.user_id == user_id)
        if action:
            q = q.where(OperationLog.action == action)

        total = len((await session.execute(q)).scalars().all())
        rows = (await session.execute(
            q.order_by(OperationLog.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()

    items = [
        {
            "id": lg.id,
            "user_id": lg.user_id,
            "user_name": lg.username,
            "role": lg.role,
            "action": lg.action,
            "target_type": lg.target_type,
            "target_id": lg.target_id,
            "detail": lg.detail,
            "ip_address": lg.ip,
            "user_agent": lg.user_agent,
            "created_at": _ts(lg.created_at),
        }
        for lg in rows
    ]
    return success_response(data={"items": items, "pagination": _pagination(total, page, page_size)})


# ---------------------------------------------------------------------------
# GET /api/admin/logs/external
# ---------------------------------------------------------------------------

@router.get("/admin/logs/external", response_model=ApiResponse)
async def admin_external_logs(
    page: int = 1,
    page_size: int = 20,
    service: str = "",
    status: str = "",
    current_user: User = Depends(require_admin),
):
    if page_size not in _PAGE_SIZE_ALLOWED:
        page_size = 20

    async with AsyncSessionLocal() as session:
        q = select(ExternalServiceLog)
        if service:
            q = q.where(ExternalServiceLog.service == service)
        if status:
            q = q.where(ExternalServiceLog.status == status)

        total = len((await session.execute(q)).scalars().all())
        rows = (await session.execute(
            q.order_by(ExternalServiceLog.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()

    items = [
        {
            "id": lg.id,
            "service": lg.service,
            "endpoint": lg.action,
            "task_id": lg.task_id,
            "tokens_in": lg.tokens_in,
            "tokens_out": lg.tokens_out,
            "tokens_used": lg.tokens_used,
            "credits": float(lg.credits) if lg.credits is not None else None,
            "audio_seconds": lg.audio_seconds,
            "duration_ms": lg.duration_ms,
            "status": lg.status,
            "error_code": lg.error_code,
            "error_message": lg.error_message,
            "created_at": _ts(lg.created_at),
        }
        for lg in rows
    ]
    return success_response(data={"items": items, "pagination": _pagination(total, page, page_size)})
