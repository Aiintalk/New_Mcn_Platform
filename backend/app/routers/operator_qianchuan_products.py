"""
app/routers/operator_qianchuan_products.py

千川产品库接口（运营端，JWT operator/admin 鉴权）：
  GET    /api/operator/qianchuan-products         — 列表（分页+搜索）
  POST   /api/operator/qianchuan-products         — 新建
  PUT    /api/operator/qianchuan-products/{id}    — 编辑
  DELETE /api/operator/qianchuan-products/{id}    — 软删除
"""
import math
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select, update

from app.core.database import AsyncSessionLocal
from app.core.response import ErrorCode, error_response, success_response
from app.middlewares.auth import get_current_user
from app.models.kol_active_product import KolActiveProduct
from app.models.log import OperationLog
from app.models.qianchuan_product import QianchuanProduct
from app.models.user import User

router = APIRouter(prefix="/operator/qianchuan-products", tags=["operator-qianchuan-products"])

_PAGE_SIZE_ALLOWED = {10, 20, 50}


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

async def require_operator(current_user: User = Depends(get_current_user)) -> User:
    if current_user.password_changed_at is None:
        raise HTTPException(status_code=403,
                            detail={"code": "AUTH_FORCE_CHANGE_PASSWORD", "message": "请先修改初始密码"})
    if current_user.role not in ("operator", "admin"):
        raise HTTPException(status_code=403,
                            detail={"code": "PERMISSION_DENIED", "message": "无权限访问"})
    return current_user


def _get_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _product_to_dict(p: QianchuanProduct) -> dict:
    return {
        "id": p.id,
        "nickname": p.nickname,
        "core_selling_point": p.core_selling_point,
        "visualization": p.visualization,
        "mechanism": p.mechanism,
        "mechanism_exclusive": p.mechanism_exclusive,
        "endorsement": p.endorsement,
        "user_feedback": p.user_feedback,
        "unique_selling": p.unique_selling,
        "awards": p.awards,
        "efficacy_proof": p.efficacy_proof,
        "created_by": p.created_by,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class ProductRequest(BaseModel):
    nickname: str
    core_selling_point: Optional[str] = None
    visualization: Optional[str] = None
    mechanism: Optional[str] = None
    mechanism_exclusive: bool = False
    endorsement: Optional[str] = None
    user_feedback: Optional[str] = None
    unique_selling: Optional[str] = None
    awards: Optional[str] = None
    efficacy_proof: Optional[str] = None


class UpdateProductRequest(BaseModel):
    nickname: Optional[str] = None
    core_selling_point: Optional[str] = None
    visualization: Optional[str] = None
    mechanism: Optional[str] = None
    mechanism_exclusive: Optional[bool] = None
    endorsement: Optional[str] = None
    user_feedback: Optional[str] = None
    unique_selling: Optional[str] = None
    awards: Optional[str] = None
    efficacy_proof: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=None)
async def list_products(
    page: int = 1,
    page_size: int = 20,
    q: Optional[str] = None,
    current_user: User = Depends(require_operator),
):
    if page_size not in _PAGE_SIZE_ALLOWED:
        page_size = 20

    async with AsyncSessionLocal() as session:
        base_q = select(QianchuanProduct).where(QianchuanProduct.deleted_at.is_(None))
        if q:
            base_q = base_q.where(QianchuanProduct.nickname.ilike(f"%{q}%"))

        total_row = await session.execute(
            select(func.count()).select_from(base_q.subquery())
        )
        total = total_row.scalar() or 0

        rows = await session.execute(
            base_q.order_by(QianchuanProduct.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = [_product_to_dict(p) for p in rows.scalars().all()]

        return success_response(data={
            "items": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": math.ceil(total / page_size) if total else 0,
            },
        })


@router.post("", response_model=None)
async def create_product(
    body: ProductRequest,
    request: Request,
    current_user: User = Depends(require_operator),
):
    async with AsyncSessionLocal() as session:
        product = QianchuanProduct(
            nickname=body.nickname,
            core_selling_point=body.core_selling_point,
            visualization=body.visualization,
            mechanism=body.mechanism,
            mechanism_exclusive=body.mechanism_exclusive,
            endorsement=body.endorsement,
            user_feedback=body.user_feedback,
            unique_selling=body.unique_selling,
            awards=body.awards,
            efficacy_proof=body.efficacy_proof,
            created_by=current_user.id,
        )
        session.add(product)
        await session.flush()

        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="create_qianchuan_product",
            target_type="qianchuan_product",
            target_id=product.id,
            ip=_get_ip(request),
        ))
        await session.commit()
        await session.refresh(product)
        return success_response(data=_product_to_dict(product))


@router.put("/{product_id}", response_model=None)
async def update_product(
    product_id: int,
    body: UpdateProductRequest,
    request: Request,
    current_user: User = Depends(require_operator),
):
    async with AsyncSessionLocal() as session:
        row = await session.execute(
            select(QianchuanProduct).where(
                QianchuanProduct.id == product_id,
                QianchuanProduct.deleted_at.is_(None),
            )
        )
        product = row.scalar_one_or_none()
        if not product:
            raise HTTPException(
                status_code=404,
                detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "产品不存在"},
            )

        updates: dict = {
            k: v for k, v in body.model_dump(exclude_none=True).items()
        }
        updates["updated_at"] = datetime.now(timezone.utc)

        await session.execute(
            update(QianchuanProduct)
            .where(QianchuanProduct.id == product_id)
            .values(**updates)
        )
        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="update_qianchuan_product",
            target_type="qianchuan_product",
            target_id=product_id,
            ip=_get_ip(request),
        ))
        await session.commit()
        await session.refresh(product)
        return success_response(data=_product_to_dict(product))


@router.delete("/{product_id}", response_model=None)
async def delete_product(
    product_id: int,
    request: Request,
    current_user: User = Depends(require_operator),
):
    async with AsyncSessionLocal() as session:
        row = await session.execute(
            select(QianchuanProduct).where(
                QianchuanProduct.id == product_id,
                QianchuanProduct.deleted_at.is_(None),
            )
        )
        product = row.scalar_one_or_none()
        if not product:
            raise HTTPException(
                status_code=404,
                detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "产品不存在"},
            )

        active_link = await session.execute(
            select(KolActiveProduct.id).where(KolActiveProduct.product_id == product_id)
        )
        if active_link.scalar() is not None:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "ACTIVE_PRODUCT_IN_USE",
                    "message": "该产品仍是某位红人的当前商品，请先解除或替换当前商品后再删除",
                },
            )

        await session.execute(
            update(QianchuanProduct)
            .where(QianchuanProduct.id == product_id)
            .values(deleted_at=datetime.now(timezone.utc))
        )
        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="delete_qianchuan_product",
            target_type="qianchuan_product",
            target_id=product_id,
            ip=_get_ip(request),
        ))
        await session.commit()
        return success_response(data={"id": product_id})
