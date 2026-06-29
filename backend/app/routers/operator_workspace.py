"""
app/routers/operator_workspace.py

红人工作台接口（运营端）：
  GET    /api/operator/workspace/{kol_id}/dashboard
  GET    /api/operator/workspace/{kol_id}/benchmarks
  POST   /api/operator/workspace/{kol_id}/benchmarks/validate  — TikHub 验证账号
  POST   /api/operator/workspace/{kol_id}/benchmarks
  PUT    /api/operator/workspace/{kol_id}/benchmarks/{id}
  DELETE /api/operator/workspace/{kol_id}/benchmarks/{id}
  GET    /api/operator/workspace/{kol_id}/active-products
  PUT    /api/operator/workspace/{kol_id}/active-products
"""
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import tikhub as tikhub_adapter
from app.core.database import AsyncSessionLocal, get_db
from app.core.response import ErrorCode, error_response, success_response
from app.middlewares.auth import get_current_user
from app.models.kol import Kol
from app.models.kol_active_product import KolActiveProduct
from app.models.kol_benchmark import KolBenchmark
from app.models.log import OperationLog
from app.models.qianchuan_product import QianchuanProduct
from app.models.user import User

router = APIRouter(prefix="/operator/workspace", tags=["operator-workspace"])


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
    }


def _benchmark_to_dict(b: KolBenchmark) -> dict:
    return {
        "id": b.id,
        "kol_id": b.kol_id,
        "account_name": b.account_name,
        "account_type": b.account_type,
        "description": b.description,
        "sort_order": b.sort_order,
    }


async def _get_kol_or_404(session, kol_id: int) -> Kol:
    row = await session.execute(
        select(Kol).where(Kol.id == kol_id, Kol.deleted_at.is_(None))
    )
    kol = row.scalar_one_or_none()
    if not kol:
        raise HTTPException(status_code=404,
                            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "达人不存在"})
    return kol


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/{kol_id}/dashboard", response_model=None)
async def get_dashboard(kol_id: int, current_user: User = Depends(require_operator)):
    async with AsyncSessionLocal() as session:
        kol = await _get_kol_or_404(session, kol_id)

        benchmarks_rows = await session.execute(
            select(KolBenchmark)
            .where(KolBenchmark.kol_id == kol_id)
            .order_by(KolBenchmark.sort_order.asc())
        )
        benchmarks = benchmarks_rows.scalars().all()

        active_rows = await session.execute(
            select(QianchuanProduct)
            .join(KolActiveProduct, KolActiveProduct.product_id == QianchuanProduct.id)
            .where(KolActiveProduct.kol_id == kol_id, QianchuanProduct.deleted_at.is_(None))
        )
        active_products = active_rows.scalars().all()

        return success_response(data={
            "kol": {
                "id": kol.id,
                "name": kol.name,
                "avatar_url": kol.avatar_url,
                "category": kol.category,
            },
            "benchmarks": {
                "content": [_benchmark_to_dict(b) for b in benchmarks if b.account_type == "content"],
                "livestream": [_benchmark_to_dict(b) for b in benchmarks if b.account_type == "livestream"],
            },
            "active_products": [_product_to_dict(p) for p in active_products],
        })


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------

class BenchmarkRequest(BaseModel):
    account_name: str
    account_type: Literal["content", "livestream"]
    description: Optional[str] = None
    sort_order: int = 0


class ValidateAccountRequest(BaseModel):
    account_input: str  # 抖音主页链接、分享短链或账号 ID


@router.post("/{kol_id}/benchmarks/validate", response_model=None)
async def validate_benchmark_account(
    kol_id: int,
    body: ValidateAccountRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """
    调 TikHub 验证抖音账号是否存在，返回昵称和头像供前端预览确认。
    成功时 success=True，失败时 success=False（不抛 HTTP 异常，由前端展示错误提示）。
    """
    async with AsyncSessionLocal() as session:
        await _get_kol_or_404(session, kol_id)

    try:
        resolved = await tikhub_adapter.resolve_sec_user_id(body.account_input, db)
        profile = await tikhub_adapter.get_user_profile(resolved["sec_user_id"], db)
    except Exception as e:
        return error_response("TIKHUB_ERROR", f"账号查找失败：{str(e)[:120]}")

    return success_response(data={
        "sec_user_id": resolved["sec_user_id"],
        "nickname": resolved["nickname"] or profile.get("nickname") or "",
        "avatar_url": profile.get("avatar_url"),
        "follower_count": profile.get("follower_count"),
    })


@router.get("/{kol_id}/benchmarks", response_model=None)
async def list_benchmarks(kol_id: int, current_user: User = Depends(require_operator)):
    async with AsyncSessionLocal() as session:
        await _get_kol_or_404(session, kol_id)
        rows = await session.execute(
            select(KolBenchmark)
            .where(KolBenchmark.kol_id == kol_id)
            .order_by(KolBenchmark.sort_order.asc())
        )
        benchmarks = rows.scalars().all()
        return success_response(data={
            "content": [_benchmark_to_dict(b) for b in benchmarks if b.account_type == "content"],
            "livestream": [_benchmark_to_dict(b) for b in benchmarks if b.account_type == "livestream"],
        })


@router.post("/{kol_id}/benchmarks", response_model=None)
async def create_benchmark(
    kol_id: int,
    body: BenchmarkRequest,
    request: Request,
    current_user: User = Depends(require_operator),
):
    async with AsyncSessionLocal() as session:
        await _get_kol_or_404(session, kol_id)
        b = KolBenchmark(
            kol_id=kol_id,
            account_name=body.account_name,
            account_type=body.account_type,
            description=body.description,
            sort_order=body.sort_order,
            created_by=current_user.id,
        )
        session.add(b)
        await session.flush()
        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="create_kol_benchmark",
            target_type="kol_benchmark",
            target_id=b.id,
            ip=_get_ip(request),
        ))
        await session.commit()
        await session.refresh(b)
        return success_response(data=_benchmark_to_dict(b))


@router.put("/{kol_id}/benchmarks/{benchmark_id}", response_model=None)
async def update_benchmark(
    kol_id: int,
    benchmark_id: int,
    body: BenchmarkRequest,
    request: Request,
    current_user: User = Depends(require_operator),
):
    async with AsyncSessionLocal() as session:
        await _get_kol_or_404(session, kol_id)
        row = await session.execute(
            select(KolBenchmark).where(KolBenchmark.id == benchmark_id, KolBenchmark.kol_id == kol_id)
        )
        b = row.scalar_one_or_none()
        if not b:
            raise HTTPException(
                status_code=404,
                detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "对标账号不存在"},
            )
        b.account_name = body.account_name
        b.account_type = body.account_type
        b.description = body.description
        b.sort_order = body.sort_order
        b.updated_at = datetime.now(timezone.utc)
        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="update_kol_benchmark",
            target_type="kol_benchmark",
            target_id=benchmark_id,
            ip=_get_ip(request),
        ))
        await session.commit()
        await session.refresh(b)
        return success_response(data=_benchmark_to_dict(b))


@router.delete("/{kol_id}/benchmarks/{benchmark_id}", response_model=None)
async def delete_benchmark(
    kol_id: int,
    benchmark_id: int,
    request: Request,
    current_user: User = Depends(require_operator),
):
    async with AsyncSessionLocal() as session:
        await _get_kol_or_404(session, kol_id)
        row = await session.execute(
            select(KolBenchmark).where(KolBenchmark.id == benchmark_id, KolBenchmark.kol_id == kol_id)
        )
        b = row.scalar_one_or_none()
        if not b:
            raise HTTPException(
                status_code=404,
                detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "对标账号不存在"},
            )
        await session.delete(b)
        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="delete_kol_benchmark",
            target_type="kol_benchmark",
            target_id=benchmark_id,
            ip=_get_ip(request),
        ))
        await session.commit()
        return success_response(data={"id": benchmark_id})


# ---------------------------------------------------------------------------
# Active Products
# ---------------------------------------------------------------------------

class ActiveProductsRequest(BaseModel):
    product_ids: list[int]


@router.get("/{kol_id}/active-products", response_model=None)
async def list_active_products(kol_id: int, current_user: User = Depends(require_operator)):
    async with AsyncSessionLocal() as session:
        await _get_kol_or_404(session, kol_id)
        rows = await session.execute(
            select(QianchuanProduct)
            .join(KolActiveProduct, KolActiveProduct.product_id == QianchuanProduct.id)
            .where(KolActiveProduct.kol_id == kol_id, QianchuanProduct.deleted_at.is_(None))
        )
        products = rows.scalars().all()
        return success_response(data=[_product_to_dict(p) for p in products])


@router.put("/{kol_id}/active-products", response_model=None)
async def update_active_products(
    kol_id: int,
    body: ActiveProductsRequest,
    request: Request,
    current_user: User = Depends(require_operator),
):
    async with AsyncSessionLocal() as session:
        await _get_kol_or_404(session, kol_id)

        # 校验 product_ids 全部存在且未软删
        if body.product_ids:
            rows = await session.execute(
                select(QianchuanProduct.id).where(
                    QianchuanProduct.id.in_(body.product_ids),
                    QianchuanProduct.deleted_at.is_(None),
                )
            )
            found_ids = {r[0] for r in rows.all()}
            missing = set(body.product_ids) - found_ids
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "VALIDATION_ERROR", "message": f"产品 {missing} 不存在"},
                )

        # 整体替换：删旧 → 插新
        await session.execute(
            delete(KolActiveProduct).where(KolActiveProduct.kol_id == kol_id)
        )
        for pid in body.product_ids:
            session.add(KolActiveProduct(kol_id=kol_id, product_id=pid))
        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="update_kol_active_products",
            target_type="kol",
            target_id=kol_id,
            ip=_get_ip(request),
        ))
        await session.commit()

        return success_response(data={"active_product_ids": body.product_ids})
