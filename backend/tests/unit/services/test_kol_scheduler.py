"""
Unit tests for app.services.kol_scheduler — run_tikhub_refresh_batch.

覆盖：
- 扫描条件：deleted_at IS NULL + 有 sec_uid 或 douyin_id + (tikhub_raw IS NULL 或 updated_at < 7 天)
- 计数：ok / skip / error
- fetch_tikhub_for_kol 抛异常 → error+1，不中断整批
- _BATCH_SIZE = 50 限制

不直接测 tikhub_refresh_scheduler（无限循环 + asyncio.sleep）。

注意：scheduler 内部用 `from app.core.database import AsyncSessionLocal` 直接持有引用，
需要在测试里 patch `app.services.kol_scheduler.AsyncSessionLocal` 才能连到测试库。
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.kol import Kol
from app.services.kol_scheduler import run_tikhub_refresh_batch


@pytest_asyncio.fixture(autouse=True)
async def _isolate_kols(test_session):
    """每条用例前后清 kols 表。"""
    await test_session.execute(delete(Kol))
    await test_session.commit()
    yield
    await test_session.execute(delete(Kol))
    await test_session.commit()


@pytest.fixture
def scheduler_session_factory(test_engine):
    """scheduler 模块内部的 AsyncSessionLocal 替换为测试库 factory。"""
    return async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


def _patch_scheduler(factory):
    """组合 patch：scheduler 的 AsyncSessionLocal 指向测试库。"""
    return patch("app.services.kol_scheduler.AsyncSessionLocal", factory)


class TestScanFilters:
    async def test_skips_deleted_kols(self, test_session, scheduler_session_factory):
        deleted = Kol(
            name="已删除",
            sec_uid="s1",
            deleted_at=datetime.now(timezone.utc),
        )
        test_session.add(deleted)
        await test_session.commit()

        with _patch_scheduler(scheduler_session_factory), \
             patch("app.services.kol_scheduler.fetch_tikhub_for_kol", AsyncMock()) as fetch_mock:
            result = await run_tikhub_refresh_batch()

        assert result == {"processed": 0, "ok": 0, "skip": 0, "error": 0}
        fetch_mock.assert_not_called()

    async def test_skips_kols_without_identifier(self, test_session, scheduler_session_factory):
        # 无 sec_uid 也无 douyin_id → 不该刷
        no_id = Kol(name="无标识")
        test_session.add(no_id)
        await test_session.commit()

        with _patch_scheduler(scheduler_session_factory), \
             patch("app.services.kol_scheduler.fetch_tikhub_for_kol", AsyncMock()) as fetch_mock:
            result = await run_tikhub_refresh_batch()

        assert result["processed"] == 0
        fetch_mock.assert_not_called()

    async def test_processes_kol_with_null_tikhub_raw(self, test_session, scheduler_session_factory):
        kol = Kol(name="待刷", sec_uid="s1")
        test_session.add(kol)
        await test_session.commit()

        with _patch_scheduler(scheduler_session_factory), \
             patch("app.services.kol_scheduler.fetch_tikhub_for_kol",
                   AsyncMock(return_value={"status": "ok"})):
            result = await run_tikhub_refresh_batch()

        assert result == {"processed": 1, "ok": 1, "skip": 0, "error": 0}

    async def test_processes_kol_with_douyin_id_only(self, test_session, scheduler_session_factory):
        """有 douyin_id（无 sec_uid）也满足扫描条件。"""
        kol = Kol(name="douyin_id达人", douyin_id="dy1")
        test_session.add(kol)
        await test_session.commit()

        with _patch_scheduler(scheduler_session_factory), \
             patch("app.services.kol_scheduler.fetch_tikhub_for_kol",
                   AsyncMock(return_value={"status": "ok"})):
            result = await run_tikhub_refresh_batch()

        assert result["processed"] == 1
        assert result["ok"] == 1

    async def test_processes_kol_with_stale_updated_at(self, test_session, scheduler_session_factory):
        """tikhub_raw 有值但 updated_at > 7 天 → 该刷。"""
        old_time = datetime.now(timezone.utc) - timedelta(days=10)
        kol = Kol(
            name="过期达人",
            sec_uid="s1",
            tikhub_raw={"some": "data"},
            updated_at=old_time,
        )
        test_session.add(kol)
        await test_session.commit()

        with _patch_scheduler(scheduler_session_factory), \
             patch("app.services.kol_scheduler.fetch_tikhub_for_kol",
                   AsyncMock(return_value={"status": "ok"})):
            result = await run_tikhub_refresh_batch()

        assert result["processed"] == 1
        assert result["ok"] == 1

    async def test_skips_recently_refreshed_kol(self, test_session, scheduler_session_factory):
        """tikhub_raw 已存在 + updated_at < 7 天 → 不刷。"""
        recent = Kol(
            name="近期已刷",
            sec_uid="s1",
            tikhub_raw={"x": 1},
            updated_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        test_session.add(recent)
        await test_session.commit()

        with _patch_scheduler(scheduler_session_factory), \
             patch("app.services.kol_scheduler.fetch_tikhub_for_kol", AsyncMock()) as fetch_mock:
            result = await run_tikhub_refresh_batch()

        assert result["processed"] == 0
        fetch_mock.assert_not_called()

    async def test_mixed_eligibility(self, test_session, scheduler_session_factory):
        """混合：1 个该刷 + 1 个已刷未过期 + 1 个已删除 + 1 个无标识。"""
        should = Kol(name="该刷", sec_uid="s1")
        recent = Kol(
            name="已刷未过期",
            sec_uid="s2",
            tikhub_raw={"x": 1},
            updated_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        deleted = Kol(
            name="已删除",
            sec_uid="s3",
            deleted_at=datetime.now(timezone.utc),
        )
        no_id = Kol(name="无标识")
        test_session.add_all([should, recent, deleted, no_id])
        await test_session.commit()

        with _patch_scheduler(scheduler_session_factory), \
             patch("app.services.kol_scheduler.fetch_tikhub_for_kol",
                   AsyncMock(return_value={"status": "ok"})) as fetch_mock:
            result = await run_tikhub_refresh_batch()

        assert result == {"processed": 1, "ok": 1, "skip": 0, "error": 0}
        assert fetch_mock.call_count == 1


class TestCountsAndErrors:
    async def test_counts_mixed_statuses(self, test_session, scheduler_session_factory):
        kols = [
            Kol(name="k1", sec_uid="s1"),
            Kol(name="k2", sec_uid="s2"),
            Kol(name="k3", sec_uid="s3"),
        ]
        test_session.add_all(kols)
        await test_session.commit()

        results = [
            {"status": "ok"},
            {"status": "skip", "reason": "no id"},
            {"status": "error", "error": "boom"},
        ]
        with _patch_scheduler(scheduler_session_factory), \
             patch("app.services.kol_scheduler.fetch_tikhub_for_kol",
                   AsyncMock(side_effect=results)):
            result = await run_tikhub_refresh_batch()

        assert result == {"processed": 3, "ok": 1, "skip": 1, "error": 1}

    async def test_exception_in_fetch_counts_as_error(self, test_session, scheduler_session_factory):
        kol = Kol(name="k1", sec_uid="s1")
        test_session.add(kol)
        await test_session.commit()

        with _patch_scheduler(scheduler_session_factory), \
             patch("app.services.kol_scheduler.fetch_tikhub_for_kol",
                   AsyncMock(side_effect=RuntimeError("unexpected"))):
            result = await run_tikhub_refresh_batch()

        assert result["processed"] == 1
        assert result["error"] == 1
        assert result["ok"] == 0

    async def test_exception_does_not_break_batch(self, test_session, scheduler_session_factory):
        """中间一条抛异常，后续仍被处理。"""
        kols = [
            Kol(name="ok1", sec_uid="s1"),
            Kol(name="boom", sec_uid="s2"),
            Kol(name="ok2", sec_uid="s3"),
        ]
        test_session.add_all(kols)
        await test_session.commit()

        async def fake_fetch(kol, db):
            if kol.name == "boom":
                raise RuntimeError("mid failure")
            return {"status": "ok"}

        with _patch_scheduler(scheduler_session_factory), \
             patch("app.services.kol_scheduler.fetch_tikhub_for_kol",
                   AsyncMock(side_effect=fake_fetch)):
            result = await run_tikhub_refresh_batch()

        assert result["processed"] == 3
        assert result["ok"] == 2
        assert result["error"] == 1


class TestBatchSizeLimit:
    async def test_capped_at_50(self, test_session, scheduler_session_factory):
        """超过 _BATCH_SIZE=50 的部分不处理。"""
        kols = [
            Kol(name=f"k{i:03}", sec_uid=f"s{i}")
            for i in range(60)
        ]
        test_session.add_all(kols)
        await test_session.commit()

        with _patch_scheduler(scheduler_session_factory), \
             patch("app.services.kol_scheduler.fetch_tikhub_for_kol",
                   AsyncMock(return_value={"status": "ok"})) as fetch_mock:
            result = await run_tikhub_refresh_batch()

        assert result["processed"] == 50
        assert result["ok"] == 50
        assert fetch_mock.call_count == 50
