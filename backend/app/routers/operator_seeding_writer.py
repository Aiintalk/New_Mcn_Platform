"""
app/routers/operator_seeding_writer.py

运营端接口（JWT 鉴权，operator / admin 角色）：
  GET  /api/tools/seeding-writer/kols/personas               — 达人人设列表（Step 1）
  GET  /api/tools/seeding-writer/references                   — 素材列表（达人维度共享）
  POST /api/tools/seeding-writer/references                   — 新增素材（粘贴文本）
  POST /api/tools/seeding-writer/references/import-from-douyin — 抖音链接导入素材（阻塞）
  DELETE /api/tools/seeding-writer/references/{id}            — 软删素材
  GET  /api/tools/seeding-writer/products                     — 产品库列表（公司共享）
  POST /api/tools/seeding-writer/products                     — 新建产品
  PUT  /api/tools/seeding-writer/products/{id}               — 更新产品
  DELETE /api/tools/seeding-writer/products/{id}             — 软删产品
  POST /api/tools/seeding-writer/products/parse-document      — 文档解析（multipart）
  POST /api/tools/seeding-writer/products/extract-selling-points — AI 卖点讨论（流式）
  POST /api/tools/seeding-writer/fetch-video                  — 抖音链接解析
  POST /api/tools/seeding-writer/transcribe/submit            — 提交 ASR 任务
  POST /api/tools/seeding-writer/transcribe/poll              — 轮询 ASR 结果
  POST /api/tools/seeding-writer/analyze-structure            — 结构拆解（流式）
  POST /api/tools/seeding-writer/ai-recommend                 — AI 推荐角度（流式）
  POST /api/tools/seeding-writer/chat                         — 写作+迭代（流式）
  POST /api/tools/seeding-writer/save-output                  — 保存产出
  POST /api/tools/seeding-writer/export-word                  — 导出 Word
  GET  /api/tools/seeding-writer/outputs                      — 历史记录（账号隔离）
"""
import asyncio
import json
import math
import re
import time
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.adapters import asr as asr_adapter
from app.adapters import oss as oss_adapter
from app.adapters import tikhub as tikhub_adapter
from app.adapters import yunwu as yunwu_adapter
from app.core.database import AsyncSessionLocal, get_db
from app.core.response import success_response
from app.middlewares.auth import get_current_user
from app.models.log import OperationLog
from app.models.output import Output
from app.models.seeding_writer import (
    SeedingWriterConfig,
    SeedingWriterProduct,
    SeedingWriterReference,
)
from app.models.task import TaskJob
from app.models.user import User
from app.services import word_export
from app.services.document_parser import parse_files_to_text
from app.services.seeding_writer_prompt import render_prompt
from app.services.workspace_prompt import resolve_prompt

router = APIRouter(prefix="/tools/seeding-writer", tags=["seeding-writer"])

TOOL_CODE = "seeding-writer"
TOOL_NAME = "种草内容仿写"
DEFAULT_LIGHT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_HEAVY_MODEL = "claude-opus-4-6"
DEFAULT_PROVIDER = "yunwu"
_RETRY_DELAYS = [2, 4, 6]
_PAGE_SIZE_ALLOWED = {10, 20, 50}
_PERSONA_PREVIEW_CHARS = 400
_MAX_REFERENCES_JOIN = 5000


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


async def _get_config(db: AsyncSession) -> SeedingWriterConfig:
    """读取激活的 default 配置，不存在则抛 503。"""
    config = (await db.execute(
        select(SeedingWriterConfig)
        .where(SeedingWriterConfig.config_key == "default")
        .where(SeedingWriterConfig.is_active == True)  # noqa: E712
    )).scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CONFIG_NOT_FOUND",
                "message": "seeding-writer 配置 'default' 未激活，请联系管理员",
            },
        )
    return config


async def _resolve_model(config: SeedingWriterConfig, db: AsyncSession, *, is_heavy: bool) -> tuple[str, str]:
    """解析配置绑定的 (model_id, provider)，留空或失效则返回默认值。"""
    model_db_id = config.heavy_model_id if is_heavy else config.light_model_id
    default_model = DEFAULT_HEAVY_MODEL if is_heavy else DEFAULT_LIGHT_MODEL
    if not model_db_id:
        return default_model, DEFAULT_PROVIDER
    row = (await db.execute(
        sa_text("SELECT model_id, COALESCE(provider, :default_p) FROM ai_models WHERE id = :id AND status = 'active'"),
        {"id": model_db_id, "default_p": DEFAULT_PROVIDER},
    )).fetchone()
    return (row[0], row[1]) if row else (default_model, DEFAULT_PROVIDER)


async def _get_kol(db: AsyncSession, kol_id: int) -> tuple[str, str, str]:
    """读取达人人设，返回 (name, persona, content_plan)。不存在抛 404。"""
    kol_row = (await db.execute(
        sa_text(
            """
            SELECT name, persona, content_plan
            FROM kols
            WHERE id = :id AND deleted_at IS NULL
            """
        ),
        {"id": kol_id},
    )).fetchone()
    if kol_row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "达人人设不存在或已删除"},
        )
    return kol_row[0], kol_row[1] or "", kol_row[2] or ""


async def _get_product(db: AsyncSession, product_id: int) -> SeedingWriterProduct:
    """读取产品，不存在抛 404。"""
    product = (await db.execute(
        select(SeedingWriterProduct)
        .where(SeedingWriterProduct.id == product_id)
        .where(SeedingWriterProduct.deleted_at.is_(None))
    )).scalar_one_or_none()
    if product is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "产品不存在或已删除"},
        )
    return product


async def _get_references(db: AsyncSession, reference_ids: list[int]) -> list[SeedingWriterReference]:
    """读取多条素材。"""
    if not reference_ids:
        return []
    result = await db.execute(
        select(SeedingWriterReference)
        .where(SeedingWriterReference.id.in_(reference_ids))
        .where(SeedingWriterReference.deleted_at.is_(None))
    )
    return list(result.scalars().all())


def _build_references_text(references: list[SeedingWriterReference]) -> str:
    """拼接素材列表为文本。"""
    if not references:
        return ""
    parts = [r.content for r in references if r.content]
    text = "\n\n---\n\n".join(parts)
    if len(text) > _MAX_REFERENCES_JOIN:
        text = text[:_MAX_REFERENCES_JOIN]
    return text


async def _download_video(url: str) -> bytes:
    """下载视频，返回 bytes。"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.douyin.com/",
    }
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        return r.content


def _parse_product_json(ai_output: str) -> dict:
    """从 AI 输出中提取 JSON 产品信息。"""
    match = re.search(r"\{[\s\S]*\}", ai_output)
    if not match:
        raise HTTPException(
            status_code=422,
            detail={"code": "PARSE_ERROR", "message": "AI 未能提取到结构化产品信息，请手动填写"},
        )
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        cleaned = match.group(0).replace("\r\n", " ").replace("\n", " ")
        cleaned = re.sub(r",\s*}", "}", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=422,
                detail={"code": "PARSE_ERROR", "message": "AI 输出 JSON 解析失败，请手动填写"},
            )


# ---------------------------------------------------------------------------
# 1. GET /kols/personas
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
                  AND k.status IN ('signed', 'pending_renewal')
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
# 2-5. References CRUD
# ---------------------------------------------------------------------------

@router.get("/references")
async def list_references(
    kol_id: int = Query(..., ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """列出某达人的素材（达人维度共享，不按 created_by 隔离）。"""
    rows = (
        await db.execute(
            sa_text(
                """
                SELECT id, kol_id, title, content, type, source, likes, douyin_url, created_at
                FROM seeding_writer_references
                WHERE kol_id = :kol_id AND deleted_at IS NULL
                ORDER BY created_at DESC
                """
            ),
            {"kol_id": kol_id},
        )
    ).fetchall()

    items = [
        {
            "id": row[0],
            "kol_id": row[1],
            "title": row[2],
            "content": row[3],
            "type": row[4],
            "source": row[5],
            "likes": row[6],
            "douyin_url": row[7],
            "created_at": row[8].isoformat() if row[8] else None,
        }
        for row in rows
    ]
    return success_response(data=items)


class CreateReferenceRequest(BaseModel):
    kol_id: int
    title: str
    content: str
    type: str | None = None
    likes: int | None = None
    source: str | None = None


@router.post("/references")
async def create_reference(
    body: CreateReferenceRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """新增素材（粘贴文本）。"""
    ref = SeedingWriterReference(
        kol_id=body.kol_id,
        title=body.title,
        content=body.content,
        type=body.type,
        likes=body.likes,
        source=body.source,
        created_by=current_user.id,
    )
    db.add(ref)
    await db.flush()

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="seeding_writer_create_reference",
        target_type="reference",
        target_id=ref.id,
        detail={"kol_id": body.kol_id, "title": body.title},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={"id": ref.id})


class ImportFromDouyinRequest(BaseModel):
    kol_id: int
    share_url: str
    type: str | None = "种草爆款"


@router.post("/references/import-from-douyin")
async def import_reference_from_douyin(
    body: ImportFromDouyinRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """抖音链接导入素材（同步阻塞：fetch-video + 下载 + OSS + ASR）。"""
    if not body.share_url.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "share_url 不能为空"},
        )

    try:
        video = await tikhub_adapter.fetch_video_by_share_url(body.share_url.strip(), db)
    except RuntimeError as e:
        raise HTTPException(
            status_code=502,
            detail={"code": "EXTERNAL_SERVICE_ERROR", "message": str(e)},
        )

    play_url = video.get("play_url", "")
    if not play_url:
        raise HTTPException(
            status_code=502,
            detail={"code": "EXTERNAL_SERVICE_ERROR", "message": "无法获取视频播放地址"},
        )

    try:
        buffer = await _download_video(play_url)
        object_key = f"seeding-writer/references/{int(time.time())}.mp4"
        await oss_adapter.upload_file(object_key, buffer, "video/mp4", db, user_id=current_user.id)
        signed_url = await oss_adapter.get_download_url(object_key, db, expires=3600, user_id=current_user.id)
        transcript = await asr_adapter.transcribe(signed_url, db, user_id=current_user.id)
    except RuntimeError as e:
        raise HTTPException(
            status_code=502,
            detail={"code": "EXTERNAL_SERVICE_ERROR", "message": str(e)},
        )

    ref = SeedingWriterReference(
        kol_id=body.kol_id,
        title=video.get("title", ""),
        content=transcript,
        type=body.type,
        source="抖音",
        likes=video.get("digg_count"),
        douyin_url=body.share_url,
        created_by=current_user.id,
    )
    db.add(ref)
    await db.flush()

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="seeding_writer_import_douyin",
        target_type="reference",
        target_id=ref.id,
        detail={"kol_id": body.kol_id, "share_url": body.share_url},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={"id": ref.id, "title": ref.title, "content": ref.content})


@router.delete("/references/{reference_id}")
async def delete_reference(
    reference_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """软删素材。"""
    ref = (await db.execute(
        select(SeedingWriterReference)
        .where(SeedingWriterReference.id == reference_id)
        .where(SeedingWriterReference.deleted_at.is_(None))
    )).scalar_one_or_none()
    if ref is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "素材不存在"},
        )

    ref.deleted_at = datetime.now(timezone.utc)
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="seeding_writer_delete_reference",
        target_type="reference",
        target_id=reference_id,
        detail={"title": ref.title},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={"id": reference_id})


# ---------------------------------------------------------------------------
# 6-9. Products CRUD
# ---------------------------------------------------------------------------

@router.get("/products")
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", max_length=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """产品库列表（公司共享，分页）。"""
    if page_size not in _PAGE_SIZE_ALLOWED:
        page_size = 20

    base_where = "deleted_at IS NULL"
    params: dict = {"limit": page_size, "offset": (page - 1) * page_size}
    if keyword.strip():
        base_where += " AND name ILIKE :keyword"
        params["keyword"] = f"%{keyword.strip()}%"

    total = (await db.execute(
        sa_text(f"SELECT COUNT(*) FROM seeding_writer_products WHERE {base_where}"),
        params,
    )).scalar() or 0

    rows = (await db.execute(
        sa_text(
            f"""
            SELECT id, name, category, price, selling_points,
                   target_audience, scenario, medical_aesthetic_anchor,
                   created_by, created_at, updated_at
            FROM seeding_writer_products
            WHERE {base_where}
            ORDER BY updated_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    )).fetchall()

    items = [
        {
            "id": row[0],
            "name": row[1],
            "category": row[2],
            "price": row[3],
            "selling_points": row[4],
            "target_audience": row[5],
            "scenario": row[6],
            "medical_aesthetic_anchor": row[7],
            "created_by": row[8],
            "created_at": row[9].isoformat() if row[9] else None,
            "updated_at": row[10].isoformat() if row[10] else None,
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


class CreateProductRequest(BaseModel):
    name: str
    category: str | None = None
    price: str | None = None
    selling_points: str | None = None
    target_audience: str | None = None
    scenario: str | None = None
    medical_aesthetic_anchor: str | None = None


@router.post("/products")
async def create_product(
    body: CreateProductRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """新建产品（公司共享）。"""
    if not body.name.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "name 不能为空"},
        )

    product = SeedingWriterProduct(
        name=body.name.strip(),
        category=body.category,
        price=body.price,
        selling_points=body.selling_points,
        target_audience=body.target_audience,
        scenario=body.scenario,
        medical_aesthetic_anchor=body.medical_aesthetic_anchor,
        created_by=current_user.id,
    )
    db.add(product)
    await db.flush()

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="seeding_writer_create_product",
        target_type="product",
        target_id=product.id,
        detail={"name": body.name},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={"id": product.id})


class UpdateProductRequest(BaseModel):
    name: str | None = None
    category: str | None = None
    price: str | None = None
    selling_points: str | None = None
    target_audience: str | None = None
    scenario: str | None = None
    medical_aesthetic_anchor: str | None = None


@router.put("/products/{product_id}")
async def update_product(
    product_id: int,
    body: UpdateProductRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """更新产品。"""
    product = await _get_product(db, product_id)

    update_data: dict = {}
    for field in ("name", "category", "price", "selling_points",
                  "target_audience", "scenario", "medical_aesthetic_anchor"):
        val = getattr(body, field)
        if val is not None:
            update_data[field] = val
    update_data["updated_at"] = datetime.now(timezone.utc)

    if update_data:
        await db.execute(
            sa_text(
                """
                UPDATE seeding_writer_products SET
                    name = COALESCE(:name, name),
                    category = COALESCE(:category, category),
                    price = COALESCE(:price, price),
                    selling_points = COALESCE(:selling_points, selling_points),
                    target_audience = COALESCE(:target_audience, target_audience),
                    scenario = COALESCE(:scenario, scenario),
                    medical_aesthetic_anchor = COALESCE(:medical_aesthetic_anchor, medical_aesthetic_anchor),
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {
                "name": update_data.get("name"),
                "category": update_data.get("category"),
                "price": update_data.get("price"),
                "selling_points": update_data.get("selling_points"),
                "target_audience": update_data.get("target_audience"),
                "scenario": update_data.get("scenario"),
                "medical_aesthetic_anchor": update_data.get("medical_aesthetic_anchor"),
                "updated_at": update_data["updated_at"],
                "id": product_id,
            },
        )

    log_detail = {k: v for k, v in update_data.items() if k != "updated_at"}
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="seeding_writer_update_product",
        target_type="product",
        target_id=product_id,
        detail=log_detail,
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={"id": product_id})


@router.delete("/products/{product_id}")
async def delete_product(
    product_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """软删产品。"""
    product = await _get_product(db, product_id)

    await db.execute(
        sa_text(
            "UPDATE seeding_writer_products SET deleted_at = :now WHERE id = :id"
        ),
        {"now": datetime.now(timezone.utc), "id": product_id},
    )

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="seeding_writer_delete_product",
        target_type="product",
        target_id=product_id,
        detail={"name": product.name},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={"id": product_id})


# ---------------------------------------------------------------------------
# 10. POST /products/parse-document (multipart)
# ---------------------------------------------------------------------------

@router.post("/products/parse-document")
async def parse_product_document(
    request: Request,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """上传文档 AI 解析（multipart/form-data）。"""
    try:
        raw_text = await parse_files_to_text(files)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "PARSE_ERROR", "message": str(e)},
        )

    config = await _get_config(db)
    model_id, provider = await _resolve_model(config, db, is_heavy=True)
    parse_prompt = config.parse_product_prompt or ""

    messages = [
        {"role": "system", "content": parse_prompt},
        {"role": "user", "content": raw_text},
    ]

    # Collect full response (non-streaming)
    ai_output = ""
    async with AsyncSessionLocal() as collect_db:
        async for chunk in yunwu_adapter.chat_stream(
            messages=messages,
            db=collect_db,
            model_id=model_id,
            provider=provider,
            user_id=current_user.id,
            feature="seeding_writer_parse_product",
            max_tokens=4096,
        ):
            ai_output += chunk

    product_info = _parse_product_json(ai_output)
    product_info["_rawText"] = raw_text

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="seeding_writer_parse_product",
        target_type="product",
        target_id=None,
        detail={"raw_text_length": len(raw_text)},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()

    return success_response(data=product_info)


# ---------------------------------------------------------------------------
# 11. POST /products/extract-selling-points (流式, heavy 模型)
# ---------------------------------------------------------------------------

class ExtractSellingPointsRequest(BaseModel):
    raw_text: str
    preliminary_info: dict | None = None
    kol_id: int | None = None


@router.post("/products/extract-selling-points")
async def extract_selling_points(
    body: ExtractSellingPointsRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """AI 卖点讨论（流式，heavy 模型，sp_system_prompt）。"""
    if not body.raw_text.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "raw_text 不能为空"},
        )

    config = await _get_config(db)
    model_id, provider = await _resolve_model(config, db, is_heavy=True)

    template = config.sp_system_prompt or ""
    kol_prompt = await resolve_prompt(body.kol_id, "seeding-writer", "sp_system", db)
    template = kol_prompt or config.sp_system_prompt or ""
    system_prompt = render_prompt(template, raw_text=body.raw_text[:4000])

    user_content = f"以下是产品资料原文：\n\n{body.raw_text[:4000]}"
    if body.preliminary_info:
        info = body.preliminary_info
        user_content += f"\n\nAI 初步提取的产品信息：\n产品名：{info.get('name', '')}\n品类：{info.get('category', '')}\n价格：{info.get('price', '')}\n目标人群：{info.get('targetAudience', '')}\n\n请站在消费者角度，帮我找出最能打动人购买的3个核心卖点。"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    user_id = current_user.id

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
                        feature="seeding_writer_extract_sp",
                        max_tokens=4096,
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

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


# ---------------------------------------------------------------------------
# 12. POST /fetch-video
# ---------------------------------------------------------------------------

class FetchVideoRequest(BaseModel):
    share_url: str


@router.post("/fetch-video")
async def fetch_video(
    body: FetchVideoRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """抖音链接解析（复用 tikhub_adapter）。"""
    if not body.share_url.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "share_url 不能为空"},
        )

    try:
        result = await tikhub_adapter.fetch_video_by_share_url(body.share_url.strip(), db)
    except RuntimeError as e:
        raise HTTPException(
            status_code=502,
            detail={"code": "EXTERNAL_SERVICE_ERROR", "message": str(e)},
        )

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="seeding_writer_fetch_video",
        target_type="video",
        target_id=None,
        detail={
            "aweme_id": result.get("aweme_id", ""),
            "digg_count": result.get("digg_count", 0),
        },
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()

    return success_response(data={
        "title": result.get("title", ""),
        "digg_count": result.get("digg_count", 0),
        "aweme_id": result.get("aweme_id", ""),
        "play_url": result.get("play_url", ""),
    })


# ---------------------------------------------------------------------------
# 13-14. POST /transcribe/submit + /poll
# ---------------------------------------------------------------------------

class TranscribeSubmitRequest(BaseModel):
    play_url: str


@router.post("/transcribe/submit")
async def submit_transcribe(
    body: TranscribeSubmitRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """提交 ASR 任务：download → OSS upload → submit ASR → 返回 task_id。"""
    if not body.play_url.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "play_url 不能为空"},
        )

    try:
        buffer = await _download_video(body.play_url.strip())
        object_key = f"seeding-writer/transcribe/{int(time.time())}.mp4"
        await oss_adapter.upload_file(object_key, buffer, "video/mp4", db, user_id=current_user.id)
        signed_url = await oss_adapter.get_download_url(object_key, db, expires=3600, user_id=current_user.id)
        task_id = await asr_adapter.submit_transcription(
            signed_url, db, user_id=current_user.id,
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=502,
            detail={"code": "EXTERNAL_SERVICE_ERROR", "message": str(e)},
        )

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="seeding_writer_transcribe_submit",
        target_type="asr_task",
        target_id=None,
        detail={"task_id": task_id},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()

    return success_response(data={"task_id": task_id, "expected_max_seconds": 600})


class TranscribePollRequest(BaseModel):
    task_id: str


@router.post("/transcribe/poll")
async def poll_transcribe(
    body: TranscribePollRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """轮询 ASR 结果（高频，不写 OperationLog）。"""
    if not body.task_id.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "task_id 不能为空"},
        )

    try:
        r = await asr_adapter.query_transcription(body.task_id.strip(), db, user_id=current_user.id)
    except RuntimeError as e:
        raise HTTPException(
            status_code=502,
            detail={"code": "EXTERNAL_SERVICE_ERROR", "message": str(e)},
        )

    status_text = r.get("StatusText", "")
    if status_text in ("RUNNING", "QUEUEING"):
        return success_response(data={"status": "processing"})
    if status_text == "SUCCESS":
        sentences = (r.get("Result") or {}).get("Sentences") or []
        text = "".join(s.get("Text", "") for s in sentences)
        return success_response(data={"status": "done", "text": text})

    raise HTTPException(
        status_code=502,
        detail={"code": "ASR_ERROR", "message": f"ASR 状态异常: {r.get('StatusCode')} {status_text}"},
    )


# ---------------------------------------------------------------------------
# 15. POST /analyze-structure (流式, light 模型)
# ---------------------------------------------------------------------------

class AnalyzeStructureRequest(BaseModel):
    transcript: str
    kol_id: int | None = None


@router.post("/analyze-structure")
async def analyze_structure(
    body: AnalyzeStructureRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """结构拆解（流式，light 模型）。"""
    if not body.transcript.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "transcript 不能为空"},
        )

    config = await _get_config(db)
    model_id, provider = await _resolve_model(config, db, is_heavy=False)

    template = config.structure_analysis_prompt or ""
    kol_prompt = await resolve_prompt(body.kol_id, "seeding-writer", "structure_analysis", db)
    template = kol_prompt or config.structure_analysis_prompt or ""
    system_prompt = render_prompt(template, transcript=body.transcript)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": body.transcript},
    ]
    user_id = current_user.id

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
                        feature="seeding_writer_analyze",
                        max_tokens=4096,
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

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


# ---------------------------------------------------------------------------
# 16. POST /ai-recommend (流式, light 模型)
# ---------------------------------------------------------------------------

class AiRecommendRequest(BaseModel):
    persona_id: int
    product_id: int
    reference_ids: list[int] = []
    transcript: str = ""
    kol_id: int | None = None


@router.post("/ai-recommend")
async def ai_recommend(
    body: AiRecommendRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """AI 推荐种草角度（流式，light 模型）。"""
    config = await _get_config(db)
    model_id, provider = await _resolve_model(config, db, is_heavy=False)

    kol_name, kol_persona, kol_content_plan = await _get_kol(db, body.persona_id)
    product = await _get_product(db, body.product_id)
    references = await _get_references(db, body.reference_ids)
    references_text = _build_references_text(references)

    template = config.ai_recommend_prompt or ""
    kol_prompt = await resolve_prompt(body.kol_id, "seeding-writer", "ai_recommend", db)
    template = kol_prompt or config.ai_recommend_prompt or ""
    system_prompt = render_prompt(
        template,
        soul=kol_persona,
        content_plan=kol_content_plan,
        product_selling_points=product.selling_points or "",
        product_target_audience=product.target_audience or "",
        references=references_text,
        transcript=body.transcript,
    )

    user_content = f"请为产品「{product.name}」推荐3个种草角度。"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    user_id = current_user.id

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
                        feature="seeding_writer_ai_recommend",
                        max_tokens=4096,
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

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


# ---------------------------------------------------------------------------
# 17. POST /chat (流式, heavy 模型, writing + iteration 双场景)
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    scene: str = "writing"  # writing | iteration
    persona_id: int = 0
    product_id: int = 0
    reference_ids: list[int] = []
    transcript: str = ""
    structure_analysis: str = ""
    topic: str = ""
    messages: list[dict] = []
    kol_id: int | None = None
    create_job: bool = False
    job_context: dict | None = None


@router.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """写作 + 迭代（流式，heavy 模型）。"""
    if not body.messages:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "messages 不能为空"},
        )
    if body.scene not in ("writing", "iteration"):
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "scene 必须为 writing 或 iteration"},
        )
    if not body.persona_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "persona_id 不能为空"},
        )
    if not body.product_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "product_id 不能为空"},
        )

    config = await _get_config(db)
    model_id, provider = await _resolve_model(config, db, is_heavy=True)

    kol_name, kol_persona, kol_content_plan = await _get_kol(db, body.persona_id)
    product = await _get_product(db, body.product_id)
    references = await _get_references(db, body.reference_ids)
    references_text = _build_references_text(references)

    render_kwargs = dict(
        name=kol_name,
        soul=kol_persona,
        content_plan=kol_content_plan,
        product_name=product.name or "",
        product_category=product.category or "",
        product_price=product.price or "",
        product_selling_points=product.selling_points or "",
        product_target_audience=product.target_audience or "",
        product_scenario=product.scenario or "",
        references=references_text,
        transcript=body.transcript,
        structure_analysis=body.structure_analysis,
    )

    if body.scene == "writing":
        kol_prompt = await resolve_prompt(body.kol_id, "seeding-writer", "writing", db)
        template = kol_prompt or config.writing_prompt or ""
        system_prompt = render_prompt(template, topic=body.topic, **render_kwargs)
    else:
        kol_prompt = await resolve_prompt(body.kol_id, "seeding-writer", "iteration", db)
        template = kol_prompt or config.iteration_prompt or ""
        system_prompt = render_prompt(template, **render_kwargs)

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
                        provider=provider,
                        user_id=user_id,
                        feature=f"seeding_writer_{body.scene}",
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
                task_no=f"SW-{int(time.time())}",
                tool_code=TOOL_CODE,
                tool_name=TOOL_NAME,
                status="completed",
                input_payload={
                    "persona_id": body.persona_id,
                    "persona_name": kol_name,
                    "product_id": body.product_id,
                    "product_name": product.name,
                    "scene": body.scene,
                    "topic": body.topic,
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
                action="seeding_writer_chat",
                target_type="task_job",
                target_id=task_job.id,
                detail={
                    "persona_name": kol_name,
                    "product_name": product.name,
                    "scene": body.scene,
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
# 18. POST /save-output
# ---------------------------------------------------------------------------

class SaveOutputRequest(BaseModel):
    content: str
    title: str = ""
    task_id: int | None = None
    topic: str | None = None


@router.post("/save-output")
async def save_output(
    body: SaveOutputRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """保存产出至 outputs 表（账号绑定）。"""
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
        action="seeding_writer_save_output",
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


# ---------------------------------------------------------------------------
# 19. POST /export-word
# ---------------------------------------------------------------------------

class ExportWordRequest(BaseModel):
    content: str
    filename: str = "种草脚本"


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
    title = body.filename or "种草脚本"
    metadata_lines = [f"导出日期: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]

    docx_bytes = word_export.markdown_to_docx_bytes(
        title=title,
        metadata_lines=metadata_lines,
        content=body.content,
    )

    safe_name = body.filename or "种草脚本"
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
# 20. GET /outputs
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
