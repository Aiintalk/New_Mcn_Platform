"""
app/models/values_writer.py

价值观仿写（values-writer）ORM 模型：
  - ValuesWriterConfig:  4 Prompt + 1 AI 模型配置（Sprint 20）
"""
from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, String, Text, TIMESTAMP, func

from app.core.database import Base


class ValuesWriterConfig(Base):
    """values-writer 工具配置（4 Prompt + 1 AI 模型，管理端可配置）"""
    __tablename__ = "values_writer_configs"

    id                       = Column(BigInteger, primary_key=True, autoincrement=True)
    config_key               = Column(String(64), nullable=False, unique=True)
    extract_values_prompt    = Column(Text, nullable=True)
    emotion_direction_prompt = Column(Text, nullable=True)
    writing_prompt           = Column(Text, nullable=True)
    iteration_prompt         = Column(Text, nullable=True)
    model_id                 = Column(BigInteger, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    is_active                = Column(Boolean, nullable=False, default=True)
    created_at               = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at               = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
