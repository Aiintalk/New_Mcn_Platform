"""
app/routers/operator_values_writer.py

运营端接口（JWT 鉴权，operator / admin 角色）：
  POST /api/operator/values-writer/extract-values    — 提炼价值观（非流式）
  POST /api/operator/values-writer/emotion-direction — 推导情绪方向（SSE 流式）
  POST /api/operator/values-writer/write             — 生成价值观内容（SSE 流式）
  POST /api/operator/values-writer/iterate           — 迭代优化（SSE 流式）
  POST /api/operator/values-writer/save-output       — 保存产出（手动保存到历史）
"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import yunwu as yunwu_adapter
from app.core.database import AsyncSessionLocal, get_db
from app.core.response import success_response
from app.middlewares.auth import get_current_user
from app.models.log import OperationLog
from app.models.output import Output
from app.models.values_writer import ValuesWriterConfig
from app.models.user import User
from app.services.workspace_prompt import resolve_prompt

router = APIRouter(prefix="/operator/values-writer", tags=["operator-values-writer"])

TOOL_CODE = "values-writer"
TOOL_NAME = "价值观仿写"

_DEFAULT_EXTRACT_PROMPT = (
    "你是一位内容策略师。根据以下达人档案，提炼出该达人在内容创作上最核心的3-6个价值观关键词。\n"
    "只输出 JSON 数组，不加任何其他文字，例如：[\"真实\", \"治愈\", \"共鸣\"]\n\n"
    "档案：{persona_text}"
)

_DEFAULT_EMOTION_PROMPT = (
    "你是一位情绪方向顾问。根据以下达人档案和选定的价值观，推导出适合的情绪方向。\n\n"
    "达人档案：{persona_text}\n"
    "选定价值观：{selected_values}\n"
    "内容基调：{tone}"
)

_DEFAULT_WRITING_PROMPT = (
    "你是一位内容创作专家。根据以下达人档案、价值观和情绪方向，生成一段价值观内容。\n\n"
    "达人档案：{persona_text}\n"
    "选定价值观：{selected_values}\n"
    "情绪方向：{emotion_direction}\n"
    "产品背景：{product_context}"
)

_DEFAULT_ITERATION_PROMPT = (
    "你是一位内容优化专家。根据用户的修改指令，对以下内容进行迭代优化。\n\n"
    "达人档案：{persona_text}\n"
    "当前内容：\n{content}\n\n"
    "修改指令：{instruction}"
)


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
    """从 request 取客户端 IP（优先 x-forwarded-for）。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _get_kol_persona(db: AsyncSession, kol_id: int) -> str:
    """读取达人档案字段，拼成文本返回。不存在则抛 404。"""
    from sqlalchemy import text as sa_text
    row = (await db.execute(
        sa_text(
            """
            SELECT name, persona, background, experience, relationships, extra_notes
            FROM kols
            WHERE id = :id AND deleted_at IS NULL
            """
        ),
        {"id": kol_id},
    )).fetchone()
    if row is None:
        return None
    name, persona, background, experience, relationships, extra_notes = row
    parts = []
    if name:
        parts.append(f"达人姓名：{name}")
    if persona:
        parts.append(f"人设：{persona}")
    if background:
        parts.append(f"背景：{background}")
    if experience:
        parts.append(f"经历：{experience}")
    if relationships:
        parts.append(f"关系：{relationships}")
    if extra_notes:
        parts.append(f"补充：{extra_notes}")
    return "\n".join(parts) if parts else ""


async def _get_config(db: AsyncSession) -> ValuesWriterConfig | None:
    """读取 default 配置，不存在返回 None（不抛错）。"""
    return (await db.execute(
        select(ValuesWriterConfig)
        .where(ValuesWriterConfig.config_key == "default")
        .where(ValuesWriterConfig.is_active == True)  # noqa: E712
    )).scalar_one_or_none()


async def _resolve_model(config: ValuesWriterConfig | None, db: AsyncSession) -> tuple[str, str]:
    """解析配置绑定的 (model_id, provider)，留空或失效则返回默认值。"""
    from sqlalchemy import text as sa_text
    default_model = "claude-haiku-4-5-20251001"
    default_provider = "yunwu"
    if config is None or config.model_id is None:
        return default_model, default_provider
    row = (await db.execute(
        sa_text("SELECT model_id, COALESCE(provider, :default_p) FROM ai_models WHERE id = :id AND status = 'active'"),
        {"id": config.model_id, "default_p": default_provider},
    )).fetchone()
    return (row[0], row[1]) if row else (default_model, default_provider)


def _sse_chunk(delta: str) -> str:
    return f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"


def _sse_done() -> str:
    return f"data: {json.dumps({'done': True})}\n\n"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ExtractValuesRequest(BaseModel):
    kol_id: int
    extra_context: str | None = None


class EmotionDirectionRequest(BaseModel):
    kol_id: int
    selected_values: list[str]
    tone: str | None = ""


class WriteRequest(BaseModel):
    kol_id: int
    selected_values: list[str]
    emotion_direction: str
    product_context: str | None = ""


class IterateRequest(BaseModel):
    kol_id: int
    content: str
    instruction: str


# ---------------------------------------------------------------------------
# POST /extract-values（非流式）
# ---------------------------------------------------------------------------

@router.post("/extract-values")
async def extract_values(
    body: ExtractValuesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """提炼达人价值观关键词（非流式，等待完整响应）。"""
    persona_text = await _get_kol_persona(db, body.kol_id)
    if persona_text is None:
        return success_response(
            data=None,
            message="达人不存在或已删除",
        )

    config = await _get_config(db)
    model_id, provider = await _resolve_model(config, db)

    prompt_template = (
        await resolve_prompt(body.kol_id, "values-writer", "extract_values_prompt", db)
        or (config.extract_values_prompt if config and config.extract_values_prompt else _DEFAULT_EXTRACT_PROMPT)
    )
    prompt = prompt_template.format(persona_text=persona_text)
    if body.extra_context:
        prompt += f"\n\n额外背景：{body.extra_context}"

    messages = [{"role": "user", "content": prompt}]

    async with AsyncSessionLocal() as ai_db:
        try:
            ai_output = await yunwu_adapter.chat(
                messages=messages,
                db=ai_db,
                model_id=model_id,
                provider=provider,
                user_id=current_user.id,
                feature="values_writer_extract",
            )
        except RuntimeError as e:
            raise HTTPException(
                status_code=502,
                detail={"code": "EXTERNAL_SERVICE_ERROR", "message": str(e)},
            )

    # 解析 JSON 数组
    try:
        start = ai_output.find("[")
        end = ai_output.rfind("]")
        if start != -1 and end != -1:
            values = json.loads(ai_output[start:end + 1])
        else:
            values = []
    except (json.JSONDecodeError, ValueError):
        values = []

    return success_response(data={"values": values})


# ---------------------------------------------------------------------------
# POST /emotion-direction（SSE 流式）
# ---------------------------------------------------------------------------

@router.post("/emotion-direction")
async def emotion_direction(
    body: EmotionDirectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """推导情绪方向（SSE 流式）。"""
    persona_text = await _get_kol_persona(db, body.kol_id)
    if persona_text is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "达人不存在或已删除"},
        )

    config = await _get_config(db)
    model_id, provider = await _resolve_model(config, db)

    prompt_template = (
        await resolve_prompt(body.kol_id, "values-writer", "emotion_direction_prompt", db)
        or (config.emotion_direction_prompt if config and config.emotion_direction_prompt else _DEFAULT_EMOTION_PROMPT)
    )
    values_str = "、".join(body.selected_values)
    prompt = prompt_template.format(
        persona_text=persona_text,
        selected_values=values_str,
        tone=body.tone or "",
    )
    messages = [{"role": "user", "content": prompt}]
    user_id = current_user.id

    async def generate():
        async with AsyncSessionLocal() as stream_db:
            try:
                async for chunk in yunwu_adapter.chat_stream(
                    messages=messages,
                    db=stream_db,
                    model_id=model_id,
                    provider=provider,
                    user_id=user_id,
                    feature="values_writer_emotion",
                ):
                    yield _sse_chunk(chunk)
            except Exception as e:
                yield _sse_chunk(f"[ERROR] {e}")
        yield _sse_done()

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# POST /write（SSE 流式）
# ---------------------------------------------------------------------------

@router.post("/write")
async def write(
    body: WriteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """生成价值观内容（SSE 流式）。"""
    persona_text = await _get_kol_persona(db, body.kol_id)
    if persona_text is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "达人不存在或已删除"},
        )

    config = await _get_config(db)
    model_id, provider = await _resolve_model(config, db)

    prompt_template = (
        await resolve_prompt(body.kol_id, "values-writer", "writing_prompt", db)
        or (config.writing_prompt if config and config.writing_prompt else _DEFAULT_WRITING_PROMPT)
    )
    values_str = "、".join(body.selected_values)
    prompt = prompt_template.format(
        persona_text=persona_text,
        selected_values=values_str,
        emotion_direction=body.emotion_direction,
        product_context=body.product_context or "",
    )
    messages = [{"role": "user", "content": prompt}]
    user_id = current_user.id

    async def generate():
        async with AsyncSessionLocal() as stream_db:
            try:
                async for chunk in yunwu_adapter.chat_stream(
                    messages=messages,
                    db=stream_db,
                    model_id=model_id,
                    provider=provider,
                    user_id=user_id,
                    feature="values_writer_write",
                ):
                    yield _sse_chunk(chunk)
            except Exception as e:
                yield _sse_chunk(f"[ERROR] {e}")
        yield _sse_done()

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# POST /iterate（SSE 流式）
# ---------------------------------------------------------------------------

@router.post("/iterate")
async def iterate(
    body: IterateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """根据指令迭代优化内容（SSE 流式）。"""
    persona_text = await _get_kol_persona(db, body.kol_id)
    if persona_text is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "达人不存在或已删除"},
        )

    config = await _get_config(db)
    model_id, provider = await _resolve_model(config, db)

    prompt_template = (
        await resolve_prompt(body.kol_id, "values-writer", "iteration_prompt", db)
        or (config.iteration_prompt if config and config.iteration_prompt else _DEFAULT_ITERATION_PROMPT)
    )
    prompt = prompt_template.format(
        persona_text=persona_text,
        content=body.content,
        instruction=body.instruction,
    )
    messages = [{"role": "user", "content": prompt}]
    user_id = current_user.id

    async def generate():
        async with AsyncSessionLocal() as stream_db:
            try:
                async for chunk in yunwu_adapter.chat_stream(
                    messages=messages,
                    db=stream_db,
                    model_id=model_id,
                    provider=provider,
                    user_id=user_id,
                    feature="values_writer_iterate",
                ):
                    yield _sse_chunk(chunk)
            except Exception as e:
                yield _sse_chunk(f"[ERROR] {e}")
        yield _sse_done()

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# POST /save-output（手动保存产出至 outputs 表）
# ---------------------------------------------------------------------------

class SaveOutputRequest(BaseModel):
    content: str
    title: str = ""
    topic: str | None = None  # 价值观主题，写入 OperationLog 便于追溯


@router.post("/save-output", response_model=None)
async def save_output(
    body: SaveOutputRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """保存价值观仿写产出至 outputs 表（账号隔离，复用全局 GET /outputs?tool_code=...）。"""
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
        created_by=current_user.id,
    )
    db.add(output)
    await db.flush()

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="values_writer_save_output",
        target_type="output",
        target_id=output.id,
        detail={
            "title": body.title,
            "topic": body.topic,
            "word_count": word_count,
        },
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()

    return success_response(data={"output_id": output.id})
