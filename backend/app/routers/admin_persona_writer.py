"""
app/routers/admin_persona_writer.py

管理端接口（admin 角色）：
  GET /api/admin/persona-writer/configs        — 配置列表
  PUT /api/admin/persona-writer/configs/{key}  — 更新配置（4 Prompt + 2 模型 + 激活状态）
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
from app.models.persona_writer import PersonaWriterConfig
from app.models.user import User

router = APIRouter(prefix="/admin/persona-writer", tags=["admin-persona-writer"])


def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class ConfigIn(BaseModel):
    evaluation_prompt: str | None = None
    analysis_prompt: str | None = None
    writing_prompt: str | None = None
    iteration_prompt: str | None = None
    light_model_id: int | None = None
    heavy_model_id: int | None = None
    is_active: bool = True


@router.get("/configs")
async def list_configs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """列出全部 persona_writer_configs（通常仅 'default' 一条）。"""
    configs = (await db.execute(select(PersonaWriterConfig))).scalars().all()
    return success_response(data=[
        {
            "id": c.id,
            "config_key": c.config_key,
            "evaluation_prompt": c.evaluation_prompt,
            "analysis_prompt": c.analysis_prompt,
            "writing_prompt": c.writing_prompt,
            "iteration_prompt": c.iteration_prompt,
            "light_model_id": c.light_model_id,
            "heavy_model_id": c.heavy_model_id,
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
    """更新指定配置（4 Prompt + 2 模型 + 激活状态），写 OperationLog。"""
    result = await db.execute(
        update(PersonaWriterConfig)
        .where(PersonaWriterConfig.config_key == config_key)
        .values(
            evaluation_prompt=body.evaluation_prompt,
            analysis_prompt=body.analysis_prompt,
            writing_prompt=body.writing_prompt,
            iteration_prompt=body.iteration_prompt,
            light_model_id=body.light_model_id,
            heavy_model_id=body.heavy_model_id,
            is_active=body.is_active,
            updated_at=datetime.now(timezone.utc),
        )
        .returning(PersonaWriterConfig.id)
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
        action="admin_update_persona_writer_config",
        target_type="config",
        target_id=None,
        detail={
            "config_key": config_key,
            "light_model_id": body.light_model_id,
            "heavy_model_id": body.heavy_model_id,
            "is_active": body.is_active,
        },
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={"config_key": config_key})
