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
import re
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import tikhub as tikhub_adapter
from app.adapters import yunwu as yunwu_adapter
from app.core.database import AsyncSessionLocal
from app.core.response import success_response, error_response, ErrorCode
from app.middlewares.auth import get_current_user
from app.models.credential import AiModel
from app.models.kol_intake import KolIntakeConfig, KolIntakeOperatorSession, KolIntakeQuestion
from app.models.log import OperationLog, ExternalServiceLog
from app.models.output import Output
from app.models.persona_report import PersonaReport
from app.models.user import User
from app.services.file_parser import parse_uploaded_file
from app.services.persona_docx import (
    generate_persona_docx,
    generate_questionnaire_template,
)

router = APIRouter(tags=["persona"])


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
        config = await _get_persona_config(db)
        if config.ai_model_id is None:
            raise HTTPException(
                status_code=400,
                detail={"code": "VALIDATION_ERROR", "message": "AI 模型未配置，请联系管理员"},
            )
        ai_model = await _get_ai_model(db, config.ai_model_id)

        # 创建报告记录
        report = PersonaReport(
            operator_id=current_user.id,
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
            detail={"douyin_nickname": body.douyin_nickname},
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
        try:
            async with AsyncSessionLocal() as db:
                async for chunk in yunwu_adapter.chat_stream(
                    messages=messages,
                    db=db,
                    model_id=ai_model.model_id,
                    provider=ai_model.provider or "yunwu",
                    user_id=current_user.id,
                    feature="persona_generation",
                    max_tokens=30000,
                ):
                    full_text += chunk
                    yield chunk
        finally:
            # 流完成后后台存档（此处已在 generator 的 finally 中，不算 background task）
            await _finalize_report(report_id, full_text, current_user, request)

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


async def _finalize_report(
    report_id: int,
    raw_output: str,
    current_user: User,
    request: Request | None,
) -> None:
    """流完成后：拆分结果、生成 Word、双写 Output、写日志。"""
    async with AsyncSessionLocal() as db:
        report = (await db.execute(
            select(PersonaReport).where(PersonaReport.id == report_id)
        )).scalar_one_or_none()
        if report is None:
            return

        try:
            # 空内容 → 标记失败（可能是前端断连导致流中断）
            if not raw_output.strip():
                report.status = "failed"
                report.updated_at = datetime.now(timezone.utc)
                await db.commit()
                return

            # 拆分
            split_parts = raw_output.split("===SPLIT===")
            profile_result = split_parts[0].strip() if len(split_parts) >= 1 else ""
            plan_result = split_parts[1].strip() if len(split_parts) >= 2 else ""

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
            report.status = "failed"
            report.updated_at = datetime.now(timezone.utc)
            await db.commit()


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
        if config.ai_model_id is None:
            raise HTTPException(
                status_code=400,
                detail={"code": "VALIDATION_ERROR", "message": "AI 模型未配置，请联系管理员"},
            )
        ai_model = await _get_ai_model(db, config.ai_model_id)

    label = "人格档案" if body.content_type == "profile" else "内容规划"
    system_prompt = _build_optimize_prompt(label, body.current_content, body.influencer_info, body.benchmark_text)
    messages = [{"role": "system", "content": system_prompt}] + body.messages

    async def stream_generator():
        async with AsyncSessionLocal() as db:
            async for chunk in yunwu_adapter.chat_stream(
                messages=messages,
                db=db,
                model_id=ai_model.model_id,
                provider=ai_model.provider or "yunwu",
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


# ── 7. GET /api/persona/kol-submissions ───────────────────────────

@router.get("/api/persona/kol-submissions")
async def list_kol_submissions(
    current_user: User = Depends(require_operator),
):
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(KolIntakeOperatorSession)
            .where(KolIntakeOperatorSession.report_status == "ready")
            .where(KolIntakeOperatorSession.ai_report.isnot(None))
            .order_by(KolIntakeOperatorSession.created_at.desc())
        )).scalars().all()

        # 按名字去重，保留最新
        seen: set[str] = set()
        result = []
        for row in rows:
            nickname = row.kol_name or f"会话_{row.id}"
            if nickname in seen:
                continue
            seen.add(nickname)
            result.append({
                "id": row.id,
                "nickname": nickname,
                "submitted_at": row.created_at.isoformat() if row.created_at else None,
                "formatted_answers": _format_session_messages(row.messages or []),
                "report": row.ai_report or "",
            })

        return success_response(data=result)


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
                "influencer_name": r.influencer_name,
                "douyin_nickname": r.douyin_nickname,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ])


# ── 9. GET /api/persona/reports/{id} ──────────────────────────────

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

        return success_response(data={
            "id": report.id,
            "influencer_name": report.influencer_name,
            "douyin_nickname": report.douyin_nickname,
            "douyin_id": report.douyin_id,
            "status": report.status,
            "profile_result": report.profile_result,
            "plan_result": report.plan_result,
            "raw_output": report.raw_output,
            "created_at": report.created_at.isoformat() if report.created_at else None,
            "generated_at": report.generated_at.isoformat() if report.generated_at else None,
        })


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
