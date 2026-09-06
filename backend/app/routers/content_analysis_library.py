"""内容分析项目库的受控下游读取和人工维护接口。"""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import ErrorCode, error_response, success_response
from app.middlewares.auth import get_current_user, require_admin_or_operator
from app.models.content_analysis import ContentAnalysisLibraryItem
from app.models.kol import Kol
from app.models.log import OperationLog
from app.models.material_library import KolReference
from app.models.user import User
from app.services.content_analysis.persistence import SqlContentAnalysisStore
from app.services.content_analysis.executor import infer_source_platform


class ContentAnalysisEnvelopeRoute(APIRoute):
    """只把本路由的框架校验错误收敛为项目标准信封。"""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def route_handler(request: Request):
            try:
                return await original(request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=422,
                    content={
                        "success": False,
                        "code": "VALIDATION_ERROR",
                        "message": "请求参数校验失败",
                        "data": None,
                    },
                )

        return route_handler


router = APIRouter(
    prefix="/tools/content-analysis/library",
    tags=["content-analysis-library"],
    dependencies=[Depends(require_admin_or_operator)],
    route_class=ContentAnalysisEnvelopeRoute,
)


class LibraryAvailabilityUpdate(BaseModel):
    project_id: int
    availability: Literal["enabled", "disabled"]


class ManualOpeningUpdate(BaseModel):
    project_id: int
    status: Literal["available", "unavailable"]
    fragment: str | None = None
    unavailable_reason: str | None = None

    @model_validator(mode="after")
    def validate_combination(self):
        if self.status == "available":
            if not self.fragment or not self.fragment.strip() or self.unavailable_reason:
                raise ValueError("可用开头必须只提供非空片段")
        elif self.fragment or not self.unavailable_reason or not self.unavailable_reason.strip():
            raise ValueError("不可用开头必须只提供明确原因")
        return self


class ManualLibraryContentCreate(BaseModel):
    project_id: int
    title: str | None = None
    transcript: str
    platform_content_id: str | None = None
    external_url: str | None = None

    @model_validator(mode="after")
    def validate_text(self):
        if self.project_id <= 0:
            raise ValueError("项目编号必须是正整数")
        if not self.transcript.strip():
            raise ValueError("人工千川内容必须包含可用正文")
        for field_name in ("platform_content_id", "external_url"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(f"{field_name} 必须是非空文本或空值")
        return self


def _ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.headers.get("x-forwarded-for", request.client.host)


def _item_dict(item: ContentAnalysisLibraryItem, reference: KolReference) -> dict:
    return {
        "id": item.id,
        "project_id": item.project_id,
        "kol_reference_id": item.kol_reference_id,
        "title": reference.title,
        "category": item.category,
        "ingestion_source": item.ingestion_source,
        "platform": item.platform,
        "source_platform_note": (
            "来源平台未知" if item.platform == "unknown" else None
        ),
        "account_id": item.account_id,
        "platform_content_id": item.platform_content_id,
        "external_url": item.external_url,
        "analysis": item.analysis,
        "project_assessment": item.project_assessment,
        "latest_metrics": item.latest_metrics,
        "confidence": item.confidence,
        "priority": item.priority,
        "opening_status": item.opening_status,
        "opening_fragment": item.opening_fragment,
        "opening_unavailable_reason": item.opening_unavailable_reason,
        "availability": item.availability,
    }


@router.post("")
async def create_manual_qianchuan_item(
    body: ManualLibraryContentCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """人工加入当前项目千川正文；开头由后续日报自动补标。"""
    project = await db.scalar(
        select(Kol).where(
            Kol.id == body.project_id,
            Kol.deleted_at.is_(None),
        )
    )
    if project is None:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "项目不存在")
    identity_filters = []
    if body.platform_content_id:
        identity_filters.append(
            ContentAnalysisLibraryItem.platform_content_id
            == body.platform_content_id.strip()
        )
    if body.external_url:
        identity_filters.append(
            ContentAnalysisLibraryItem.external_url == body.external_url.strip()
        )
    existing_rows = []
    if identity_filters:
        await SqlContentAnalysisStore(db).lock_library_mutations()
        existing_rows = list(
            (
                await db.scalars(
                    select(ContentAnalysisLibraryItem).where(
                        ContentAnalysisLibraryItem.project_id == body.project_id,
                        or_(*identity_filters),
                    )
                )
            ).all()
        )
    if len(existing_rows) > 1:
        return error_response(
            ErrorCode.VALIDATION_ERROR,
            "人工内容的两个稳定身份命中了不同记录",
        )
    if existing_rows:
        item = existing_rows[0]
        if (
            body.platform_content_id
            and item.platform_content_id
            and body.platform_content_id.strip() != item.platform_content_id
        ) or (
            body.external_url
            and item.external_url
            and body.external_url.strip() != item.external_url
        ):
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "人工内容稳定身份与已有记录冲突",
            )
        item.platform_content_id = (
            item.platform_content_id
            or (body.platform_content_id.strip() if body.platform_content_id else None)
        )
        item.external_url = (
            item.external_url
            or (body.external_url.strip() if body.external_url else None)
        )
        item.ingestion_source = "manual"
        item.updated_at = datetime.now(timezone.utc)
        reference = await db.get(KolReference, item.kol_reference_id)
        if reference is None or reference.deleted_at is not None:
            return error_response(ErrorCode.RESOURCE_NOT_FOUND, "已有项目库正文不存在")
        action = "content_analysis_library_merge_manual"
    else:
        platform, _ = infer_source_platform(body.external_url)
        reference = KolReference(
            kol_id=body.project_id,
            title=(
                body.title.strip()
                if body.title and body.title.strip()
                else "人工千川正文"
            ),
            source="人工",
            type="千川爆款文案",
            content=body.transcript.strip(),
            data_description='{"source":"manual"}',
            created_by=user.id,
        )
        db.add(reference)
        await db.flush()
        item = ContentAnalysisLibraryItem(
            kol_reference_id=reference.id,
            project_id=body.project_id,
            platform=platform,
            account_id=None,
            platform_content_id=(
                body.platform_content_id.strip()
                if body.platform_content_id
                else None
            ),
            external_url=body.external_url.strip() if body.external_url else None,
            category="qianchuan",
            ingestion_source="manual",
            analysis={"opening": {"status": "unannotated"}},
            project_assessment={},
            latest_metrics={},
            confidence="unverified",
            priority=None,
            opening_status="unannotated",
            opening_fragment=None,
            opening_unavailable_reason=None,
            availability="enabled",
            latest_result_id=None,
        )
        db.add(item)
        await db.flush()
        action = "content_analysis_library_create_manual"
    db.add(
        OperationLog(
            user_id=user.id,
            username=user.username,
            role=user.role,
            action=action,
            target_type="content_analysis_library_item",
            target_id=item.id,
            detail={"project_id": body.project_id, "category": "qianchuan"},
            ip=_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()
    return success_response(data=_item_dict(item, reference))


@router.get("")
async def list_library_items(
    project_id: int = Query(..., ge=1),
    category: Literal["persona", "qianchuan"] = Query(...),
    availability: Literal["enabled", "disabled"] = Query("enabled"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """只返回明确项目、分类和可用状态内的结构化候选。"""
    filters = (
        ContentAnalysisLibraryItem.project_id == project_id,
        ContentAnalysisLibraryItem.category == category,
        ContentAnalysisLibraryItem.availability == availability,
        KolReference.deleted_at.is_(None),
    )
    total = await db.scalar(
        select(func.count(ContentAnalysisLibraryItem.id))
        .join(KolReference, KolReference.id == ContentAnalysisLibraryItem.kol_reference_id)
        .where(*filters)
    )
    rows = (
        await db.execute(
            select(ContentAnalysisLibraryItem, KolReference)
            .join(KolReference, KolReference.id == ContentAnalysisLibraryItem.kol_reference_id)
            .where(*filters)
            .order_by(ContentAnalysisLibraryItem.updated_at.desc(), ContentAnalysisLibraryItem.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return success_response(
        data={
            "items": [_item_dict(item, reference) for item, reference in rows],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": int(total or 0),
            },
        }
    )


async def _project_item(
    db: AsyncSession,
    item_id: int,
    project_id: int,
):
    return (
        await db.execute(
            select(ContentAnalysisLibraryItem, KolReference)
            .join(KolReference, KolReference.id == ContentAnalysisLibraryItem.kol_reference_id)
            .where(
                ContentAnalysisLibraryItem.id == item_id,
                ContentAnalysisLibraryItem.project_id == project_id,
                KolReference.deleted_at.is_(None),
            )
        )
    ).one_or_none()


@router.patch("/{item_id}/availability")
async def set_library_availability(
    item_id: int,
    body: LibraryAvailabilityUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """按项目停用或恢复内容分析候选。"""
    await SqlContentAnalysisStore(db).lock_library_mutations()
    row = await _project_item(db, item_id, body.project_id)
    if row is None:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "项目内容库候选不存在")
    item, _ = row
    item.availability = body.availability
    item.updated_at = datetime.now(timezone.utc)
    item.disabled_at = (
        datetime.now(timezone.utc) if body.availability == "disabled" else None
    )
    if item.latest_result_id is not None:
        await SqlContentAnalysisStore(db).rebuild_cross_project_opportunities(
            item.latest_result_id
        )
    db.add(
        OperationLog(
            user_id=user.id,
            username=user.username,
            role=user.role,
            action=f"content_analysis_library_{body.availability}",
            target_type="content_analysis_library_item",
            target_id=item.id,
            detail={
                "project_id": body.project_id,
                "availability": body.availability,
            },
            ip=_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()
    return success_response(
        data={
            "id": item.id,
            "project_id": item.project_id,
            "availability": item.availability,
        }
    )


@router.patch("/{item_id}/opening")
async def annotate_library_opening(
    item_id: int,
    body: ManualOpeningUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """人工补标千川候选开头，并与正文候选保持同一记录。"""
    await SqlContentAnalysisStore(db).lock_library_mutations()
    row = await _project_item(db, item_id, body.project_id)
    if row is None:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "项目内容库候选不存在")
    item, reference = row
    if item.category != "qianchuan":
        return error_response(ErrorCode.VALIDATION_ERROR, "仅千川候选支持人工开头补标")
    if body.fragment and body.fragment not in reference.content:
        return error_response(
            ErrorCode.VALIDATION_ERROR,
            "开头片段必须能回到当前候选转写",
        )
    item.opening_status = body.status
    item.opening_fragment = body.fragment
    item.opening_unavailable_reason = body.unavailable_reason
    item.updated_at = datetime.now(timezone.utc)
    analysis = dict(item.analysis or {})
    analysis["opening"] = (
        {
            "status": "available",
            "kind": "language",
            "fragment": body.fragment,
            "source": "manual",
        }
        if body.status == "available"
        else {
            "status": "unavailable",
            "kind": "language",
            "unavailable_reason": body.unavailable_reason,
            "source": "manual",
        }
    )
    item.analysis = analysis
    db.add(
        OperationLog(
            user_id=user.id,
            username=user.username,
            role=user.role,
            action="content_analysis_library_annotate_opening",
            target_type="content_analysis_library_item",
            target_id=item.id,
            detail={
                "project_id": body.project_id,
                "opening_status": body.status,
            },
            ip=_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()
    return success_response(
        data={
            "id": item.id,
            "project_id": item.project_id,
            "opening_status": item.opening_status,
            "opening_fragment": item.opening_fragment,
            "opening_unavailable_reason": item.opening_unavailable_reason,
        }
    )
