"""
app/models/seeding_writer.py

种草内容仿写（seeding-writer）ORM 模型：
  - SeedingWriterConfig:   6 Prompt + 2 AI 模型配置
  - SeedingWriterProduct:  公司共享产品库
  - SeedingWriterReference: 达人维度共享素材库
"""
from sqlalchemy import BigInteger, Column, String, Text, Boolean, Integer, ForeignKey, TIMESTAMP, func

from app.core.database import Base


class SeedingWriterConfig(Base):
    """seeding-writer 工具配置（6 Prompt + 2 AI 模型，管理端可配置）"""
    __tablename__ = "seeding_writer_configs"

    id                        = Column(BigInteger, primary_key=True, autoincrement=True)
    config_key                = Column(String(64), nullable=False, unique=True)
    sp_system_prompt          = Column(Text, nullable=True)
    parse_product_prompt      = Column(Text, nullable=True)
    structure_analysis_prompt = Column(Text, nullable=True)
    ai_recommend_prompt       = Column(Text, nullable=True)
    writing_prompt            = Column(Text, nullable=True)
    iteration_prompt          = Column(Text, nullable=True)
    light_model_id            = Column(BigInteger, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    heavy_model_id            = Column(BigInteger, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    is_active                 = Column(Boolean, nullable=False, default=True)
    created_at                = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at                = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class SeedingWriterProduct(Base):
    """seeding-writer 产品库（公司共享，不按 created_by 隔离查询）"""
    __tablename__ = "seeding_writer_products"

    id                        = Column(BigInteger, primary_key=True, autoincrement=True)
    name                      = Column(Text, nullable=False)
    category                  = Column(Text, nullable=True)
    price                     = Column(Text, nullable=True)
    selling_points            = Column(Text, nullable=True)
    target_audience           = Column(Text, nullable=True)
    scenario                  = Column(Text, nullable=True)
    medical_aesthetic_anchor  = Column(Text, nullable=True)
    created_by                = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at                = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at                = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    deleted_at                = Column(TIMESTAMP(timezone=True), nullable=True)


class SeedingWriterReference(Base):
    """seeding-writer 素材库（达人维度共享，不按 created_by 隔离查询）"""
    __tablename__ = "seeding_writer_references"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    kol_id      = Column(BigInteger, ForeignKey("kols.id", ondelete="SET NULL"), nullable=True)
    title       = Column(Text, nullable=False)
    content     = Column(Text, nullable=False)
    type        = Column(String(32), nullable=True)
    source      = Column(String(32), nullable=True)
    likes       = Column(Integer, nullable=True)
    douyin_url  = Column(Text, nullable=True)
    created_by  = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at  = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at  = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    deleted_at  = Column(TIMESTAMP(timezone=True), nullable=True)
