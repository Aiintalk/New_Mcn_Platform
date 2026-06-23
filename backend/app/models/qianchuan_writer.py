"""
app/models/qianchuan_writer.py

千川文案写作（qianchuan-writer）配置表 ORM 模型。
参照 TiktokWriterConfig 结构。
"""
from sqlalchemy import BigInteger, Column, String, Text, Boolean, ForeignKey, TIMESTAMP, func

from app.core.database import Base


class QianchuanWriterConfig(Base):
    """qianchuan-writer 工具配置（Prompt + 模型，管理端可配置）"""
    __tablename__ = "qianchuan_writer_configs"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    config_key    = Column(String(64), nullable=False, unique=True)
    system_prompt = Column(Text, nullable=True)
    ai_model_id   = Column(BigInteger, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
