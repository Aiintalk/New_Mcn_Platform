"""
app/services/kol_scheduler.py

定时任务：每 7 天批量刷新 KOL 的 TikHub 数据。
- 扫描条件：tikhub_raw IS NULL  或  updated_at < now() - 7 days
- 每批最多 50 条
- 单条失败跳过，不中断整批
- 通过 asyncio 后台任务运行，在 app 生命周期内持续存活
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from app.core.database import AsyncSessionLocal
from app.models.kol import Kol
from app.services.kol_tikhub import fetch_tikhub_for_kol

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50
_INTERVAL_SECONDS = 7 * 24 * 3600  # 7 days
_STARTUP_DELAY = 10                 # 等待应用完全启动


async def run_tikhub_refresh_batch() -> dict:
    """
    扫描需要刷新的 KOL 并批量调用 TikHub，每批最多 50 条。
    Returns: {"processed": int, "ok": int, "skip": int, "error": int}
    """
    threshold = datetime.now(timezone.utc) - timedelta(days=7)

    async with AsyncSessionLocal() as session:
        kols = (await session.execute(
            select(Kol)
            .where(
                Kol.deleted_at.is_(None),
                or_(Kol.sec_uid.isnot(None), Kol.douyin_id.isnot(None)),
                or_(Kol.tikhub_raw.is_(None), Kol.updated_at < threshold),
            )
            .limit(_BATCH_SIZE)
        )).scalars().all()

    counts = {"processed": len(kols), "ok": 0, "skip": 0, "error": 0}
    logger.info(f"[kol_scheduler] Starting batch: {len(kols)} kols to refresh")

    for kol in kols:
        try:
            async with AsyncSessionLocal() as db:
                result = await fetch_tikhub_for_kol(kol, db)
            counts[result["status"]] = counts.get(result["status"], 0) + 1
        except Exception as e:
            logger.warning(f"[kol_scheduler] Unexpected error for kol id={kol.id}: {e}")
            counts["error"] += 1

    logger.info(f"[kol_scheduler] Batch done: {counts}")
    return counts


async def tikhub_refresh_scheduler():
    """
    后台协程：启动后等待 _STARTUP_DELAY 秒，
    然后每 _INTERVAL_SECONDS 运行一次 run_tikhub_refresh_batch。
    """
    await asyncio.sleep(_STARTUP_DELAY)
    while True:
        try:
            await run_tikhub_refresh_batch()
        except Exception as e:
            logger.error(f"[kol_scheduler] Batch failed with unexpected error: {e}")
        await asyncio.sleep(_INTERVAL_SECONDS)
