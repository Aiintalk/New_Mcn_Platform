from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, String, Text, TIMESTAMP
from sqlalchemy.sql import func

from app.core.database import Base


class QianchuanScriptReviewConfig(Base):
    __tablename__ = "qianchuan_script_review_configs"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    config_key    = Column(String(64), nullable=False, unique=True)
    direct_prompt = Column(Text, nullable=True)
    value_prompt  = Column(Text, nullable=True)
    ai_model_id   = Column(BigInteger, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
