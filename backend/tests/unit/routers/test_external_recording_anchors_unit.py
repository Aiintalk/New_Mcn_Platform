"""Unit tests for external_recording_anchors helper mapping."""
from datetime import datetime, timezone
from types import SimpleNamespace

from app.routers import external_recording_anchors


def _now():
    return datetime(2026, 8, 7, 10, 0, tzinfo=timezone.utc)


def _kol(**overrides):
    base = {
        "id": 1,
        "name": "测试红人",
        "account_name": "红人昵称",
        "platform": "douyin",
        "douyin_id": "douyin_001",
        "sec_uid": "MS4wLjABAAAA_kol",
        "avatar_url": "https://example.com/kol.png",
        "signature": "简介",
        "follower_count": 1000,
        "video_count": 12,
        "style_notes": "备注",
        "created_at": _now(),
        "updated_at": _now(),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _benchmark(**overrides):
    base = {
        "id": 9,
        "account_name": "直播对标昵称",
        "account_input": "live_douyin_id",
        "sec_uid": "MS4wLjABAAAA_live",
        "avatar_url": "https://example.com/live.png",
        "follower_count": 8888,
        "description": "直播对标说明",
        "created_at": _now(),
        "updated_at": _now(),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_kol_anchor_marks_source_as_kol_and_ready():
    data = external_recording_anchors._kol_anchor_to_dict(_kol())

    assert data["source_key"] == "kol:1"
    assert data["source_type"] == "kol"
    assert data["source_label"] == "红人主播"
    assert data["douyin_id"] == "douyin_001"
    assert data["sec_user_id"] == "MS4wLjABAAAA_kol"
    assert data["sec_uid"] == "MS4wLjABAAAA_kol"
    assert data["sync_ready"] is True
    assert data["sync_block_reason"] is None


def test_benchmark_anchor_marks_source_as_live_benchmark_and_ready():
    data = external_recording_anchors._benchmark_anchor_to_dict(
        _benchmark(),
        _kol(id=3, name="父达人"),
    )

    assert data["source_key"] == "live_benchmark:9"
    assert data["source_type"] == "live_benchmark"
    assert data["source_label"] == "直播对标主播"
    assert data["parent_kol_id"] == 3
    assert data["parent_kol_name"] == "父达人"
    assert data["douyin_id"] == "live_douyin_id"
    assert data["sec_user_id"] == "MS4wLjABAAAA_live"
    assert data["follower_count"] == 8888
    assert data["sync_ready"] is True


def test_benchmark_anchor_does_not_treat_url_or_sec_uid_as_douyin_id():
    for account_input in (
        "https://www.douyin.com/user/MS4wLjABAAAA_live",
        "MS4wLjABAAAA_live",
    ):
        data = external_recording_anchors._benchmark_anchor_to_dict(
            _benchmark(account_input=account_input),
            _kol(),
        )
        assert data["douyin_id"] is None
        assert data["sync_ready"] is True


def test_benchmark_anchor_blocks_old_record_without_identifier():
    data = external_recording_anchors._benchmark_anchor_to_dict(
        _benchmark(account_input=None, sec_uid=None),
        _kol(),
    )

    assert data["account_input"] == "直播对标昵称"
    assert data["douyin_id"] is None
    assert data["sec_user_id"] is None
    assert data["sync_ready"] is False
    assert "缺少抖音账号 ID" in data["sync_block_reason"]
