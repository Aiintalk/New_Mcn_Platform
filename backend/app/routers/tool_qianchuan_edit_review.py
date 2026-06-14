"""
app/routers/tool_qianchuan_edit_review.py

POST /api/tools/qianchuan-edit-review/outputs
保存剪辑预审报告到 outputs 表。
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.middlewares.auth import require_password_changed
from app.models.log import OperationLog
from app.models.output import Output
from app.models.user import User

router = APIRouter(prefix="/tools/qianchuan-edit-review", tags=["qianchuan-edit-review"])

TOOL_CODE = "qianchuan-edit-review"
TOOL_NAME = "千川剪辑预审"


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class SaveOutputRequest(BaseModel):
    title: str
    report: str
    original_duration: float = 0.0
    ours_duration: float = 0.0
    original_frame_count: int = 0
    ours_frame_count: int = 0


@router.post("/outputs")
async def save_output(
    request: Request,
    body: SaveOutputRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_password_changed),
):
    """保存剪辑预审报告到 outputs 表。"""
    if not body.report.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "报告内容不能为空"},
        )

    output = Output(
        title=body.title or TOOL_NAME,
        tool_code=TOOL_CODE,
        tool_name=TOOL_NAME,
        content=body.report,
        content_json={
            "original_duration": body.original_duration,
            "ours_duration": body.ours_duration,
            "original_frame_count": body.original_frame_count,
            "ours_frame_count": body.ours_frame_count,
        },
        word_count=len(body.report),
        created_by=current_user.id,
    )
    db.add(output)
    await db.flush()

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="qianchuan_edit_review_save_output",
        target_type="output",
        target_id=output.id,
        detail={"title": body.title},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(output)

    return success_response(data={
        "id": output.id,
        "created_at": output.created_at.isoformat(),
    })
