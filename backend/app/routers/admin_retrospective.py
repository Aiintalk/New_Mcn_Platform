"""
app/routers/admin_retrospective.py

管理端接口（require_admin 鉴权）：
  GET  /api/admin/retrospective/config  — 读取 default 配置
  PUT  /api/admin/retrospective/config  — 更新 default 配置
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.middlewares.auth import require_admin
from app.models.log import OperationLog
from app.models.retrospective import RetrospectiveConfig
from app.models.user import User

router = APIRouter(prefix="/admin/retrospective", tags=["admin-retrospective"])


def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class ConfigIn(BaseModel):
    system_prompt: str | None = None
    ai_model_id: int | None = None
    is_active: bool = True


@router.get("/config")
async def get_config(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """读取 default 复盘配置。"""
    config = (await db.execute(
        select(RetrospectiveConfig).where(RetrospectiveConfig.config_key == "default")
    )).scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "配置不存在"},
        )

    return success_response(data={
        "id": config.id,
        "config_key": config.config_key,
        "system_prompt": config.system_prompt,
        "ai_model_id": config.ai_model_id,
        "is_active": config.is_active,
        "updated_at": _ts(config.updated_at),
    })


@router.put("/config")
async def update_config(
    body: ConfigIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """更新 default 复盘配置，写 OperationLog。"""
    result = await db.execute(
        update(RetrospectiveConfig)
        .where(RetrospectiveConfig.config_key == "default")
        .values(
            system_prompt=body.system_prompt,
            ai_model_id=body.ai_model_id,
            is_active=body.is_active,
            updated_at=datetime.now(timezone.utc),
        )
        .returning(RetrospectiveConfig.id)
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
        action="admin_update_retrospective_config",
        target_type="config",
        detail={"config_key": "default", "ai_model_id": body.ai_model_id},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={"config_key": "default"})
