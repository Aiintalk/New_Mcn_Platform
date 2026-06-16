"""
app/routers/admin_livestream_review.py

管理端接口（admin 角色）：
  GET /api/admin/livestream-review/configs        — 配置列表（with_excel / without_excel）
  PUT /api/admin/livestream-review/configs/{key}  — 更新配置（Prompt / 模型 / 激活状态）
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.middlewares.auth import require_admin
from app.models.user import User

router = APIRouter(prefix="/admin/livestream-review", tags=["admin-livestream-review"])


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
    from sqlalchemy import text as sa_text
    rows = (await db.execute(sa_text(
        "SELECT id, config_key, ai_model_id, system_prompt, is_active, updated_at "
        "FROM livestream_review_configs ORDER BY config_key"
    ))).fetchall()
    return success_response(data=[
        {
            "id": r[0],
            "config_key": r[1],
            "ai_model_id": r[2],
            "system_prompt": r[3],
            "is_active": r[4],
            "updated_at": _ts(r[5]),
        }
        for r in rows
    ])


@router.put("/configs/{config_key}")
async def update_config(
    config_key: str,
    body: ConfigIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    from sqlalchemy import text as sa_text
    result = await db.execute(sa_text(
        "UPDATE livestream_review_configs "
        "SET ai_model_id=:model, system_prompt=:prompt, is_active=:active, updated_at=:ts "
        "WHERE config_key=:key RETURNING id"
    ), {
        "model": body.ai_model_id,
        "prompt": body.system_prompt,
        "active": body.is_active,
        "ts": datetime.now(timezone.utc),
        "key": config_key,
    })
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "配置不存在"},
        )
    await db.commit()
    return success_response(data={"config_key": config_key})
