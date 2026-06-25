"""
app/routers/admin_values_writer.py

管理端接口（admin 角色）：
  GET /api/admin/values-writer/config  — 读取 default 配置
  PUT /api/admin/values-writer/config  — 更新配置（4 Prompt + model_id + is_active）
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.core.response import success_response
from app.middlewares.auth import require_admin
from app.models.log import OperationLog
from app.models.values_writer import ValuesWriterConfig
from app.models.user import User

router = APIRouter(prefix="/admin/values-writer", tags=["admin-values-writer"])


def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class ConfigIn(BaseModel):
    extract_values_prompt: str | None = None
    emotion_direction_prompt: str | None = None
    writing_prompt: str | None = None
    iteration_prompt: str | None = None
    model_id: int | None = None
    is_active: bool = True


@router.get("/config")
async def get_config(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """读取 config_key='default' 配置，不存在时返回空模板（不报错）。"""
    config = (await db.execute(
        select(ValuesWriterConfig)
        .where(ValuesWriterConfig.config_key == "default")
    )).scalar_one_or_none()

    if config is None:
        return success_response(data={
            "config_key": "default",
            "extract_values_prompt": None,
            "emotion_direction_prompt": None,
            "writing_prompt": None,
            "iteration_prompt": None,
            "model_id": None,
            "is_active": True,
            "updated_at": None,
        })

    return success_response(data={
        "id": config.id,
        "config_key": config.config_key,
        "extract_values_prompt": config.extract_values_prompt,
        "emotion_direction_prompt": config.emotion_direction_prompt,
        "writing_prompt": config.writing_prompt,
        "iteration_prompt": config.iteration_prompt,
        "model_id": config.model_id,
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
    """更新 default 配置（PATCH 语义），写 OperationLog。"""
    result = await db.execute(
        update(ValuesWriterConfig)
        .where(ValuesWriterConfig.config_key == "default")
        .values(
            extract_values_prompt=body.extract_values_prompt,
            emotion_direction_prompt=body.emotion_direction_prompt,
            writing_prompt=body.writing_prompt,
            iteration_prompt=body.iteration_prompt,
            model_id=body.model_id,
            is_active=body.is_active,
            updated_at=datetime.now(timezone.utc),
        )
        .returning(ValuesWriterConfig.id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        # default 行不存在则创建
        config = ValuesWriterConfig(
            config_key="default",
            extract_values_prompt=body.extract_values_prompt,
            emotion_direction_prompt=body.emotion_direction_prompt,
            writing_prompt=body.writing_prompt,
            iteration_prompt=body.iteration_prompt,
            model_id=body.model_id,
            is_active=body.is_active,
        )
        db.add(config)
        await db.flush()

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="admin_update_values_writer_config",
        target_type="config",
        target_id=None,
        detail={
            "model_id": body.model_id,
            "is_active": body.is_active,
        },
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={"config_key": "default"})
