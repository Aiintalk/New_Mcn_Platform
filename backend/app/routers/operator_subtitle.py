"""
app/routers/operator_subtitle.py

运营端接口（JWT 鉴权，operator / admin 角色）— Sprint 19 字幕提取迁移自旧架构
subtitle-extractor-web。公共服务走 adapter：tikhub / oss / asr / yunwu。

接口清单：
  POST /extract            — 单条字幕提取（share_text 或 file_url → ASR → 字幕）
  POST /batch              — 批量字幕任务（多 share_text → 后台执行）
  GET  /batches            — 我的批量任务列表（分页，绑定 created_by）
  GET  /batch/{job_code}   — 查询批量任务进度（仅自己的，含 items）
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


# ---------------------------------------------------------------------------
# 1. POST /extract — 单条字幕提取
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
    """单条字幕提取：share_text → tikhub → audio_url → asr → 字幕；或 file_url → asr。"""
    share_text = (body.share_text or "").strip()
    file_url = (body.file_url or "").strip()

    if not share_text and not file_url:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "share_text 或 file_url 至少提供一个"},
        )

    title = ""
    if share_text:
        # 走 tikhub 解析视频，拿 audio_url
        try:
            result = await tikhub_adapter.fetch_video_by_share_url(share_text, db)
        except RuntimeError as e:
            raise HTTPException(
                status_code=502,
                detail={"code": "EXTERNAL_SERVICE_ERROR", "message": f"视频解析失败：{e}"},
            )
        audio_url = result.get("audio_url") or result.get("play_url") or ""
        title = result.get("title") or ""
        if not audio_url:
            raise HTTPException(
                status_code=502,
                detail={"code": "EXTERNAL_SERVICE_ERROR", "message": "解析未返回 audio_url"},
            )
    else:
        audio_url = file_url

    # ASR 转写
    try:
        text = await asr_adapter.transcribe(audio_url, db, user_id=current_user.id)
    except RuntimeError as e:
        raise HTTPException(
            status_code=502,
            detail={"code": "EXTERNAL_SERVICE_ERROR", "message": f"ASR 失败：{e}"},
        )

    db.add(_make_operation_log(
        current_user, request, action="subtitle_extract",
        detail={"share_text": share_text[:200], "audio_url": audio_url[:200], "chars": len(text)},
    ))
    await db.commit()

    return success_response(data={
        "text": text,
        "title": title,
        "audio_url": audio_url,
    })


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

def _gen_job_code() -> str:
    """生成 sub_yyyymmdd_xxxx 格式任务码。"""
    today = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"sub_{today}_{suffix}"


class BatchItemIn(BaseModel):
    share_text: str


class BatchRequest(BaseModel):
    items: list[BatchItemIn]


def _job_to_dict(job: SubtitleJob, items: list[SubtitleItem] | None = None) -> dict:
    data = {
        "id": job.id,
        "job_code": job.job_code,
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


def _item_to_dict(item: SubtitleItem) -> dict:
    return {
        "id": item.id,
        "row_number": item.row_number,
        "original_url": item.original_url,
        "title": item.title,
        "transcript": item.transcript,
        "status": item.status,
        "error": item.error,
    }


@router.post("/batch")
async def create_batch(
    body: BatchRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """创建批量字幕任务：N 条 share_text → subtitle_jobs + N subtitle_items + 后台 _run_batch。"""
    if not body.items:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "items 不能为空"},
        )

    # 生成唯一 job_code（少量重试）
    for _ in range(5):
        job_code = _gen_job_code()
        exists = (
            await db.execute(select(SubtitleJob.id).where(SubtitleJob.job_code == job_code))
        ).scalar_one_or_none()
        if not exists:
            break
    else:
        raise HTTPException(status_code=500, detail="job_code 生成失败，请重试")

    job = SubtitleJob(
        job_code=job_code,
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
            # 锁定 job
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
                    audio_url = result.get("audio_url") or result.get("play_url") or ""
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
# 4. GET /batches — 我的批量任务列表（分页，绑定 created_by）
# ---------------------------------------------------------------------------

@router.get("/batches")
async def list_my_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """当前用户的批量任务列表（按 created_at 倒序，不含 items，轻量）。"""
    base_q = select(SubtitleJob).where(SubtitleJob.created_by == current_user.id)
    total = len((await db.execute(base_q)).scalars().all())
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
# 5. GET /batch/{job_code} — 查询自己的批量任务详情（含 items）
# ---------------------------------------------------------------------------

@router.get("/batch/{job_code}")
async def get_batch(
    job_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """按 job_code 查询自己的批量任务详情（含 items 进度）。

    通过 created_by 绑定，仅能查到自己创建的任务；他人 job_code → 404。
    """
    job = (
        await db.execute(
            select(SubtitleJob).where(
                SubtitleJob.job_code == job_code,
                SubtitleJob.created_by == current_user.id,
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
# 6. POST /save-output — 保存字幕到产出中心（写共享 outputs 表）
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
