"""Unit tests for external_kols router helpers and endpoint functions."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.routers import external_kols


pytestmark = pytest.mark.asyncio


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _RowsResult:
    def __init__(self, rows=None, one=None):
        self._rows = rows or []
        self._one = one

    def scalars(self):
        return _Scalars(self._rows)

    def scalar_one_or_none(self):
        return self._one


class _FakeDb:
    def __init__(self, *results):
        self._results = list(results)
        self.executed = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        return self._results.pop(0)


def _kol(**overrides):
    now = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
    base = {
        "id": 1,
        "name": "测试红人",
        "account_name": "测试账号",
        "category": "美妆",
        "platform": "douyin",
        "external_id": "ext-1",
        "douyin_id": "douyin-1",
        "sec_uid": "sec-1",
        "avatar_url": "https://example.com/a.png",
        "signature": "简介",
        "follower_count": 100,
        "video_count": 5,
        "owner": "运营A",
        "owner_id": 2,
        "persona": "人格",
        "content_plan": "规划",
        "style_notes": "风格",
        "status": "signed",
        "created_by": 3,
        "background": "背景",
        "experience": "经历",
        "relationships": "关系",
        "unique_story": "故事",
        "extra_notes": "补充",
        "tikhub_raw": {"raw": True},
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


async def test_require_external_api_key_accepts_matching_key(monkeypatch):
    monkeypatch.setattr(settings, "external_kols_api_key", "unit-key")
    assert await external_kols.require_external_kols_api_key("unit-key") is None


async def test_require_external_api_key_rejects_invalid_key(monkeypatch):
    monkeypatch.setattr(settings, "external_kols_api_key", "unit-key")
    with pytest.raises(HTTPException) as exc:
        await external_kols.require_external_kols_api_key("bad-key")
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "EXTERNAL_API_KEY_INVALID"


async def test_require_external_api_key_rejects_unconfigured_key(monkeypatch):
    monkeypatch.setattr(settings, "external_kols_api_key", "")
    with pytest.raises(HTTPException) as exc:
        await external_kols.require_external_kols_api_key("unit-key")
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "EXTERNAL_API_KEY_NOT_CONFIGURED"


@pytest.mark.parametrize(
    ("persona", "content_plan", "expected"),
    [
        ("人设", "规划", "onboarded"),
        ("人设", "  ", "persona_done"),
        ("", "规划", "content_done"),
        (None, None, "pending_onboarding"),
    ],
)
async def test_compute_status(persona, content_plan, expected):
    assert external_kols._compute_status(persona, content_plan) == expected


async def test_kol_to_dict_omits_raw_by_default():
    data = external_kols._kol_to_dict(_kol())
    assert data["computed_status"] == "onboarded"
    assert data["created_at"] == "2026-08-05T12:00:00+00:00"
    assert "tikhub_raw" not in data


async def test_kol_to_dict_includes_raw_when_requested():
    data = external_kols._kol_to_dict(_kol(persona=None, content_plan="规划"), include_raw=True)
    assert data["computed_status"] == "content_done"
    assert data["tikhub_raw"] == {"raw": True}


async def test_status_filter_returns_none_for_unknown_status():
    assert external_kols._status_filter("unknown") is None


async def test_list_external_kols_empty_result():
    db = _FakeDb(_ScalarResult(0), _RowsResult(rows=[]))

    body = await external_kols.list_external_kols(
        page=1,
        page_size=20,
        keyword="",
        platform="",
        status_value="",
        include_raw=False,
        _=None,
        db=db,
    )

    assert body.success is True
    assert body.data["items"] == []
    assert body.data["pagination"] == {
        "page": 1,
        "page_size": 20,
        "total": 0,
        "total_pages": 0,
    }


async def test_list_external_kols_applies_filters_and_raw():
    db = _FakeDb(_ScalarResult(1), _RowsResult(rows=[_kol()]))

    body = await external_kols.list_external_kols(
        page=2,
        page_size=10,
        keyword="测试",
        platform="douyin",
        status_value="onboarded",
        include_raw=True,
        _=None,
        db=db,
    )

    assert body.success is True
    assert body.data["pagination"]["total_pages"] == 1
    assert body.data["items"][0]["tikhub_raw"] == {"raw": True}
    assert len(db.executed) == 2


async def test_get_external_kol_success_without_raw():
    db = _FakeDb(_RowsResult(one=_kol()))

    body = await external_kols.get_external_kol(1, include_raw=False, _=None, db=db)

    assert body.success is True
    assert body.data["id"] == 1
    assert "tikhub_raw" not in body.data


async def test_get_external_kol_not_found():
    db = _FakeDb(_RowsResult(one=None))

    with pytest.raises(HTTPException) as exc:
        await external_kols.get_external_kol(999, include_raw=True, _=None, db=db)

    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "RESOURCE_NOT_FOUND"
