from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.response import ApiResponse, ErrorCode, error_response, success_response
from app.middlewares.auth import require_password_changed
from app.models.user import User
from app.models.workspace import WorkspaceTool

router = APIRouter(prefix="/workspace")


def _tool_to_dict(t: WorkspaceTool) -> dict:
    return {
        "id": t.id,
        "tool_code": t.tool_code,
        "tool_name": t.tool_name,
        "category": t.category,
        "description": t.description,
        "status": t.status,
        "tags": t.tags or [],
        "sort_order": t.sort_order,
    }


# ---------------------------------------------------------------------------
# GET /api/workspace/tools
# ---------------------------------------------------------------------------

@router.get("/tools", response_model=ApiResponse)
async def list_workspace_tools(
    current_user: User = Depends(require_password_changed),
):
    """
    返回 status IN ('online', 'dev') 的工具列表，按 sort_order ASC 排序。
    offline/disabled 工具不返回。admin 和 operator 均可访问。
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WorkspaceTool)
            .where(WorkspaceTool.status.in_(["online", "dev"]))
            .order_by(WorkspaceTool.sort_order.asc())
        )
        tools = result.scalars().all()

    return success_response(data={"items": [_tool_to_dict(t) for t in tools]})


# ---------------------------------------------------------------------------
# GET /api/workspace/tools/{tool_code}
# ---------------------------------------------------------------------------

@router.get("/tools/{tool_code}", response_model=ApiResponse)
async def get_workspace_tool(
    tool_code: str,
    current_user: User = Depends(require_password_changed),
):
    """
    返回单个 online 工具详情。
    status != 'online' 或不存在 → RESOURCE_NOT_FOUND。
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WorkspaceTool).where(WorkspaceTool.tool_code == tool_code)
        )
        tool: WorkspaceTool | None = result.scalar_one_or_none()

    if tool is None or tool.status != "online":
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "工具不存在或未上线")

    return success_response(data=_tool_to_dict(tool))
