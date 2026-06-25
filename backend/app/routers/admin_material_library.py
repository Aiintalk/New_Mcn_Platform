"""
app/routers/admin_material_library.py

素材库管理端 API（2 接口）：
  GET /configs   获取 soul_generator Prompt + 模型配置
  PUT /configs   更新配置
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.response import success_response
from app.middlewares.auth import require_admin
from app.models.user import User
from app.models.log import OperationLog
from app.models.material_library import MaterialLibraryConfig

router = APIRouter(prefix="/admin/material-library", tags=["admin-material-library"])


class ConfigUpdate(BaseModel):
    ai_model_id: Optional[int] = None
    system_prompt: Optional[str] = None
    is_active: Optional[bool] = None


def _get_ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")


def _to_dict(cfg: MaterialLibraryConfig) -> dict:
    return {
        "id": cfg.id,
        "config_key": cfg.config_key,
        "ai_model_id": cfg.ai_model_id,
        "system_prompt": cfg.system_prompt or "",
        "is_active": cfg.is_active,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }


@router.get("/configs")
async def get_configs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """获取素材库所有配置项（当前只有 soul_generator）。"""
    configs = (
        await db.execute(
            select(MaterialLibraryConfig).order_by(MaterialLibraryConfig.id)
        )
    ).scalars().all()
    return success_response(data=[_to_dict(c) for c in configs])


@router.put("/configs")
async def update_configs(
    body: ConfigUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """更新 soul_generator 配置（ai_model_id / system_prompt / is_active）。"""
    cfg = (
        await db.execute(
            select(MaterialLibraryConfig).where(
                MaterialLibraryConfig.config_key == "soul_generator"
            )
        )
    ).scalar_one_or_none()
    if not cfg:
        return success_response(message="配置项不存在")

    changes = []
    if body.ai_model_id is not None:
        cfg.ai_model_id = body.ai_model_id
        changes.append("ai_model_id")
    if body.system_prompt is not None:
        cfg.system_prompt = body.system_prompt
        changes.append("system_prompt")
    if body.is_active is not None:
        cfg.is_active = body.is_active
        changes.append("is_active")

    db.add(OperationLog(
        user_id=admin.id,
        username=admin.username,
        role=admin.role,
        action="admin_material_library_update_config",
        target_type="material_library_config",
        target_id=cfg.id,
        detail={"updated_fields": changes},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(cfg)

    return success_response(data=_to_dict(cfg))
