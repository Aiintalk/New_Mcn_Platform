"""
app/services/kol_tikhub.py

封装单条 KOL 的 TikHub 数据拉取逻辑：
- 优先用 sec_uid，为空时用 douyin_id
- 第一步：get_user_profile → 获取基础信息 + uid
- 第二步：get_user_fans_info(uid) → 获取粉丝画像（失败不阻断第一步结果）
- 合并两份原始响应存入 kols.tikhub_raw: {"profile": ..., "fans_info": ...}
- 成功：更新 kol 字段 + tikhub_raw，写 external_service_logs(success)
- 失败：写 external_service_logs(error)，不抛异常
- 返回 {"status": "ok"/"skip"/"error", ...}

供 admin_kols 路由和定时调度器复用。
"""
import time
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import tikhub as tikhub_adapter
from app.models.kol import Kol
from app.models.log import ExternalServiceLog


async def fetch_tikhub_for_kol(kol: Kol, db: AsyncSession) -> dict:
    """
    拉取单条 KOL 的 TikHub 数据（profile + fans_info）并更新入库。

    Args:
        kol:  已加载的 Kol ORM 对象（只需读取 id / sec_uid / douyin_id）
        db:   AsyncSession

    Returns:
        {
            "status": "ok" | "skip" | "error",
            "duration_ms": int,
            "nickname": str | None,
            "avatar_url": str | None,
            "follower_count": int | None,
            "fans_info_fetched": bool,   # ok 时：fans_info 是否也成功
            "error": str,                # error 时有值
            "reason": str,               # skip 时有值
        }
    """
    identifier = kol.sec_uid or kol.douyin_id
    if not identifier:
        return {"status": "skip", "reason": "no sec_uid or douyin_id"}

    start = time.monotonic()
    try:
        # ── 第一步：获取用户基础信息 ──────────────────────────────────
        profile = await tikhub_adapter.get_user_profile(identifier, db)
        profile_raw = profile["raw"]

        nickname    = profile.get("nickname")
        avatar_url  = profile.get("avatar_url")
        follower_count = profile.get("follower_count")
        video_count = profile.get("video_count")
        signature   = profile.get("signature")
        uid_str     = profile.get("uid", "")

        # sec_uid 回填（用 douyin_id 查询时 TikHub 可能返回 sec_uid）
        raw_user_data = (profile_raw.get("data") or {}).get("user") or {}
        returned_sec_uid = raw_user_data.get("sec_uid")

        # ── 第二步：获取粉丝画像（失败不阻断）────────────────────────
        fans_raw = None
        fans_info_fetched = False
        if uid_str and uid_str.isdigit() and int(uid_str) > 0:
            try:
                fans_result = await tikhub_adapter.get_user_fans_info(int(uid_str), db)
                fans_raw = fans_result["raw"]
                fans_info_fetched = True
            except Exception as fans_err:
                # 粉丝画像获取失败，记录但不影响主流程
                fans_raw = {"error": str(fans_err)[:200]}

        duration_ms = int((time.monotonic() - start) * 1000)

        # ── 合并 tikhub_raw ───────────────────────────────────────────
        combined_raw = {
            "profile": profile_raw,
            "fans_info": fans_raw,
        }

        # ── 构造 kol 更新字段 ─────────────────────────────────────────
        values: dict = {
            "tikhub_raw": combined_raw,
            "updated_at": datetime.now(timezone.utc),
        }
        if nickname:
            values["account_name"] = nickname
        if avatar_url:
            values["avatar_url"] = avatar_url
        if follower_count is not None:
            values["follower_count"] = int(follower_count)
        if video_count is not None:
            values["video_count"] = int(video_count)
        if signature:
            values["signature"] = signature
        if returned_sec_uid and not kol.sec_uid:
            values["sec_uid"] = returned_sec_uid

        await db.execute(update(Kol).where(Kol.id == kol.id).values(**values))

        db.add(ExternalServiceLog(
            service="tikhub",
            action="get_user_profile+fans_info",
            duration_ms=duration_ms,
            status="success",
        ))
        await db.commit()

        return {
            "status": "ok",
            "duration_ms": duration_ms,
            "nickname": nickname,
            "avatar_url": avatar_url,
            "follower_count": follower_count,
            "fans_info_fetched": fans_info_fetched,
        }

    except Exception as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        try:
            db.add(ExternalServiceLog(
                service="tikhub",
                action="get_user_profile+fans_info",
                duration_ms=duration_ms,
                status="error",
                error_message=str(e)[:500],
            ))
            await db.commit()
        except Exception:
            pass
        return {
            "status": "error",
            "duration_ms": duration_ms,
            "error": str(e),
        }
