"""
app/routers/admin_kols.py

红人（KOL）管理接口：
  GET    /api/admin/kols
  POST   /api/admin/kols
  GET    /api/admin/kols/{id}
  PATCH  /api/admin/kols/{id}
  DELETE /api/admin/kols/{id}        (软删)
  POST   /api/admin/kols/{id}/fetch-tikhub
"""
import math
from datetime import datetime, timezone

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import and_, or_, select, update

from app.core.database import AsyncSessionLocal, get_db
from app.core.response import ApiResponse, ErrorCode, error_response, success_response
from app.middlewares.auth import get_current_user, require_admin, require_admin_or_operator
from app.models.kol import Kol
from app.models.log import OperationLog
from app.models.user import User
from app.services.kol_tikhub import fetch_tikhub_for_kol
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/admin/kols", tags=["admin-kols"])

_PAGE_SIZE_ALLOWED = {10, 20, 50}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


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


def _kol_to_dict(k: Kol, include_raw: bool = False) -> dict:
    d = {
        "id": k.id,
        "name": k.name,
        "account_name": k.account_name,
        "category": k.category,
        "platform": k.platform,
        "douyin_id": k.douyin_id,
        "sec_uid": k.sec_uid,
        "avatar_url": k.avatar_url,
        "followers_count": k.follower_count,   # 前端字段名
        "works_count": k.video_count,           # 前端字段名
        "persona": k.persona,
        "content_plan": k.content_plan,
        "style_note": k.style_notes,            # 前端字段名
        "owner": k.owner,                       # 负责人姓名（自由文本）
        "owner_id": k.owner_id,
        "status": _compute_status(k.persona, k.content_plan),
        "tikhub_fetched": k.tikhub_raw is not None,
        "created_by": k.created_by,
        "created_at": _ts(k.created_at),
        "updated_at": _ts(k.updated_at),
    }
    if include_raw:
        d["tikhub_raw"] = k.tikhub_raw
    return d


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class CreateKolRequest(BaseModel):
    name: str
    account_name: str | None = None
    category: str | None = None
    platform: str = "douyin"
    douyin_id: str | None = None
    sec_uid: str | None = None
    avatar_url: str | None = None
    follower_count: int | None = None
    video_count: int | None = None
    persona: str | None = None
    content_plan: str | None = None
    style_note: str | None = None   # 前端字段名，映射到 style_notes
    owner: str | None = None         # 负责人姓名
    owner_id: int | None = None


class UpdateKolRequest(BaseModel):
    name: str | None = None
    account_name: str | None = None
    category: str | None = None
    platform: str | None = None
    douyin_id: str | None = None
    sec_uid: str | None = None
    avatar_url: str | None = None
    follower_count: int | None = None
    video_count: int | None = None
    persona: str | None = None
    content_plan: str | None = None
    style_note: str | None = None   # 前端字段名
    owner: str | None = None         # 负责人姓名
    owner_id: int | None = None


# ---------------------------------------------------------------------------
# GET /api/admin/kols
# ---------------------------------------------------------------------------

@router.get("", response_model=ApiResponse)
async def list_kols(
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
    status: str = "",
    current_user: User = Depends(require_admin_or_operator),
):
    if page_size not in _PAGE_SIZE_ALLOWED:
        page_size = 20

    async with AsyncSessionLocal() as session:
        q = select(Kol).where(Kol.deleted_at.is_(None))
        if keyword:
            q = q.where(
                Kol.name.ilike(f"%{keyword}%")
                | Kol.account_name.ilike(f"%{keyword}%")
                | Kol.douyin_id.ilike(f"%{keyword}%")
            )
        if status:
            _has_p = and_(Kol.persona.isnot(None), Kol.persona != '')
            _no_p  = or_(Kol.persona.is_(None), Kol.persona == '')
            _has_c = and_(Kol.content_plan.isnot(None), Kol.content_plan != '')
            _no_c  = or_(Kol.content_plan.is_(None), Kol.content_plan == '')
            status_filter = {
                "onboarded":          and_(_has_p, _has_c),
                "persona_done":       and_(_has_p, _no_c),
                "content_done":       and_(_no_p, _has_c),
                "pending_onboarding": and_(_no_p, _no_c),
            }.get(status)
            if status_filter is not None:
                q = q.where(status_filter)

        total = len((await session.execute(q)).scalars().all())
        rows = (await session.execute(
            q.order_by(Kol.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()

    return success_response(data={
        "items": [_kol_to_dict(k) for k in rows],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": math.ceil(total / page_size) if page_size else 1,
        },
    })


# ---------------------------------------------------------------------------
# POST /api/admin/kols
# ---------------------------------------------------------------------------

@router.post("", response_model=ApiResponse)
async def create_kol(
    body: CreateKolRequest,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # 预检查 douyin_id / sec_uid 唯一性（数据库层面已加部分唯一索引兜底，
    # 这里提前返回友好错误，避免 IntegrityError 直接冒泡到 500）。
    if body.douyin_id:
        existing = (await db.execute(
            select(Kol).where(
                Kol.douyin_id == body.douyin_id,
                Kol.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        if existing:
            return error_response(
                ErrorCode.RESOURCE_ALREADY_EXISTS,
                f"抖音号 {body.douyin_id} 已存在（红人：{existing.name}）",
            )
    if body.sec_uid:
        existing = (await db.execute(
            select(Kol).where(
                Kol.sec_uid == body.sec_uid,
                Kol.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        if existing:
            return error_response(
                ErrorCode.RESOURCE_ALREADY_EXISTS,
                f"sec_uid 已存在（红人：{existing.name}）",
            )

    kol = Kol(
        name=body.name,
        account_name=body.account_name,
        category=body.category,
        platform=body.platform,
        douyin_id=body.douyin_id,
        sec_uid=body.sec_uid,
        avatar_url=body.avatar_url,
        follower_count=body.follower_count,
        video_count=body.video_count,
        persona=body.persona,
        content_plan=body.content_plan,
        style_notes=body.style_note,    # 映射前端 style_note → DB style_notes
        owner=body.owner,               # 负责人姓名
        owner_id=body.owner_id,
        created_by=current_user.id,
    )
    db.add(kol)
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="create_kol",
        target_type="kol",
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(kol)

    return success_response(data=_kol_to_dict(kol), message="红人创建成功")


# ---------------------------------------------------------------------------
# GET /api/admin/kols/{kol_id}   — 必须在有冲突的子路由之前
# ---------------------------------------------------------------------------

@router.get("/{kol_id}", response_model=ApiResponse)
async def get_kol(
    kol_id: int,
    current_user: User = Depends(require_admin_or_operator),
):
    async with AsyncSessionLocal() as session:
        kol = (await session.execute(
            select(Kol).where(Kol.id == kol_id, Kol.deleted_at.is_(None))
        )).scalar_one_or_none()

    if kol is None:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "红人不存在")

    return success_response(data=_kol_to_dict(kol, include_raw=True))


# ---------------------------------------------------------------------------
# PATCH /api/admin/kols/{kol_id}
# ---------------------------------------------------------------------------

@router.patch("/{kol_id}", response_model=ApiResponse)
async def update_kol(
    kol_id: int,
    body: UpdateKolRequest,
    request: Request,
    current_user: User = Depends(require_admin),
):
    async with AsyncSessionLocal() as session:
        kol = (await session.execute(
            select(Kol).where(Kol.id == kol_id, Kol.deleted_at.is_(None))
        )).scalar_one_or_none()
        if kol is None:
            return error_response(ErrorCode.RESOURCE_NOT_FOUND, "红人不存在")

        values: dict = {}
        for field in (
            "name", "account_name", "category", "platform",
            "douyin_id", "sec_uid", "avatar_url",
            "follower_count", "video_count",
            "persona", "content_plan",
            "owner", "owner_id",
        ):
            v = getattr(body, field)
            if v is not None:
                values[field] = v
        # style_note (前端) → style_notes (DB)
        if body.style_note is not None:
            values["style_notes"] = body.style_note

        if values:
            values["updated_at"] = datetime.now(timezone.utc)
            await session.execute(update(Kol).where(Kol.id == kol_id).values(**values))

        # detail 排除 updated_at（datetime 不能序列化为 JSONB）
        log_detail = {k: v for k, v in values.items() if k != "updated_at"} or None
        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="update_kol",
            target_type="kol",
            target_id=kol_id,
            detail=log_detail,
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent"),
        ))
        await session.commit()
        await session.refresh(kol)

    return success_response(data=_kol_to_dict(kol))


# ---------------------------------------------------------------------------
# DELETE /api/admin/kols/{kol_id}  (软删)
# ---------------------------------------------------------------------------

@router.delete("/{kol_id}", response_model=ApiResponse)
async def delete_kol(
    kol_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
):
    async with AsyncSessionLocal() as session:
        kol = (await session.execute(
            select(Kol).where(Kol.id == kol_id, Kol.deleted_at.is_(None))
        )).scalar_one_or_none()
        if kol is None:
            return error_response(ErrorCode.RESOURCE_NOT_FOUND, "红人不存在")

        await session.execute(
            update(Kol).where(Kol.id == kol_id)
            .values(deleted_at=datetime.now(timezone.utc))
        )
        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="delete_kol",
            target_type="kol",
            target_id=kol_id,
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent"),
        ))
        await session.commit()

    return success_response(data=None, message="红人已删除")


# ---------------------------------------------------------------------------
# POST /api/admin/kols/{kol_id}/fetch-tikhub
# ---------------------------------------------------------------------------

@router.post("/{kol_id}/fetch-tikhub", response_model=ApiResponse)
async def fetch_tikhub(
    kol_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    手动触发 TikHub 数据拉取。
    - 优先用 sec_uid，为空时用 douyin_id
    - 无论成功失败都写 external_service_logs
    - 返回拉取结果 + 更新后的 kol 字段
    """
    kol = (await db.execute(
        select(Kol).where(Kol.id == kol_id, Kol.deleted_at.is_(None))
    )).scalar_one_or_none()
    if kol is None:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "红人不存在")

    tikhub_result = await fetch_tikhub_for_kol(kol, db)
    await db.refresh(kol)

    return success_response(data={
        "tikhub": tikhub_result,
        "kol": _kol_to_dict(kol),
    })


# ---------------------------------------------------------------------------
# Persona Details — 运营端（GET/PUT /api/operator/kols/{kol_id}/persona-details）
# ---------------------------------------------------------------------------

_operator_router = APIRouter(prefix="/operator/kols", tags=["operator-kols"])


async def _require_operator_kols(current_user: User = Depends(get_current_user)) -> User:
    if current_user.password_changed_at is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "AUTH_FORCE_CHANGE_PASSWORD", "message": "请先修改初始密码"},
        )
    if current_user.role not in ("operator", "admin"):
        raise HTTPException(
            status_code=403,
            detail={"code": "PERMISSION_DENIED", "message": "无权限访问"},
        )
    return current_user


class PersonaDetailsRequest(BaseModel):
    background: Optional[str] = None
    experience: Optional[str] = None
    relationships: Optional[str] = None
    unique_story: Optional[str] = None
    extra_notes: Optional[str] = None


def _persona_dict(kol: Kol) -> dict:
    return {
        "kol_id": kol.id,
        "background": kol.background,
        "experience": kol.experience,
        "relationships": kol.relationships,
        "unique_story": kol.unique_story,
        "extra_notes": kol.extra_notes,
        "updated_at": _ts(kol.updated_at),
    }


@_operator_router.get("/{kol_id}/persona-details", response_model=None)
async def get_persona_details(
    kol_id: int,
    current_user: User = Depends(_require_operator_kols),
):
    async with AsyncSessionLocal() as session:
        row = await session.execute(
            select(Kol).where(Kol.id == kol_id, Kol.deleted_at.is_(None))
        )
        kol = row.scalar_one_or_none()
        if not kol:
            return error_response(ErrorCode.RESOURCE_NOT_FOUND, "达人不存在")
        return success_response(data=_persona_dict(kol))


@_operator_router.put("/{kol_id}/persona-details", response_model=None)
async def update_persona_details(
    kol_id: int,
    body: PersonaDetailsRequest,
    request: Request,
    current_user: User = Depends(_require_operator_kols),
):
    async with AsyncSessionLocal() as session:
        row = await session.execute(
            select(Kol).where(Kol.id == kol_id, Kol.deleted_at.is_(None))
        )
        kol = row.scalar_one_or_none()
        if not kol:
            return error_response(ErrorCode.RESOURCE_NOT_FOUND, "达人不存在")

        # PATCH 语义：只更新非 None 字段
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        updates["updated_at"] = datetime.now(timezone.utc)

        await session.execute(
            update(Kol).where(Kol.id == kol_id).values(**updates)
        )
        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="update_kol_persona_details",
            target_type="kol",
            target_id=kol_id,
            ip=_get_ip(request),
        ))
        await session.commit()
        await session.refresh(kol)
        return success_response(data=_persona_dict(kol))
