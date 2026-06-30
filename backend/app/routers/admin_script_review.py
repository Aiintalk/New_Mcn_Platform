"""
app/routers/admin_script_review.py

管理端接口（admin 角色）：
  GET /api/admin/qianchuan-script-review/config  — 读取 default 配置
  PUT /api/admin/qianchuan-script-review/config  — 更新配置（PATCH 语义）
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.middlewares.auth import require_admin
from app.models.log import OperationLog
from app.models.qianchuan_script_review import QianchuanScriptReviewConfig
from app.models.user import User

router = APIRouter(prefix="/admin/qianchuan-script-review", tags=["admin-qianchuan-script-review"])


def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class ConfigIn(BaseModel):
    direct_prompt: str | None = None
    value_prompt: str | None = None
    ai_model_id: int | None = None
    is_active: bool = True


@router.get("/config")
async def get_config(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """读取 config_key='default' 配置，不存在时返回空模板。"""
    config = (await db.execute(
        select(QianchuanScriptReviewConfig)
        .where(QianchuanScriptReviewConfig.config_key == "default")
    )).scalar_one_or_none()

    if config is None:
        return success_response(data={
            "config_key": "default",
            "direct_prompt": None,
            "value_prompt": None,
            "ai_model_id": None,
            "is_active": True,
            "updated_at": None,
        })

    return success_response(data={
        "id": config.id,
        "config_key": config.config_key,
        "direct_prompt": config.direct_prompt,
        "value_prompt": config.value_prompt,
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
    """更新 default 配置（PATCH 语义），写 OperationLog。"""
    result = await db.execute(
        update(QianchuanScriptReviewConfig)
        .where(QianchuanScriptReviewConfig.config_key == "default")
        .values(
            direct_prompt=body.direct_prompt,
            value_prompt=body.value_prompt,
            ai_model_id=body.ai_model_id,
            is_active=body.is_active,
            updated_at=datetime.now(timezone.utc),
        )
        .returning(QianchuanScriptReviewConfig.id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        config = QianchuanScriptReviewConfig(
            config_key="default",
            direct_prompt=body.direct_prompt,
            value_prompt=body.value_prompt,
            ai_model_id=body.ai_model_id,
            is_active=body.is_active,
        )
        db.add(config)
        await db.flush()

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="admin_update_script_review_config",
        target_type="config",
        target_id=None,
        detail={"ai_model_id": body.ai_model_id, "is_active": body.is_active},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data={"config_key": "default"})
