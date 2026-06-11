"""
app/adapters/tikhub.py

TikHub 服务适配器：
- 使用 Key 池选取 Credential（provider="tikhub"）
- 实现多个 Douyin API 接口（用户资料、粉丝、视频列表等）
- 原始响应完整存入 kols.tikhub_raw JSONB 后再提取结构化字段
"""
import re
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.credential_selector import pick_credential, report_failure, report_success


async def _get_key_and_url(db: AsyncSession) -> tuple[int, str, str]:
    """返回 (credential_id, api_key, base_url)"""
    credential = await pick_credential(provider="tikhub", db=db)
    config = credential.config or {}
    base_url = config.get("base_url", "https://api.tikhub.io")
    api_key = credential.secret_enc  # Sprint 3: secret_enc 存储明文 API Key
    return credential.id, api_key, base_url


async def get_user_profile(sec_user_id: str, db: AsyncSession) -> dict:
    """
    获取抖音用户基础信息。

    GET /api/v1/douyin/app/v3/handler_user_profile
    参数: sec_user_id
    返回: nickname / uid / room_id / unique_id + 完整原始响应
    """
    cred_id, api_key, base_url = await _get_key_and_url(db)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{base_url}/api/v1/douyin/app/v3/handler_user_profile",
                params={"sec_user_id": sec_user_id},
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
            raw = response.json()
            await report_success(cred_id, db)

            user_data = (raw.get("data") or {}).get("user") or {}
            # 优先级：avatar_thumb > avatar_medium > avatar_larger
            # url_list 末尾条目是 .jpeg，路径部分判断（忽略 query string）
            def _pick_jpeg(key: str) -> str | None:
                urls = (user_data.get(key) or {}).get("url_list") or []
                for u in urls:
                    path = u.split("?")[0]
                    if path.endswith(".jpeg"):
                        return u
                return urls[0] if urls else None

            avatar_url = _pick_jpeg("avatar_thumb") or _pick_jpeg("avatar_medium") or _pick_jpeg("avatar_larger")
            return {
                "raw": raw,
                "nickname": user_data.get("nickname"),
                "uid": str(user_data.get("uid", "")),
                "unique_id": user_data.get("unique_id"),
                "avatar_url": avatar_url,
                "follower_count": user_data.get("follower_count"),
                "video_count": user_data.get("aweme_count"),
                "signature": user_data.get("signature"),
            }
    except Exception as e:
        await report_failure(cred_id, db)
        raise RuntimeError(f"TikHub get_user_profile failed: {e}") from e


async def get_user_fans_info(user_id: int, db: AsyncSession) -> dict:
    """
    获取抖音达人粉丝数据。

    POST /api/v1/douyin/index/fetch_daren_great_user_fans_info
    参数: user_id（数字型 uid）
    返回: 粉丝数相关数据 + 完整原始响应
    """
    cred_id, api_key, base_url = await _get_key_and_url(db)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{base_url}/api/v1/douyin/index/fetch_daren_great_user_fans_info",
                params={"user_id": str(user_id)},
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
            raw = response.json()
            await report_success(cred_id, db)

            fans_data = raw.get("data") or {}
            return {
                "raw": raw,
                "fans_count": fans_data.get("fans_count"),
                "gender_ratio": (
                    fans_data.get("gender_distribution") or fans_data.get("gender")
                ),
                "age_ratio": (
                    fans_data.get("age_distribution") or fans_data.get("age")
                ),
                "region_distribution": (
                    fans_data.get("region_distribution") or fans_data.get("city")
                ),
            }
    except Exception as e:
        await report_failure(cred_id, db)
        raise RuntimeError(f"TikHub get_user_fans_info failed: {e}") from e


async def get_live_room_products(
    room_id: str,
    author_id: str,
    db: AsyncSession,
    limit: int = 100,
) -> dict:
    """
    获取直播间商品列表。

    GET /api/v1/douyin/web/fetch_live_room_product_result
    参数: room_id / author_id / limit
    返回: data.promotions 列表 + 完整原始响应
    """
    cred_id, api_key, base_url = await _get_key_and_url(db)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{base_url}/api/v1/douyin/web/fetch_live_room_product_result",
                params={"room_id": room_id, "author_id": author_id, "limit": limit},
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
            raw = response.json()
            await report_success(cred_id, db)

            promotions = raw.get("data", {}).get("promotions", [])
            return {"raw": raw, "promotions": promotions}
    except Exception as e:
        await report_failure(cred_id, db)
        raise RuntimeError(f"TikHub get_live_room_products failed: {e}") from e


async def test_connection(db: AsyncSession) -> dict:
    """
    测试 TikHub 连通性（用已知测试 sec_user_id 验证）。

    Returns:
        {"status": "ok/error", "latency_ms": 123}
    """
    # 抖音官方账号的 sec_user_id
    TEST_SEC_USER_ID = "MS4wLjABAAAA5ZrIrbgva3dqI80CsHQMCUPAR5Q5KFBOMOrMnVKESnzNPk7sLBRKCTMSzfQkUzSZ"
    start = time.monotonic()
    try:
        result = await get_user_profile(TEST_SEC_USER_ID, db)
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "ok",
            "latency_ms": latency_ms,
            "sample_nickname": result.get("nickname"),
        }
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "error",
            "latency_ms": latency_ms,
            "error": str(e),
        }


# ── 人格定位功能新增方法 ──────────────────────────────────────────


def _extract_douyin_url(text: str) -> str | None:
    """从用户输入中提取抖音链接（可能是分享文本混合了中文和链接）。"""
    match = re.search(r'(https?://[^\s<>"\']+/?)', text)
    return match.group(1) if match else None


async def _resolve_short_url(url: str) -> str:
    """Follow redirect 将 v.douyin.com 短链接解析为完整 douyin.com URL。"""
    if "v.douyin.com" not in url:
        return url
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        return str(resp.url)


async def resolve_sec_user_id(input_str: str, db: AsyncSession) -> dict:
    """
    解析用户输入的抖音号或分享链接，返回 sec_user_id 和 nickname。

    支持的输入格式：
    - 抖音号（纯字母数字，如 xiao_hong_123）
    - 主页链接（https://www.douyin.com/user/MS4wLj...）
    - 分享短链接（https://v.douyin.com/xxx/）
    - 分享文本（"长按复制此条消息... https://v.douyin.com/xxx/"）

    Returns: {"sec_user_id": str, "nickname": str}
    """
    cred_id, api_key, base_url = await _get_key_and_url(db)
    try:
        url_match = _extract_douyin_url(input_str)

        if url_match:
            # 链接：先解析短链接，再用 get_sec_user_id 端点提取
            full_url = await _resolve_short_url(url_match)
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{base_url}/api/v1/douyin/web/get_sec_user_id",
                    params={"url": full_url},
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                response.raise_for_status()
                data = response.json()
                await report_success(cred_id, db)
            # TikHub get_sec_user_id 返回 data 为纯字符串（sec_user_id）
            sec_uid = data.get("data")
            if not sec_uid or not isinstance(sec_uid, str):
                raise RuntimeError("无法从链接中解析 sec_user_id")
        else:
            # 纯抖音号：用 unique_id 查询用户资料
            sec_uid = input_str.strip()

        # 复用已有的 get_user_profile 获取 nickname（使用 app/v3 端点，支持 sec_user_id）
        profile = await get_user_profile(sec_uid, db)

        return {
            "sec_user_id": sec_uid,
            "nickname": profile.get("nickname") or "",
        }
    except Exception as e:
        await report_failure(cred_id, db)
        raise RuntimeError(f"TikHub resolve_sec_user_id failed: {e}") from e


async def fetch_user_videos(
    sec_user_id: str,
    db: AsyncSession,
    max_pages: int = 10,
) -> list[dict]:
    """
    分页获取用户发布的视频列表。

    Args:
        sec_user_id: 抖音 sec_user_id
        db: 数据库会话
        max_pages: 最大翻页数（每页约20条，默认最多200条视频）

    Returns:
        [{"desc": str, "digg_count": int, "create_time": int, "aweme_id": str}, ...]
    """
    cred_id, api_key, base_url = await _get_key_and_url(db)
    all_videos: list[dict] = []
    cursor = 0

    try:
        for _ in range(max_pages):
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{base_url}/api/v1/douyin/web/fetch_user_post_videos",
                    params={
                        "sec_user_id": sec_user_id,
                        "count": 20,
                        "cursor": cursor,
                    },
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                response.raise_for_status()
                raw = response.json()

            await report_success(cred_id, db)

            data = raw.get("data") or {}
            aweme_list = data.get("aweme_list") or []
            if not aweme_list:
                break

            for item in aweme_list:
                all_videos.append({
                    "desc": item.get("desc", ""),
                    "digg_count": (item.get("statistics") or {}).get("digg_count", 0),
                    "create_time": item.get("create_time", 0),
                    "aweme_id": item.get("aweme_id", ""),
                })

            cursor = data.get("cursor", 0)
            has_more = data.get("has_more")
            if not has_more:
                break

        return all_videos
    except Exception as e:
        await report_failure(cred_id, db)
        raise RuntimeError(f"TikHub fetch_user_videos failed: {e}") from e


def get_top10_videos(videos: list[dict]) -> list[dict]:
    """按点赞数降序取前10个视频。"""
    sorted_videos = sorted(videos, key=lambda v: v["digg_count"], reverse=True)
    return sorted_videos[:10]


def get_recent_30day_videos(videos: list[dict]) -> list[dict]:
    """筛选最近30天的视频。"""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30)
    cutoff_ts = int(cutoff.timestamp())
    return [v for v in videos if v["create_time"] >= cutoff_ts]


def format_videos_text(videos: list[dict], label: str) -> str:
    """
    将视频列表格式化为文本（与旧架构 formatVideos 一致）。

    格式: 第N条 | 日期 | 点赞数 | 描述
    """
    if not videos:
        return ""
    lines = [f"--- {label} ---"]
    for i, v in enumerate(videos, 1):
        dt = datetime.fromtimestamp(v["create_time"], tz=timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")
        count = v["digg_count"]
        desc = v["desc"][:80] if v["desc"] else ""
        lines.append(f"第{i}条 | {date_str} | 点赞 {count} | {desc}")
    return "\n".join(lines)
