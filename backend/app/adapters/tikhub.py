"""
app/adapters/tikhub.py

TikHub 服务适配器：
- 使用 Key 池选取 Credential（provider="tikhub"）
- 实现 3 个真实 Douyin API 接口
- 原始响应完整存入 kols.tikhub_raw JSONB 后再提取结构化字段
"""
import time

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
