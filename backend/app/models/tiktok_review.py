from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, TIMESTAMP, func
from app.core.database import Base


class TiktokReviewConfig(Base):
    """tiktok-review 工具配置（Prompt + 模型，管理端可配置）"""
    __tablename__ = "tiktok_review_configs"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    config_key    = Column(String(50), nullable=False, unique=True)
    ai_model_id   = Column(Integer, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    system_prompt = Column(Text, nullable=True)
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
