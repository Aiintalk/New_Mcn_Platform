"""
app/routers/admin_benchmark.py

管理员接口：
  GET  /api/admin/benchmark/configs              — 配置列表
  PUT  /api/admin/benchmark/configs/{key}        — 更新配置
  GET  /api/admin/benchmark/analyses             — 全部分析记录
  GET  /api/admin/benchmark/analyses/{id}        — 分析详情
  POST /api/admin/benchmark/analyses/{id}/regenerate — 重新生成
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.middlewares.auth import require_admin
from app.models.benchmark import BenchmarkAnalysis, BenchmarkConfig
from app.models.log import OperationLog
from app.models.user import User

router = APIRouter(prefix="/admin/benchmark", tags=["admin-benchmark"])


def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# Configs
# ---------------------------------------------------------------------------

class ConfigIn(BaseModel):
    ai_model_id: int | None = None
    system_prompt: str | None = None
    is_active: bool = True


@router.get("/configs")
async def list_configs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    configs = (await db.execute(select(BenchmarkConfig))).scalars().all()
    return success_response(data=[
        {
            "id": c.id,
            "config_key": c.config_key,
            "ai_model_id": c.ai_model_id,
            "system_prompt": c.system_prompt,
            "is_active": c.is_active,
            "updated_at": _ts(c.updated_at),
        }
        for c in configs
    ])


@router.put("/configs/{config_key}")
async def update_config(
    config_key: str,
    body: ConfigIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(
        update(BenchmarkConfig)
        .where(BenchmarkConfig.config_key == config_key)
        .values(
            ai_model_id=body.ai_model_id,
            system_prompt=body.system_prompt,
            is_active=body.is_active,
            updated_at=datetime.now(timezone.utc),
        )
        .returning(BenchmarkConfig.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "配置不存在"},
        )
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="update_benchmark_config",
        target_type="config",
        target_id=None,
        detail={"config_key": config_key, "ai_model_id": body.ai_model_id},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={"config_key": config_key})


# ---------------------------------------------------------------------------
# Analyses
# ---------------------------------------------------------------------------

@router.get("/analyses")
async def list_analyses(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    analyses = (await db.execute(
        select(BenchmarkAnalysis).order_by(BenchmarkAnalysis.created_at.desc())
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
            "created_by": a.created_by,
            "created_at": _ts(a.created_at),
        }
        for a in analyses
    ])


@router.get("/analyses/{analysis_id}")
async def get_analysis_detail(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    analysis = (await db.execute(
        select(BenchmarkAnalysis).where(BenchmarkAnalysis.id == analysis_id)
    )).scalar_one_or_none()

    if not analysis:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "分析记录不存在"},
        )

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
        "created_by": analysis.created_by,
        "created_at": _ts(analysis.created_at),
    })


@router.post("/analyses/{analysis_id}/regenerate")
async def regenerate_analysis(
    analysis_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """重新生成：重置状态为 pending，前端需重新调用 analyze 接口。"""
    analysis = (await db.execute(
        select(BenchmarkAnalysis).where(BenchmarkAnalysis.id == analysis_id)
    )).scalar_one_or_none()

    if not analysis:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "分析记录不存在"},
        )

    await db.execute(
        update(BenchmarkAnalysis)
        .where(BenchmarkAnalysis.id == analysis_id)
        .values(
            profile_result=None,
            plan_result=None,
            status="pending",
            tokens_used=None,
            duration_ms=None,
            updated_at=datetime.now(timezone.utc),
        )
    )
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="regenerate_benchmark_analysis",
        target_type="output",
        target_id=analysis_id,
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()

    return success_response(data={"id": analysis_id, "status": "pending"})
