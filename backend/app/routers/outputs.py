import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, update

from app.core.database import AsyncSessionLocal
from app.core.response import ApiResponse, ErrorCode, error_response, success_response
from app.middlewares.auth import require_admin, require_password_changed
from app.models.log import OperationLog
from app.models.output import Output
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


def _output_to_dict(o: Output, username: str | None = None, include_content: bool = False) -> dict:
    d = {
        "id": o.id,
        "title": o.title,
        "tool_code": o.tool_code,
        "tool_name": o.tool_name,
        "task_id": o.task_id,
        "word_count": o.word_count,
        "file_id": o.file_id,
        "created_by": o.created_by,
        "created_at": _ts(o.created_at),
    }
    if include_content:
        d["content"] = o.content
        d["content_json"] = o.content_json
    if username is not None:
        d["created_by_username"] = username
    return d


def _pagination(total: int, page: int, page_size: int) -> dict:
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": math.ceil(total / page_size) if page_size else 1,
    }


# ---------------------------------------------------------------------------
# GET /api/outputs  (operator — own, deleted_at IS NULL)
# ---------------------------------------------------------------------------

@router.get("/outputs", response_model=ApiResponse)
async def list_outputs(
    page: int = 1,
    page_size: int = 20,
    tool_code: str = "",
    current_user: User = Depends(require_password_changed),
):
    if page_size not in _PAGE_SIZE_ALLOWED:
        page_size = 20

    async with AsyncSessionLocal() as session:
        q = select(Output).where(
            Output.created_by == current_user.id,
            Output.deleted_at.is_(None),
        )
        if tool_code:
            q = q.where(Output.tool_code == tool_code)

        total = len((await session.execute(q)).scalars().all())
        rows = (await session.execute(
            q.order_by(Output.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()

    return success_response(data={
        "items": [_output_to_dict(o) for o in rows],
        "pagination": _pagination(total, page, page_size),
    })


# ---------------------------------------------------------------------------
# GET /api/outputs/{output_id}  (operator — own only, with content)
# ---------------------------------------------------------------------------

@router.get("/outputs/{output_id}", response_model=ApiResponse)
async def get_output(
    output_id: int,
    current_user: User = Depends(require_password_changed),
):
    async with AsyncSessionLocal() as session:
        output = (await session.execute(
            select(Output).where(Output.id == output_id, Output.deleted_at.is_(None))
        )).scalar_one_or_none()

    if output is None or output.created_by != current_user.id:
        return error_response(ErrorCode.PERMISSION_DENIED, "无权限访问")

    return success_response(data=_output_to_dict(output, include_content=True))


# ---------------------------------------------------------------------------
# DELETE /api/outputs/{output_id}  (operator — soft delete own only)
# ---------------------------------------------------------------------------

@router.delete("/outputs/{output_id}", response_model=ApiResponse)
async def delete_output(
    output_id: int,
    request: Request,
    current_user: User = Depends(require_password_changed),
):
    async with AsyncSessionLocal() as session:
        output = (await session.execute(
            select(Output).where(Output.id == output_id, Output.deleted_at.is_(None))
        )).scalar_one_or_none()

        if output is None or output.created_by != current_user.id:
            return error_response(ErrorCode.PERMISSION_DENIED, "无权限访问")

        now = datetime.now(tz=timezone.utc)
        await session.execute(
            update(Output).where(Output.id == output_id).values(deleted_at=now)
        )
        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="delete_output",
            target_type="output",
            target_id=output_id,
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent"),
        ))
        await session.commit()

    return success_response(data=None, message="产出已删除")


# ---------------------------------------------------------------------------
# GET /api/admin/outputs  (admin — all, user_id/tool_code filter)
# ---------------------------------------------------------------------------

@router.get("/admin/outputs", response_model=ApiResponse)
async def admin_list_outputs(
    page: int = 1,
    page_size: int = 20,
    tool_code: str = "",
    user_id: int = 0,
    current_user: User = Depends(require_admin),
):
    if page_size not in _PAGE_SIZE_ALLOWED:
        page_size = 20

    async with AsyncSessionLocal() as session:
        q = select(Output).where(Output.deleted_at.is_(None))
        if tool_code:
            q = q.where(Output.tool_code == tool_code)
        if user_id:
            q = q.where(Output.created_by == user_id)

        total = len((await session.execute(q)).scalars().all())
        rows = (await session.execute(
            q.order_by(Output.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()

        uids = list({o.created_by for o in rows})
        users = (await session.execute(
            select(User.id, User.username).where(User.id.in_(uids))
        )).all()
        uid_to_name = {u.id: u.username for u in users}

    return success_response(data={
        "items": [_output_to_dict(o, uid_to_name.get(o.created_by)) for o in rows],
        "pagination": _pagination(total, page, page_size),
    })


# ---------------------------------------------------------------------------
# GET /api/admin/outputs/{output_id}  (admin)
# ---------------------------------------------------------------------------

@router.get("/admin/outputs/{output_id}", response_model=ApiResponse)
async def admin_get_output(
    output_id: int,
    current_user: User = Depends(require_admin),
):
    async with AsyncSessionLocal() as session:
        output = (await session.execute(
            select(Output).where(Output.id == output_id, Output.deleted_at.is_(None))
        )).scalar_one_or_none()

    if output is None:
        return error_response(ErrorCode.OUTPUT_NOT_FOUND, "产出不存在")

    return success_response(data=_output_to_dict(output, include_content=True))


# ---------------------------------------------------------------------------
# DELETE /api/admin/outputs/{output_id}  (admin — soft delete any)
# ---------------------------------------------------------------------------

@router.delete("/admin/outputs/{output_id}", response_model=ApiResponse)
async def admin_delete_output(
    output_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
):
    async with AsyncSessionLocal() as session:
        output = (await session.execute(
            select(Output).where(Output.id == output_id, Output.deleted_at.is_(None))
        )).scalar_one_or_none()

        if output is None:
            return error_response(ErrorCode.OUTPUT_NOT_FOUND, "产出不存在")

        now = datetime.now(tz=timezone.utc)
        await session.execute(
            update(Output).where(Output.id == output_id).values(deleted_at=now)
        )
        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="admin_delete_output",
            target_type="output",
            target_id=output_id,
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent"),
        ))
        await session.commit()

    return success_response(data=None, message="产出已删除")
