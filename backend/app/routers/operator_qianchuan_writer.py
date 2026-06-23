"""
app/routers/operator_qianchuan_writer.py

运营端接口（JWT 鉴权，operator / admin 角色）：
  GET  /api/tools/qianchuan-writer/kols/personas  — 达人人设列表
  POST /api/tools/qianchuan-writer/parse-file     — 文件解析
  POST /api/tools/qianchuan-writer/chat           — AI 流式对话（raw text stream）
  POST /api/tools/qianchuan-writer/save-output    — 保存产出
  POST /api/tools/qianchuan-writer/export-word    — 导出 Word 文档
  GET  /api/tools/qianchuan-writer/outputs        — 历史记录（账号隔离）
"""
import asyncio
import time
import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.adapters import yunwu as yunwu_adapter
from app.core.database import AsyncSessionLocal, get_db
from app.core.response import success_response, error_response, ErrorCode
from app.middlewares.auth import get_current_user
from app.models.kol import Kol
from app.models.log import OperationLog
from app.models.output import Output
from app.models.qianchuan_writer import QianchuanWriterConfig
from app.models.task import TaskJob
from app.models.user import User
from app.services import word_export
from app.services.file_parser import parse_uploaded_file
from app.services.qianchuan_writer_prompt import render_system_prompt

router = APIRouter(prefix="/tools/qianchuan-writer", tags=["qianchuan-writer"])

TOOL_CODE = "qianchuan-writer"
TOOL_NAME = "千川文案写作"
DEFAULT_MODEL = "claude-opus-4-6-thinking"
_RETRY_DELAYS = [2, 4, 6]
_PAGE_SIZE_ALLOWED = {10, 20, 50}
_PERSONA_PREVIEW_CHARS = 400


# ---------------------------------------------------------------------------
# 内部 helpers
# ---------------------------------------------------------------------------

async def require_operator(current_user: User = Depends(get_current_user)) -> User:
    """operator / admin 角色校验 + 已改密。"""
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


async def _get_config(db: AsyncSession) -> QianchuanWriterConfig:
    """读取激活的 default 配置，不存在则抛 503。"""
    config = (await db.execute(
        select(QianchuanWriterConfig)
        .where(QianchuanWriterConfig.config_key == "default")
        .where(QianchuanWriterConfig.is_active == True)  # noqa: E712
    )).scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CONFIG_NOT_FOUND",
                "message": "qianchuan-writer 配置 'default' 未激活，请联系管理员",
            },
        )
    return config


async def _resolve_model_id(config: QianchuanWriterConfig, db: AsyncSession) -> str:
    """解析配置绑定的模型 ID，留空或失效则返回默认值。"""
    if not config.ai_model_id:
        return DEFAULT_MODEL
    row = (await db.execute(
        sa_text("SELECT model_id FROM ai_models WHERE id = :id AND status = 'active'"),
        {"id": config.ai_model_id},
    )).fetchone()
    return row[0] if row else DEFAULT_MODEL


# ---------------------------------------------------------------------------
# GET /kols/personas
# ---------------------------------------------------------------------------

@router.get("/kols/personas")
async def get_kol_personas(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Step 1 达人下拉：返回 persona + content_plan 均非空且未删除的达人。"""
    rows = (
        await db.execute(
            sa_text(
                """
                SELECT k.id,
                       k.name,
                       LEFT(k.persona, :preview_len) AS soul_preview,
                       COALESCE(u.username, '系统预设') AS creator_name
                FROM kols k
                LEFT JOIN users u ON k.created_by = u.id
                WHERE k.persona IS NOT NULL
                  AND k.content_plan IS NOT NULL
                  AND k.deleted_at IS NULL
                  AND k.status = 'active'
                ORDER BY k.name
                """
            ),
            {"preview_len": _PERSONA_PREVIEW_CHARS},
        )
    ).fetchall()

    personas = [
        {
            "id": row[0],
            "name": row[1],
            "soul_preview": row[2] or "",
            "creator_name": row[3],
        }
        for row in rows
    ]
    return success_response(data=personas)


# ---------------------------------------------------------------------------
# POST /parse-file
# ---------------------------------------------------------------------------

@router.post("/parse-file")
async def parse_file(
    file: UploadFile = File(...),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Step 2 产品卖点卡文件解析（.txt/.md/.docx/.pdf）。"""
    try:
        text = await parse_uploaded_file(file)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "UNSUPPORTED_FILE_TYPE", "message": str(e)},
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "FILE_PARSE_ERROR", "message": f"文件解析失败: {e}"},
        )

    word_count = len(text.replace(" ", "").replace("\n", "").replace("\t", ""))
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="qianchuan_parse_file",
        target_type="file",
        target_id=None,
        detail={"filename": file.filename, "word_count": word_count},
        ip=_get_ip(request) if request else "unknown",
        user_agent=request.headers.get("user-agent") if request else None,
    ))
    await db.commit()

    return success_response(data={"text": text, "word_count": word_count})


# ---------------------------------------------------------------------------
# POST /chat  (流式)
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    messages: list[dict]
    persona_id: int
    create_job: bool = False
    job_context: dict | None = None


@router.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Step 4 AI 流式仿写：DB 读 Prompt 模板 → 读达人 → 渲染 → chat_stream。"""
    if not body.messages:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "messages 不能为空"},
        )

    config = await _get_config(db)
    model_id = await _resolve_model_id(config, db)

    # 读达人人设
    kol_row = (await db.execute(
        sa_text(
            """
            SELECT name, persona, content_plan
            FROM kols
            WHERE id = :id AND deleted_at IS NULL
            """
        ),
        {"id": body.persona_id},
    )).fetchone()
    if kol_row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "达人人设不存在或已删除"},
        )
    kol_name, kol_persona, kol_content_plan = kol_row[0], kol_row[1] or "", kol_row[2] or ""

    # 渲染 system_prompt
    template = config.system_prompt or ""
    system_prompt = render_system_prompt(
        template,
        name=kol_name,
        soul=kol_persona,
        content_plan=kol_content_plan,
    )

    messages = [{"role": "system", "content": system_prompt}] + body.messages
    user_id = current_user.id
    create_job = body.create_job
    job_context = body.job_context or {}

    async def generate():
        delays = [0] + _RETRY_DELAYS
        for i, delay in enumerate(delays):
            if delay:
                await asyncio.sleep(delay)
            try:
                async with AsyncSessionLocal() as stream_db:
                    async for chunk in yunwu_adapter.chat_stream(
                        messages=messages,
                        db=stream_db,
                        model_id=model_id,
                        user_id=user_id,
                        feature="qianchuan_writer_chat",
                        max_tokens=8192,
                    ):
                        yield chunk
                return
            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = "429" in err_str or "rate" in err_str
                if is_rate_limit and i < len(delays) - 1:
                    continue
                yield f"\n\n[ERROR] {str(e)}"
                return

    async def write_task_job():
        """BackgroundTask：创建 task_job + 写 OperationLog。"""
        if not create_job:
            return
        async with AsyncSessionLocal() as bg_db:
            task_job = TaskJob(
                task_no=f"QC-{int(time.time())}",
                tool_code=TOOL_CODE,
                tool_name=TOOL_NAME,
                status="completed",
                input_payload={
                    "persona_id": body.persona_id,
                    "persona_name": kol_name,
                    "product_name": job_context.get("product_name", ""),
                    "original_script_length": job_context.get("original_script_length", 0),
                },
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                created_by=user_id,
            )
            bg_db.add(task_job)
            await bg_db.flush()
            bg_db.add(OperationLog(
                user_id=current_user.id,
                username=current_user.username,
                role=current_user.role,
                action="qianchuan_writer_chat",
                target_type="task_job",
                target_id=task_job.id,
                detail={
                    "persona_name": kol_name,
                    "model_id": model_id,
                    "job_context": job_context,
                },
                ip=_get_ip(request),
                user_agent=request.headers.get("user-agent"),
            ))
            await bg_db.commit()

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        background=BackgroundTask(write_task_job),
    )


# ---------------------------------------------------------------------------
# POST /save-output
# ---------------------------------------------------------------------------

class SaveOutputRequest(BaseModel):
    task_id: int | None = None
    title: str = ""
    content: str
    product_name: str | None = None


@router.post("/save-output")
async def save_output(
    body: SaveOutputRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """保存仿写产出至 outputs 表（账号绑定）。"""
    if not body.content.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "content 不能为空"},
        )

    word_count = len(body.content.replace(" ", "").replace("\n", "").replace("\t", ""))
    output = Output(
        title=body.title or f"{TOOL_NAME} · {datetime.now().strftime('%Y-%m-%d')}",
        tool_code=TOOL_CODE,
        tool_name=TOOL_NAME,
        content=body.content,
        word_count=word_count,
        task_id=body.task_id,
        created_by=current_user.id,
    )
    db.add(output)
    await db.flush()

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="qianchuan_writer_save_output",
        target_type="output",
        target_id=output.id,
        detail={
            "title": body.title,
            "product_name": body.product_name,
            "word_count": word_count,
        },
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()

    return success_response(data={"output_id": output.id})


# ---------------------------------------------------------------------------
# POST /export-word
# ---------------------------------------------------------------------------

class ExportWordRequest(BaseModel):
    content: str
    filename: str = "千川仿写"


@router.post("/export-word")
async def export_word(
    body: ExportWordRequest,
    current_user: User = Depends(require_operator),
):
    """导出 Word 文档（.docx），返回二进制流。"""
    if not body.content.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "content 不能为空"},
        )

    date_str = datetime.now().strftime("%Y-%m-%d")
    title = body.filename or "千川仿写"
    metadata_lines = [f"导出日期: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]

    docx_bytes = word_export.markdown_to_docx_bytes(
        title=title,
        metadata_lines=metadata_lines,
        content=body.content,
    )

    safe_name = body.filename or "千川仿写"
    from urllib.parse import quote
    filename_encoded = quote(f"{safe_name}_{date_str}.docx")
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename_encoded}",
        },
    )


# ---------------------------------------------------------------------------
# GET /outputs
# ---------------------------------------------------------------------------

@router.get("/outputs")
async def list_outputs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """历史记录：按账号隔离，只返回当前用户的 outputs。"""
    if page_size not in _PAGE_SIZE_ALLOWED:
        page_size = 20

    # 总数
    total = (await db.execute(
        sa_text(
            """
            SELECT COUNT(*) FROM outputs
            WHERE tool_code = :tool_code
              AND created_by = :user_id
              AND deleted_at IS NULL
            """
        ),
        {"tool_code": TOOL_CODE, "user_id": current_user.id},
    )).scalar() or 0

    rows = (await db.execute(
        sa_text(
            """
            SELECT id, title, content, word_count, task_id, created_at
            FROM outputs
            WHERE tool_code = :tool_code
              AND created_by = :user_id
              AND deleted_at IS NULL
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {
            "tool_code": TOOL_CODE,
            "user_id": current_user.id,
            "limit": page_size,
            "offset": (page - 1) * page_size,
        },
    )).fetchall()

    items = [
        {
            "id": row[0],
            "title": row[1],
            "content": row[2],
            "word_count": row[3],
            "task_id": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
        }
        for row in rows
    ]

    total_pages = math.ceil(total / page_size) if total > 0 else 0
    return success_response(data={
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        },
    })
