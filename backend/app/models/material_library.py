"""
app/models/material_library.py

素材库（material-library）ORM 模型：
  - KolReference:          红人参考素材（6 种类型手动录入）
  - MaterialLibraryConfig: 管理端 AI 配置（soul_generator Prompt + 模型）

注意：soul.md / content-plan.md 复用 kols.persona / kols.content_plan 字段，不在此建 profile 表。
"""
from sqlalchemy import BigInteger, Column, String, Text, Boolean, Integer, ForeignKey, TIMESTAMP, func

from app.core.database import Base


class KolReference(Base):
    """红人参考素材（6 种类型：红人爆款/红人喜欢/风格参考/千川爆款/千川喜欢/千川风格）"""
    __tablename__ = "kol_references"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    kol_id      = Column(BigInteger, ForeignKey("kols.id", ondelete="CASCADE"), nullable=False)
    title       = Column(String(500), nullable=False)
    likes       = Column(Integer, nullable=True)
    source      = Column(String(100), nullable=True, default="抖音")
    type        = Column(String(50), nullable=False)
    content     = Column(Text, nullable=False)
    data_description = Column(Text, nullable=True)
    document_name = Column(String(500), nullable=True)
    document_type = Column(String(100), nullable=True)
    document_size = Column(BigInteger, nullable=True)
    video_oss_key = Column(String(1024), nullable=True)
    video_name = Column(String(500), nullable=True)
    video_content_type = Column(String(100), nullable=True)
    video_size = Column(BigInteger, nullable=True)
    created_by  = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at  = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at  = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    deleted_at  = Column(TIMESTAMP(timezone=True), nullable=True)


class MaterialLibraryConfig(Base):
    """素材库 AI 配置（soul_generator Prompt + 模型，管理端可配置）"""
    __tablename__ = "material_library_configs"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    config_key    = Column(String(64), nullable=False, unique=True)
    ai_model_id   = Column(BigInteger, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    system_prompt = Column(Text, nullable=True)
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
