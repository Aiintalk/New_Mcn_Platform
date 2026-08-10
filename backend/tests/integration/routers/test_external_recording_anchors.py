"""Integration tests for external recording anchors API."""
import uuid

import pytest
from sqlalchemy import text

from app.core.config import settings


pytestmark = pytest.mark.asyncio

API_KEY = "recording-anchor-test-key"


@pytest.fixture(autouse=True)
def _configure_external_api_key(monkeypatch):
    monkeypatch.setattr(settings, "external_kols_api_key", API_KEY)


def _headers(key: str = API_KEY) -> dict[str, str]:
    return {"X-API-Key": key}


async def _create_kol(
    test_session,
    *,
    name: str,
    platform: str = "douyin",
    douyin_id: str | None = None,
    sec_uid: str | None = None,
    account_name: str | None = None,
    deleted: bool = False,
) -> int:
    result = await test_session.execute(
        text(
            """
            INSERT INTO kols (
              name, account_name, platform, douyin_id, sec_uid, avatar_url,
              signature, follower_count, video_count, style_notes, status, deleted_at
            )
            VALUES (
              :name, :account_name, :platform, :douyin_id, :sec_uid,
              'https://example.com/a.png', '简介', 1000, 12, '说明',
              'signed', CASE WHEN :deleted THEN now() ELSE NULL END
            )
            RETURNING id
            """
        ),
        {
            "name": name,
            "account_name": account_name,
            "platform": platform,
            "douyin_id": douyin_id,
            "sec_uid": sec_uid,
            "deleted": deleted,
        },
    )
    kol_id = result.scalar_one()
    await test_session.commit()
    return kol_id


async def _create_benchmark(
    test_session,
    *,
    kol_id: int,
    account_name: str,
    account_type: str,
    account_input: str | None = None,
    sec_uid: str | None = None,
) -> int:
    result = await test_session.execute(
        text(
            """
            INSERT INTO kol_benchmarks (
              kol_id, account_name, account_input, sec_uid, avatar_url,
              follower_count, account_type, description, sort_order
            )
            VALUES (
              :kol_id, :account_name, :account_input, :sec_uid,
              'https://example.com/b.png', 8888, :account_type, '对标说明', 0
            )
            RETURNING id
            """
        ),
        {
            "kol_id": kol_id,
            "account_name": account_name,
            "account_input": account_input,
            "sec_uid": sec_uid,
            "account_type": account_type,
        },
    )
    benchmark_id = result.scalar_one()
    await test_session.commit()
    return benchmark_id


class TestExternalRecordingAnchorsAuth:
    async def test_missing_key_returns_401(self, test_client):
        resp = await test_client.get("/api/external/recording-anchors")

        assert resp.status_code == 401
        body = resp.json()
        assert body["success"] is False
        assert body["code"] == "EXTERNAL_API_KEY_INVALID"

    async def test_wrong_key_returns_401(self, test_client):
        resp = await test_client.get(
            "/api/external/recording-anchors",
            headers=_headers("wrong-recording-key"),
        )

        assert resp.status_code == 401
        body = resp.json()
        assert body["success"] is False
        assert body["code"] == "EXTERNAL_API_KEY_INVALID"

    async def test_unconfigured_key_returns_503(self, test_client, monkeypatch):
        monkeypatch.setattr(settings, "external_kols_api_key", "")

        resp = await test_client.get(
            "/api/external/recording-anchors",
            headers=_headers(),
        )

        assert resp.status_code == 503
        body = resp.json()
        assert body["success"] is False
        assert body["code"] == "EXTERNAL_API_KEY_NOT_CONFIGURED"


class TestExternalRecordingAnchorsList:
    async def test_list_merges_kols_and_livestream_benchmarks_only(
        self, test_client, test_session
    ):
        marker = f"录屏同步-{uuid.uuid4().hex[:8]}"
        kol_id = await _create_kol(
            test_session,
            name=f"{marker}-红人",
            douyin_id=f"douyin-{marker}",
            sec_uid=f"sec-{marker}",
            account_name=f"{marker}-红人昵称",
        )
        parent_id = await _create_kol(test_session, name="录屏同步父达人")
        deleted_parent_id = await _create_kol(
            test_session,
            name="录屏同步已删父达人",
            deleted=True,
        )
        live_benchmark_id = await _create_benchmark(
            test_session,
            kol_id=parent_id,
            account_name=f"{marker}-直播对标",
            account_type="livestream",
            account_input=f"live-{marker}",
            sec_uid=f"sec-live-{marker}",
        )
        await _create_benchmark(
            test_session,
            kol_id=parent_id,
            account_name=f"{marker}-内容对标",
            account_type="content",
            account_input=f"content-{marker}",
            sec_uid=f"sec-content-{marker}",
        )
        await _create_benchmark(
            test_session,
            kol_id=deleted_parent_id,
            account_name=f"{marker}-已删父直播对标",
            account_type="livestream",
            account_input=f"deleted-{marker}",
            sec_uid=f"sec-deleted-{marker}",
        )

        resp = await test_client.get(
            "/api/external/recording-anchors",
            params={"keyword": marker, "page_size": 20},
            headers=_headers(),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        items = body["data"]["items"]
        assert {item["source_type"] for item in items} == {"kol", "live_benchmark"}
        assert body["data"]["pagination"]["total"] == 2

        kol_item = next(item for item in items if item["source_type"] == "kol")
        assert kol_item["source_id"] == kol_id
        assert kol_item["source_label"] == "红人主播"
        assert kol_item["douyin_id"] == f"douyin-{marker}"
        assert kol_item["sec_user_id"] == f"sec-{marker}"
        assert kol_item["sync_ready"] is True

        live_item = next(item for item in items if item["source_type"] == "live_benchmark")
        assert live_item["source_id"] == live_benchmark_id
        assert live_item["source_label"] == "直播对标主播"
        assert live_item["parent_kol_id"] == parent_id
        assert live_item["douyin_id"] == f"live-{marker}"
        assert live_item["sec_user_id"] == f"sec-live-{marker}"
        assert live_item["follower_count"] == 8888
        assert live_item["sync_ready"] is True
        assert all("内容对标" not in item["nickname"] for item in items)

    async def test_ready_only_excludes_livestream_benchmark_without_identifier(
        self, test_client, test_session
    ):
        marker = f"旧对标-{uuid.uuid4().hex[:8]}"
        parent_id = await _create_kol(test_session, name="旧对标父达人")
        await _create_benchmark(
            test_session,
            kol_id=parent_id,
            account_name=f"{marker}-只有昵称",
            account_type="livestream",
        )

        resp = await test_client.get(
            "/api/external/recording-anchors",
            params={"keyword": marker, "source_type": "live_benchmark"},
            headers=_headers(),
        )
        assert resp.status_code == 200
        item = resp.json()["data"]["items"][0]
        assert item["sync_ready"] is False
        assert "缺少抖音账号 ID" in item["sync_block_reason"]

        ready_resp = await test_client.get(
            "/api/external/recording-anchors",
            params={"keyword": marker, "source_type": "live_benchmark", "ready_only": True},
            headers=_headers(),
        )
        assert ready_resp.status_code == 200
        assert ready_resp.json()["data"]["items"] == []

    async def test_invalid_source_type_returns_standard_error(self, test_client):
        resp = await test_client.get(
            "/api/external/recording-anchors",
            params={"source_type": "content"},
            headers=_headers(),
        )

        assert resp.status_code == 400
        body = resp.json()
        assert body["success"] is False
        assert body["code"] == "VALIDATION_ERROR"

    async def test_source_type_kol_returns_only_kol_anchors(
        self, test_client, test_session
    ):
        marker = f"来源筛选-{uuid.uuid4().hex[:8]}"
        kol_id = await _create_kol(
            test_session,
            name=f"{marker}-红人",
            douyin_id=f"douyin-{marker}",
        )
        parent_id = await _create_kol(test_session, name=f"{marker}-父达人")
        await _create_benchmark(
            test_session,
            kol_id=parent_id,
            account_name=f"{marker}-直播对标",
            account_type="livestream",
            account_input=f"live-{marker}",
        )

        resp = await test_client.get(
            "/api/external/recording-anchors",
            params={"keyword": marker, "source_type": "kol"},
            headers=_headers(),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        items = body["data"]["items"]
        assert body["data"]["pagination"]["total"] == 2
        assert {item["source_type"] for item in items} == {"kol"}
        assert {item["source_id"] for item in items} == {kol_id, parent_id}

    async def test_platform_filter_excludes_livestream_when_not_douyin(
        self, test_client, test_session
    ):
        marker = f"平台筛选-{uuid.uuid4().hex[:8]}"
        xhs_kol_id = await _create_kol(
            test_session,
            name=f"{marker}-小红书红人",
            platform="xiaohongshu",
            douyin_id=f"xhs-{marker}",
        )
        parent_id = await _create_kol(test_session, name=f"{marker}-抖音父达人")
        await _create_benchmark(
            test_session,
            kol_id=parent_id,
            account_name=f"{marker}-直播对标",
            account_type="livestream",
            account_input=f"live-{marker}",
        )

        resp = await test_client.get(
            "/api/external/recording-anchors",
            params={"keyword": marker, "platform": "xiaohongshu"},
            headers=_headers(),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        items = body["data"]["items"]
        assert body["data"]["pagination"]["total"] == 1
        assert items[0]["source_id"] == xhs_kol_id
        assert items[0]["source_type"] == "kol"
        assert items[0]["platform"] == "xiaohongshu"

    async def test_paginates_after_merging_sources(self, test_client, test_session):
        marker = f"分页录屏-{uuid.uuid4().hex[:8]}"
        await _create_kol(
            test_session,
            name=f"{marker}-红人A",
            douyin_id=f"douyin-a-{marker}",
        )
        await _create_kol(
            test_session,
            name=f"{marker}-红人B",
            douyin_id=f"douyin-b-{marker}",
        )
        parent_id = await _create_kol(test_session, name=f"{marker}-父达人")
        await _create_benchmark(
            test_session,
            kol_id=parent_id,
            account_name=f"{marker}-直播对标",
            account_type="livestream",
            account_input=f"live-{marker}",
        )

        resp = await test_client.get(
            "/api/external/recording-anchors",
            params={"keyword": marker, "page": 2, "page_size": 2},
            headers=_headers(),
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["items"]) == 2
        assert data["pagination"] == {
            "page": 2,
            "page_size": 2,
            "total": 4,
            "total_pages": 2,
        }
