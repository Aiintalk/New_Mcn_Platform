"""
app/routers/operator_subtitle.py

运营端接口（JWT 鉴权，operator / admin 角色）— Sprint 19 字幕提取迁移自旧架构
subtitle-extractor-web。公共服务走 adapter：tikhub / oss / asr / yunwu。

接口清单（Sprint 21 起单条 extract 异步化，单条+批量统一走 SubtitleJob 表）：
  POST /extract            — 单条字幕提取（异步：创建 job → 后台跑 → 返回 job_code）
  POST /batch              — 批量字幕任务（多 share_text → 后台执行）
  GET  /batches            — 历史记录列表（单条+批量混排，过滤软删除，分页，绑定 created_by）
  GET  /batch/{job_code}   — 查询任务详情（含 items / transcript / 视频元信息）
  DELETE /batch/{job_code} — 软删除一条历史记录
  POST /mindmap            — 字幕 → AI 思维导图（JSON）
  POST /save-output        — 保存字幕到产出中心（写共享 outputs 表）
"""
import asyncio
import json
import logging
import math
import random
import re
import string
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select, text as sa_text, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import tikhub as tikhub_adapter
from app.adapters import asr as asr_adapter
from app.adapters import yunwu as yunwu_adapter
from app.core.database import get_db, AsyncSessionLocal
from app.core.response import success_response, error_response, ErrorCode
from app.middlewares.auth import get_current_user
from app.models.log import OperationLog
from app.models.output import Output
from app.models.subtitle import SubtitleJob, SubtitleItem, SubtitleConfig
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools/subtitle", tags=["subtitle"])

TOOL_CODE = "subtitle"
TOOL_NAME = "字幕提取"
DEFAULT_MINDMAP_MODEL = "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# 内部 helpers
# ---------------------------------------------------------------------------

async def require_operator(current_user: User = Depends(get_current_user)) -> User:
    """operator / admin 角色校验 + 已改密（参照 persona-writer 模式）。"""
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


def _make_operation_log(
    current_user: User, request: Request, action: str,
    target_type: str = "subtitle", target_id: str | None = None,
    detail: dict | None = None,
) -> OperationLog:
    return OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail or {},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent", "")[:500],
    )


async def _get_subtitle_config(db: AsyncSession) -> SubtitleConfig:
    """读取激活的 default 配置，不存在则抛 503。"""
    config = (
        await db.execute(
            select(SubtitleConfig)
            .where(SubtitleConfig.config_key == "default")
            .where(SubtitleConfig.is_active == True)  # noqa: E712
        )
    ).scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CONFIG_NOT_FOUND",
                "message": "subtitle 配置 'default' 未激活，请联系管理员",
            },
        )
    return config


async def _resolve_mindmap_model_id(config: SubtitleConfig, db: AsyncSession) -> str:
    """解析思维导图绑定的模型字符串。配置缺失或失效则返回默认 haiku。"""
    if not config.mindmap_model_id:
        return DEFAULT_MINDMAP_MODEL
    row = (
        await db.execute(
            sa_text("SELECT model_id FROM ai_models WHERE id = :id AND status = 'active'"),
            {"id": config.mindmap_model_id},
        )
    ).fetchone()
    return row[0] if row else DEFAULT_MINDMAP_MODEL


def _gen_job_code() -> str:
    """生成 sub_yyyymmdd_xxxxxxxx 格式任务码（单条 + 批量共用）。"""
    today = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"sub_{today}_{suffix}"


async def _claim_unique_job_code(db: AsyncSession) -> str:
    """生成未占用的 job_code（少量重试）。"""
    for _ in range(5):
        job_code = _gen_job_code()
        exists = (
            await db.execute(select(SubtitleJob.id).where(SubtitleJob.job_code == job_code))
        ).scalar_one_or_none()
        if not exists:
            return job_code
    raise HTTPException(status_code=500, detail="job_code 生成失败，请重试")


def _parse_item_meta(item: SubtitleItem) -> dict:
    """解析 SubtitleItem.meta_json → dict（视频元信息）。

    批量任务 / 未完成的单条任务返回空 dict（前端容错）。
    """
    if not item.meta_json:
        return {}
    try:
        return json.loads(item.meta_json)
    except (json.JSONDecodeError, TypeError):
        return {}


def _item_to_dict(item: SubtitleItem) -> dict:
    """SubtitleItem 序列化。单条任务会带 video_meta（play_url/cover_url 等）。"""
    data = {
        "id": item.id,
        "row_number": item.row_number,
        "original_url": item.original_url,
        "title": item.title,
        "transcript": item.transcript,
        "status": item.status,
        "error": item.error,
    }
    meta = _parse_item_meta(item)
    if meta:
        # 把视频元信息扁平展开到 item 顶层（方便前端直接用）
        data["play_url"] = meta.get("play_url", "")
        data["audio_url"] = meta.get("audio_url", "")
        data["cover_url"] = meta.get("cover_url")
        data["nickname"] = meta.get("nickname", "")
        data["digg_count"] = meta.get("digg_count", 0)
        data["aweme_id"] = meta.get("aweme_id", "")
    return data


def _job_to_dict(job: SubtitleJob, items: list[SubtitleItem] | None = None) -> dict:
    """SubtitleJob 序列化。kind='single' 时 items 长度为 1，含视频元信息。"""
    data = {
        "id": job.id,
        "job_code": job.job_code,
        "kind": job.kind,
        "status": job.status,
        "phase": job.phase,
        "total": job.total,
        "success": job.success,
        "failed": job.failed,
        "created_by": job.created_by,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }
    if items is not None:
        data["items"] = [_item_to_dict(it) for it in items]
    return data


# ---------------------------------------------------------------------------
# 1. POST /extract — 单条字幕提取（异步任务化）
# ---------------------------------------------------------------------------

class ExtractRequest(BaseModel):
    share_text: str | None = None    # 抖音分享文本（带链接）
    file_url: str | None = None      # 已上传到 OSS 的音频 URL（前端走 /api/files 拿到）


@router.post("/extract")
async def extract(
    body: ExtractRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """单条字幕提取（异步任务化）：share_text/file_url → 创建 SubtitleJob(kind='single')
    → 后台 _run_single_extract → 立即返回 job_code → 前端轮询 GET /batch/{job_code}。

    异步化的目的：解析+ASR 需要 1-3 分钟，前端切页面/刷新后能通过 job_code 恢复进度。
    """
    share_text = (body.share_text or "").strip()
    file_url = (body.file_url or "").strip()

    if not share_text and not file_url:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "share_text 或 file_url 至少提供一个"},
        )

    job_code = await _claim_unique_job_code(db)

    # original_url 存 share_text 或 "file://{file_url}" 前缀，后台任务按前缀分流
    original_url = share_text if share_text else f"file://{file_url}"
    job = SubtitleJob(
        job_code=job_code,
        kind="single",
        status="processing",
        phase="queued",
        total=1,
        success=0,
        failed=0,
        created_by=current_user.id,
    )
    db.add(job)
    await db.flush()

    db.add(SubtitleItem(
        job_id=job.id,
        row_number=1,
        original_url=original_url,
        title="",
        transcript="",
        status="pending",
        error="",
    ))

    db.add(_make_operation_log(
        current_user, request, action="subtitle_extract",
        target_type="subtitle_job", target_id=job.id,
        detail={"job_code": job_code, "share_text": share_text[:200]},
    ))
    await db.commit()

    # 后台执行（脱离请求生命周期）
    asyncio.create_task(_run_single_extract(job.id, int(current_user.id)))

    return success_response(data={
        "job_code": job_code,
        "status": "processing",
    })


async def _run_single_extract(job_id: int, user_id: int) -> None:
    """单条 extract 后台执行：tikhub 解析 + ASR 转写，更新 item + job 状态。

    使用 AsyncSessionLocal 独立 session。视频元信息存 item.meta_json，
    transcript 存 item.transcript，前端通过 GET /batch/{job_code} 拉取。
    """
    try:
        async with AsyncSessionLocal() as db:
            job = (
                await db.execute(
                    select(SubtitleJob).where(SubtitleJob.id == job_id).with_for_update()
                )
            ).scalar_one_or_none()
            if job is None:
                logger.error("subtitle _run_single_extract: job %s not found", job_id)
                return
            job.phase = "running"
            await db.commit()

            item = (
                await db.execute(
                    select(SubtitleItem)
                    .where(SubtitleItem.job_id == job_id)
                    .order_by(SubtitleItem.row_number)
                    .limit(1)
                )
            ).scalar_one()

            item.status = "processing"
            item.error = ""
            await db.commit()

            original_url = item.original_url or ""

            try:
                if original_url.startswith("file://"):
                    # file_url 模式：直接 ASR（不走 tikhub）
                    audio_url = original_url[7:]
                    title = ""
                    video_meta = {}
                else:
                    # share_text 模式：tikhub 解析
                    result = await tikhub_adapter.fetch_video_by_share_url(original_url, db)
                    audio_url = result.get("audio_url") or ""
                    title = result.get("title") or ""
                    video_meta = {
                        "play_url": result.get("play_url") or "",
                        "audio_url": audio_url,
                        "cover_url": result.get("cover_url"),
                        "nickname": result.get("nickname") or "",
                        "digg_count": result.get("digg_count") or 0,
                        "aweme_id": result.get("aweme_id") or "",
                    }
                    if not audio_url:
                        raise RuntimeError("解析未返回 audio_url")

                # ASR 转写
                text = await asr_adapter.transcribe(audio_url, db, user_id=user_id)

                item.title = title
                item.transcript = text
                item.meta_json = json.dumps(video_meta, ensure_ascii=False) if video_meta else None
                item.status = "success"

                job.status = "completed"
                job.phase = "done"
                job.success = 1
                job.failed = 0
                await db.commit()
            except Exception as e:
                item.status = "failed"
                item.error = str(e)[:500]
                job.status = "failed"
                job.phase = "failed"
                job.failed = 1
                job.success = 0
                await db.commit()
    except Exception:
        logger.exception("subtitle _run_single_extract job_id=%s failed", job_id)


# ---------------------------------------------------------------------------
# 2. POST /mindmap — 字幕 → AI 思维导图
# ---------------------------------------------------------------------------

class MindmapRequest(BaseModel):
    transcript: str


@router.post("/mindmap")
async def generate_mindmap(
    body: MindmapRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """字幕 → yunwu adapter → JSON 思维导图（rootTitle + summary + branches[]）。"""
    transcript = (body.transcript or "").strip()
    if not transcript:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "transcript 不能为空"},
        )

    config = await _get_subtitle_config(db)
    model_id = await _resolve_mindmap_model_id(config, db)

    # 渲染 Prompt 占位符 {{transcript}}
    prompt_template = config.mindmap_prompt or ""
    system_prompt = prompt_template.replace("{{transcript}}", transcript)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请根据以下字幕生成思维导图：\n\n{transcript}"},
    ]

    try:
        raw = await yunwu_adapter.chat(
            messages=messages,
            db=db,
            model_id=model_id,
            user_id=current_user.id,
            feature="subtitle_mindmap",
            max_tokens=2048,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={"code": "EXTERNAL_SERVICE_ERROR", "message": f"AI 调用失败：{e}"},
        )

    # 清理 markdown fence 后解析 JSON
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned).strip()
    try:
        mindmap = json.loads(cleaned)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "AI_RESPONSE_PARSE_ERROR",
                "message": "AI 返回格式解析失败，请重试",
            },
        )

    db.add(_make_operation_log(
        current_user, request, action="subtitle_mindmap",
        detail={"chars": len(transcript), "model_id": model_id},
    ))
    await db.commit()

    return success_response(data=mindmap)


# ---------------------------------------------------------------------------
# 3. POST /batch — 批量字幕任务
# ---------------------------------------------------------------------------

class BatchItemIn(BaseModel):
    share_text: str


class BatchRequest(BaseModel):
    items: list[BatchItemIn]


@router.post("/batch")
async def create_batch(
    body: BatchRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """创建批量字幕任务：N 条 share_text → subtitle_jobs(kind='batch') + N subtitle_items + 后台 _run_batch。"""
    if not body.items:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "items 不能为空"},
        )

    job_code = await _claim_unique_job_code(db)

    job = SubtitleJob(
        job_code=job_code,
        kind="batch",
        status="processing",
        phase="queued",
        total=len(body.items),
        success=0,
        failed=0,
        created_by=current_user.id,
    )
    db.add(job)
    await db.flush()  # 拿 job.id

    for idx, item in enumerate(body.items, start=1):
        db.add(SubtitleItem(
            job_id=job.id,
            row_number=idx,
            original_url=item.share_text.strip(),
            title="",
            transcript="",
            status="pending",
            error="",
        ))

    db.add(_make_operation_log(
        current_user, request, action="subtitle_batch_create",
        target_type="subtitle_job", target_id=job.id,
        detail={"job_code": job_code, "total": len(body.items)},
    ))
    await db.commit()

    # 后台执行（不阻塞响应）
    asyncio.create_task(_run_batch(job.id, int(current_user.id)))

    return success_response(data={
        "job_code": job_code,
        "total": len(body.items),
    })


async def _run_batch(job_id: int, user_id: int) -> None:
    """批量任务后台执行：逐条 tikhub + ASR，更新 item + job 状态。

    使用 AsyncSessionLocal 独立 session（脱离请求生命周期）。
    """
    try:
        async with AsyncSessionLocal() as db:
            job = (
                await db.execute(
                    select(SubtitleJob).where(SubtitleJob.id == job_id).with_for_update()
                )
            ).scalar_one_or_none()
            if job is None:
                logger.error("subtitle _run_batch: job %s not found", job_id)
                return
            job.phase = "running"
            await db.commit()

            items = (
                await db.execute(
                    select(SubtitleItem)
                    .where(SubtitleItem.job_id == job_id)
                    .order_by(SubtitleItem.row_number)
                )
            ).scalars().all()

            success_count = 0
            failed_count = 0

            for item in items:
                item.status = "processing"
                item.error = ""
                await db.commit()

                try:
                    # 1. tikhub 解析视频
                    result = await tikhub_adapter.fetch_video_by_share_url(
                        item.original_url, db
                    )
                    audio_url = result.get("audio_url") or ""
                    title = result.get("title") or ""
                    if not audio_url:
                        raise RuntimeError("解析未返回 audio_url")

                    # 2. ASR 转写
                    text = await asr_adapter.transcribe(audio_url, db, user_id=user_id)

                    item.title = title
                    item.transcript = text
                    item.status = "success"
                    success_count += 1
                except Exception as e:
                    item.status = "failed"
                    item.error = str(e)[:500]
                    failed_count += 1

                await db.commit()

            # 聚合统计
            job.status = "completed" if failed_count < job.total else "failed"
            job.phase = "done"
            job.success = success_count
            job.failed = failed_count
            await db.commit()
    except Exception:
        logger.exception("subtitle _run_batch job_id=%s failed", job_id)


# ---------------------------------------------------------------------------
# 4. GET /batches — 历史记录列表（单条+批量混排，过滤软删除，分页）
# ---------------------------------------------------------------------------

@router.get("/batches")
async def list_my_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """当前用户的历史记录列表（单条 + 批量统一展示，按 created_at 倒序，过滤软删除）。

    轻量返回：不含 items，只含 job 概要（kind/status/total/success/failed 等）。
    前端展开某条时单独调 GET /batch/{job_code} 拿 items 详情。
    """
    base_q = select(SubtitleJob).where(
        SubtitleJob.created_by == current_user.id,
        SubtitleJob.deleted_at.is_(None),
    )
    total = (
        await db.execute(
            select(func.count()).select_from(base_q.subquery())
        )
    ).scalar_one()

    rows = (
        await db.execute(
            base_q.order_by(SubtitleJob.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return success_response(data={
        "items": [_job_to_dict(j) for j in rows],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": math.ceil(total / page_size) if page_size else 1,
        },
    })


# ---------------------------------------------------------------------------
# 5. GET /batch/{job_code} — 查询任务详情（含 items / transcript / 视频元信息）
# ---------------------------------------------------------------------------

@router.get("/batch/{job_code}")
async def get_batch(
    job_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """按 job_code 查询任务详情（含 items，单条任务 items[0] 含视频元信息）。

    通过 created_by 绑定，仅能查到自己创建的任务；他人 job_code → 404。
    软删除的任务也返回 404（前端用户感知是"已删除"）。
    """
    job = (
        await db.execute(
            select(SubtitleJob).where(
                SubtitleJob.job_code == job_code,
                SubtitleJob.created_by == current_user.id,
                SubtitleJob.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "任务不存在或无权限访问"},
        )
    items = (
        await db.execute(
            select(SubtitleItem)
            .where(SubtitleItem.job_id == job.id)
            .order_by(SubtitleItem.row_number)
        )
    ).scalars().all()
    return success_response(data=_job_to_dict(job, list(items)))


# ---------------------------------------------------------------------------
# 6. DELETE /batch/{job_code} — 软删除历史记录
# ---------------------------------------------------------------------------

@router.delete("/batch/{job_code}")
async def delete_batch(
    job_code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """软删除一条历史记录（设置 deleted_at，不实际从数据库删除）。

    仅任务创建者可删除自己的记录；他人或已删除的 → 404。
    """
    job = (
        await db.execute(
            select(SubtitleJob).where(
                SubtitleJob.job_code == job_code,
                SubtitleJob.created_by == current_user.id,
                SubtitleJob.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "任务不存在或无权限访问"},
        )

    job.deleted_at = datetime.now(tz=timezone.utc)

    db.add(_make_operation_log(
        current_user, request, action="subtitle_delete",
        target_type="subtitle_job", target_id=job.id,
        detail={"job_code": job_code, "kind": job.kind},
    ))
    await db.commit()

    return success_response(data={"job_code": job_code, "deleted": True})


# ---------------------------------------------------------------------------
# 7. POST /save-output — 保存字幕到产出中心（写共享 outputs 表）
# ---------------------------------------------------------------------------

class SaveOutputRequest(BaseModel):
    title: str = ""
    transcript: str
    mindmap: dict | None = None   # 可选：思维导图 JSON 一并存到 content_json


@router.post("/save-output")
async def save_output(
    body: SaveOutputRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """保存字幕（+ 可选思维导图）到产出中心。共享 outputs 表，tool_code=subtitle。

    前端列表/详情/删除走通用 `/api/outputs?tool_code=subtitle`。
    """
    title = (body.title or "").strip()
    transcript = (body.transcript or "").strip()
    if not transcript:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "transcript 不能为空"},
        )
    if not title:
        title = "未命名字幕"

    output = Output(
        title=title,
        tool_code=TOOL_CODE,
        tool_name=TOOL_NAME,
        content=transcript,
        content_json={"mindmap": body.mindmap} if body.mindmap else None,
        word_count=len(transcript),
        created_by=current_user.id,
    )
    db.add(output)
    await db.flush()

    db.add(_make_operation_log(
        current_user, request, action="subtitle_save_output",
        target_type="output", target_id=output.id,
        detail={"title": title, "chars": len(transcript)},
    ))
    await db.commit()

    return success_response(data={
        "id": output.id,
        "title": output.title,
        "tool_code": output.tool_code,
        "word_count": output.word_count,
        "created_at": output.created_at.isoformat() if output.created_at else None,
    })
