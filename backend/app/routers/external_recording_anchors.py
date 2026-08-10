"""
外部录屏主播同步接口。

给远程录屏/分析项目读取本平台需要进入录屏系统的主播：
- kols：红人主播
- kol_benchmarks(account_type='livestream')：直播对标主播

内容对标账号不会出现在这个接口里。
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import ErrorCode, success_response
from app.models.kol import Kol
from app.models.kol_benchmark import KolBenchmark
from app.routers.external_kols import require_external_kols_api_key

router = APIRouter(prefix="/external/recording-anchors", tags=["external-recording-anchors"])

_SOURCE_TYPES = {"", "kol", "live_benchmark"}


def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _douyin_id_from_input(value: str | None) -> str | None:
    raw = _clean(value)
    if not raw:
        return None
    lowered = raw.lower()
    if raw.startswith("MS4") or "douyin.com" in lowered or lowered.startswith("http"):
        return None
    return raw


def _sync_block_reason(*identifiers: str | None) -> str | None:
    if any(_clean(identifier) for identifier in identifiers):
        return None
    return "缺少抖音账号 ID 或 sec_user_id，暂不能同步到远程录屏系统"


def _kol_anchor_to_dict(kol: Kol) -> dict:
    douyin_id = _clean(kol.douyin_id)
    sec_user_id = _clean(kol.sec_uid)
    block_reason = _sync_block_reason(douyin_id, sec_user_id)
    return {
        "source_key": f"kol:{kol.id}",
        "source_type": "kol",
        "source_label": "红人主播",
        "source_table": "kols",
        "source_id": kol.id,
        "parent_kol_id": kol.id,
        "parent_kol_name": kol.name,
        "should_record": True,
        "platform": kol.platform or "douyin",
        "account_input": douyin_id or sec_user_id,
        "douyin_id": douyin_id,
        "sec_user_id": sec_user_id,
        "sec_uid": sec_user_id,
        "nickname": kol.account_name or kol.name,
        "name": kol.name,
        "avatar_url": kol.avatar_url,
        "signature": kol.signature,
        "follower_count": kol.follower_count,
        "video_count": kol.video_count,
        "description": kol.style_notes,
        "sync_ready": block_reason is None,
        "sync_block_reason": block_reason,
        "created_at": _ts(kol.created_at),
        "updated_at": _ts(kol.updated_at),
    }


def _benchmark_anchor_to_dict(benchmark: KolBenchmark, parent_kol: Kol) -> dict:
    account_input = _clean(benchmark.account_input)
    douyin_id = _douyin_id_from_input(account_input)
    sec_user_id = _clean(benchmark.sec_uid)
    block_reason = _sync_block_reason(douyin_id, sec_user_id)
    return {
        "source_key": f"live_benchmark:{benchmark.id}",
        "source_type": "live_benchmark",
        "source_label": "直播对标主播",
        "source_table": "kol_benchmarks",
        "source_id": benchmark.id,
        "parent_kol_id": parent_kol.id,
        "parent_kol_name": parent_kol.name,
        "should_record": True,
        "platform": "douyin",
        "account_input": account_input or benchmark.account_name,
        "douyin_id": douyin_id,
        "sec_user_id": sec_user_id,
        "sec_uid": sec_user_id,
        "nickname": benchmark.account_name,
        "name": benchmark.account_name,
        "avatar_url": benchmark.avatar_url,
        "signature": None,
        "follower_count": benchmark.follower_count,
        "video_count": None,
        "description": benchmark.description,
        "sync_ready": block_reason is None,
        "sync_block_reason": block_reason,
        "created_at": _ts(benchmark.created_at),
        "updated_at": _ts(benchmark.updated_at),
    }


@router.get("", response_model=None)
async def list_recording_anchors(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    keyword: str = "",
    platform: str = "",
    source_type: str = "",
    ready_only: bool = False,
    _: None = Depends(require_external_kols_api_key),
    db: AsyncSession = Depends(get_db),
):
    source_type = source_type.strip()
    if source_type not in _SOURCE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": ErrorCode.VALIDATION_ERROR,
                "message": "source_type 只能为空、kol 或 live_benchmark",
            },
        )

    items: list[dict] = []
    keyword = keyword.strip()
    platform = platform.strip()

    if source_type in ("", "kol"):
        stmt = select(Kol).where(Kol.deleted_at.is_(None))
        if keyword:
            pattern = f"%{keyword}%"
            stmt = stmt.where(
                or_(
                    Kol.name.ilike(pattern),
                    Kol.account_name.ilike(pattern),
                    Kol.douyin_id.ilike(pattern),
                    Kol.sec_uid.ilike(pattern),
                )
            )
        if platform:
            stmt = stmt.where(Kol.platform == platform)
        rows = (await db.execute(stmt)).scalars().all()
        items.extend(_kol_anchor_to_dict(kol) for kol in rows)

    if source_type in ("", "live_benchmark") and platform in ("", "douyin"):
        stmt = (
            select(KolBenchmark, Kol)
            .join(Kol, Kol.id == KolBenchmark.kol_id)
            .where(
                KolBenchmark.account_type == "livestream",
                Kol.deleted_at.is_(None),
            )
        )
        if keyword:
            pattern = f"%{keyword}%"
            stmt = stmt.where(
                or_(
                    KolBenchmark.account_name.ilike(pattern),
                    KolBenchmark.account_input.ilike(pattern),
                    KolBenchmark.sec_uid.ilike(pattern),
                    Kol.name.ilike(pattern),
                )
            )
        rows = (await db.execute(stmt)).all()
        items.extend(
            _benchmark_anchor_to_dict(benchmark, parent_kol)
            for benchmark, parent_kol in rows
        )

    if ready_only:
        items = [item for item in items if item["sync_ready"]]

    items.sort(
        key=lambda item: item["updated_at"] or item["created_at"] or "",
        reverse=True,
    )
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size

    return success_response(data={
        "items": items[start:end],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    })
