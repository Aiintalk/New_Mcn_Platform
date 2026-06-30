"""
app/services/workspace_prompt.py

红人工作台 Prompt 覆盖服务：
  resolve_prompt(kol_id, tool_code, prompt_key, db)
    → 返回该红人的专属 Prompt（字符串），未配置时返回 None（调用方 fallback 全局默认）
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kol_workspace_config import KolWorkspaceConfig


async def resolve_prompt(
    kol_id: int | None,
    tool_code: str,
    prompt_key: str,
    db: AsyncSession,
) -> str | None:
    """
    查询红人专属 Prompt。

    Args:
        kol_id: 红人 ID，为 None 时直接返回 None
        tool_code: 工具标识，如 "qianchuan-writer" / "retrospective"
        prompt_key: Prompt 字段名，如 "system_prompt" / "writing_prompt"
        db: 数据库会话

    Returns:
        非空字符串（专属 Prompt）或 None（调用方使用全局默认值）
    """
    if not kol_id:
        return None

    row = (await db.execute(
        select(KolWorkspaceConfig).where(KolWorkspaceConfig.kol_id == kol_id)
    )).scalar_one_or_none()

    if not row:
        return None

    overrides = row.prompt_overrides or {}
    value = (overrides.get(tool_code) or {}).get(prompt_key)
    return value if value and str(value).strip() else None
