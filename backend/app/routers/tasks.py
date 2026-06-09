import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.response import ApiResponse, ErrorCode, error_response, success_response
from app.middlewares.auth import require_admin, require_password_changed
from app.models.task import TaskJob, TaskLog
from app.models.user import User

router = APIRouter()

_PAGE_SIZE_ALLOWED = {10, 20, 50}


def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


def _task_to_dict(t: TaskJob, username: str | None = None) -> dict:
    d = {
        "id": t.id,
        "task_no": t.task_no,
        "tool_code": t.tool_code,
        "tool_name": t.tool_name,
        "status": t.status,
        "created_by": t.created_by,
        "started_at": _ts(t.started_at),
        "finished_at": _ts(t.finished_at),
        "duration_ms": t.duration_ms,
        "output_id": t.output_id,
        "error_code": t.error_code,
        "error_message": t.error_message,
        "created_at": _ts(t.created_at),
    }
    if username is not None:
        d["created_by_username"] = username
    return d


def _log_to_dict(lg: TaskLog) -> dict:
    return {
        "id": lg.id,
        "step_code": lg.step_code,
        "step_name": lg.step_name,
        "status": lg.status,
        "message": lg.message,
        "created_at": _ts(lg.created_at),
    }


def _pagination(total: int, page: int, page_size: int) -> dict:
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": math.ceil(total / page_size) if page_size else 1,
    }


# ---------------------------------------------------------------------------
# GET /api/tasks  (operator — own tasks only)
# ---------------------------------------------------------------------------

@router.get("/tasks", response_model=ApiResponse)
async def list_tasks(
    page: int = 1,
    page_size: int = 20,
    status: str = "",
    tool_code: str = "",
    current_user: User = Depends(require_password_changed),
):
    if page_size not in _PAGE_SIZE_ALLOWED:
        page_size = 20

    async with AsyncSessionLocal() as session:
        q = select(TaskJob).where(TaskJob.created_by == current_user.id)
        if status:
            q = q.where(TaskJob.status == status)
        if tool_code:
            q = q.where(TaskJob.tool_code == tool_code)

        all_rows = (await session.execute(q)).scalars().all()
        total = len(all_rows)

        q = q.order_by(TaskJob.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        rows = (await session.execute(q)).scalars().all()

    return success_response(data={
        "items": [_task_to_dict(t) for t in rows],
        "pagination": _pagination(total, page, page_size),
    })


# ---------------------------------------------------------------------------
# GET /api/tasks/{task_id}  (operator — own only, includes task_logs)
# ---------------------------------------------------------------------------

@router.get("/tasks/{task_id}", response_model=ApiResponse)
async def get_task(
    task_id: int,
    current_user: User = Depends(require_password_changed),
):
    async with AsyncSessionLocal() as session:
        task = (await session.execute(
            select(TaskJob).where(TaskJob.id == task_id)
        )).scalar_one_or_none()

        if task is None or task.created_by != current_user.id:
            return error_response(ErrorCode.PERMISSION_DENIED, "无权限访问")

        logs = (await session.execute(
            select(TaskLog).where(TaskLog.task_id == task_id)
            .order_by(TaskLog.created_at.asc())
        )).scalars().all()

    data = _task_to_dict(task)
    data["task_logs"] = [_log_to_dict(lg) for lg in logs]
    return success_response(data=data)


# ---------------------------------------------------------------------------
# GET /api/admin/tasks  (admin — all tasks)
# ---------------------------------------------------------------------------

@router.get("/admin/tasks", response_model=ApiResponse)
async def admin_list_tasks(
    page: int = 1,
    page_size: int = 20,
    status: str = "",
    tool_code: str = "",
    user_id: int = 0,
    current_user: User = Depends(require_admin),
):
    if page_size not in _PAGE_SIZE_ALLOWED:
        page_size = 20

    async with AsyncSessionLocal() as session:
        q = select(TaskJob)
        if status:
            q = q.where(TaskJob.status == status)
        if tool_code:
            q = q.where(TaskJob.tool_code == tool_code)
        if user_id:
            q = q.where(TaskJob.created_by == user_id)

        all_rows = (await session.execute(q)).scalars().all()
        total = len(all_rows)

        q = q.order_by(TaskJob.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        rows = (await session.execute(q)).scalars().all()

        # Fetch usernames for the page
        user_ids = list({t.created_by for t in rows})
        users = (await session.execute(
            select(User.id, User.username).where(User.id.in_(user_ids))
        )).all()
        uid_to_name = {u.id: u.username for u in users}

    return success_response(data={
        "items": [_task_to_dict(t, uid_to_name.get(t.created_by)) for t in rows],
        "pagination": _pagination(total, page, page_size),
    })


# ---------------------------------------------------------------------------
# GET /api/admin/tasks/{task_id}  (admin — any task with task_logs)
# ---------------------------------------------------------------------------

@router.get("/admin/tasks/{task_id}", response_model=ApiResponse)
async def admin_get_task(
    task_id: int,
    current_user: User = Depends(require_admin),
):
    async with AsyncSessionLocal() as session:
        task = (await session.execute(
            select(TaskJob).where(TaskJob.id == task_id)
        )).scalar_one_or_none()

        if task is None:
            return error_response(ErrorCode.TASK_NOT_FOUND, "任务不存在")

        creator = (await session.execute(
            select(User.username).where(User.id == task.created_by)
        )).scalar_one_or_none()

        logs = (await session.execute(
            select(TaskLog).where(TaskLog.task_id == task_id)
            .order_by(TaskLog.created_at.asc())
        )).scalars().all()

    data = _task_to_dict(task, creator)
    data["task_logs"] = [_log_to_dict(lg) for lg in logs]
    return success_response(data=data)
