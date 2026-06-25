from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, String, Text, TIMESTAMP
from sqlalchemy.sql import func

from app.core.database import Base


class QianchuanProduct(Base):
    __tablename__ = "qianchuan_products"

    id                  = Column(BigInteger, primary_key=True, autoincrement=True)
    nickname            = Column(String(100), nullable=False)
    core_selling_point  = Column(String(200), nullable=True)
    visualization       = Column(Text, nullable=True)
    mechanism           = Column(Text, nullable=True)
    mechanism_exclusive = Column(Boolean, nullable=False, default=False)
    endorsement         = Column(Text, nullable=True)
    user_feedback       = Column(Text, nullable=True)
    unique_selling      = Column(Text, nullable=True)
    awards              = Column(String(500), nullable=True)
    efficacy_proof      = Column(Text, nullable=True)
    created_by          = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at          = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at          = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at          = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
