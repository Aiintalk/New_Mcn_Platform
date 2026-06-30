"""
app/models/retrospective.py

复盘（retrospective）ORM 模型：
  - RetrospectiveConfig:   复盘 AI 配置（管理端可配置）
  - RetrospectiveSession:  复盘记录表（达人维度）
"""
from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class RetrospectiveConfig(Base):
    """复盘 AI 配置（管理端可配置，config_key='default'）"""
    __tablename__ = "retrospective_configs"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    config_key    = Column(String(64), nullable=False, unique=True)
    system_prompt = Column(Text, nullable=True)
    ai_model_id   = Column(BigInteger, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class RetrospectiveSession(Base):
    """复盘记录表（达人维度，kol_id 隔离）"""
    __tablename__ = "retrospective_sessions"

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    kol_id           = Column(BigInteger, ForeignKey("kols.id", ondelete="CASCADE"), nullable=False)
    created_by       = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title            = Column(String(200), nullable=False)
    status           = Column(String(20), nullable=False, default="draft")  # draft / done
    live_data        = Column(Text, nullable=True)
    material_data    = Column(Text, nullable=True)
    review_text      = Column(Text, nullable=True)
    live_script      = Column(Text, nullable=True)
    material_scripts = Column(JSONB, nullable=True)
    result           = Column(Text, nullable=True)
    created_at       = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at       = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
