"""
app/services/credential_selector.py

通用 Key 池选择器：
- 按 provider 过滤，选取状态可用、未超限、未冷却的 Key
- 加权随机选择（weight 字段）
- 成功时：fail_count 归零，quota_used += 1
- 失败时：fail_count += 1；累计 3 次后冷却 5 分钟
"""
import random
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credential import ServiceCredential


async def pick_credential(
    provider: str,
    db: AsyncSession,
    model: str | None = None,
) -> ServiceCredential:
    """
    从 Key 池中选择一个可用的 Credential。

    Args:
        provider: 服务提供商标识，如 "ai" / "tikhub" / "oss"
        db: AsyncSession
        model: 仅 provider="ai" 时使用，匹配 config->>'model'

    Returns:
        ServiceCredential 对象

    Raises:
        RuntimeError: 无可用 Key 时抛出
    """
    now = datetime.now(timezone.utc)

    result = await db.execute(
        text("""
            SELECT * FROM service_credentials
            WHERE provider = :provider
              AND status = 'enabled'
              AND (cooldown_until IS NULL OR cooldown_until < :now)
              AND (quota_limit IS NULL OR quota_used < quota_limit)
            ORDER BY weight DESC
        """),
        {"provider": provider, "now": now},
    )
    rows = result.mappings().all()

    if model and rows:
        filtered = [r for r in rows if r["config"] and r["config"].get("model") == model]
        if filtered:
            rows = filtered

    if not rows:
        raise RuntimeError(f"No available credential for provider={provider}")

    weights = [max(r["weight"] or 1, 1) for r in rows]
    selected_row = random.choices(rows, weights=weights, k=1)[0]

    # Re-fetch as ORM object so callers can access .config, .secret_enc, etc.
    cred = (await db.execute(
        select(ServiceCredential).where(ServiceCredential.id == selected_row["id"])
    )).scalar_one()
    return cred


async def report_success(credential_id: int, db: AsyncSession) -> None:
    """调用成功：fail_count 归零，quota_used += 1"""
    await db.execute(
        text("""
            UPDATE service_credentials
            SET fail_count = 0,
                quota_used = COALESCE(quota_used, 0) + 1,
                updated_at = NOW()
            WHERE id = :id
        """),
        {"id": credential_id},
    )
    await db.commit()


async def report_failure(credential_id: int, db: AsyncSession) -> None:
    """
    调用失败：fail_count += 1；
    累计 >= 3 次时冷却 5 分钟（cooldown_until = now + 5min）
    """
    result = await db.execute(
        text("SELECT fail_count FROM service_credentials WHERE id = :id"),
        {"id": credential_id},
    )
    row = result.fetchone()
    new_fail_count = (row.fail_count or 0) + 1

    cooldown_until = None
    if new_fail_count >= 3:
        cooldown_until = datetime.now(timezone.utc) + timedelta(minutes=5)

    await db.execute(
        text("""
            UPDATE service_credentials
            SET fail_count = :fail_count,
                cooldown_until = :cooldown_until,
                updated_at = NOW()
            WHERE id = :id
        """),
        {"id": credential_id, "fail_count": new_fail_count, "cooldown_until": cooldown_until},
    )
    await db.commit()
