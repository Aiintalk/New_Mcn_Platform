"""
app/routers/operator_benchmark.py

运营端接口（JWT 鉴权，operator / admin 角色）：
  POST /api/operator/benchmark/fetch            — 抖音号/链接解析 + 视频拉取
  POST /api/operator/benchmark/analyze          — AI 分析（SSE 流式）
  GET  /api/operator/benchmark/history          — 自己的分析历史
  GET  /api/operator/benchmark/history/{id}     — 历史详情
  POST /api/operator/benchmark/export-word      — 导出 Word
"""
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.adapters import tikhub as tikhub_adapter
from app.adapters import yunwu as yunwu_adapter
from app.core.database import get_db, AsyncSessionLocal
from app.core.response import success_response
from app.middlewares.auth import get_current_user
from app.models.benchmark import BenchmarkAnalysis, BenchmarkConfig
from app.models.log import ExternalServiceLog, OperationLog
from app.models.output import Output
from app.models.task import TaskJob, TaskLog
from app.models.user import User
from app.services import benchmark_report

router = APIRouter(prefix="/operator/benchmark", tags=["operator-benchmark"])


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


def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


# ---------------------------------------------------------------------------
# POST /operator/benchmark/fetch
# ---------------------------------------------------------------------------

class FetchRequest(BaseModel):
    input: str


@router.post("/fetch")
async def fetch_account(
    body: FetchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """输入抖音号或链接，拉取视频数据。"""
    if not body.input.strip():
        raise HTTPException(status_code=400, detail={"code": "INVALID_INPUT", "message": "请输入抖音号或链接"})

    try:
        resolve_result = await tikhub_adapter.resolve_sec_user_id(body.input, db)
        sec_user_id = resolve_result["sec_user_id"]
        nickname = resolve_result.get("nickname")

        # 分享链接解析不返回 nickname，额外调 get_user_profile 获取
        if not nickname:
            try:
                profile = await tikhub_adapter.get_user_profile(sec_user_id, db)
                nickname = profile.get("nickname")
            except Exception:
                pass

        videos = await tikhub_adapter.fetch_user_videos(sec_user_id, db)
        if not videos:
            raise HTTPException(status_code=404, detail={"code": "NO_VIDEOS", "message": "未找到该账号的作品"})

        top10 = tikhub_adapter.get_top10_videos(videos)
        recent30 = tikhub_adapter.get_recent_30day_videos(videos)
        top10_text = tikhub_adapter.format_videos_text(top10, "全账号点赞TOP10")
        recent30_text = tikhub_adapter.format_videos_text(recent30, "最近30天内容")

        db.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="benchmark_fetch",
            target_type="benchmark",
            detail={"sec_user_id": sec_user_id, "total_videos": len(videos)},
        ))
        await db.commit()

        return success_response(data={
            "sec_user_id": sec_user_id,
            "nickname": nickname or "",
            "total_videos": len(videos),
            "top10_count": len(top10),
            "recent30_count": len(recent30),
            "top10_text": top10_text,
            "recent30_text": recent30_text,
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail={"code": "FETCH_FAILED", "message": str(e)})


# ---------------------------------------------------------------------------
# POST /operator/benchmark/analyze
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    account_name: str | None = None
    sec_user_id: str | None = None
    top10_content: str
    recent30_content: str


@router.post("/analyze")
async def analyze(
    body: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """AI 分析，返回 SSE 流。"""
    if not body.top10_content.strip() and not body.recent30_content.strip():
        raise HTTPException(status_code=400, detail={"code": "INVALID_INPUT", "message": "请至少提供一组内容数据"})

    config = (await db.execute(
        select(BenchmarkConfig).where(BenchmarkConfig.config_key == "analyze", BenchmarkConfig.is_active == True)
    )).scalar_one_or_none()

    if not config or not config.system_prompt:
        raise HTTPException(status_code=500, detail={"code": "CONFIG_MISSING", "message": "对标分析 Prompt 未配置"})

    model_id = "claude-sonnet-4-6"
    provider = "yunwu"
    if config.ai_model_id:
        from app.models.credential import AiModel
        ai_model = (await db.execute(
            select(AiModel).where(AiModel.id == config.ai_model_id)
        )).scalar_one_or_none()
        if ai_model:
            model_id = ai_model.model_id
            provider = ai_model.provider or provider

    analysis = BenchmarkAnalysis(
        account_name=body.account_name,
        sec_user_id=body.sec_user_id,
        top10_content=body.top10_content,
        recent30_content=body.recent30_content,
        model_used=model_id,
        status="generating",
        created_by=current_user.id,
    )
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)

    task_job = TaskJob(
        task_no=f"BENCH-{analysis.id}-{int(time.time())}",
        tool_code="benchmark",
        tool_name="对标分析助手",
        status="running",
        created_by=current_user.id,
        started_at=datetime.now(timezone.utc),
    )
    db.add(task_job)
    await db.commit()
    await db.refresh(task_job)

    user_message = f"""请分析以下抖音账号：{body.account_name or '（未提供账号名）'}

## 全账号点赞TOP10视频文案

{body.top10_content or '（未提供）'}

## 最近30天全部视频文案

{body.recent30_content or '（未提供）'}

请根据以上内容，输出【人格档案】和【内容规划】两份文档，用 ===SPLIT=== 分隔。"""

    messages = [
        {"role": "system", "content": config.system_prompt},
        {"role": "user", "content": user_message},
    ]

    state = {"full_text": "", "start_time": time.monotonic()}

    async def generate():
        try:
            async with AsyncSessionLocal() as stream_db:
                async for chunk in yunwu_adapter.chat_stream(
                    messages=messages,
                    db=stream_db,
                    model_id=model_id,
                    provider=provider,
                    user_id=current_user.id,
                    feature="benchmark_analyze",
                    max_tokens=8192,
                ):
                    state["full_text"] += chunk
                    yield chunk
        except Exception as e:
            yield f"\n\n[ERROR] {str(e)}"

    async def save_results():
        duration_ms = int((time.monotonic() - state["start_time"]) * 1000)
        parts = state["full_text"].split("===SPLIT===")
        profile_result = parts[0].strip() if parts else ""
        plan_result = parts[1].strip() if len(parts) > 1 else ""

        async with AsyncSessionLocal() as new_db:
            await new_db.execute(
                BenchmarkAnalysis.__table__.update()
                .where(BenchmarkAnalysis.id == analysis.id)
                .values(
                    profile_result=profile_result,
                    plan_result=plan_result,
                    duration_ms=duration_ms,
                    status="completed" if (profile_result or plan_result) else "failed",
                )
            )

            if profile_result or plan_result:
                output = Output(
                    title=f"「{body.account_name or '未知'}」对标分析",
                    tool_code="benchmark",
                    tool_name="对标分析助手",
                    content=profile_result[:500],
                    content_json={"profile": profile_result, "plan": plan_result},
                    created_by=current_user.id,
                )
                new_db.add(output)

            await new_db.execute(
                TaskJob.__table__.update()
                .where(TaskJob.id == task_job.id)
                .values(
                    status="completed",
                    finished_at=datetime.now(timezone.utc),
                    duration_ms=duration_ms,
                    result_summary={"analysis_id": analysis.id},
                )
            )
            new_db.add(TaskLog(
                task_id=task_job.id,
                step_code="analyze",
                step_name="AI 分析",
                status="completed",
                message=f"耗时 {duration_ms}ms",
            ))
            new_db.add(OperationLog(
                user_id=current_user.id,
                username=current_user.username,
                role=current_user.role,
                action="benchmark_analyze",
                target_type="benchmark",
                target_id=analysis.id,
                detail={"account_name": body.account_name, "duration_ms": duration_ms},
            ))
            new_db.add(ExternalServiceLog(
                service="ai",
                action="benchmark_analyze",
                duration_ms=duration_ms,
                status="success",
            ))
            await new_db.commit()

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Analysis-Id": str(analysis.id), "X-Task-Id": str(task_job.id)},
        background=BackgroundTask(save_results),
    )


# ---------------------------------------------------------------------------
# GET /operator/benchmark/history
# ---------------------------------------------------------------------------

@router.get("/history")
async def list_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """自己的分析历史列表。"""
    analyses = (await db.execute(
        select(BenchmarkAnalysis)
        .where(BenchmarkAnalysis.created_by == current_user.id)
        .order_by(BenchmarkAnalysis.created_at.desc())
    )).scalars().all()

    return success_response(data=[
        {
            "id": a.id,
            "account_name": a.account_name,
            "sec_user_id": a.sec_user_id,
            "model_used": a.model_used,
            "tokens_used": a.tokens_used,
            "duration_ms": a.duration_ms,
            "status": a.status,
            "created_at": _ts(a.created_at),
        }
        for a in analyses
    ])


# ---------------------------------------------------------------------------
# GET /operator/benchmark/history/{id}
# ---------------------------------------------------------------------------

@router.get("/history/{analysis_id}")
async def get_history_detail(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """历史详情。"""
    analysis = (await db.execute(
        select(BenchmarkAnalysis)
        .where(BenchmarkAnalysis.id == analysis_id)
        .where(BenchmarkAnalysis.created_by == current_user.id)
    )).scalar_one_or_none()

    if not analysis:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "分析记录不存在"})

    return success_response(data={
        "id": analysis.id,
        "account_name": analysis.account_name,
        "sec_user_id": analysis.sec_user_id,
        "top10_content": analysis.top10_content,
        "recent30_content": analysis.recent30_content,
        "profile_result": analysis.profile_result,
        "plan_result": analysis.plan_result,
        "model_used": analysis.model_used,
        "tokens_used": analysis.tokens_used,
        "duration_ms": analysis.duration_ms,
        "status": analysis.status,
        "created_at": _ts(analysis.created_at),
    })


# ---------------------------------------------------------------------------
# POST /operator/benchmark/export-word
# ---------------------------------------------------------------------------

class ExportRequest(BaseModel):
    analysis_id: int
    type: str = "profile"


@router.post("/export-word")
async def export_word(
    body: ExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """导出 Word 文档。"""
    analysis = (await db.execute(
        select(BenchmarkAnalysis)
        .where(BenchmarkAnalysis.id == body.analysis_id)
        .where(BenchmarkAnalysis.created_by == current_user.id)
    )).scalar_one_or_none()

    if not analysis:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "分析记录不存在"})

    if analysis.status != "completed":
        raise HTTPException(status_code=400, detail={"code": "NOT_READY", "message": "分析尚未完成"})

    content = analysis.profile_result if body.type == "profile" else analysis.plan_result
    if not content:
        raise HTTPException(status_code=400, detail={"code": "NO_CONTENT", "message": "该部分内容为空"})

    file_path = benchmark_report.generate_docx(
        analysis_id=analysis.id,
        content=content,
        account_name=analysis.account_name,
        doc_type=body.type,
    )

    label = "人格档案" if body.type == "profile" else "内容规划"
    filename = f"{label}_{analysis.account_name or '未知'}_{datetime.now().strftime('%Y-%m-%d')}.docx"

    return FileResponse(
        path=file_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
    )
