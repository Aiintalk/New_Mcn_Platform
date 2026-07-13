from sqlalchemy import BigInteger, Column, ForeignKey, TIMESTAMP, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class KolActiveProduct(Base):
    __tablename__ = "kol_active_products"
    __table_args__ = (UniqueConstraint("kol_id", name="uq_kol_active_products_kol"),)

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    kol_id     = Column(BigInteger, ForeignKey("kols.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(BigInteger, ForeignKey("qianchuan_products.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
