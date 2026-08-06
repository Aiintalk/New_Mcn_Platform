"""
外部只读 KOL 数据接口。

用于给其它项目读取 kols 表，鉴权方式为请求头 X-API-Key。
"""
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.response import success_response
from app.models.kol import Kol

router = APIRouter(prefix="/external/kols", tags=["external-kols"])


def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


def _compute_status(persona: str | None, content_plan: str | None) -> str:
    has_persona = bool(persona and persona.strip())
    has_content = bool(content_plan and content_plan.strip())
    if has_persona and has_content:
        return "onboarded"
    if has_persona:
        return "persona_done"
    if has_content:
        return "content_done"
    return "pending_onboarding"


async def require_external_kols_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    expected = settings.external_kols_api_key.strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "EXTERNAL_API_KEY_NOT_CONFIGURED",
                "message": "外部 KOL API 密钥未配置",
            },
        )

    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "EXTERNAL_API_KEY_INVALID",
                "message": "外部 API 密钥无效",
            },
        )


def _kol_to_dict(kol: Kol, include_raw: bool = False) -> dict:
    data = {
        "id": kol.id,
        "name": kol.name,
        "account_name": kol.account_name,
        "category": kol.category,
        "platform": kol.platform,
        "external_id": kol.external_id,
        "douyin_id": kol.douyin_id,
        "sec_uid": kol.sec_uid,
        "avatar_url": kol.avatar_url,
        "signature": kol.signature,
        "follower_count": kol.follower_count,
        "video_count": kol.video_count,
        "owner": kol.owner,
        "owner_id": kol.owner_id,
        "persona": kol.persona,
        "content_plan": kol.content_plan,
        "style_notes": kol.style_notes,
        "status": kol.status,
        "computed_status": _compute_status(kol.persona, kol.content_plan),
        "created_by": kol.created_by,
        "background": kol.background,
        "experience": kol.experience,
        "relationships": kol.relationships,
        "unique_story": kol.unique_story,
        "extra_notes": kol.extra_notes,
        "created_at": _ts(kol.created_at),
        "updated_at": _ts(kol.updated_at),
        "deleted_at": _ts(kol.deleted_at),
    }
    if include_raw:
        data["tikhub_raw"] = kol.tikhub_raw
    return data


def _status_filter(status_value: str):
    has_persona = and_(Kol.persona.isnot(None), Kol.persona != "")
    no_persona = or_(Kol.persona.is_(None), Kol.persona == "")
    has_content = and_(Kol.content_plan.isnot(None), Kol.content_plan != "")
    no_content = or_(Kol.content_plan.is_(None), Kol.content_plan == "")
    return {
        "onboarded": and_(has_persona, has_content),
        "persona_done": and_(has_persona, no_content),
        "content_done": and_(no_persona, has_content),
        "pending_onboarding": and_(no_persona, no_content),
    }.get(status_value)


@router.get("", response_model=None)
async def list_external_kols(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str = "",
    platform: str = "",
    status_value: str = Query(default="", alias="status"),
    include_raw: bool = False,
    _: None = Depends(require_external_kols_api_key),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Kol).where(Kol.deleted_at.is_(None))
    count_stmt = select(func.count()).select_from(Kol).where(Kol.deleted_at.is_(None))

    filters = []
    if keyword:
        filters.append(
            or_(
                Kol.name.ilike(f"%{keyword}%"),
                Kol.account_name.ilike(f"%{keyword}%"),
                Kol.douyin_id.ilike(f"%{keyword}%"),
                Kol.sec_uid.ilike(f"%{keyword}%"),
            )
        )
    if platform:
        filters.append(Kol.platform == platform)
    if status_value:
        sf = _status_filter(status_value)
        if sf is not None:
            filters.append(sf)

    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    total = (await db.execute(count_stmt)).scalar() or 0
    rows = (await db.execute(
        stmt.order_by(Kol.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    return success_response(data={
        "items": [_kol_to_dict(kol, include_raw=include_raw) for kol in rows],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    })


@router.get("/{kol_id}", response_model=None)
async def get_external_kol(
    kol_id: int,
    include_raw: bool = True,
    _: None = Depends(require_external_kols_api_key),
    db: AsyncSession = Depends(get_db),
):
    kol = (await db.execute(
        select(Kol).where(Kol.id == kol_id, Kol.deleted_at.is_(None))
    )).scalar_one_or_none()
    if kol is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "红人不存在"},
        )

    return success_response(data=_kol_to_dict(kol, include_raw=include_raw))
