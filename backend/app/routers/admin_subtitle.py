"""
app/routers/admin_subtitle.py

字幕提取管理端 API（2 接口）：
  GET /configs   获取思维导图 Prompt + 模型配置
  PUT /configs   更新配置
"""
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.middlewares.auth import require_admin
from app.models.log import OperationLog
from app.models.subtitle import SubtitleConfig
from app.models.user import User

router = APIRouter(prefix="/admin/subtitle", tags=["admin-subtitle"])


class ConfigUpdate(BaseModel):
    mindmap_model_id: Optional[int] = None
    mindmap_prompt: Optional[str] = None
    is_active: Optional[bool] = None


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _to_dict(cfg: SubtitleConfig) -> dict:
    return {
        "id": cfg.id,
        "config_key": cfg.config_key,
        "mindmap_model_id": cfg.mindmap_model_id,
        "mindmap_prompt": cfg.mindmap_prompt or "",
        "is_active": cfg.is_active,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }


@router.get("/configs")
async def get_configs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """获取字幕库所有配置项（当前只有 default 思维导图 Prompt）。"""
    configs = (
        await db.execute(select(SubtitleConfig).order_by(SubtitleConfig.id))
    ).scalars().all()
    return success_response(data=[_to_dict(c) for c in configs])


@router.put("/configs")
async def update_configs(
    body: ConfigUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """更新思维导图配置（mindmap_model_id / mindmap_prompt / is_active）。"""
    cfg = (
        await db.execute(
            select(SubtitleConfig).where(SubtitleConfig.config_key == "default")
        )
    ).scalar_one_or_none()
    if cfg is None:
        return success_response(message="配置项不存在")

    changes = []
    if body.mindmap_model_id is not None:
        cfg.mindmap_model_id = body.mindmap_model_id
        changes.append("mindmap_model_id")
    if body.mindmap_prompt is not None:
        cfg.mindmap_prompt = body.mindmap_prompt
        changes.append("mindmap_prompt")
    if body.is_active is not None:
        cfg.is_active = body.is_active
        changes.append("is_active")

    db.add(OperationLog(
        user_id=admin.id,
        username=admin.username,
        role=admin.role,
        action="admin_subtitle_config_update",
        target_type="subtitle_config",
        target_id=cfg.id,
        detail={"changes": changes},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent", "")[:500],
    ))
    await db.commit()

    return success_response(data=_to_dict(cfg))
