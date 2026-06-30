"""
app/routers/admin_kol_workspace.py

红人工作台个性化配置（管理端 + 运营端只读）：
  GET  /api/admin/kols/{kol_id}/workspace-config  — 读取配置（含全局 Prompt 参考值）
  PUT  /api/admin/kols/{kol_id}/workspace-config  — 保存配置（upsert）
"""
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.middlewares.auth import get_current_user, require_admin
from app.models.kol import Kol
from app.models.kol_workspace_config import KolWorkspaceConfig, _DEFAULT_TABS
from app.models.log import OperationLog
from app.models.user import User

router = APIRouter(prefix="/admin/kols", tags=["admin-kol-workspace"])


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _get_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _get_kol_or_404(db: AsyncSession, kol_id: int) -> Kol:
    kol = (await db.execute(
        select(Kol).where(Kol.id == kol_id, Kol.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not kol:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "红人不存在"},
        )
    return kol


async def _get_global_prompts(db: AsyncSession) -> dict[str, dict[str, Any]]:
    """聚合 8 个 AI 模块的全局 Prompt，供前端参考展示。"""
    result: dict[str, dict[str, Any]] = {}

    # 千川仿写
    row = (await db.execute(
        text("SELECT system_prompt FROM qianchuan_writer_configs WHERE config_key='default' LIMIT 1")
    )).fetchone()
    result["qianchuan-writer"] = {"system_prompt": row[0] if row else None}

    # 人设仿写
    row = (await db.execute(
        text("SELECT evaluation_prompt, analysis_prompt, writing_prompt, iteration_prompt "
             "FROM persona_writer_configs WHERE config_key='default' LIMIT 1")
    )).fetchone()
    result["persona-writer"] = {
        "evaluation_prompt": row[0] if row else None,
        "analysis_prompt":   row[1] if row else None,
        "writing_prompt":    row[2] if row else None,
        "iteration_prompt":  row[3] if row else None,
    }

    # 种草仿写
    row = (await db.execute(
        text("SELECT sp_system_prompt, parse_product_prompt, structure_analysis_prompt, "
             "ai_recommend_prompt, writing_prompt, iteration_prompt "
             "FROM seeding_writer_configs WHERE config_key='default' LIMIT 1")
    )).fetchone()
    result["seeding-writer"] = {
        "sp_system":          row[0] if row else None,
        "parse_product":      row[1] if row else None,
        "structure_analysis": row[2] if row else None,
        "ai_recommend":       row[3] if row else None,
        "writing":            row[4] if row else None,
        "iteration":          row[5] if row else None,
    }

    # 直播仿写
    row = (await db.execute(
        text("SELECT system_prompt FROM livestream_writer_configs WHERE config_key='default' LIMIT 1")
    )).fetchone()
    result["livestream-writer"] = {"system_prompt": row[0] if row else None}

    # 直播复盘（两条记录：with_excel / without_excel）
    rows = (await db.execute(
        text("SELECT config_key, system_prompt FROM livestream_review_configs ORDER BY config_key")
    )).fetchall()
    lsr: dict[str, Any] = {"with_excel_prompt": None, "without_excel_prompt": None}
    for r in rows:
        if r[0] == "with_excel":
            lsr["with_excel_prompt"] = r[1]
        elif r[0] == "without_excel":
            lsr["without_excel_prompt"] = r[1]
    result["livestream-review"] = lsr

    # 价值观仿写
    row = (await db.execute(
        text("SELECT extract_values_prompt, emotion_direction_prompt, writing_prompt, iteration_prompt "
             "FROM values_writer_configs WHERE config_key='default' LIMIT 1")
    )).fetchone()
    result["values-writer"] = {
        "extract_values_prompt":    row[0] if row else None,
        "emotion_direction_prompt": row[1] if row else None,
        "writing_prompt":           row[2] if row else None,
        "iteration_prompt":         row[3] if row else None,
    }

    # 千川脚本预审
    row = (await db.execute(
        text("SELECT direct_prompt, value_prompt FROM qianchuan_script_review_configs "
             "WHERE config_key='default' LIMIT 1")
    )).fetchone()
    result["script-review"] = {
        "direct_prompt": row[0] if row else None,
        "value_prompt":  row[1] if row else None,
    }

    # 复盘
    row = (await db.execute(
        text("SELECT system_prompt FROM retrospective_configs WHERE config_key='default' LIMIT 1")
    )).fetchone()
    result["retrospective"] = {"system_prompt": row[0] if row else None}

    return result


# ---------------------------------------------------------------------------
# GET /{kol_id}/workspace-config
# ---------------------------------------------------------------------------

@router.get("/{kol_id}/workspace-config", response_model=None)
async def get_workspace_config(
    kol_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    读取红人工作台配置。operator 和 admin 均可调用（运营端工作台读取 enabled_tabs 用）。
    """
    if current_user.password_changed_at is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "AUTH_FORCE_CHANGE_PASSWORD", "message": "请先修改初始密码"},
        )

    await _get_kol_or_404(db, kol_id)

    config = (await db.execute(
        select(KolWorkspaceConfig).where(KolWorkspaceConfig.kol_id == kol_id)
    )).scalar_one_or_none()

    global_prompts = await _get_global_prompts(db)

    return success_response(data={
        "kol_id":          kol_id,
        "enabled_tabs":    config.enabled_tabs if config else list(_DEFAULT_TABS),
        "prompt_overrides": config.prompt_overrides if config else {},
        "global_prompts":  global_prompts,
    })


# ---------------------------------------------------------------------------
# PUT /{kol_id}/workspace-config
# ---------------------------------------------------------------------------

class WorkspaceConfigIn(BaseModel):
    enabled_tabs: list[str]
    prompt_overrides: dict[str, dict[str, str | None]] = {}


@router.put("/{kol_id}/workspace-config", response_model=None)
async def update_workspace_config(
    kol_id: int,
    body: WorkspaceConfigIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """保存红人工作台配置（upsert）。仅 admin 可写。"""
    await _get_kol_or_404(db, kol_id)

    # 清理 prompt_overrides 中的空字符串（空字符串 = 不覆盖，存 null）
    clean_overrides: dict[str, dict[str, str | None]] = {}
    for tool, prompts in body.prompt_overrides.items():
        cleaned = {k: (v if v and v.strip() else None) for k, v in prompts.items()}
        if any(v is not None for v in cleaned.values()):
            clean_overrides[tool] = cleaned

    config = (await db.execute(
        select(KolWorkspaceConfig).where(KolWorkspaceConfig.kol_id == kol_id)
    )).scalar_one_or_none()

    if config:
        config.enabled_tabs     = body.enabled_tabs
        config.prompt_overrides = clean_overrides
        config.updated_at       = datetime.now(timezone.utc)
    else:
        config = KolWorkspaceConfig(
            kol_id           = kol_id,
            enabled_tabs     = body.enabled_tabs,
            prompt_overrides = clean_overrides,
        )
        db.add(config)

    db.add(OperationLog(
        user_id    = current_user.id,
        username   = current_user.username,
        role       = current_user.role,
        action     = "admin_update_kol_workspace_config",
        target_type = "kol_workspace_config",
        target_id  = kol_id,
        detail     = {"enabled_tabs_count": len(body.enabled_tabs)},
        ip         = _get_ip(request),
        user_agent = request.headers.get("user-agent"),
    ))

    await db.commit()
    return success_response(data={"kol_id": kol_id, "enabled_tabs": body.enabled_tabs})
