"""
app/routers/persona.py

人格定位（persona-positioning）路由：
  POST   /api/persona/fetch-douyin              — 解析抖音账号
  POST   /api/persona/parse-file                — 解析上传文件
  POST   /api/persona/generate                  — SSE 流式生成
  POST   /api/persona/optimize                  — SSE 流式优化对话
  POST   /api/persona/export-word               — 导出 Word
  GET    /api/persona/questionnaire-template    — 下载问卷模板
  GET    /api/persona/kol-submissions            — KOL 入驻列表
  GET    /api/persona/reports                    — 报告列表
  GET    /api/persona/reports/{id}               — 报告详情
  DELETE /api/persona/reports/{id}               — 删除报告
"""
import json
import logging
import math
import re
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import tikhub as tikhub_adapter
from app.adapters import yunwu as yunwu_adapter
from app.core.database import AsyncSessionLocal
from app.core.response import success_response, error_response, ErrorCode
from app.middlewares.auth import get_current_user
from app.models.credential import AiModel
from app.models.kol import Kol
from app.models.kol_intake import (
    KolIntakeConfig,
    KolIntakeLink,
    KolIntakeOperatorSession,
    KolIntakeQuestion,
    KolIntakeSubmission,
)
from app.models.log import OperationLog, ExternalServiceLog
from app.models.output import Output
from app.models.persona_report import PersonaReport
from app.models.user import User
from app.services.file_parser import parse_uploaded_file
from app.services.persona_docx import (
    generate_persona_docx,
    generate_questionnaire_template,
)
from app.services.persona_profile_sync import (
    FACT_FIELDS,
    POSITIONING_FIELDS,
    build_grounded_fact_messages,
    decide_initial_positioning_sync,
    parse_grounded_fact_candidates,
    resolve_positioning_decisions,
)

router = APIRouter(tags=["persona"])
logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-6"
_DEFAULT_PROVIDER = "yunwu"


# ── 鉴权 ──────────────────────────────────────────────────────────

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


# ── 辅助函数 ────────────────────────────────────────────────────────

def _get_ip(request: Request | None) -> str:
    if request is None:
        return "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _write_op_log(
    session: AsyncSession,
    actor: User,
    action: str,
    request: Request,
    target_id: int | None = None,
    detail: dict | None = None,
) -> None:
    log = OperationLog(
        user_id=actor.id,
        username=actor.username,
        role=actor.role,
        action=action,
        target_type="persona_report",
        target_id=target_id,
        detail=detail,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    session.add(log)
    await session.commit()


async def _write_ext_service_log(
    session: AsyncSession,
    service: str,
    action: str,
    status: str,
    duration_ms: int | None = None,
    error_message: str | None = None,
) -> None:
    log = ExternalServiceLog(
        service=service,
        action=action,
        status=status,
        duration_ms=duration_ms,
        error_message=error_message[:500] if error_message else None,
    )
    session.add(log)
    await session.commit()


async def _get_persona_config(db: AsyncSession) -> KolIntakeConfig:
    config = (await db.execute(
        select(KolIntakeConfig).where(KolIntakeConfig.config_key == "persona_generation")
    )).scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "VALIDATION_ERROR", "message": "人格定位功能未配置，请联系管理员"},
        )
    return config


async def _get_ai_model(db: AsyncSession, model_id: int) -> AiModel:
    ai_model = (await db.execute(
        select(AiModel).where(AiModel.id == model_id)
    )).scalar_one_or_none()
    if ai_model is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "VALIDATION_ERROR", "message": "AI 模型不存在"},
        )
    return ai_model


async def _get_active_kol(db: AsyncSession, kol_id: int) -> Kol:
    kol = (await db.execute(
        select(Kol).where(Kol.id == kol_id).where(Kol.deleted_at.is_(None))
    )).scalar_one_or_none()
    if kol is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "达人不存在"},
        )
    return kol


def _get_own_report(
    report_id: int, current_user: User, db: AsyncSession,
) -> PersonaReport | None:
    """返回 scalar 查询的 coroutine，由调用方 await。"""
    return db.execute(
        select(PersonaReport)
        .where(PersonaReport.id == report_id)
        .where(PersonaReport.operator_id == current_user.id)
        .where(PersonaReport.deleted_at.is_(None))
    )


# ── Pydantic Schemas ──────────────────────────────────────────────

class FetchDouyinRequest(BaseModel):
    url: str


class ParseFileResponse(BaseModel):
    text: str


class GenerateRequest(BaseModel):
    kol_id: int
    influencer_info: str
    top10_content: str | None = None
    supplement_text: str | None = None
    benchmark_text: str | None = None
    douyin_id: str | None = None
    douyin_nickname: str | None = None
    recent30_text: str | None = None
    questionnaire_files: list[dict] | None = None
    supplement_files: list[dict] | None = None
    benchmark_profile_files: list[dict] | None = None
    benchmark_plan_files: list[dict] | None = None


class OptimizeRequest(BaseModel):
    messages: list[dict]
    current_content: str
    content_type: str  # "profile" or "plan"
    influencer_info: str
    benchmark_text: str | None = None


class ExportWordRequest(BaseModel):
    report_id: int
    type: str  # "profile" or "plan"


class SyncDecisionsRequest(BaseModel):
    decisions: dict[str, str]


# ── 1. POST /api/persona/fetch-douyin ─────────────────────────────

@router.post("/api/persona/fetch-douyin")
async def fetch_douyin(
    body: FetchDouyinRequest,
    current_user: User = Depends(require_operator),
    request: Request = None,
):
    import time
    start = time.monotonic()
    async with AsyncSessionLocal() as db:
        try:
            result = await tikhub_adapter.resolve_sec_user_id(body.url, db)
            sec_uid = result["sec_user_id"]
            nickname = result["nickname"]

            videos = await tikhub_adapter.fetch_user_videos(sec_uid, db)
            top10 = tikhub_adapter.get_top10_videos(videos)
            recent30 = tikhub_adapter.get_recent_30day_videos(videos)

            top10_text = tikhub_adapter.format_videos_text(top10, "点赞TOP10视频")
            recent30_text = tikhub_adapter.format_videos_text(recent30, "最近30天视频")

            await _write_ext_service_log(db, "tikhub", "resolve_sec_user_id+fetch_user_videos", "success",
                                         duration_ms=int((time.monotonic() - start) * 1000))

            return success_response(data={
                "nickname": nickname,
                "sec_user_id": sec_uid,
                "total_videos": len(videos),
                "top10_count": len(top10),
                "recent30_count": len(recent30),
                "top10_text": top10_text,
                "recent30_text": recent30_text,
            })
        except Exception as e:
            await _write_ext_service_log(db, "tikhub", "resolve_sec_user_id+fetch_user_videos", "error",
                                         duration_ms=int((time.monotonic() - start) * 1000),
                                         error_message=str(e))
            raise HTTPException(
                status_code=502,
                detail={"code": "EXTERNAL_SERVICE_ERROR", "message": f"抖音号解析失败：{e}"},
            )


# ── 2. POST /api/persona/parse-file ──────────────────────────────

@router.post("/api/persona/parse-file")
async def parse_file(
    file: UploadFile = File(...),
    current_user: User = Depends(require_operator),
):
    try:
        text = await parse_uploaded_file(file)
        return success_response(data={"text": text})
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "VALIDATION_ERROR", "message": str(e)},
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": f"文件解析失败：{e}"},
        )


# ── 3. POST /api/persona/generate — SSE 流式生成 ─────────────────

@router.post("/api/persona/generate")
async def generate(
    body: GenerateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_operator),
    request: Request = None,
):
    if not body.influencer_info.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "VALIDATION_ERROR", "message": "达人资料不能为空"},
        )

    async with AsyncSessionLocal() as db:
        await _get_active_kol(db, body.kol_id)
        config = await _get_persona_config(db)
        if config.ai_model_id is not None:
            ai_model = await _get_ai_model(db, config.ai_model_id)
            _model_id = ai_model.model_id
            _provider = ai_model.provider or _DEFAULT_PROVIDER
        else:
            _model_id = _DEFAULT_MODEL
            _provider = _DEFAULT_PROVIDER

        # 创建报告记录
        report = PersonaReport(
            operator_id=current_user.id,
            kol_id=body.kol_id,
            douyin_id=body.douyin_id,
            douyin_nickname=body.douyin_nickname,
            top10_text=body.top10_content,
            recent30_text=body.recent30_text,
            questionnaire_files=body.questionnaire_files or [],
            supplement_text=body.supplement_text,
            supplement_files=body.supplement_files or [],
            benchmark_profile_files=body.benchmark_profile_files or [],
            benchmark_plan_files=body.benchmark_plan_files or [],
            status="generating",
        )
        db.add(report)
        await db.flush()
        db.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="persona_generate",
            target_type="persona_report",
            target_id=report.id,
            detail={"kol_id": body.kol_id, "douyin_nickname": body.douyin_nickname},
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent") if request else None,
        ))
        await db.commit()
        await db.refresh(report)
        report_id = report.id

    # 构建消息
    system_prompt = config.system_prompt or ""
    user_message = _build_user_message(body)

    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}]

    async def stream_generator():
        full_text = ""
        generation_succeeded = False
        try:
            async with AsyncSessionLocal() as db:
                async for chunk in yunwu_adapter.chat_stream(
                    messages=messages,
                    db=db,
                    model_id=_model_id,
                    provider=_provider,
                    user_id=current_user.id,
                    feature="persona_generation",
                    max_tokens=30000,
                ):
                    full_text += chunk
                    yield chunk
            generation_succeeded = True
        finally:
            # 流完成后后台存档（此处已在 generator 的 finally 中，不算 background task）
            await _finalize_report(
                report_id,
                full_text,
                current_user,
                request,
                generation_succeeded=generation_succeeded,
            )

    return StreamingResponse(
        stream_generator(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Report-Id": str(report_id)},
    )


def _build_user_message(body: GenerateRequest) -> str:
    """构建用户消息（与旧架构 generate/route.ts 拼接逻辑一致）。"""
    parts = []
    if body.benchmark_text:
        parts.append(f"## 对标账号资料（如有）\n{body.benchmark_text}")
    parts.append(f"## 目标达人的问答采集信息\n{body.influencer_info}")
    if body.top10_content:
        parts.append(f"## 目标达人点赞TOP10视频文案（如有）\n{body.top10_content}")
    if body.supplement_text:
        parts.append(f"## 补充资料（运营手动填写，优先级最高）\n{body.supplement_text}")
    parts.append("请根据以上信息，为目标达人生成专属的人格档案和内容规划。")
    return "\n\n".join(parts)


def _positioning_values(report: PersonaReport) -> dict[str, str | None]:
    return {"persona": report.profile_result, "content_plan": report.plan_result}


def _current_positioning(kol: Kol) -> dict[str, str | None]:
    return {field: getattr(kol, field) for field in POSITIONING_FIELDS}


def _summary(value: str | None, limit: int = 160) -> str:
    compact = " ".join((value or "").split())
    return compact if len(compact) <= limit else f"{compact[:limit]}…"


async def _extract_grounded_facts(
    profile_result: str,
    current_user: User,
) -> dict[str, str]:
    async with AsyncSessionLocal() as db:
        config = await _get_persona_config(db)
        if config.ai_model_id is not None:
            ai_model = await _get_ai_model(db, config.ai_model_id)
            model_id = ai_model.model_id
            provider = ai_model.provider or _DEFAULT_PROVIDER
        else:
            model_id = _DEFAULT_MODEL
            provider = _DEFAULT_PROVIDER
        raw_json = await yunwu_adapter.chat(
            messages=build_grounded_fact_messages(profile_result),
            db=db,
            model_id=model_id,
            provider=provider,
            user_id=current_user.id,
            feature="persona_fact_extraction",
            temperature=0,
            max_tokens=3000,
            extra_body={"response_format": {"type": "json_object"}},
        )
    return parse_grounded_fact_candidates(profile_result, raw_json)


async def _active_sync_subject(
    db: AsyncSession, report_id: int,
) -> tuple[PersonaReport, Kol] | None:
    report = (await db.execute(
        select(PersonaReport).where(PersonaReport.id == report_id)
    )).scalar_one_or_none()
    if report is None or report.kol_id is None:
        return None
    kol = (await db.execute(
        select(Kol).where(Kol.id == report.kol_id, Kol.deleted_at.is_(None))
        .with_for_update()
    )).scalar_one_or_none()
    return (report, kol) if kol is not None else None


async def _sync_initial_positioning(
    report_id: int,
    current_user: User,
    request: Request | None,
) -> dict[str, str] | None:
    async with AsyncSessionLocal() as db:
        subject = await _active_sync_subject(db, report_id)
        if subject is None:
            return None
        report, kol = subject
        generated = _positioning_values(report)
        actions = decide_initial_positioning_sync(_current_positioning(kol), generated)
        now = datetime.now(timezone.utc)
        for field, action in actions.items():
            if action == "auto_written":
                setattr(kol, field, generated[field])
                kol.updated_at = now
        db.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="persona_profile_sync",
            target_type="persona_report",
            target_id=report_id,
            detail={"kol_id": kol.id, "fields": actions},
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent") if request else None,
        ))
        await db.commit()
        return actions


async def _fill_empty_facts(
    report_id: int,
    facts: dict[str, str],
    current_user: User,
    request: Request | None,
) -> list[str]:
    async with AsyncSessionLocal() as db:
        subject = await _active_sync_subject(db, report_id)
        if subject is None:
            return []
        _report, kol = subject
        filled_fields = [
            field for field in FACT_FIELDS
            if facts.get(field) and not (getattr(kol, field) or "").strip()
        ]
        if not filled_fields:
            return []
        for field in filled_fields:
            setattr(kol, field, facts[field])
        kol.updated_at = datetime.now(timezone.utc)
        db.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="fill_kol_persona_facts",
            target_type="persona_report",
            target_id=report_id,
            detail={"kol_id": kol.id, "report_id": report_id, "fields": filled_fields},
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent") if request else None,
        ))
        await db.commit()
        return filled_fields


async def _record_fact_sync_failure(
    report_id: int,
    current_user: User,
    request: Request | None,
) -> None:
    async with AsyncSessionLocal() as db:
        subject = await _active_sync_subject(db, report_id)
        if subject is None:
            return
        _report, kol = subject
        db.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="persona_fact_sync_failed",
            target_type="persona_report",
            target_id=report_id,
            detail={"kol_id": kol.id, "status": "failed"},
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent") if request else None,
        ))
        await db.commit()


async def _record_positioning_sync_failure(
    report_id: int,
    current_user: User,
    request: Request | None,
) -> None:
    async with AsyncSessionLocal() as db:
        subject = await _active_sync_subject(db, report_id)
        if subject is None:
            return
        _report, kol = subject
        db.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="persona_profile_sync_failed",
            target_type="persona_report",
            target_id=report_id,
            detail={"kol_id": kol.id, "status": "failed"},
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent") if request else None,
        ))
        await db.commit()


async def _mark_generation_failed(
    db: AsyncSession,
    report: PersonaReport,
    current_user: User,
    request: Request | None,
    reason: str,
) -> None:
    report.profile_result = None
    report.plan_result = None
    report.raw_output = None
    report.profile_docx_path = None
    report.plan_docx_path = None
    report.generated_at = None
    report.status = "failed"
    report.updated_at = datetime.now(timezone.utc)
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="persona_generation_failed",
        target_type="persona_report",
        target_id=report.id,
        detail={"kol_id": report.kol_id, "reason": reason},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent") if request else None,
    ))
    await db.commit()


async def _finalize_report(
    report_id: int,
    raw_output: str,
    current_user: User,
    request: Request | None,
    *,
    generation_succeeded: bool = True,
) -> None:
    """先保存报告历史和 Output，再独立同步正式档案。"""
    async with AsyncSessionLocal() as db:
        report = (await db.execute(
            select(PersonaReport).where(PersonaReport.id == report_id)
        )).scalar_one_or_none()
        if report is None:
            return

        try:
            kol = None
            if report.kol_id is not None:
                kol = (await db.execute(
                    select(Kol)
                    .where(Kol.id == report.kol_id, Kol.deleted_at.is_(None))
                    .with_for_update()
                )).scalar_one_or_none()
            if kol is None:
                await _mark_generation_failed(
                    db, report, current_user, request, "kol_deleted"
                )
                return

            # 部分流、客户端断连或空内容都不能进入正式归档和档案同步。
            if not generation_succeeded or not raw_output.strip():
                await _mark_generation_failed(
                    db, report, current_user, request, "generation_failed"
                )
                return

            # 人格档案与内容规划必须同时存在，异常分段不能进入正式归档。
            split_parts = raw_output.split("===SPLIT===")
            if (
                len(split_parts) != 2
                or not split_parts[0].strip()
                or not split_parts[1].strip()
            ):
                await _mark_generation_failed(
                    db, report, current_user, request, "generation_failed"
                )
                return
            profile_result, plan_result = (
                part.strip() for part in split_parts
            )

            # 提取达人名字
            influencer_name = _extract_influencer_name(profile_result) or report.douyin_nickname or "达人"

            # 生成 Word
            profile_path = generate_persona_docx(report_id, "profile", profile_result, influencer_name)
            plan_path = generate_persona_docx(report_id, "plan", plan_result, influencer_name)

            # 更新报告
            report.profile_result = profile_result
            report.plan_result = plan_result
            report.raw_output = raw_output
            report.influencer_name = influencer_name
            report.profile_docx_path = profile_path
            report.plan_docx_path = plan_path
            report.status = "ready"
            report.generated_at = datetime.now(timezone.utc)
            report.updated_at = datetime.now(timezone.utc)

            # 双写 Output
            output = Output(
                title=f"{influencer_name} · 人格档案 + 内容规划",
                tool_code="persona-positioning",
                tool_name="人格定位",
                content=raw_output,
                content_json={
                    "report_id": report_id,
                    "kol_id": report.kol_id,
                    "influencer_name": influencer_name,
                    "profile_result": profile_result,
                    "plan_result": plan_result,
                },
                word_count=len(raw_output),
                created_by=current_user.id,
            )
            db.add(output)

            await db.commit()

        except Exception:
            await db.rollback()
            report = await db.get(PersonaReport, report_id)
            if report is not None:
                await _mark_generation_failed(
                    db, report, current_user, request, "generation_failed"
                )
            return

    try:
        await _sync_initial_positioning(report_id, current_user, request)
    except Exception:
        logger.exception("Persona positioning sync failed after report finalization")
        try:
            await _record_positioning_sync_failure(report_id, current_user, request)
        except Exception:
            logger.exception("Failed to record persona positioning sync failure")
    try:
        async with AsyncSessionLocal() as db:
            subject = await _active_sync_subject(db, report_id)
            if subject is None:
                return
            report, _kol = subject
            profile_result = report.profile_result or ""
        facts = await _extract_grounded_facts(profile_result, current_user)
        await _fill_empty_facts(report_id, facts, current_user, request)
    except Exception:
        logger.exception("Persona fact extraction or fill failed")
        try:
            await _record_fact_sync_failure(report_id, current_user, request)
        except Exception:
            logger.exception("Failed to record persona fact sync failure")


def _extract_influencer_name(profile_text: str) -> str | None:
    """从人格档案第一行提取达人名字（格式：# {名字} · 人格档案 v1.0）。"""
    if not profile_text:
        return None
    match = re.match(r"^#\s*(.+?)\s*·", profile_text)
    return match.group(1).strip() if match else None


# ── 4. POST /api/persona/optimize — SSE 流式优化对话 ──────────────

@router.post("/api/persona/optimize")
async def optimize(
    body: OptimizeRequest,
    current_user: User = Depends(require_operator),
):
    async with AsyncSessionLocal() as db:
        config = await _get_persona_config(db)
        if config.ai_model_id is not None:
            ai_model = await _get_ai_model(db, config.ai_model_id)
            _model_id = ai_model.model_id
            _provider = ai_model.provider or _DEFAULT_PROVIDER
        else:
            _model_id = _DEFAULT_MODEL
            _provider = _DEFAULT_PROVIDER

    label = "人格档案" if body.content_type == "profile" else "内容规划"
    system_prompt = _build_optimize_prompt(label, body.current_content, body.influencer_info, body.benchmark_text)
    messages = [{"role": "system", "content": system_prompt}] + body.messages

    async def stream_generator():
        async with AsyncSessionLocal() as db:
            async for chunk in yunwu_adapter.chat_stream(
                messages=messages,
                db=db,
                model_id=_model_id,
                provider=_provider,
                user_id=current_user.id,
                feature="persona_optimize",
                max_tokens=16000,
            ):
                yield chunk

    return StreamingResponse(
        stream_generator(),
        media_type="text/plain; charset=utf-8",
    )


def _build_optimize_prompt(
    label: str, current_content: str, influencer_info: str, benchmark_text: str | None,
) -> str:
    """构建优化对话 system prompt（与旧架构 page.tsx 逻辑一致）。"""
    parts = [
        f"你是一个顶级的内容策划操盘手，正在帮用户优化迭代「{label}」。",
        "",
        "## 最高优先级：运营的修改意见",
        "用户（运营）在对话中提出的每一条修改意见都是最高优先级指令，必须严格执行。",
        "",
        f"## 当前{label}",
        current_content,
    ]
    if benchmark_text:
        parts.extend([
            "",
            "## 对标资料（运营选定的参照对象，按运营要求参照）",
            benchmark_text,
        ])
    parts.extend([
        "",
        "## 达人基础信息",
        influencer_info,
        "",
        "## 执行规则",
        "1. 运营的修改意见 > 一切其他考量",
        "2. 输出完整的修改后版本（不是 diff）",
        "3. 保持原有格式和结构",
        "4. 如果运营的要求不清楚，先简短确认再修改",
        "5. 输出时不要加前缀，直接输出完整内容",
    ])
    return "\n".join(parts)


# ── 5. POST /api/persona/export-word ──────────────────────────────

@router.post("/api/persona/export-word")
async def export_word(
    body: ExportWordRequest,
    current_user: User = Depends(require_operator),
    request: Request = None,
):
    async with AsyncSessionLocal() as db:
        result = await _get_own_report(body.report_id, current_user, db)
        report = result.scalar_one_or_none()
        if report is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "RESOURCE_NOT_FOUND", "message": "报告不存在"},
            )

        docx_path = report.profile_docx_path if body.type == "profile" else report.plan_docx_path
        content = report.profile_result if body.type == "profile" else report.plan_result
        name = report.influencer_name or "达人"

        # 如果文件不存在但内容有值，实时生成
        if docx_path is None or not __import__("os").path.exists(docx_path):
            if content:
                docx_path = generate_persona_docx(report.id, body.type, content, name)
            else:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "VALIDATION_ERROR", "message": "报告内容为空，无法导出"},
                )

        type_label = "人格档案" if body.type == "profile" else "内容规划"
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        filename = f"{type_label}_{name}_{date_str}.docx"

        await _write_op_log(db, current_user, "export_persona_word", request,
                            target_id=report.id, detail={"type": body.type})

    from urllib.parse import quote
    encoded_filename = quote(filename)
    return FileResponse(
        path=docx_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


# ── 6. GET /api/persona/questionnaire-template ────────────────────

@router.get("/api/persona/questionnaire-template")
async def download_questionnaire_template(
    current_user: User = Depends(require_operator),
):
    filepath = generate_questionnaire_template()
    return FileResponse(
        path=filepath,
        filename="达人入职信息采集表.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# ── 7. GET /api/persona/kols ──────────────────────────────────────

_PROFILE_FIELDS = (
    "persona", "content_plan", "background", "experience", "relationships",
    "unique_story", "extra_notes",
)
_PAGE_SIZE_ALLOWED = {10, 20, 50}


def _profile_filled_count(kol: Kol) -> int:
    return sum(bool((getattr(kol, field) or "").strip()) for field in _PROFILE_FIELDS)


@router.get("/api/persona/kols")
async def list_formal_kols(
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    current_user: User = Depends(require_operator),
):
    if page < 1:
        page = 1
    if page_size not in _PAGE_SIZE_ALLOWED:
        page_size = 20

    async with AsyncSessionLocal() as db:
        filters = [Kol.deleted_at.is_(None)]
        if keyword and keyword.strip():
            term = f"%{keyword.strip()}%"
            filters.append(or_(
                Kol.name.ilike(term),
                Kol.account_name.ilike(term),
                Kol.douyin_id.ilike(term),
            ))
        total = (await db.execute(
            select(func.count()).select_from(Kol).where(*filters)
        )).scalar_one()
        rows = (await db.execute(
            select(Kol).where(*filters).order_by(Kol.id.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()

    return success_response(data={
        "items": [{
            "id": kol.id,
            "name": kol.name,
            "account_name": kol.account_name,
            "douyin_id": kol.douyin_id,
            "profile_filled_count": _profile_filled_count(kol),
            "profile_total": len(_PROFILE_FIELDS),
        } for kol in rows],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": math.ceil(total / page_size) if total else 0,
        },
    })


# ── 8. GET /api/persona/kols/{kol_id}/intake ──────────────────────

@router.get("/api/persona/kols/{kol_id}/intake")
async def get_bound_intake(
    kol_id: int,
    current_user: User = Depends(require_operator),
):
    async with AsyncSessionLocal() as db:
        await _get_active_kol(db, kol_id)
        direct_rows = (await db.execute(
            select(KolIntakeOperatorSession)
            .where(KolIntakeOperatorSession.operator_id == current_user.id)
            .where(KolIntakeOperatorSession.kol_id == kol_id)
            .where(KolIntakeOperatorSession.report_status == "ready")
            .where(KolIntakeOperatorSession.ai_report.is_not(None))
            .where(KolIntakeOperatorSession.ai_report != "")
        )).scalars().all()
        linked_rows = (await db.execute(
            select(KolIntakeSubmission, KolIntakeLink)
            .join(KolIntakeLink, KolIntakeSubmission.link_id == KolIntakeLink.id)
            .where(KolIntakeLink.operator_id == current_user.id)
            .where(KolIntakeLink.kol_id == kol_id)
            .where(KolIntakeSubmission.report_status == "ready")
            .where(KolIntakeSubmission.ai_report.is_not(None))
            .where(KolIntakeSubmission.ai_report != "")
        )).all()

    candidates = [
        {
            "completed_at": row.report_generated_at or row.created_at,
            "formatted_answers": _format_session_messages(row.messages or []),
            "report": row.ai_report,
        }
        for row in direct_rows
    ]
    candidates.extend({
        "completed_at": submission.report_generated_at or submission.created_at,
        "formatted_answers": _format_session_messages(submission.messages or []),
        "report": submission.ai_report,
    } for submission, _link in linked_rows)
    if not candidates:
        return success_response(data=None)

    newest = max(candidates, key=lambda item: item["completed_at"] or datetime.min.replace(tzinfo=timezone.utc))
    return success_response(data={
        "completed_at": newest["completed_at"].isoformat() if newest["completed_at"] else None,
        "formatted_answers": newest["formatted_answers"],
        "report": newest["report"],
    })


# ── 9. GET /api/persona/kol-submissions（兼容旧调用）───────────────

@router.get("/api/persona/kol-submissions")
async def list_kol_submissions(
    current_user: User = Depends(require_operator),
):
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(Kol).where(Kol.deleted_at.is_(None)).order_by(Kol.id.desc())
        )).scalars().all()
    return success_response(data=[
        {"id": kol.id, "nickname": kol.name, "submitted_at": None}
        for kol in rows
    ])


def _format_session_messages(messages: list) -> str:
    """将运营直发会话消息格式化为带标签的文本。"""
    lines = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "assistant" and content:
            # AI 的过渡语/问题提取
            lines.append(f"【AI引导】{content[:200]}")
        elif role == "user" and content:
            lines.append(f"【达人回答】{content}")
    return "\n".join(lines)


# ── 8. GET /api/persona/reports ───────────────────────────────────

@router.get("/api/persona/reports")
async def list_reports(
    current_user: User = Depends(require_operator),
):
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(PersonaReport)
            .where(PersonaReport.operator_id == current_user.id)
            .where(PersonaReport.deleted_at.is_(None))
            .order_by(PersonaReport.created_at.desc())
            .limit(50)
        )).scalars().all()

        return success_response(data=[
            {
                "id": r.id,
                "kol_id": r.kol_id,
                "influencer_name": r.influencer_name,
                "douyin_nickname": r.douyin_nickname,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ])


# ── 9. GET /api/persona/reports/{id} ──────────────────────────────

async def _report_sync_result(
    db: AsyncSession,
    report: PersonaReport,
    *,
    positioning_sync_failed: bool,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    if positioning_sync_failed:
        return {}, []
    latest_log = (await db.execute(
        select(OperationLog)
        .where(OperationLog.target_type == "persona_report")
        .where(OperationLog.target_id == report.id)
        .where(OperationLog.action.in_(("persona_profile_sync", "persona_sync_decisions")))
        .order_by(OperationLog.created_at.desc(), OperationLog.id.desc())
        .limit(1)
    )).scalar_one_or_none()
    logged_fields = (latest_log.detail or {}).get("fields") if latest_log else None

    if report.kol_id is None:
        return logged_fields or {}, []
    kol = (await db.execute(
        select(Kol).where(Kol.id == report.kol_id, Kol.deleted_at.is_(None))
    )).scalar_one_or_none()
    if kol is None:
        return logged_fields or {}, []
    generated = _positioning_values(report)
    fields = logged_fields or decide_initial_positioning_sync(
        _current_positioning(kol), generated
    )
    pending = [{
        "field": field,
        "current_summary": _summary(getattr(kol, field)),
        "report_summary": _summary(generated[field]),
    } for field in POSITIONING_FIELDS if fields.get(field) == "pending"]
    return fields, pending


async def _report_failure_state(
    db: AsyncSession, report_id: int,
) -> tuple[str | None, bool, bool]:
    logs = (await db.execute(
        select(OperationLog)
        .where(or_(
            (
                (OperationLog.target_type == "persona_report")
                & (OperationLog.target_id == report_id)
                & OperationLog.action.in_((
                    "persona_generation_failed",
                    "persona_profile_sync_failed",
                    "persona_fact_sync_failed",
                    "fill_kol_persona_facts",
                ))
            ),
            (
                (OperationLog.action == "fill_kol_persona_facts")
                & (OperationLog.detail["report_id"].astext == str(report_id))
            ),
        ))
        .order_by(OperationLog.created_at.desc(), OperationLog.id.desc())
    )).scalars().all()
    actions = {log.action for log in logs}
    generation_failure = next(
        (log for log in logs if log.action == "persona_generation_failed"), None
    )
    failure_reason = (
        (generation_failure.detail or {}).get("reason")
        if generation_failure else None
    )
    latest_fact_sync = next((
        log for log in logs
        if log.action in ("persona_fact_sync_failed", "fill_kol_persona_facts")
    ), None)
    return (
        failure_reason,
        "persona_profile_sync_failed" in actions,
        latest_fact_sync is not None
        and latest_fact_sync.action == "persona_fact_sync_failed",
    )

@router.get("/api/persona/reports/{report_id}")
async def get_report_detail(
    report_id: int,
    current_user: User = Depends(require_operator),
):
    async with AsyncSessionLocal() as db:
        result = await _get_own_report(report_id, current_user, db)
        report = result.scalar_one_or_none()
        if report is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "RESOURCE_NOT_FOUND", "message": "报告不存在"},
            )

        (
            failure_reason,
            positioning_sync_failed,
            fact_sync_failed,
        ) = await _report_failure_state(db, report.id)
        sync_result, pending_overwrites = await _report_sync_result(
            db,
            report,
            positioning_sync_failed=positioning_sync_failed,
        )
        return success_response(data={
            "id": report.id,
            "kol_id": report.kol_id,
            "influencer_name": report.influencer_name,
            "douyin_nickname": report.douyin_nickname,
            "douyin_id": report.douyin_id,
            "status": report.status,
            "profile_result": report.profile_result,
            "plan_result": report.plan_result,
            "raw_output": report.raw_output,
            "created_at": report.created_at.isoformat() if report.created_at else None,
            "generated_at": report.generated_at.isoformat() if report.generated_at else None,
            "sync_result": sync_result,
            "pending_overwrites": pending_overwrites,
            "failure_reason": failure_reason,
            "positioning_sync_failed": positioning_sync_failed,
            "fact_sync_failed": fact_sync_failed,
        })


@router.post("/api/persona/reports/{report_id}/sync-decisions")
async def submit_sync_decisions(
    report_id: int,
    body: SyncDecisionsRequest,
    current_user: User = Depends(require_operator),
    request: Request = None,
):
    if any(
        field not in POSITIONING_FIELDS or decision not in ("keep", "overwrite")
        for field, decision in body.decisions.items()
    ):
        return error_response(ErrorCode.VALIDATION_ERROR, "覆盖决定字段或动作无效")

    async with AsyncSessionLocal() as db:
        result = await _get_own_report(report_id, current_user, db)
        report = result.scalar_one_or_none()
        if report is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "RESOURCE_NOT_FOUND", "message": "报告不存在"},
            )
        if report.status != "ready" or report.kol_id is None:
            return error_response(ErrorCode.VALIDATION_ERROR, "报告尚未完成或未关联达人")

        kol = (await db.execute(
            select(Kol).where(Kol.id == report.kol_id, Kol.deleted_at.is_(None))
            .execution_options(populate_existing=True)
            .with_for_update()
        )).scalar_one_or_none()
        if kol is None:
            return error_response(ErrorCode.RESOURCE_NOT_FOUND, "达人不存在")

        generated = _positioning_values(report)
        actions = resolve_positioning_decisions(
            _current_positioning(kol), generated, body.decisions
        )
        updates = {
            field: generated[field]
            for field, action in actions.items()
            if action in ("auto_written", "overwritten")
        }

        previous_log = (await db.execute(
            select(OperationLog)
            .where(OperationLog.action == "persona_sync_decisions")
            .where(OperationLog.target_id == report_id)
            .order_by(OperationLog.created_at.desc(), OperationLog.id.desc())
            .limit(1)
        )).scalar_one_or_none()

        if updates:
            for field, value in updates.items():
                setattr(kol, field, value)
            kol.updated_at = datetime.now(timezone.utc)

        if updates or previous_log is None:
            db.add(OperationLog(
                user_id=current_user.id,
                username=current_user.username,
                role=current_user.role,
                action="persona_sync_decisions",
                target_type="persona_report",
                target_id=report_id,
                detail={"kol_id": kol.id, "fields": actions},
                ip=_get_ip(request),
                user_agent=request.headers.get("user-agent") if request else None,
            ))
            await db.commit()

        return success_response(data={"report_id": report_id, "fields": actions})


# ── 10. DELETE /api/persona/reports/{id} ──────────────────────────

@router.delete("/api/persona/reports/{report_id}")
async def delete_report(
    report_id: int,
    current_user: User = Depends(require_operator),
    request: Request = None,
):
    async with AsyncSessionLocal() as db:
        result = await _get_own_report(report_id, current_user, db)
        report = result.scalar_one_or_none()
        if report is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "RESOURCE_NOT_FOUND", "message": "报告不存在"},
            )

        report.deleted_at = datetime.now(timezone.utc)
        report.updated_at = datetime.now(timezone.utc)
        await db.commit()

        await _write_op_log(db, current_user, "delete_persona_report", request, target_id=report_id)

        return success_response(data={"deleted": True})
