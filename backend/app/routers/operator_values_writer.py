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
import re
from datetime import datetime
from uuid import uuid4

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
from app.models.task import TaskJob
from app.models.values_writer import ValuesWriterConfig
from app.models.user import User
from app.services.kol_context import get_current_product, get_kol_context
from app.services.workspace_prompt import resolve_prompt

router = APIRouter(prefix="/operator/values-writer", tags=["operator-values-writer"])

TOOL_CODE = "values-writer"
TOOL_NAME = "价值观仿写"
ALLOWED_DIRECTION_TYPES = {"焦虑型", "诱惑型"}

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


def _restore_locked_opening(content: str, opening_line: str) -> str:
    """兜底恢复 <rewrite> 中被模型改动的锁定开头。"""
    match = re.search(r"(<rewrite>)(.*?)(</rewrite>)", content, flags=re.DOTALL)
    if match is None:
        return content
    rewrite = match.group(2)
    first_line = rewrite.split("\n", 1)[0]
    if first_line == opening_line:
        return content
    remainder = rewrite.split("\n", 1)[1] if "\n" in rewrite else ""
    restored = opening_line if not remainder else f"{opening_line}\n{remainder}"
    return f"{content[:match.start(2)]}{restored}{content[match.end(2):]}"


def _direct_product_facts(product) -> list[str]:
    return [str(value) for value in (
        product.nickname, product.core_selling_point, product.mechanism,
        product.visualization, product.endorsement, product.user_feedback,
        product.unique_selling, product.awards, product.efficacy_proof,
        "只有我有" if product.mechanism_exclusive else None,
    ) if value]


def _validate_directions(directions: list[dict]) -> list[dict]:
    if not 2 <= len(directions) <= 3:
        raise ValueError("需返回 2 至 3 个情绪方向")
    if any(item.get("type") not in ALLOWED_DIRECTION_TYPES for item in directions):
        raise ValueError("情绪方向只支持焦虑型或诱惑型")
    return directions


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


class EmotionDirection(BaseModel):
    type: str
    title: str
    description: str
    anchor: str


class DeriveDirectionsRequest(BaseModel):
    kol_id: int
    opening_line: str
    original_script: str


class GenerateValueScriptRequest(BaseModel):
    kol_id: int
    opening_line: str
    original_script: str
    direction: EmotionDirection


class StructuredValueScriptResult(BaseModel):
    analysis: str
    rewrite: str
    report: str


class StructuredIterationHistoryItem(BaseModel):
    instruction: str
    result: StructuredValueScriptResult


class StructuredIterateRequest(BaseModel):
    kol_id: int
    opening_line: str
    original_script: str
    direction: EmotionDirection
    current_result: StructuredValueScriptResult
    instruction: str
    history: list[StructuredIterationHistoryItem] = []


def _product_prompt(product) -> str:
    fields = (
        ("产品昵称", product.nickname),
        ("最主推卖点", product.core_selling_point),
        ("可视化", product.visualization),
        ("主推机制", product.mechanism),
        ("推荐来源", product.endorsement),
        ("用户反馈", product.user_feedback),
        ("独家卖点", product.unique_selling),
        ("获奖荣誉", product.awards),
        ("功效承诺", product.efficacy_proof),
        ("只有我有", "是" if product.mechanism_exclusive else None),
    )
    return "\n".join(f"{label}：{value}" for label, value in fields if value)


def _profile_prompt(context) -> str:
    sections = [("红人姓名", context.name), *context.prompt_sections()]
    return "\n".join(f"{label}：{value}" for label, value in sections if value)


def _parse_directions(ai_output: str) -> list[dict]:
    cleaned = ai_output.replace("```json", "").replace("```", "").strip()
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("未返回方向列表")
    directions = json.loads(cleaned[start:end + 1])
    if not isinstance(directions, list) or not 2 <= len(directions) <= 3:
        raise ValueError("方向数量必须为 2 到 3 个")
    required = {"type", "title", "description", "anchor"}
    if any(not isinstance(item, dict) or not required.issubset(item) for item in directions):
        raise ValueError("方向字段不完整")
    return directions


async def _require_current_product(db: AsyncSession, kol_id: int):
    product = await get_current_product(db, kol_id)
    if product is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "CURRENT_PRODUCT_REQUIRED", "message": "请先在产品库选择当前商品"},
        )
    return product


# ---------------------------------------------------------------------------
# 红人工作台旧版四步流程
# ---------------------------------------------------------------------------

@router.post("/derive-directions", response_model=None)
async def derive_directions(
    body: DeriveDirectionsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """根据唯一当前商品和完整档案推导 2 至 3 个情绪方向。"""
    if not body.opening_line.strip() or not body.original_script.strip():
        raise HTTPException(status_code=400, detail={"code": "INVALID_INPUT", "message": "锁定开头和爆款全文均不能为空"})
    context = await get_kol_context(db, body.kol_id)
    product = await _require_current_product(db, body.kol_id)
    config = await _get_config(db)
    model_id, provider = await _resolve_model(config, db)
    configured_prompt = (
        await resolve_prompt(body.kol_id, TOOL_CODE, "emotion_direction_prompt", db)
        or (config.emotion_direction_prompt if config and config.emotion_direction_prompt else "")
    )
    prompt = f"""{configured_prompt}

你是短视频电商内容策略师。根据产品卖点、红人档案与爆款原文，推导 2 至 3 个价值观内容的情绪方向。
规则：方向只能是焦虑型或诱惑型；不提产品名、成分、价格；不要输出任何商品直接信息。
只输出 JSON 数组，每项必须包含 type、title、description、anchor。

当前商品（仅用于推导情绪）：
{_product_prompt(product)}

红人档案：
{_profile_prompt(context)}

锁定开头：{body.opening_line}
爆款全文：\n{body.original_script}
"""
    last_error = ""
    for _ in range(3):
        try:
            async with AsyncSessionLocal() as ai_db:
                output = await yunwu_adapter.chat(
                    messages=[{"role": "user", "content": prompt}], db=ai_db,
                    model_id=model_id, provider=provider, user_id=current_user.id,
                    feature="values_writer_derive_directions",
            )
            directions = _validate_directions(_parse_directions(output))
            db.add(TaskJob(
                task_no=f"values-{uuid4().hex}", tool_code=TOOL_CODE, tool_name=TOOL_NAME,
                status="success", created_by=current_user.id,
                input_payload={"kol_id": body.kol_id, "product_id": product.id,
                               "original_length": len(body.original_script), "model_id": model_id},
                result_summary={"output_kind": "emotion_directions"},
            ))
            await db.commit()
            return success_response(data={"directions": directions})
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            last_error = str(exc)
    raise HTTPException(
        status_code=502,
        detail={"code": "DIRECTION_PARSE_FAILED", "message": f"情绪方向生成失败，已重试 3 次：{last_error}"},
    )


@router.post("/generate")
async def generate_value_script(
    body: GenerateValueScriptRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """按旧版结构生成脚本与情绪检测报告，商品只在服务端读取。"""
    if not body.opening_line.strip() or not body.original_script.strip():
        raise HTTPException(status_code=400, detail={"code": "INVALID_INPUT", "message": "锁定开头和爆款全文均不能为空"})
    if body.direction.type not in ALLOWED_DIRECTION_TYPES:
        raise HTTPException(status_code=400, detail={"code": "INVALID_DIRECTION", "message": "情绪方向只支持焦虑型或诱惑型"})
    context = await get_kol_context(db, body.kol_id)
    product = await _require_current_product(db, body.kol_id)
    config = await _get_config(db)
    model_id, provider = await _resolve_model(config, db)
    configured_prompt = (
        await resolve_prompt(body.kol_id, TOOL_CODE, "writing_prompt", db)
        or (config.writing_prompt if config and config.writing_prompt else "")
    )
    prompt = f"""{configured_prompt}

你要将爆款价值观内容改写，并严格输出 <analysis>、<rewrite>、<report> 三段。
硬规则：
1. <rewrite> 的第一句必须逐字保留“{body.opening_line}”。
2. 保留原文段落数量、各段功能和节奏，正文完全重写。
3. <rewrite> 和 <report> 不得出现商品名、成分、价格、功效等直接商品信息。
4. 改写必须服务于 {body.direction.type} 情绪，方向标题是“{body.direction.title}”，说明是“{body.direction.description}”，锚点是“{body.direction.anchor}”。
5. <analysis> 写总字数、段落数和各段功能；<report> 写触发句、恐惧强度、诱惑强度、产品联想、开头核查和优化建议。

红人档案：
{_profile_prompt(context)}

爆款全文：
{body.original_script}
"""
    user_id = current_user.id

    async def generate():
        async with AsyncSessionLocal() as stream_db:
            try:
                chunks = []
                async for chunk in yunwu_adapter.chat_stream(
                    messages=[{"role": "user", "content": prompt}], db=stream_db,
                    model_id=model_id, provider=provider, user_id=user_id,
                    feature="values_writer_generate",
                ):
                    chunks.append(chunk)
                output = _restore_locked_opening("".join(chunks), body.opening_line)
                if any(fact in output for fact in _direct_product_facts(product)):
                    yield _sse_chunk("[ERROR] 生成结果包含商品直接信息")
                    return
                stream_db.add(TaskJob(
                    task_no=f"values-{uuid4().hex}", tool_code=TOOL_CODE, tool_name=TOOL_NAME,
                    status="success", created_by=user_id,
                    input_payload={"kol_id": body.kol_id, "product_id": product.id,
                                   "original_length": len(body.original_script), "model_id": model_id},
                    result_summary={"output_kind": "structured_script"},
                ))
                await stream_db.commit()
                yield _sse_chunk(output)
            except Exception as exc:
                yield _sse_chunk(f"[ERROR] {exc}")
        yield _sse_done()

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/iterate-structured")
async def iterate_structured_value_script(
    body: StructuredIterateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """按人工修改要求迭代旧版结构化脚本，并保留可追溯的上下文。"""
    if not body.instruction.strip():
        raise HTTPException(status_code=400, detail={"code": "INVALID_INPUT", "message": "修改要求不能为空"})
    if body.direction.type not in ALLOWED_DIRECTION_TYPES:
        raise HTTPException(status_code=400, detail={"code": "INVALID_DIRECTION", "message": "情绪方向只支持焦虑型或诱惑型"})
    context = await get_kol_context(db, body.kol_id)
    product = await _require_current_product(db, body.kol_id)
    config = await _get_config(db)
    model_id, provider = await _resolve_model(config, db)
    history_text = "\n\n".join(
        f"第 {index} 次修改要求：{item.instruction}\n当轮脚本：{item.result.rewrite}\n当轮报告：{item.result.report}"
        for index, item in enumerate(body.history, start=1)
    ) or "无"
    prompt = f"""你要按人工要求迭代一份价值观改写，并严格输出 <analysis>、<rewrite>、<report> 三段。
硬规则：
1. <rewrite> 的第一句必须逐字保留“{body.opening_line}”。
2. 保留原文段落功能和节奏，按当前修改要求重写。
3. <rewrite> 和 <report> 不得出现商品名、成分、价格、功效等直接商品信息。
4. 继续服务于 {body.direction.type} 情绪，方向标题是“{body.direction.title}”，说明是“{body.direction.description}”，锚点是“{body.direction.anchor}”。
5. <analysis> 写本轮改动、字数和段落功能；<report> 写触发句、恐惧强度、诱惑强度、产品联想、开头核查和优化建议。

红人档案：
{_profile_prompt(context)}

爆款全文：
{body.original_script}

当前版本：
结构分析：{body.current_result.analysis}
脚本：{body.current_result.rewrite}
情绪报告：{body.current_result.report}

此前修改历史：
{history_text}

本轮人工修改要求：{body.instruction}
"""
    user_id = current_user.id

    async def generate():
        async with AsyncSessionLocal() as stream_db:
            try:
                chunks = []
                async for chunk in yunwu_adapter.chat_stream(
                    messages=[{"role": "user", "content": prompt}], db=stream_db,
                    model_id=model_id, provider=provider, user_id=user_id,
                    feature="values_writer_structured_iterate",
                ):
                    chunks.append(chunk)
                output = _restore_locked_opening("".join(chunks), body.opening_line)
                if any(fact in output for fact in _direct_product_facts(product)):
                    yield _sse_chunk("[ERROR] 修改结果包含商品直接信息")
                    return
                stream_db.add(TaskJob(
                    task_no=f"values-{uuid4().hex}", tool_code=TOOL_CODE, tool_name=TOOL_NAME,
                    status="success", created_by=user_id,
                    input_payload={"kol_id": body.kol_id, "product_id": product.id, "history_count": len(body.history), "model_id": model_id},
                    result_summary={"output_kind": "structured_iteration"},
                ))
                await stream_db.commit()
                yield _sse_chunk(output)
            except Exception as exc:
                yield _sse_chunk(f"[ERROR] {exc}")
        yield _sse_done()

    return StreamingResponse(generate(), media_type="text/event-stream")


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
