"""
app/routers/operator_qianchuan_review.py

千川脚本复盘接口（operator / admin 鉴权）：
  POST  /api/tools/qianchuan-review/parse-file  — 上传脚本文件，返回文本
  POST  /api/tools/qianchuan-review/generate    — SSE 流式生成复盘报告
  POST  /api/tools/qianchuan-review/save        — 保存报告到 outputs 表
  GET   /api/tools/qianchuan-review/outputs     — 查询历史复盘报告列表
"""
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.core.database import AsyncSessionLocal, get_db
from app.core.response import success_response
from app.middlewares.auth import get_current_user
from app.models.log import OperationLog
from app.models.output import Output
from app.models.qianchuan_review import QianchuanReviewConfig
from app.models.task import TaskJob
from app.models.user import User
from app.services.file_parser import parse_qianchuan_review_file
from app.services.qianchuan_review_service import (
    TOOL_CODE,
    TOOL_NAME,
    MAX_SCRIPTS,
    ExcelRow,
    ScriptItem,
    generate_review_stream,
    merge_scripts_and_excel,
)

router = APIRouter(prefix="/tools/qianchuan-review", tags=["qianchuan-review"])


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


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _get_qr_config(key: str, db: AsyncSession) -> QianchuanReviewConfig:
    """从 DB 读取激活的 qianchuan-review 配置，不存在则抛 503。"""
    config = (await db.execute(
        select(QianchuanReviewConfig)
        .where(QianchuanReviewConfig.config_key == key)
        .where(QianchuanReviewConfig.is_active == True)  # noqa: E712
    )).scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "CONFIG_NOT_FOUND", "message": f"qianchuan-review 配置 '{key}' 未激活，请联系管理员"},
        )
    return config


async def _resolve_qr_model(config: QianchuanReviewConfig, db: AsyncSession) -> str:
    """解析绑定的模型 ID，无绑定则返回默认值。"""
    from sqlalchemy import text as sa_text
    if not config.ai_model_id:
        return "claude-sonnet-4-6"
    row = (await db.execute(
        sa_text("SELECT model_id FROM ai_models WHERE id = :id AND status = 'active'"),
        {"id": config.ai_model_id},
    )).fetchone()
    return row[0] if row else "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# POST /parse-file
# ---------------------------------------------------------------------------

@router.post("/parse-file")
async def parse_file(
    file: UploadFile = File(...),
    current_user: User = Depends(require_operator),
):
    """上传脚本文件，解析返回文本。支持 .txt/.md/.docx/.pages，不支持 .pdf。"""
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "未收到文件"},
        )
    try:
        text = await parse_qianchuan_review_file(file)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "UNSUPPORTED_FORMAT", "message": str(e)},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "PARSE_ERROR", "message": f"文件解析失败: {str(e)}"},
        ) from e
    return success_response(data={"text": text, "filename": file.filename})


# ---------------------------------------------------------------------------
# POST /generate
# ---------------------------------------------------------------------------

class ScriptItemSchema(BaseModel):
    title: str
    content: str


class ExcelRowSchema(BaseModel):
    video_theme: str
    spend: str | None = None
    impressions: str | None = None
    ctr: str | None = None
    three_sec_rate: str | None = None
    conversions: str | None = None
    cost_per_conversion: str | None = None
    roi: str | None = None
    cpm: str | None = None
    time_range: str | None = None


class GenerateRequest(BaseModel):
    scripts: list[ScriptItemSchema]
    excel_data: list[ExcelRowSchema] = []


@router.post("/generate")
async def generate(
    body: GenerateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """SSE 流式生成复盘报告。Response Header X-Task-Id 供前端保存时使用。"""
    if not body.scripts:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "scripts 不能为空"},
        )
    if len(body.scripts) > MAX_SCRIPTS:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "SCRIPTS_LIMIT_EXCEEDED",
                "message": f"脚本条数超过上限（{MAX_SCRIPTS}条），请分批复盘",
            },
        )

    # 流开始前创建 task_job（processing）
    task_no = f"QR-{int(time.time() * 1000)}"
    has_excel = len(body.excel_data) > 0
    task_job = TaskJob(
        task_no=task_no,
        tool_code=TOOL_CODE,
        tool_name=TOOL_NAME,
        status="processing",
        input_payload={
            "script_count": len(body.scripts),
            "has_excel": has_excel,
        },
        started_at=datetime.now(timezone.utc),
        created_by=current_user.id,
    )
    db.add(task_job)
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="qianchuan_review_generate",
        target_type="task_job",
        target_id=None,
        detail={"script_count": len(body.scripts), "has_excel": has_excel},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(task_job)
    task_id = task_job.id

    scripts = [ScriptItem(title=s.title, content=s.content) for s in body.scripts]
    excel_rows = [
        ExcelRow(
            video_theme=e.video_theme,
            spend=e.spend,
            impressions=e.impressions,
            ctr=e.ctr,
            three_sec_rate=e.three_sec_rate,
            conversions=e.conversions,
            cost_per_conversion=e.cost_per_conversion,
            roi=e.roi,
            cpm=e.cpm,
            time_range=e.time_range,
        )
        for e in body.excel_data
    ]
    items = merge_scripts_and_excel(scripts, excel_rows)
    user_id = current_user.id
    start_time = time.monotonic()

    # 从 DB 读取 Prompt + 模型
    config_key = "with_excel" if has_excel else "without_excel"
    qr_config = await _get_qr_config(config_key, db)
    system_prompt = qr_config.system_prompt or ""
    model_id = await _resolve_qr_model(qr_config, db)

    async def generate_stream():
        try:
            async with AsyncSessionLocal() as stream_db:
                async for chunk in generate_review_stream(
                    items=items,
                    system_prompt=system_prompt,
                    model_id=model_id,
                    db=stream_db,
                    user_id=user_id,
                    task_id=task_id,
                ):
                    yield chunk
        except GeneratorExit:
            pass
        except Exception as e:
            yield f"\n\n[ERROR] {str(e)}"

    async def update_task_status():
        duration_ms = int((time.monotonic() - start_time) * 1000)
        async with AsyncSessionLocal() as bg_db:
            job = await bg_db.get(TaskJob, task_id)
            if job:
                job.status = "success"
                job.finished_at = datetime.now(timezone.utc)
                job.duration_ms = duration_ms
                await bg_db.commit()

    return StreamingResponse(
        generate_stream(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Task-Id": str(task_id)},
        background=BackgroundTask(update_task_status),
    )


# ---------------------------------------------------------------------------
# POST /save
# ---------------------------------------------------------------------------

class SaveRequest(BaseModel):
    task_id: int
    report: str
    script_count: int
    has_excel: bool


@router.post("/save")
async def save_report(
    body: SaveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """保存报告到 outputs 表。"""
    if not body.report.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "report 不能为空"},
        )

    excel_label = "含投放数据" if body.has_excel else "仅脚本"
    title = f"千川复盘_{body.script_count}条素材_{excel_label}"

    output = Output(
        title=title,
        tool_code=TOOL_CODE,
        tool_name=TOOL_NAME,
        task_id=body.task_id,
        content=body.report,
        content_json={
            "script_count": body.script_count,
            "has_excel": body.has_excel,
        },
        word_count=len(body.report),
        created_by=current_user.id,
    )
    db.add(output)
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="qianchuan_review_save",
        target_type="output",
        target_id=None,
        detail={"script_count": body.script_count, "has_excel": body.has_excel},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(output)

    return success_response(data={"output_id": output.id})


# ---------------------------------------------------------------------------
# GET /outputs
# ---------------------------------------------------------------------------

@router.get("/outputs")
async def get_outputs(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """operator 只看自己的；admin 看全部。"""
    query = (
        select(Output)
        .where(Output.tool_code == TOOL_CODE)
        .where(Output.deleted_at.is_(None))
    )
    if current_user.role == "operator":
        query = query.where(Output.created_by == current_user.id)

    all_rows = (
        await db.execute(
            query.order_by(Output.created_at.desc())
        )
    ).scalars().all()
    total = len(all_rows)

    start = (page - 1) * size
    rows = all_rows[start: start + size]

    items = []
    for r in rows:
        cj = r.content_json or {}
        items.append({
            "id": r.id,
            "title": r.title,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "preview": (r.content or "")[:100],
            "script_count": cj.get("script_count"),
            "has_excel": cj.get("has_excel"),
            "word_count": r.word_count,
        })

    return success_response(data={"items": items, "total": total})
