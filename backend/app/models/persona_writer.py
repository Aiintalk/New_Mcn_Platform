"""
app/models/persona_writer.py

人设脚本仿写（persona-writer）配置表 ORM 模型。
参照 QianchuanWriterConfig 结构，扩展为 4 Prompt + 2 模型字段。
"""
from sqlalchemy import BigInteger, Column, String, Text, Boolean, ForeignKey, TIMESTAMP, func

from app.core.database import Base


class PersonaWriterConfig(Base):
    """persona-writer 工具配置（4 Prompt + 2 AI 模型，管理端可配置）"""
    __tablename__ = "persona_writer_configs"

    id                = Column(BigInteger, primary_key=True, autoincrement=True)
    config_key        = Column(String(64), nullable=False, unique=True)
    evaluation_prompt = Column(Text, nullable=True)
    analysis_prompt   = Column(Text, nullable=True)
    writing_prompt    = Column(Text, nullable=True)
    iteration_prompt  = Column(Text, nullable=True)
    light_model_id    = Column(BigInteger, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    heavy_model_id    = Column(BigInteger, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    is_active         = Column(Boolean, nullable=False, default=True)
    created_at        = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at        = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
