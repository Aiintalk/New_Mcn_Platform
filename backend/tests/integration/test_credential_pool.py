"""
AI 凭证池并发安全测试 — yunwu.py adapter。

覆盖维度:
  1. _pick_and_lock — 原子选取凭证（FOR UPDATE SKIP LOCKED）
  2. _release — 释放槽位 + 唤醒排队者
  3. 僵尸锁清理 — 超时未释放的 active_requests 自动归零
  4. 并发竞争 — 多协程同时获取槽位不超限
  5. chat() — 全流程（mock httpx）：成功、失败、无凭证

这些是集成测试，使用真实测试数据库（mcn_test），不依赖运行中的服务器。
并发测试通过 asyncio.gather + 多个独立 session 验证数据库级隔离。
"""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.yunwu import (
    _pick_and_lock,
    _release,
    _wait_queue,
    chat,
)


# ---------------------------------------------------------------------------
# Helpers & Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_factory(test_engine):
    """
    提供 session 工厂，用于创建独立的数据库会话。
    并发测试需要多个独立 session（每个协程一个），test_session 单一 session 不够。
    """
    return async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest.fixture(autouse=True)
def clear_wait_queue():
    """每个测试前后清空全局等待队列，防止跨测试干扰。"""
    _drain_queue()
    yield
    _drain_queue()


def _drain_queue():
    """排空 _wait_queue，取消未完成的 future。"""
    while True:
        try:
            fut = _wait_queue.get_nowait()
            if not fut.done():
                fut.cancel()
        except Exception:
            break


async def _seed_credential(factory, **kwargs) -> int:
    """插入一条凭证记录并返回其 id。所有字段有默认值，可通过 kwargs 覆盖。"""
    defaults = {
        "provider": "yunwu",
        "label": "pool-test",
        "api_key": "sk-pool-test-key",
        "base_url": "https://yunwu.ai/v1",
        "status": "active",
        "active_requests": 0,
        "max_concurrent": 5,
        "max_users": 10,
    }
    defaults.update(kwargs)
    async with factory() as s:
        row = (await s.execute(text("""
            INSERT INTO credentials
                (provider, label, api_key, base_url, status,
                 active_requests, max_concurrent, max_users)
            VALUES
                (:provider, :label, :api_key, :base_url, :status,
                 :active_requests, :max_concurrent, :max_users)
            RETURNING id
        """), defaults)).fetchone()
        await s.commit()
    return int(row[0])


async def _get_field(factory, cred_id: int, field: str):
    """读取凭证的指定字段。"""
    async with factory() as s:
        row = (await s.execute(
            text(f"SELECT {field} FROM credentials WHERE id = :id"),
            {"id": cred_id},
        )).fetchone()
        return row[0] if row else None


async def _count_aicalllogs(factory, cred_id: int) -> int:
    """统计某凭证的 AiCallLog 条数。"""
    async with factory() as s:
        row = (await s.execute(
            text("SELECT COUNT(*) FROM ai_call_logs WHERE credential_id = :id"),
            {"id": cred_id},
        )).fetchone()
        return int(row[0])


async def _seed_user(factory, username: str = "pool_test_user") -> int:
    """创建测试用户并返回其 id（AiCallLog.user_id 有 FK 约束）。"""
    from passlib.context import CryptContext
    _pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
    async with factory() as s:
        row = (await s.execute(text("""
            INSERT INTO users (username, real_name, password_hash, role, status,
                              password_changed_at, token_version)
            VALUES (:username, '测试用户', :hash, 'admin', 'enabled', NOW(), 0)
            RETURNING id
        """), {"username": username, "hash": _pwd.hash("Test@123456")})).fetchone()
        await s.commit()
    return int(row[0])


async def _cleanup(factory, *cred_ids: int, user_ids: list[int] | None = None):
    """删除凭证及其关联的 AiCallLog。"""
    async with factory() as s:
        for cid in cred_ids:
            await s.execute(
                text("DELETE FROM ai_call_logs WHERE credential_id = :id"),
                {"id": cid},
            )
            await s.execute(
                text("DELETE FROM credentials WHERE id = :id"),
                {"id": cid},
            )
        if user_ids:
            for uid in user_ids:
                await s.execute(
                    text("DELETE FROM users WHERE id = :id"),
                    {"id": uid},
                )
        await s.commit()


# --- httpx mock helpers ---

@contextmanager
def _mock_httpx_success(content: str = "AI回复内容",
                        input_tokens: int = 10,
                        output_tokens: int = 5):
    """Mock httpx.AsyncClient 返回成功的 AI 响应。"""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
        },
    }
    with patch("app.adapters.yunwu.httpx.AsyncClient") as MockClient:
        client = AsyncMock()
        client.post = AsyncMock(return_value=mock_response)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
        yield client


@contextmanager
def _mock_httpx_error(status_code: int = 500, text: str = "Internal Error"):
    """Mock httpx.AsyncClient 返回 HTTP 错误。"""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.text = text
    mock_response.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError(
        f"HTTP {status_code}", request=MagicMock(), response=mock_response,
    ))
    with patch("app.adapters.yunwu.httpx.AsyncClient") as MockClient:
        client = AsyncMock()
        client.post = AsyncMock(return_value=mock_response)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
        yield client


# ---------------------------------------------------------------------------
# 1. TestPickAndLock — 原子选取凭证
# ---------------------------------------------------------------------------

class TestPickAndLock:
    """验证 _pick_and_lock 的基本行为：选取、过滤、计数。"""

    async def test_returns_credential_when_slot_available(self, db_factory):
        """有可用槽位时返回 (id, api_key, base_url) 三元组。"""
        cred_id = await _seed_credential(db_factory)
        try:
            async with db_factory() as s:
                result = await _pick_and_lock(s, "yunwu")
                await s.commit()
            assert result is not None
            picked_id, api_key, base_url = result
            assert picked_id == cred_id
            assert api_key == "sk-pool-test-key"
            assert base_url == "https://yunwu.ai/v1"
        finally:
            await _cleanup(db_factory, cred_id)

    async def test_pick_increments_active_requests(self, db_factory):
        """选取后 active_requests +1。"""
        cred_id = await _seed_credential(db_factory, max_concurrent=5)
        try:
            async with db_factory() as s:
                await _pick_and_lock(s, "yunwu")
                await s.commit()
            assert await _get_field(db_factory, cred_id, "active_requests") == 1
        finally:
            await _cleanup(db_factory, cred_id)

    async def test_returns_none_when_max_concurrent_reached(self, db_factory):
        """active_requests == max_concurrent 时返回 None。"""
        cred_id = await _seed_credential(
            db_factory, max_concurrent=2, active_requests=2
        )
        try:
            async with db_factory() as s:
                result = await _pick_and_lock(s, "yunwu")
                await s.commit()
            assert result is None
        finally:
            await _cleanup(db_factory, cred_id)

    async def test_returns_none_when_status_inactive(self, db_factory):
        """status != 'active' 的凭证被跳过。"""
        cred_id = await _seed_credential(db_factory, status="inactive")
        try:
            async with db_factory() as s:
                result = await _pick_and_lock(s, "yunwu")
                await s.commit()
            assert result is None
        finally:
            await _cleanup(db_factory, cred_id)

    async def test_returns_none_when_provider_mismatch(self, db_factory):
        """provider 不匹配的凭证被跳过。"""
        cred_id = await _seed_credential(db_factory, provider="siliconflow")
        try:
            async with db_factory() as s:
                result = await _pick_and_lock(s, "yunwu")
                await s.commit()
            assert result is None
        finally:
            await _cleanup(db_factory, cred_id)

    async def test_uses_fallback_base_url_when_null(self, db_factory):
        """base_url 为 NULL 时使用 _DEFAULT_BASE_URLS 中的 fallback。"""
        cred_id = await _seed_credential(db_factory, base_url=None)
        try:
            async with db_factory() as s:
                result = await _pick_and_lock(s, "yunwu")
                await s.commit()
            assert result is not None
            _, _, base_url = result
            assert base_url == "https://yunwu.ai/v1"
        finally:
            await _cleanup(db_factory, cred_id)

    async def test_prioritizes_least_loaded_credential(self, db_factory):
        """多个可用凭证时，优先选 active_requests 最少的。"""
        cred_a = await _seed_credential(
            db_factory, label="A", active_requests=3, max_concurrent=10
        )
        cred_b = await _seed_credential(
            db_factory, label="B", active_requests=0, max_concurrent=10
        )
        try:
            async with db_factory() as s:
                result = await _pick_and_lock(s, "yunwu")
                await s.commit()
            assert result is not None
            picked_id, _, _ = result
            assert picked_id == cred_b, "应选 active_requests=0 的凭证 B"
        finally:
            await _cleanup(db_factory, cred_a, cred_b)


# ---------------------------------------------------------------------------
# 2. TestRelease — 释放槽位
# ---------------------------------------------------------------------------

class TestRelease:
    """验证 _release 正确递减 active_requests。"""

    async def test_release_decrements_active_requests(self, db_factory):
        """释放后 active_requests -1。"""
        cred_id = await _seed_credential(
            db_factory, max_concurrent=5, active_requests=3
        )
        try:
            async with db_factory() as s:
                await _release(cred_id, s)
                await s.commit()
            assert await _get_field(db_factory, cred_id, "active_requests") == 2
        finally:
            await _cleanup(db_factory, cred_id)

    async def test_release_floors_at_zero(self, db_factory):
        """active_requests 已经是 0 时，释放不会变成 -1（GREATEST 保护）。"""
        cred_id = await _seed_credential(
            db_factory, max_concurrent=5, active_requests=0
        )
        try:
            async with db_factory() as s:
                await _release(cred_id, s)
                await s.commit()
            assert await _get_field(db_factory, cred_id, "active_requests") == 0
        finally:
            await _cleanup(db_factory, cred_id)


# ---------------------------------------------------------------------------
# 3. TestStaleLockCleanup — 僵尸锁清理
# ---------------------------------------------------------------------------

class TestStaleLockCleanup:
    """验证 _pick_and_lock 中的僵尸锁清理逻辑。"""

    async def test_stale_lock_gets_reset(self, db_factory):
        """active_requests > 0 且 updated_at 超过 _STALE_LOCK_SECS 的凭证被重置为 0。"""
        from app.adapters.yunwu import _STALE_LOCK_SECS
        stale_time = datetime.now(timezone.utc) - timedelta(seconds=_STALE_LOCK_SECS + 60)

        cred_id = await _seed_credential(
            db_factory, max_concurrent=5, active_requests=3
        )
        # 手动把 updated_at 改成很久以前
        async with db_factory() as s:
            await s.execute(text("""
                UPDATE credentials SET updated_at = :stale WHERE id = :id
            """), {"stale": stale_time, "id": cred_id})
            await s.commit()
        try:
            # 触发 _pick_and_lock（内部先清理僵尸锁）
            async with db_factory() as s:
                result = await _pick_and_lock(s, "yunwu")
                await s.commit()

            # 僵尸锁被重置后，正常选取 → active_requests 应为 1（重置为 0 后 +1）
            assert result is not None
            assert await _get_field(db_factory, cred_id, "active_requests") == 1
        finally:
            await _cleanup(db_factory, cred_id)

    async def test_fresh_lock_not_affected(self, db_factory):
        """updated_at 在 _STALE_LOCK_SECS 内的凭证不受清理影响。"""
        cred_id = await _seed_credential(
            db_factory, max_concurrent=2, active_requests=2
        )
        try:
            # active_requests == max_concurrent，且有新鲜 updated_at
            async with db_factory() as s:
                result = await _pick_and_lock(s, "yunwu")
                await s.commit()

            # 不应被清理 → active_requests 仍为 2 → 无可用槽位 → None
            assert result is None
            assert await _get_field(db_factory, cred_id, "active_requests") == 2
        finally:
            await _cleanup(db_factory, cred_id)


# ---------------------------------------------------------------------------
# 4. TestConcurrentAllocation — 并发竞争安全
# ---------------------------------------------------------------------------

class TestConcurrentAllocation:
    """
    验证 FOR UPDATE SKIP LOCKED 在并发场景下的正确性。

    关键：每个并发任务必须用独立的 session（独立数据库连接），
    否则 asyncio 单线程下不会有真正的并发竞争。
    """

    async def test_concurrent_pick_distributes_across_credentials(
        self, db_factory
    ):
        """3 个凭证（各 max_concurrent=1），3 个并发任务，各拿到不同凭证。"""
        ids = await asyncio.gather(
            _seed_credential(db_factory, label="C1", max_concurrent=1),
            _seed_credential(db_factory, label="C2", max_concurrent=1),
            _seed_credential(db_factory, label="C3", max_concurrent=1),
        )
        try:
            async def pick_and_commit():
                async with db_factory() as s:
                    result = await _pick_and_lock(s, "yunwu")
                    await s.commit()
                    return result

            results = await asyncio.gather(
                pick_and_commit(),
                pick_and_commit(),
                pick_and_commit(),
            )

            # 全部成功
            assert all(r is not None for r in results), \
                f"部分选取失败: {results}"
            # 各拿到不同凭证
            picked_ids = {r[0] for r in results}
            assert len(picked_ids) == 3, \
                f"并发选取应分布到 3 个凭证，实际: {picked_ids}"
            # 每个凭证 active_requests = 1
            for cid in ids:
                assert await _get_field(db_factory, cid, "active_requests") == 1
        finally:
            await _cleanup(db_factory, *ids)

    async def test_concurrent_pick_returns_none_when_all_full(
        self, db_factory
    ):
        """1 个凭证（max_concurrent=1，已被占），3 个并发任务全返回 None。"""
        cred_id = await _seed_credential(
            db_factory, max_concurrent=1, active_requests=1
        )
        try:
            async def pick_and_commit():
                async with db_factory() as s:
                    result = await _pick_and_lock(s, "yunwu")
                    await s.commit()
                    return result

            results = await asyncio.gather(
                pick_and_commit(),
                pick_and_commit(),
                pick_and_commit(),
            )

            assert all(r is None for r in results), \
                "槽位已满时不应有任何选取成功"
            # active_requests 不变
            assert await _get_field(db_factory, cred_id, "active_requests") == 1
        finally:
            await _cleanup(db_factory, cred_id)

    async def test_pick_release_repick_cycle(self, db_factory):
        """完整生命周期：选取 → 释放 → 再选取 → 成功。"""
        cred_id = await _seed_credential(db_factory, max_concurrent=1)
        try:
            # 第一次选取
            async with db_factory() as s1:
                r1 = await _pick_and_lock(s1, "yunwu")
                await s1.commit()
            assert r1 is not None
            assert await _get_field(db_factory, cred_id, "active_requests") == 1

            # 释放
            async with db_factory() as s2:
                await _release(cred_id, s2)
                await s2.commit()
            assert await _get_field(db_factory, cred_id, "active_requests") == 0

            # 再选取
            async with db_factory() as s3:
                r2 = await _pick_and_lock(s3, "yunwu")
                await s3.commit()
            assert r2 is not None
            assert await _get_field(db_factory, cred_id, "active_requests") == 1
        finally:
            await _cleanup(db_factory, cred_id)

    async def test_concurrent_never_exceeds_max_across_multiple_credentials(
        self, db_factory
    ):
        """
        2 个凭证（各 max_concurrent=2，总槽位=4），10 个并发任务。
        验证：成功数 <= 4，失败数 >= 6。
        """
        ids = await asyncio.gather(
            _seed_credential(db_factory, label="P1", max_concurrent=2),
            _seed_credential(db_factory, label="P2", max_concurrent=2),
        )
        try:
            async def pick_and_commit():
                async with db_factory() as s:
                    result = await _pick_and_lock(s, "yunwu")
                    await s.commit()
                    return result

            results = await asyncio.gather(
                *[pick_and_commit() for _ in range(10)]
            )

            successes = [r for r in results if r is not None]
            failures = [r for r in results if r is None]

            assert len(successes) <= 4, \
                f"总槽位只有 4 个，但 {len(successes)} 个任务成功"
            assert len(failures) >= 6, \
                f"应有至少 6 个任务失败，实际 {len(failures)}"

            # 验证每个凭证的 active_requests 不超过 max_concurrent
            for cid in ids:
                ar = await _get_field(db_factory, cid, "active_requests")
                assert ar <= 2, \
                    f"凭证 {cid} 的 active_requests={ar} 超过 max_concurrent=2"
        finally:
            await _cleanup(db_factory, *ids)


# ---------------------------------------------------------------------------
# 5. TestQueueWakeup — 排队等待与唤醒
# ---------------------------------------------------------------------------

class TestQueueWakeup:
    """验证 _release 唤醒 _wait_queue 中的等待者。"""

    async def test_release_wakes_waiting_future(self, db_factory):
        """_release 执行后，队列中的下一个 future 被 set_result(True)。"""
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        await _wait_queue.put(fut)

        assert not fut.done()

        # _release 内部唤醒队列首个未完成的 future
        # 用不存在的 credential_id（UPDATE 影响 0 行但唤醒逻辑仍执行）
        async with db_factory() as s:
            await _release(999999, s)
            await s.commit()

        assert fut.done()
        assert fut.result() is True

    async def test_release_skips_cancelled_future(self, db_factory):
        """已取消的 future 被跳过，唤醒下一个有效的。"""
        loop = asyncio.get_running_loop()
        cancelled_fut = loop.create_future()
        valid_fut = loop.create_future()
        cancelled_fut.cancel()

        await _wait_queue.put(cancelled_fut)
        await _wait_queue.put(valid_fut)

        async with db_factory() as s:
            await _release(999998, s)
            await s.commit()

        assert valid_fut.done()
        assert valid_fut.result() is True


# ---------------------------------------------------------------------------
# 6. TestChatIntegration — chat() 全流程（mock httpx）
# ---------------------------------------------------------------------------

class TestChatIntegration:
    """验证 chat() 函数的完整调用流程。"""

    async def test_chat_success_returns_content_and_writes_log(
        self, db_factory
    ):
        """成功调用：返回内容 + 写 AiCallLog + 释放槽位。"""
        cred_id = await _seed_credential(db_factory, max_concurrent=5)
        uid = await _seed_user(db_factory)
        try:
            messages = [{"role": "user", "content": "你好"}]
            with _mock_httpx_success(content="你好！", input_tokens=8, output_tokens=3):
                async with db_factory() as s:
                    result = await chat(
                        messages, s, "gpt-4o-mini",
                        provider="yunwu", user_id=uid, feature="test",
                    )

            assert result == "你好！"
            # 槽位已释放
            assert await _get_field(db_factory, cred_id, "active_requests") == 0
            # AiCallLog 已写入
            log_count = await _count_aicalllogs(db_factory, cred_id)
            assert log_count == 1
        finally:
            await _cleanup(db_factory, cred_id, user_ids=[uid])

    async def test_chat_http_error_still_releases_and_logs(
        self, db_factory
    ):
        """HTTP 错误：抛 RuntimeError + 写 error 日志 + 释放槽位。"""
        cred_id = await _seed_credential(db_factory, max_concurrent=5)
        uid = await _seed_user(db_factory)
        try:
            messages = [{"role": "user", "content": "测试"}]
            with _mock_httpx_error(status_code=500, text="Server Error"):
                async with db_factory() as s:
                    with pytest.raises(RuntimeError, match="chat failed"):
                        await chat(
                            messages, s, "gpt-4o-mini",
                            provider="yunwu", user_id=uid, feature="test",
                        )

            # 即使出错，槽位也必须释放
            assert await _get_field(db_factory, cred_id, "active_requests") == 0
            # 错误日志已写入
            log_count = await _count_aicalllogs(db_factory, cred_id)
            assert log_count == 1
        finally:
            await _cleanup(db_factory, cred_id, user_ids=[uid])

    async def test_chat_no_credential_raises_after_queue_timeout(
        self, db_factory
    ):
        """无可用凭证：排队超时后抛 RuntimeError。"""
        # 不创建任何凭证 → _pick_and_lock 返回 None
        with patch("app.adapters.yunwu._QUEUE_TIMEOUT", 0.5):
            messages = [{"role": "user", "content": "测试"}]
            async with db_factory() as s:
                with pytest.raises(RuntimeError, match="queue timeout"):
                    await chat(
                        messages, s, "gpt-4o-mini",
                        provider="yunwu", user_id=None, feature="test",
                    )

    async def test_chat_picks_correct_provider(self, db_factory):
        """chat() 按 provider 过滤凭证池。"""
        # 创建 siliconflow 的凭证，请求 yunwu → 应超时失败
        sf_id = await _seed_credential(
            db_factory, provider="siliconflow", label="SF"
        )
        try:
            with patch("app.adapters.yunwu._QUEUE_TIMEOUT", 0.5):
                messages = [{"role": "user", "content": "测试"}]
                async with db_factory() as s:
                    with pytest.raises(RuntimeError, match="queue timeout"):
                        await chat(
                            messages, s, "some-model",
                            provider="yunwu",  # yunwu 池无凭证
                            user_id=None, feature="test",
                        )
        finally:
            await _cleanup(db_factory, sf_id)
