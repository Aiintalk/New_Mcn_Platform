from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select, update

from app.core.database import AsyncSessionLocal
from app.core.response import ApiResponse, ErrorCode, error_response, success_response
from app.middlewares.auth import require_admin
from app.models.log import OperationLog
from app.models.user import User
from app.models.workspace import WorkspaceTool

router = APIRouter(prefix="/admin/workspace")


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _tool_to_dict(t: WorkspaceTool) -> dict:
    return {
        "id": t.id,
        "tool_code": t.tool_code,
        "tool_name": t.tool_name,
        "category": t.category,
        "description": t.description,
        "status": t.status,
        "tags": t.tags or [],
        "config": t.config,
        "sort_order": t.sort_order,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


class UpdateToolRequest(BaseModel):
    tool_name: str | None = None
    category: str | None = None
    description: str | None = None
    status: str | None = None
    tags: list | None = None
    config: dict | None = None
    sort_order: int | None = None


# ---------------------------------------------------------------------------
# GET /api/admin/workspace/tools
# ---------------------------------------------------------------------------

@router.get("/tools", response_model=ApiResponse)
async def admin_list_tools(
    status: str = "",
    current_user: User = Depends(require_admin),
):
    """
    返回全部工具（不过滤 online），可通过 status 参数筛选，按 sort_order ASC 排序。
    """
    async with AsyncSessionLocal() as session:
        q = select(WorkspaceTool).order_by(WorkspaceTool.sort_order.asc())
        if status:
            q = q.where(WorkspaceTool.status == status)
        result = await session.execute(q)
        tools = result.scalars().all()

    return success_response(data={"items": [_tool_to_dict(t) for t in tools]})


# ---------------------------------------------------------------------------
# PATCH /api/admin/workspace/tools/{tool_code}
# ---------------------------------------------------------------------------

@router.patch("/tools/{tool_code}", response_model=ApiResponse)
async def admin_update_tool(
    tool_code: str,
    body: UpdateToolRequest,
    request: Request,
    current_user: User = Depends(require_admin),
):
    """
    更新工具配置，写 operation_logs（action=update_workspace_tool）。
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WorkspaceTool).where(WorkspaceTool.tool_code == tool_code)
        )
        tool: WorkspaceTool | None = result.scalar_one_or_none()
        if tool is None:
            return error_response(ErrorCode.RESOURCE_NOT_FOUND, "工具不存在")

        values: dict = {}
        if body.tool_name is not None:
            values["tool_name"] = body.tool_name
        if body.category is not None:
            values["category"] = body.category
        if body.description is not None:
            values["description"] = body.description
        if body.status is not None:
            values["status"] = body.status
        if body.tags is not None:
            values["tags"] = body.tags
        if body.config is not None:
            values["config"] = body.config
        if body.sort_order is not None:
            values["sort_order"] = body.sort_order

        if values:
            values["updated_at"] = datetime.now(timezone.utc)
            await session.execute(
                update(WorkspaceTool)
                .where(WorkspaceTool.tool_code == tool_code)
                .values(**values)
            )

        log_detail = {k: v for k, v in values.items() if k != "updated_at"}
        log = OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="update_workspace_tool",
            target_type="workspace_tool",
            detail={"tool_code": tool_code, **log_detail} if log_detail else {"tool_code": tool_code},
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        session.add(log)
        await session.commit()
        await session.refresh(tool)

    return success_response(data=_tool_to_dict(tool))
