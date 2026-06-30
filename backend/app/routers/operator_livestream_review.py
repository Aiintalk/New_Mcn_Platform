"""
app/routers/operator_livestream_review.py

运营端接口（JWT 鉴权，operator / admin 角色）：
  POST  /api/tools/livestream-review/parse-file  — 解析脚本文件
  POST  /api/tools/livestream-review/generate    — 流式生成复盘报告
  POST  /api/tools/livestream-review/save        — 保存报告到 outputs 表
  GET   /api/tools/livestream-review/outputs     — 查询当前用户历史报告
"""
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.core.database import AsyncSessionLocal, get_db
from app.core.response import success_response
from app.middlewares.auth import get_current_user
from app.models.log import OperationLog
from app.models.output import Output
from app.models.task import TaskJob
from app.models.user import User
from app.services.file_parser import parse_livestream_review_file
from app.services.workspace_prompt import resolve_prompt
from app.tools.livestream_review.service import (
    merge_scripts_and_excel,
    generate_review_stream,
)

router = APIRouter(prefix="/tools/livestream-review", tags=["livestream-review"])

TOOL_CODE = "livestream-review"
TOOL_NAME = "直播间脚本复盘"


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def require_operator(current_user: User = Depends(get_current_user)) -> User:
    if current_user.password_changed_at is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "AUTH_FORCE_CHANGE_PASSWORD", "message": "请先修改初始密码"},
        )
    if current_user.role not in ("operator", "admin"):
        raise HTTPException(
            status_code=403,
            detail={"code": "PERMISSION_DENIED", "message": "无权限访问"},
        )
    return current_user


# ---------------------------------------------------------------------------
# POST /tools/livestream-review/parse-file
# ---------------------------------------------------------------------------

@router.post("/parse-file")
async def parse_file(
    file: UploadFile = File(...),
    current_user: User = Depends(require_operator),
):
    try:
        text = await parse_livestream_review_file(file)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "UNSUPPORTED_FORMAT", "message": str(e)},
        )
    return success_response(data={"text": text, "filename": file.filename})


# ---------------------------------------------------------------------------
# POST /tools/livestream-review/generate
# ---------------------------------------------------------------------------

class ScriptItem(BaseModel):
    title: str
    content: str


class ExcelRowItem(BaseModel):
    live_theme: str = ""
    live_date: str = ""
    duration: str = ""
    peak_viewers: str = ""
    avg_viewers: str = ""
    total_uv: str = ""
    avg_stay_time: str = ""
    likes: str = ""
    comments: str = ""
    follows_gained: str = ""
    conversions: str = ""
    gmv: str = ""
    gpm: str = ""
    ad_spend: str = ""


class GenerateRequest(BaseModel):
    scripts: list[ScriptItem]
    excel_data: list[ExcelRowItem] = []
    kol_id: int | None = None


@router.post("/generate")
async def generate(
    body: GenerateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    if not body.scripts:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "脚本列表不能为空"},
        )

    # 创建 task_job
    task_no = f"LR-{int(time.time())}-{current_user.id}"
    task_job = TaskJob(
        task_no=task_no,
        tool_code=TOOL_CODE,
        tool_name=TOOL_NAME,
        status="processing",
        started_at=datetime.now(timezone.utc),
        created_by=current_user.id,
    )
    db.add(task_job)
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="generate_livestream_review",
        target_type="task_job",
        target_id=None,
        detail={"task_no": task_no, "tool_code": TOOL_CODE, "script_count": len(body.scripts)},
        ip=(request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown")),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(task_job)
    task_job_id = task_job.id

    # 合并脚本与 Excel 数据
    scripts = [s.model_dump() for s in body.scripts]
    excel_data = [e.model_dump() for e in body.excel_data]
    merged = merge_scripts_and_excel(scripts, excel_data)

    user_id = current_user.id

    # 查询红人专属 Prompt（has_excel 决定用哪条，这里先在 router 层做决策）
    has_excel_flag = any(
        row.get("gmv") or row.get("gpm") or row.get("ad_spend")
        for row in [e.model_dump() for e in body.excel_data]
    )
    prompt_key = "with_excel_prompt" if has_excel_flag else "without_excel_prompt"
    override_prompt = await resolve_prompt(body.kol_id, "livestream-review", prompt_key, db)

    async def stream_with_db():
        async with AsyncSessionLocal() as stream_db:
            async for chunk in generate_review_stream(
                merged=merged,
                db=stream_db,
                user_id=user_id,
                task_job_id=task_job_id,
                override_prompt=override_prompt,
            ):
                yield chunk

    return StreamingResponse(
        stream_with_db(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Task-Id": str(task_job_id)},
    )


# ---------------------------------------------------------------------------
# POST /tools/livestream-review/save
# ---------------------------------------------------------------------------

class SaveRequest(BaseModel):
    task_id: int
    report: str
    script_count: int = 0
    has_excel: bool = False


@router.post("/save")
async def save_report(
    body: SaveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    if not body.report.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "报告内容不能为空"},
        )

    data_label = "有数据" if body.has_excel else "仅脚本"
    title = f"直播间脚本复盘_{body.script_count}场_{data_label}"

    output = Output(
        title=title,
        tool_code=TOOL_CODE,
        tool_name=TOOL_NAME,
        content=body.report,
        word_count=len(body.report.split()),
        task_id=body.task_id,
        created_by=current_user.id,
    )
    db.add(output)
    await db.flush()

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="save_review",
        target_type="output",
        target_id=output.id,
        detail={"script_count": body.script_count, "has_excel": body.has_excel},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()

    return success_response(data={"output_id": output.id})


# ---------------------------------------------------------------------------
# GET /tools/livestream-review/outputs
# ---------------------------------------------------------------------------

@router.get("/outputs")
async def get_outputs(
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    from sqlalchemy import func, desc

    total_row = (await db.execute(
        sa_text(
            "SELECT COUNT(*) FROM outputs WHERE tool_code=:tc AND created_by=:uid"
        ),
        {"tc": TOOL_CODE, "uid": current_user.id},
    )).scalar()

    rows = (await db.execute(
        sa_text(
            "SELECT id, title, created_at, task_id FROM outputs "
            "WHERE tool_code=:tc AND created_by=:uid "
            "ORDER BY created_at DESC LIMIT :lim OFFSET :off"
        ),
        {"tc": TOOL_CODE, "uid": current_user.id, "lim": size, "off": (page - 1) * size},
    )).fetchall()

    items = [
        {
            "id": r[0],
            "title": r[1],
            "created_at": r[2].isoformat() if r[2] else None,
            "task_id": r[3],
        }
        for r in rows
    ]
    return success_response(data={"items": items, "total": total_row or 0})
