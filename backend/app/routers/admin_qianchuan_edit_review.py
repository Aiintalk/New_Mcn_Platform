"""
app/routers/admin_qianchuan_edit_review.py

管理端接口（admin 角色）：
  GET /api/admin/qianchuan-edit-review/configs        — 配置列表
  PUT /api/admin/qianchuan-edit-review/configs/{key}  — 更新配置
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.middlewares.auth import require_admin
from app.models.qianchuan_edit_review import QianchuanEditReviewConfig
from app.models.user import User

router = APIRouter(prefix="/admin/qianchuan-edit-review", tags=["admin-qianchuan-edit-review"])


def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


class ConfigIn(BaseModel):
    ai_model_id: int | None = None
    system_prompt: str | None = None
    is_active: bool = True


@router.get("/configs")
async def list_configs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    configs = (await db.execute(select(QianchuanEditReviewConfig))).scalars().all()
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
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = await db.execute(
        update(QianchuanEditReviewConfig)
        .where(QianchuanEditReviewConfig.config_key == config_key)
        .values(
            ai_model_id=body.ai_model_id,
            system_prompt=body.system_prompt,
            is_active=body.is_active,
            updated_at=datetime.now(timezone.utc),
        )
        .returning(QianchuanEditReviewConfig.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "配置不存在"},
        )
    await db.commit()
    return success_response(data={"config_key": config_key})
