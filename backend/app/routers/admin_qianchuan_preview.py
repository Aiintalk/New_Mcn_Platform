"""
app/routers/admin_qianchuan_preview.py

管理端接口（admin 角色）：
  GET /api/admin/qianchuan-preview/configs        — 配置列表
  PUT /api/admin/qianchuan-preview/configs/{key}  — 更新配置
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
from app.models.qianchuan_preview import QianchuanPreviewConfig
from app.models.user import User

router = APIRouter(prefix="/admin/qianchuan-preview", tags=["admin-qianchuan-preview"])


def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class ConfigIn(BaseModel):
    ai_model_id: int | None = None
    system_prompt: str | None = None
    is_active: bool = True


@router.get("/configs")
async def list_configs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    configs = (await db.execute(select(QianchuanPreviewConfig))).scalars().all()
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
        update(QianchuanPreviewConfig)
        .where(QianchuanPreviewConfig.config_key == config_key)
        .values(
            ai_model_id=body.ai_model_id,
            system_prompt=body.system_prompt,
            is_active=body.is_active,
            updated_at=datetime.now(timezone.utc),
        )
        .returning(QianchuanPreviewConfig.id)
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
        action="update_qianchuan_preview_config",
        target_type="config",
        target_id=None,
        detail={"config_key": config_key, "ai_model_id": body.ai_model_id},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={"config_key": config_key})
