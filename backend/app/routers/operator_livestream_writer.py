"""
app/routers/operator_livestream_writer.py

运营端接口（JWT 鉴权，operator / admin 角色）：
  GET  /api/tools/livestream-writer/config         — 获取激活的 Prompt + 模型（实时拉取）
  GET  /api/tools/livestream-writer/kols/personas  — 达人列表（content_plan 和 persona 均非空）
  POST /api/tools/livestream-writer/parse-file     — 文件解析（.txt/.md/.docx/.pages）
  POST /api/tools/livestream-writer/chat           — AI 流式对话（raw text stream）
"""
import asyncio
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.adapters import yunwu as yunwu_adapter
from app.core.database import AsyncSessionLocal, get_db
from app.core.response import success_response
from app.middlewares.auth import get_current_user
from app.models.kol import Kol
from app.models.livestream_writer import LivestreamWriterConfig
from app.models.log import OperationLog
from app.models.output import Output
from app.models.task import TaskJob
from app.models.user import User
from app.services.file_parser import parse_livestream_writer_file
from app.services.kol_context import get_current_product, get_kol_context
from app.services.workspace_prompt import resolve_prompt

router = APIRouter(prefix="/tools/livestream-writer", tags=["livestream-writer"])

TOOL_CODE = "livestream-writer"
TOOL_NAME = "直播脚本仿写"
DEFAULT_MODEL = "claude-opus-4-6-thinking"
# 429 重试退避（秒），比 tiktok-writer 更激进（5次，5/10/15/20/25s）
_RETRY_DELAYS = [5, 10, 15, 20, 25]


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


async def _get_lw_config(key: str, db: AsyncSession) -> LivestreamWriterConfig:
    """读取激活的配置，不存在则抛 503。"""
    config = (await db.execute(
        select(LivestreamWriterConfig)
        .where(LivestreamWriterConfig.config_key == key)
        .where(LivestreamWriterConfig.is_active == True)  # noqa: E712
    )).scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "CONFIG_NOT_FOUND", "message": f"livestream-writer 配置 '{key}' 未激活，请联系管理员"},
        )
    return config


async def _resolve_lw_model(config: LivestreamWriterConfig, db: AsyncSession) -> str:
    """解析绑定的模型 ID，无绑定则返回默认值。"""
    if not config.ai_model_id:
        return DEFAULT_MODEL
    row = (await db.execute(
        sa_text("SELECT model_id FROM ai_models WHERE id = :id AND status = 'active'"),
        {"id": config.ai_model_id},
    )).fetchone()
    return row[0] if row else DEFAULT_MODEL


# ---------------------------------------------------------------------------
# GET /config
# ---------------------------------------------------------------------------

@router.get("/config")
async def get_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """返回两条激活配置的 Prompt + 绑定模型，供前端实时拉取。"""
    generate_cfg = await _get_lw_config("generate", db)
    iterate_cfg  = await _get_lw_config("iterate",  db)
    model_id = await _resolve_lw_model(generate_cfg, db)
    return success_response(data={
        "generate_prompt": generate_cfg.system_prompt or "",
        "iterate_prompt":  iterate_cfg.system_prompt or "",
        "model_id": model_id,
    })


# ---------------------------------------------------------------------------
# GET /kols/personas
# ---------------------------------------------------------------------------

@router.get("/kols/personas")
async def get_kol_personas(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """查询 kols 表，返回 content_plan 和 persona 均非空的达人列表。"""
    rows = (
        await db.execute(
            select(Kol.id, Kol.name, Kol.persona, Kol.content_plan)
            .where(Kol.content_plan.is_not(None))
            .where(Kol.persona.is_not(None))
            .where(Kol.deleted_at.is_(None))
            .where(Kol.status.in_(["signed", "pending_renewal"]))
            .order_by(Kol.name)
        )
    ).all()

    personas = [
        {
            "id": row.id,
            "name": row.name,
            "soul": row.persona or "",
            "contentPlan": row.content_plan or "",
        }
        for row in rows
    ]
    return success_response(data={"personas": personas})


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
    """解析上传文件，返回纯文本。支持 .txt/.md/.docx/.pages，不支持 .pdf。"""
    try:
        text = await parse_livestream_writer_file(file)
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

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="livestream_parse_file",
        target_type="file",
        target_id=None,
        detail={"filename": file.filename},
        ip=_get_ip(request) if request else "unknown",
        user_agent=request.headers.get("user-agent") if request else None,
    ))
    await db.commit()

    return success_response(data={"text": text, "filename": file.filename})


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    messages: list[dict]
    systemPrompt: str
    model: str = DEFAULT_MODEL
    workspace_mode: bool = False
    kol_id: int | None = None
    reference_script: str | None = None
    reference_confirmed: bool = False
    sp_order: str | None = None
    createJob: bool = False
    jobContext: dict | None = None


def _product_fields_for_prompt(product) -> dict[str, str]:
    """只将数据库中已有的商品事实写入提示词。"""
    fields = {
        "产品昵称": product.nickname,
        "最主推卖点": product.core_selling_point,
        "可视化": product.visualization,
        "主推机制": product.mechanism,
        "推荐来源": product.endorsement,
        "用户反馈": product.user_feedback,
        "独家卖点": product.unique_selling,
        "获奖荣誉": product.awards,
        "功效承诺": product.efficacy_proof,
        "只有我有": "是，必须强调独家权益" if product.mechanism_exclusive else "否",
    }
    return {label: str(value) for label, value in fields.items() if value and str(value).strip()}


def _build_initial_system_prompt(
    template: str,
    *,
    kol_context,
    product,
    reference_script: str,
    sp_order: str | None,
) -> str:
    """组合旧版直播仿写所需的服务端事实，不接受前端拼接的商品或系统信息。"""
    sections = [template]
    profile_text = "\n\n".join(
        f"### {label}\n{value}" for label, value in kol_context.prompt_sections()
    )
    if profile_text:
        sections.append(f"## {kol_context.name}完整档案\n{profile_text}")

    product_text = "\n".join(
        f"- {label}：{value}" for label, value in _product_fields_for_prompt(product).items()
    )
    if product_text:
        sections.append(
            "## 当前商品事实（必须以此为准，不得编造）\n"
            f"{product_text}\n"
            "“只有我有”为是时，必须遵守独家权益约束。"
        )

    sections.append(f"## 已确认的对标直播文案\n{reference_script}")
    if sp_order and sp_order.strip():
        sections.append(f"## 卖点顺序\n{sp_order.strip()}")
    return "\n\n".join(section for section in sections if section)


@router.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """AI 流式对话，返回 raw text stream（非 SSE）。429 时最多重试 5 次（5/10/15/20/25s 退避）。"""
    if not body.messages:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "messages 不能为空"},
        )

    if not body.workspace_mode and not body.systemPrompt.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "systemPrompt 不能为空"},
        )

    config_key = "generate" if body.createJob else "iterate"
    config = await _get_lw_config(config_key, db)
    model_id = await _resolve_lw_model(config, db)
    kol_context = None
    product = None
    if body.workspace_mode:
        if body.kol_id is None:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_INPUT", "message": "工作台生成必须选择红人"},
            )
        if not body.reference_confirmed or not (body.reference_script or "").strip():
            raise HTTPException(
                status_code=400,
                detail={"code": "REFERENCE_SCRIPT_REQUIRED", "message": "请先确认对标直播文案后再生成或修改"},
            )
        if not (body.sp_order or "").strip():
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_INPUT", "message": "请先选择卖点顺序"},
            )
        kol_context = await get_kol_context(db, body.kol_id)
        product = await get_current_product(db, body.kol_id)
        if product is None:
            raise HTTPException(
                status_code=400,
                detail={"code": "CURRENT_PRODUCT_REQUIRED", "message": "请先选择或新建当前商品后再生成"},
            )

    # 工作台只信任后台配置和数据库事实；独立入口保留旧版前端拼好的业务输入。
    kol_prompt = await resolve_prompt(body.kol_id, "livestream-writer", "system_prompt", db)
    template = (
        kol_prompt or config.system_prompt or ""
        if body.workspace_mode
        else kol_prompt or body.systemPrompt
    )
    if body.workspace_mode:
        resolved_system_prompt = _build_initial_system_prompt(
            template,
            kol_context=kol_context,
            product=product,
            reference_script=(body.reference_script or "").strip(),
            sp_order=body.sp_order,
        )
    else:
        resolved_system_prompt = template

    messages = [{"role": "system", "content": resolved_system_prompt}] + body.messages
    user_id = current_user.id
    create_job = body.createJob
    job_context = body.jobContext or {}
    # 模型始终由后台统一配置决定，前端 model 参数仅为旧调用兼容字段。
    provider = "yunwu"

    # 流式生成时积累完整内容，供 BackgroundTask 写 outputs
    accumulated: list[str] = []

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
                        provider=provider,
                        user_id=user_id,
                        feature="livestream_writer_chat",
                        max_tokens=8192,
                    ):
                        accumulated.append(chunk)
                        yield chunk
                return
            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = "429" in err_str or "rate" in err_str
                if is_rate_limit and i < len(delays) - 1:
                    continue
                yield f"\n\n[ERROR] {str(e)}"
                return

    async def write_job_and_output():
        if not create_job:
            return
        full_content = "".join(accumulated)
        product_name = product.nickname if product else job_context.get("productName", "")
        persona_name = kol_context.name if kol_context else job_context.get("personaName", "")

        async with AsyncSessionLocal() as bg_db:
            task_job = TaskJob(
                task_no=f"LW-{time.time_ns()}",
                tool_code=TOOL_CODE,
                tool_name=TOOL_NAME,
                status="completed",
                input_payload={
                    "kol_id": kol_context.kol_id if kol_context else None,
                    "product_id": product.id if product else None,
                    "productName": product_name,
                    "personaName": persona_name,
                    "spOrder": body.sp_order or job_context.get("spOrder", ""),
                    "refLength": len((body.reference_script or "").strip()) or job_context.get("refLength", 0),
                    "feature": job_context.get("feature", "livestream_draft"),
                    "model": model_id,
                    "output_marker": "stream_completed",
                },
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                created_by=user_id,
            )
            bg_db.add(task_job)
            await bg_db.flush()

            output = Output(
                title=f"开播方案 · {product_name} · {persona_name}",
                tool_code=TOOL_CODE,
                tool_name=TOOL_NAME,
                content=full_content,
                word_count=len(full_content.replace(" ", "").replace("\n", "").replace("\t", "")),
                task_id=task_job.id,
                created_by=user_id,
            )
            bg_db.add(output)
            bg_db.add(OperationLog(
                user_id=user_id,
                username=current_user.username,
                role=current_user.role,
                action="chat_livestream_writer",
                target_type="output",
                target_id=output.id,
                detail={
                    "task_no": task_job.task_no,
                    "tool_code": TOOL_CODE,
                    "model": model_id,
                    "word_count": output.word_count,
                },
                ip=(request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                    or (request.client.host if request.client else "unknown")),
                user_agent=request.headers.get("user-agent"),
            ))
            await bg_db.commit()

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        background=BackgroundTask(write_job_and_output),
    )
