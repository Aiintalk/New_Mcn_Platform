"""
Integration tests for external_kols router.

Covers:
- X-API-Key auth: configured / missing / invalid / unconfigured
- GET /api/external/kols list pagination + filters
- GET /api/external/kols/{id} detail response and not-found envelope
"""
import json
import uuid

import pytest
from sqlalchemy import text

from app.core.config import settings


pytestmark = pytest.mark.asyncio

API_KEY = "external-test-key"


@pytest.fixture(autouse=True)
def _configure_external_api_key(monkeypatch):
    monkeypatch.setattr(settings, "external_kols_api_key", API_KEY)


def _headers(key: str = API_KEY) -> dict[str, str]:
    return {"X-API-Key": key}


async def _create_kol(
    test_session,
    *,
    name_prefix: str,
    platform: str = "douyin",
    persona: str | None = None,
    content_plan: str | None = None,
    deleted: bool = False,
) -> tuple[int, dict]:
    suffix = uuid.uuid4().hex[:8]
    raw = {"source": "external-kols-test", "suffix": suffix}
    result = await test_session.execute(
        text(
            """
            INSERT INTO kols (
              name, account_name, category, platform, external_id,
              douyin_id, sec_uid, avatar_url, signature,
              follower_count, video_count, owner, persona, content_plan,
              style_notes, tikhub_raw, status, background, experience,
              relationships, unique_story, extra_notes, deleted_at
            )
            VALUES (
              :name, :account_name, '美妆', :platform, :external_id,
              :douyin_id, :sec_uid, :avatar_url, '签名',
              12345, 67, '运营A', :persona, :content_plan,
              '风格说明', CAST(:raw AS JSONB), 'signed', '背景',
              '经历', '关系', '独特故事', '补充',
              CASE WHEN :deleted THEN now() ELSE NULL END
            )
            RETURNING id
            """
        ),
        {
            "name": f"{name_prefix}-{suffix}",
            "account_name": f"账号-{suffix}",
            "platform": platform,
            "external_id": f"ext-{suffix}",
            "douyin_id": f"douyin-{suffix}",
            "sec_uid": f"sec-{suffix}",
            "avatar_url": f"https://example.com/{suffix}.png",
            "persona": persona,
            "content_plan": content_plan,
            "raw": json.dumps(raw),
            "deleted": deleted,
        },
    )
    kol_id = result.scalar_one()
    await test_session.commit()
    return kol_id, raw


class TestExternalKolsAuth:
    async def test_missing_key_returns_401(self, test_client):
        resp = await test_client.get("/api/external/kols")
        assert resp.status_code == 401
        body = resp.json()
        assert body["success"] is False
        assert body["code"] == "EXTERNAL_API_KEY_INVALID"

    async def test_invalid_key_returns_401(self, test_client):
        resp = await test_client.get("/api/external/kols", headers=_headers("wrong-key"))
        assert resp.status_code == 401
        body = resp.json()
        assert body["success"] is False
        assert body["code"] == "EXTERNAL_API_KEY_INVALID"

    async def test_unconfigured_key_returns_503(self, test_client, monkeypatch):
        monkeypatch.setattr(settings, "external_kols_api_key", "")
        resp = await test_client.get("/api/external/kols", headers=_headers())
        assert resp.status_code == 503
        body = resp.json()
        assert body["success"] is False
        assert body["code"] == "EXTERNAL_API_KEY_NOT_CONFIGURED"


class TestExternalKolsList:
    async def test_list_filters_paginates_and_omits_raw_by_default(
        self, test_client, test_session
    ):
        marker = f"外部接口达人-{uuid.uuid4().hex[:8]}"
        await _create_kol(
            test_session,
            name_prefix=marker,
            platform="douyin",
            persona="完整人格档案",
            content_plan="完整内容规划",
        )
        await _create_kol(
            test_session,
            name_prefix=marker,
            platform="tiktok",
            persona=None,
            content_plan=None,
        )
        await _create_kol(
            test_session,
            name_prefix=marker,
            platform="douyin",
            persona="已软删",
            content_plan="已软删",
            deleted=True,
        )

        resp = await test_client.get(
            "/api/external/kols",
            params={
                "keyword": marker,
                "platform": "douyin",
                "status": "onboarded",
                "page": 1,
                "page_size": 1,
            },
            headers=_headers(),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["page_size"] == 1
        assert data["pagination"]["total"] == 1
        assert data["pagination"]["total_pages"] == 1

        item = data["items"][0]
        assert item["name"].startswith(marker)
        assert item["platform"] == "douyin"
        assert item["computed_status"] == "onboarded"
        assert item["follower_count"] == 12345
        assert item["video_count"] == 67
        assert "tikhub_raw" not in item


class TestExternalKolsDetail:
    async def test_detail_includes_raw_by_default(self, test_client, test_session):
        kol_id, raw = await _create_kol(
            test_session,
            name_prefix="外部详情达人",
            persona="有人格",
            content_plan=None,
        )

        resp = await test_client.get(f"/api/external/kols/{kol_id}", headers=_headers())

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["id"] == kol_id
        assert data["computed_status"] == "persona_done"
        assert data["tikhub_raw"] == raw

    async def test_detail_can_omit_raw(self, test_client, test_session):
        kol_id, _ = await _create_kol(
            test_session,
            name_prefix="外部详情不含raw达人",
            persona=None,
            content_plan="有内容规划",
        )

        resp = await test_client.get(
            f"/api/external/kols/{kol_id}",
            params={"include_raw": False},
            headers=_headers(),
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["computed_status"] == "content_done"
        assert "tikhub_raw" not in data

    async def test_detail_not_found_returns_standard_envelope(self, test_client):
        resp = await test_client.get("/api/external/kols/999999999", headers=_headers())

        assert resp.status_code == 404
        body = resp.json()
        assert body["success"] is False
        assert body["code"] == "RESOURCE_NOT_FOUND"
