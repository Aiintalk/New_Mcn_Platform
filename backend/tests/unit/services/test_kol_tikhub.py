"""
Unit tests for app.services.kol_tikhub — single KOL TikHub fetch logic.

覆盖：
- skip 分支：无 sec_uid/douyin_id
- ok 主路径：profile 返回完整数据 + fans_info 成功 → Kol 字段更新 + ExternalServiceLog(success)
- ok：uid 非法（空/非数字/0）→ fans_info 不调用
- ok：fans_info 抛错 → fans_raw 记 error，主流程继续 ok
- ok：字段回填（nickname/avatar/follower/video/signature）
- ok：returned_sec_uid 回填（kol 无 sec_uid 时回填，有则保留原值）
- ok：profile 返回字段全 None → 仅 tikhub_raw + updated_at 更新
- ok：sec_uid 缺失但 douyin_id 存在 → 用 douyin_id 作 identifier
- error：profile 抛错 → except 写 ExternalServiceLog(error) → 返回 error dict

使用 test_session fixture（real PostgreSQL test DB），mock tikhub_adapter。
"""
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from sqlalchemy import delete, select

from app.models.kol import Kol
from app.models.log import ExternalServiceLog
from app.services.kol_tikhub import fetch_tikhub_for_kol


@pytest_asyncio.fixture(autouse=True)
async def _isolate_kol_logs(test_session):
    """每条用例前后清 kols / external_service_logs，避免跨测试累积。"""
    await test_session.execute(delete(ExternalServiceLog))
    await test_session.execute(delete(Kol))
    await test_session.commit()
    yield
    await test_session.execute(delete(ExternalServiceLog))
    await test_session.execute(delete(Kol))
    await test_session.commit()


def _make_profile(**overrides) -> dict:
    """构造 get_user_profile 返回值。"""
    base = {
        "raw": {"data": {"user": {"sec_uid": "returned-sec-uid-xyz"}}},
        "nickname": "测试昵称",
        "avatar_url": "https://example.com/a.png",
        "follower_count": 12345,
        "video_count": 67,
        "signature": "测试签名",
        "uid": "999888",
    }
    base.update(overrides)
    return base


async def _seed(test_session, **kol_kwargs) -> Kol:
    kol = Kol(name=kol_kwargs.pop("name", "测试达人"), **kol_kwargs)
    test_session.add(kol)
    await test_session.commit()
    await test_session.refresh(kol)
    return kol


class TestSkipBranch:
    async def test_skip_when_no_identifier(self, test_session):
        kol = await _seed(test_session, name="无标识达人")

        result = await fetch_tikhub_for_kol(kol, test_session)

        assert result == {"status": "skip", "reason": "no sec_uid or douyin_id"}


class TestOkPaths:
    async def test_full_profile_with_fans_info(self, test_session):
        kol = await _seed(test_session, name="完整达人", sec_uid="orig-sec-uid")

        with patch("app.services.kol_tikhub.tikhub_adapter.get_user_profile",
                   AsyncMock(return_value=_make_profile())), \
             patch("app.services.kol_tikhub.tikhub_adapter.get_user_fans_info",
                   AsyncMock(return_value={"raw": {"fans": "data"}})):
            result = await fetch_tikhub_for_kol(kol, test_session)

        assert result["status"] == "ok"
        assert result["fans_info_fetched"] is True
        assert result["nickname"] == "测试昵称"
        assert result["follower_count"] == 12345
        assert result["duration_ms"] >= 0

        await test_session.refresh(kol)
        assert kol.account_name == "测试昵称"
        assert kol.avatar_url == "https://example.com/a.png"
        assert kol.follower_count == 12345
        assert kol.video_count == 67
        assert kol.signature == "测试签名"
        # 已有 sec_uid 不回填
        assert kol.sec_uid == "orig-sec-uid"
        assert kol.tikhub_raw is not None
        assert "profile" in kol.tikhub_raw
        assert "fans_info" in kol.tikhub_raw
        assert kol.tikhub_raw["fans_info"] == {"fans": "data"}

        logs = (await test_session.execute(
            select(ExternalServiceLog).where(ExternalServiceLog.service == "tikhub")
        )).scalars().all()
        assert len(logs) == 1
        assert logs[0].status == "success"
        assert logs[0].action == "get_user_profile+fans_info"

    async def test_uid_empty_skips_fans_info(self, test_session):
        kol = await _seed(test_session, name="无UID", sec_uid="s1")

        with patch("app.services.kol_tikhub.tikhub_adapter.get_user_profile",
                   AsyncMock(return_value=_make_profile(uid=""))), \
             patch("app.services.kol_tikhub.tikhub_adapter.get_user_fans_info",
                   AsyncMock()) as fans_mock:
            result = await fetch_tikhub_for_kol(kol, test_session)

        assert result["status"] == "ok"
        assert result["fans_info_fetched"] is False
        fans_mock.assert_not_called()

    async def test_uid_non_digit_skips_fans_info(self, test_session):
        kol = await _seed(test_session, name="非数字UID", sec_uid="s1")

        with patch("app.services.kol_tikhub.tikhub_adapter.get_user_profile",
                   AsyncMock(return_value=_make_profile(uid="abc-not-digit"))), \
             patch("app.services.kol_tikhub.tikhub_adapter.get_user_fans_info",
                   AsyncMock()) as fans_mock:
            result = await fetch_tikhub_for_kol(kol, test_session)

        assert result["fans_info_fetched"] is False
        fans_mock.assert_not_called()

    async def test_uid_zero_skips_fans_info(self, test_session):
        kol = await _seed(test_session, name="零UID", sec_uid="s1")

        with patch("app.services.kol_tikhub.tikhub_adapter.get_user_profile",
                   AsyncMock(return_value=_make_profile(uid="0"))), \
             patch("app.services.kol_tikhub.tikhub_adapter.get_user_fans_info",
                   AsyncMock()) as fans_mock:
            result = await fetch_tikhub_for_kol(kol, test_session)

        assert result["fans_info_fetched"] is False
        fans_mock.assert_not_called()

    async def test_fans_info_exception_records_error(self, test_session):
        kol = await _seed(test_session, name="fans失败", sec_uid="s1")

        with patch("app.services.kol_tikhub.tikhub_adapter.get_user_profile",
                   AsyncMock(return_value=_make_profile())), \
             patch("app.services.kol_tikhub.tikhub_adapter.get_user_fans_info",
                   AsyncMock(side_effect=RuntimeError("fans api timeout"))):
            result = await fetch_tikhub_for_kol(kol, test_session)

        assert result["status"] == "ok"
        assert result["fans_info_fetched"] is False

        await test_session.refresh(kol)
        assert kol.tikhub_raw["fans_info"]["error"] == "fans api timeout"

    async def test_backfills_sec_uid_when_missing(self, test_session):
        kol = await _seed(test_session, name="无sec_uid达人", douyin_id="dy123")

        with patch("app.services.kol_tikhub.tikhub_adapter.get_user_profile",
                   AsyncMock(return_value=_make_profile())), \
             patch("app.services.kol_tikhub.tikhub_adapter.get_user_fans_info",
                   AsyncMock(return_value={"raw": {"x": 1}})):
            result = await fetch_tikhub_for_kol(kol, test_session)

        assert result["status"] == "ok"
        await test_session.refresh(kol)
        assert kol.sec_uid == "returned-sec-uid-xyz"

    async def test_keeps_existing_sec_uid(self, test_session):
        kol = await _seed(test_session, name="已有sec_uid", sec_uid="orig")

        with patch("app.services.kol_tikhub.tikhub_adapter.get_user_profile",
                   AsyncMock(return_value=_make_profile())), \
             patch("app.services.kol_tikhub.tikhub_adapter.get_user_fans_info",
                   AsyncMock(return_value={"raw": {"x": 1}})):
            await fetch_tikhub_for_kol(kol, test_session)

        await test_session.refresh(kol)
        assert kol.sec_uid == "orig"

    async def test_minimal_profile_skips_optional_fields(self, test_session):
        """profile 返回字段全 None/空 → 仅 tikhub_raw + updated_at 更新，原字段保留。"""
        kol = await _seed(test_session, name="最小达人", sec_uid="s1", follower_count=999)

        profile = {
            "raw": {"data": {"user": {}}},  # 无 returned sec_uid
            "nickname": None,
            "avatar_url": None,
            "follower_count": None,
            "video_count": None,
            "signature": None,
            "uid": "",
        }
        with patch("app.services.kol_tikhub.tikhub_adapter.get_user_profile",
                   AsyncMock(return_value=profile)), \
             patch("app.services.kol_tikhub.tikhub_adapter.get_user_fans_info",
                   AsyncMock()) as fans_mock:
            result = await fetch_tikhub_for_kol(kol, test_session)

        assert result["status"] == "ok"
        fans_mock.assert_not_called()

        await test_session.refresh(kol)
        assert kol.follower_count == 999
        assert kol.account_name is None
        assert kol.avatar_url is None
        assert kol.signature is None
        assert kol.tikhub_raw is not None
        assert kol.tikhub_raw["fans_info"] is None

    async def test_uses_douyin_id_when_no_sec_uid(self, test_session):
        """sec_uid 缺失但 douyin_id 存在 → 用 douyin_id 作 identifier 调 profile。"""
        kol = await _seed(test_session, name="douyin_id", douyin_id="dy456")

        profile_mock = AsyncMock(return_value=_make_profile())
        with patch("app.services.kol_tikhub.tikhub_adapter.get_user_profile",
                   profile_mock), \
             patch("app.services.kol_tikhub.tikhub_adapter.get_user_fans_info",
                   AsyncMock(return_value={"raw": {"x": 1}})):
            result = await fetch_tikhub_for_kol(kol, test_session)

        assert result["status"] == "ok"
        profile_mock.assert_called_once_with("dy456", test_session)

    async def test_no_returned_sec_uid_in_raw(self, test_session):
        """profile_raw.data.user 不存在 → returned_sec_uid 为 None，不回填。"""
        kol = await _seed(test_session, name="无user_data", douyin_id="dy000")

        profile = _make_profile()
        profile["raw"] = {}  # 完全无 data 键
        with patch("app.services.kol_tikhub.tikhub_adapter.get_user_profile",
                   AsyncMock(return_value=profile)), \
             patch("app.services.kol_tikhub.tikhub_adapter.get_user_fans_info",
                   AsyncMock(return_value={"raw": {"x": 1}})):
            await fetch_tikhub_for_kol(kol, test_session)

        await test_session.refresh(kol)
        assert kol.sec_uid is None


class TestErrorPath:
    async def test_profile_raises_writes_error_log(self, test_session):
        kol = await _seed(test_session, name="profile失败", sec_uid="s1")

        with patch("app.services.kol_tikhub.tikhub_adapter.get_user_profile",
                   AsyncMock(side_effect=RuntimeError("profile api down"))):
            result = await fetch_tikhub_for_kol(kol, test_session)

        assert result["status"] == "error"
        assert "profile api down" in result["error"]
        assert result["duration_ms"] >= 0

        logs = (await test_session.execute(
            select(ExternalServiceLog).where(ExternalServiceLog.service == "tikhub")
        )).scalars().all()
        assert len(logs) == 1
        assert logs[0].status == "error"
        assert "profile api down" in logs[0].error_message
