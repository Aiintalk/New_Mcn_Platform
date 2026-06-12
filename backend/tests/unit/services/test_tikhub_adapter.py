"""
Unit tests for tikhub adapter (app/adapters/tikhub.py).

覆盖：
- resolve_sec_user_id：抖音号解析、链接解析、短链解析、错误处理
- fetch_user_videos：分页逻辑、空数据、异常处理
- get_top10 / get_recent30days / format_videos：纯函数逻辑
- get_top10_videos / get_recent_30day_videos / format_videos_text：纯函数逻辑
"""
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.tikhub import (
    get_top10,
    get_recent30days,
    format_videos,
    get_top10_videos,
    get_recent_30day_videos,
    format_videos_text,
)


# ── 纯函数测试：get_top10 ────────────────────────────────────────


def test_get_top10_returns_top_10_by_likes():
    """按点赞数降序取前 10。"""
    videos = [{"desc": f"v{i}", "digg_count": i * 100, "create_time": 1000} for i in range(20)]
    result = get_top10(videos)
    assert len(result) == 10
    assert result[0]["digg_count"] == 1900
    assert result[9]["digg_count"] == 1000


def test_get_top10_fewer_than_10():
    """不足 10 条时返回全部。"""
    videos = [{"desc": f"v{i}", "digg_count": i, "create_time": 1000} for i in range(5)]
    result = get_top10(videos)
    assert len(result) == 5


def test_get_top10_empty_list():
    """空列表返回空。"""
    assert get_top10([]) == []


def test_get_top10_missing_digg_count():
    """缺少 digg_count 字段时默认为 0，排序在后。"""
    videos = [{"desc": "v1"}, {"desc": "v2", "digg_count": 100}]
    result = get_top10(videos)
    # 有 digg_count=100 的排在前面
    assert result[0]["desc"] == "v2"
    assert result[1]["desc"] == "v1"


# ── 纯函数测试：get_recent30days ──────────────────────────────────


def test_get_recent30days_filters_recent():
    """只返回最近 30 天的视频。"""
    now = time.time()
    videos = [
        {"desc": "recent1", "create_time": int(now - 86400)},       # 1 天前
        {"desc": "recent2", "create_time": int(now - 86400 * 15)},  # 15 天前
        {"desc": "old1", "create_time": int(now - 86400 * 45)},     # 45 天前
    ]
    result = get_recent30days(videos)
    assert len(result) == 2
    assert all(v["desc"].startswith("recent") for v in result)


def test_get_recent30days_all_old():
    """全部超过 30 天，返回空。"""
    now = time.time()
    videos = [{"desc": "old", "create_time": int(now - 86400 * 60)}]
    assert get_recent30days(videos) == []


def test_get_recent30days_empty_list():
    """空列表返回空。"""
    assert get_recent30days([]) == []


def test_get_recent30days_sorted_by_time_desc():
    """结果按时间降序排列。"""
    now = time.time()
    videos = [
        {"desc": "newest", "create_time": int(now - 3600)},
        {"desc": "oldest", "create_time": int(now - 86400 * 20)},
        {"desc": "middle", "create_time": int(now - 86400 * 10)},
    ]
    result = get_recent30days(videos)
    assert result[0]["desc"] == "newest"
    assert result[-1]["desc"] == "oldest"


# ── 纯函数测试：format_videos ────────────────────────────────────


def test_format_videos_normal():
    """正常格式化视频列表。"""
    now = int(time.time())
    videos = [
        {"desc": "测试视频描述", "digg_count": 32000, "create_time": now},
    ]
    result = format_videos(videos, "TOP10")
    # format_videos 不在输出中包含 label，只格式化视频条目
    assert "3.2万" in result
    assert "测试视频描述" in result
    assert "第1条" in result


def test_format_videos_empty():
    """空列表返回提示文本。"""
    result = format_videos([], "TOP10")
    assert "无数据" in result


def test_format_videos_likes_format():
    """点赞数 >= 10000 显示为 X.X 万。"""
    now = int(time.time())
    videos = [
        {"desc": "v1", "digg_count": 15600, "create_time": now},
        {"desc": "v2", "digg_count": 999, "create_time": now},
    ]
    result = format_videos(videos, "测试")
    assert "1.6万" in result
    assert "999" in result


# ── 纯函数测试：get_top10_videos / get_recent_30day_videos ──────


def test_get_top10_videos_by_digg_count():
    videos = [{"desc": f"v{i}", "digg_count": (20 - i) * 100, "create_time": 1000} for i in range(20)]
    result = get_top10_videos(videos)
    assert len(result) == 10
    assert result[0]["digg_count"] == 2000


def test_get_recent_30day_videos():
    now_ts = int(datetime.now(timezone.utc).timestamp())
    videos = [
        {"desc": "recent", "create_time": now_ts - 3600, "digg_count": 10},
        {"desc": "old", "create_time": now_ts - 86400 * 60, "digg_count": 10},
    ]
    result = get_recent_30day_videos(videos)
    assert len(result) == 1
    assert result[0]["desc"] == "recent"


def test_format_videos_text_normal():
    now_ts = int(datetime.now(timezone.utc).timestamp())
    videos = [{"desc": "测试描述", "digg_count": 500, "create_time": now_ts}]
    result = format_videos_text(videos, "TOP10")
    assert "TOP10" in result
    assert "测试描述" in result
    assert "500" in result


def test_format_videos_text_empty():
    result = format_videos_text([], "TOP10")
    assert result == ""


# ── 异步函数测试：resolve_sec_user_id ────────────────────────────


@pytest.mark.asyncio
@patch("app.adapters.tikhub._get_key_and_url")
@patch("app.adapters.tikhub.report_success", new_callable=AsyncMock)
@patch("app.adapters.tikhub.report_failure", new_callable=AsyncMock)
@patch("app.adapters.tikhub.get_user_profile", new_callable=AsyncMock)
async def test_resolve_sec_user_id_with_douyin_id(mock_profile, mock_failure, mock_success, mock_get_key):
    """纯抖音号解析：输入直接作为 sec_uid，通过 get_user_profile 获取 nickname。"""
    mock_get_key.return_value = (1, "test_key", "https://api.tikhub.io")
    mock_profile.return_value = {"nickname": "测试达人"}
    mock_db = AsyncMock()

    from app.adapters.tikhub import resolve_sec_user_id
    result = await resolve_sec_user_id("testuser123", mock_db)

    assert result["sec_user_id"] == "testuser123"
    assert result["nickname"] == "测试达人"


@pytest.mark.asyncio
@patch("app.adapters.tikhub._get_key_and_url")
@patch("app.adapters.tikhub.report_success", new_callable=AsyncMock)
@patch("app.adapters.tikhub.report_failure", new_callable=AsyncMock)
async def test_resolve_sec_user_id_with_url(mock_failure, mock_success, mock_get_key):
    """链接解析：先通过 get_sec_user_id 获取 sec_uid，再查 profile。"""
    mock_get_key.return_value = (1, "test_key", "https://api.tikhub.io")
    mock_db = AsyncMock()

    with patch("httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = client_instance

        # get_sec_user_id 返回
        sec_resp = MagicMock()
        sec_resp.status_code = 200
        sec_resp.raise_for_status = MagicMock()
        sec_resp.json.return_value = {"data": "SEC_UID_FROM_URL"}

        # get_user_profile 返回
        profile_resp = MagicMock()
        profile_resp.status_code = 200
        profile_resp.raise_for_status = MagicMock()
        profile_resp.json.return_value = {
            "data": {"user": {"nickname": "链接达人", "uid": "12345"}}
        }

        client_instance.get.side_effect = [sec_resp, profile_resp]

        from app.adapters.tikhub import resolve_sec_user_id
        result = await resolve_sec_user_id("https://www.douyin.com/user/SEC_UID_FROM_URL", mock_db)

    assert result["sec_user_id"] == "SEC_UID_FROM_URL"
    assert result["nickname"] == "链接达人"


@pytest.mark.asyncio
@patch("app.adapters.tikhub._get_key_and_url")
@patch("app.adapters.tikhub.report_failure", new_callable=AsyncMock)
async def test_resolve_sec_user_id_api_error(mock_failure, mock_get_key):
    """API 调用失败应抛出 RuntimeError。"""
    mock_get_key.return_value = (1, "test_key", "https://api.tikhub.io")
    mock_db = AsyncMock()

    with patch("httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = client_instance
        client_instance.get.side_effect = Exception("网络超时")

        from app.adapters.tikhub import resolve_sec_user_id
        with pytest.raises(RuntimeError, match="resolve_sec_user_id failed"):
            await resolve_sec_user_id("testuser", mock_db)

    # report_failure called at least once (inner get_user_profile + outer wrapper)
    assert mock_failure.call_count >= 1


# ── 异步函数测试：fetch_user_videos ──────────────────────────────


@pytest.mark.asyncio
@patch("app.adapters.tikhub._get_key_and_url")
@patch("app.adapters.tikhub.report_success", new_callable=AsyncMock)
@patch("app.adapters.tikhub.report_failure", new_callable=AsyncMock)
async def test_fetch_user_videos_single_page(mock_failure, mock_success, mock_get_key):
    """单页返回。"""
    mock_get_key.return_value = (1, "test_key", "https://api.tikhub.io")
    mock_db = AsyncMock()

    with patch("httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = client_instance

        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "data": {
                "aweme_list": [
                    {"desc": "视频1", "statistics": {"digg_count": 100}, "create_time": 1000, "aweme_id": "v1"},
                    {"desc": "视频2", "statistics": {"digg_count": 200}, "create_time": 2000, "aweme_id": "v2"},
                ],
                "has_more": False,
                "cursor": 0,
            }
        }
        client_instance.get.return_value = resp

        from app.adapters.tikhub import fetch_user_videos
        result = await fetch_user_videos("SEC123", mock_db)

    assert len(result) == 2
    assert result[0]["desc"] == "视频1"
    assert result[0]["digg_count"] == 100


@pytest.mark.asyncio
@patch("app.adapters.tikhub._get_key_and_url")
@patch("app.adapters.tikhub.report_success", new_callable=AsyncMock)
@patch("app.adapters.tikhub.report_failure", new_callable=AsyncMock)
async def test_fetch_user_videos_pagination(mock_failure, mock_success, mock_get_key):
    """多页翻页。"""
    mock_get_key.return_value = (1, "test_key", "https://api.tikhub.io")
    mock_db = AsyncMock()

    with patch("httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = client_instance

        page1_resp = MagicMock()
        page1_resp.status_code = 200
        page1_resp.raise_for_status = MagicMock()
        page1_resp.json.return_value = {
            "data": {
                "aweme_list": [{"desc": "p1", "statistics": {"digg_count": 1}, "create_time": 1000, "aweme_id": "a1"}],
                "has_more": True,
                "cursor": 100,
            }
        }

        page2_resp = MagicMock()
        page2_resp.status_code = 200
        page2_resp.raise_for_status = MagicMock()
        page2_resp.json.return_value = {
            "data": {
                "aweme_list": [{"desc": "p2", "statistics": {"digg_count": 2}, "create_time": 2000, "aweme_id": "a2"}],
                "has_more": False,
                "cursor": 200,
            }
        }

        client_instance.get.side_effect = [page1_resp, page2_resp]

        from app.adapters.tikhub import fetch_user_videos
        result = await fetch_user_videos("SEC123", mock_db, max_pages=5)

    assert len(result) == 2
    assert result[0]["desc"] == "p1"
    assert result[1]["desc"] == "p2"


@pytest.mark.asyncio
@patch("app.adapters.tikhub._get_key_and_url")
@patch("app.adapters.tikhub.report_success", new_callable=AsyncMock)
@patch("app.adapters.tikhub.report_failure", new_callable=AsyncMock)
async def test_fetch_user_videos_empty(mock_failure, mock_success, mock_get_key):
    """无视频返回空列表。"""
    mock_get_key.return_value = (1, "test_key", "https://api.tikhub.io")
    mock_db = AsyncMock()

    with patch("httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = client_instance

        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"data": {"aweme_list": [], "has_more": False, "cursor": 0}}
        client_instance.get.return_value = resp

        from app.adapters.tikhub import fetch_user_videos
        result = await fetch_user_videos("SEC123", mock_db)

    assert result == []


@pytest.mark.asyncio
@patch("app.adapters.tikhub._get_key_and_url")
@patch("app.adapters.tikhub.report_failure", new_callable=AsyncMock)
async def test_fetch_user_videos_api_error(mock_failure, mock_get_key):
    """API 异常应抛出 RuntimeError。"""
    mock_get_key.return_value = (1, "test_key", "https://api.tikhub.io")
    mock_db = AsyncMock()

    with patch("httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = client_instance
        client_instance.get.side_effect = Exception("连接超时")

        from app.adapters.tikhub import fetch_user_videos
        with pytest.raises(RuntimeError, match="fetch_user_videos failed"):
            await fetch_user_videos("SEC123", mock_db)

    mock_failure.assert_called_once()
