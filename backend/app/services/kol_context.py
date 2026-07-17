"""红人工作台工具共用的红人和商品事实源读取服务。"""
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import ErrorCode
from app.models.kol import Kol
from app.models.kol_active_product import KolActiveProduct
from app.models.qianchuan_product import QianchuanProduct


@dataclass(frozen=True)
class KolContext:
    kol_id: int
    name: str
    persona: str | None
    content_plan: str | None
    background: str | None
    experience: str | None
    relationships: str | None
    unique_story: str | None
    extra_notes: str | None

    def prompt_sections(self) -> list[tuple[str, str]]:
        """返回仅含非空档案字段的 AI 输入分段。"""
        fields = (
            ("原有人设", self.persona),
            ("内容规划", self.content_plan),
            ("基本身份", self.background),
            ("真实经历", self.experience),
            ("关系网", self.relationships),
            ("独家经历", self.unique_story),
            ("其他补充", self.extra_notes),
        )
        return [(label, value) for label, value in fields if value and value.strip()]


async def get_kol_context(session: AsyncSession, kol_id: int) -> KolContext:
    row = await session.execute(
        select(Kol).where(Kol.id == kol_id, Kol.deleted_at.is_(None))
    )
    kol = row.scalar_one_or_none()
    if not kol:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "达人不存在"},
        )
    return KolContext(
        kol_id=kol.id,
        name=kol.name,
        persona=kol.persona,
        content_plan=kol.content_plan,
        background=kol.background,
        experience=kol.experience,
        relationships=kol.relationships,
        unique_story=kol.unique_story,
        extra_notes=kol.extra_notes,
    )


async def get_product_by_id(session: AsyncSession, product_id: int) -> QianchuanProduct:
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
            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "产品不存在或已删除"},
        )
    return product


async def get_current_product(session: AsyncSession, kol_id: int) -> QianchuanProduct | None:
    row = await session.execute(
        select(QianchuanProduct)
        .join(KolActiveProduct, KolActiveProduct.product_id == QianchuanProduct.id)
        .where(
            KolActiveProduct.kol_id == kol_id,
            QianchuanProduct.deleted_at.is_(None),
        )
    )
    return row.scalar_one_or_none()
