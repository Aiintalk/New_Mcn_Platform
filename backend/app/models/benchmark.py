from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, TIMESTAMP, func
from app.core.database import Base


class BenchmarkConfig(Base):
    """管理员配置（Prompt + 模型）"""
    __tablename__ = "benchmark_configs"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    config_key    = Column(String(50), nullable=False, unique=True)
    ai_model_id   = Column(Integer, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    system_prompt = Column(Text, nullable=True)
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class BenchmarkAnalysis(Base):
    """分析记录"""
    __tablename__ = "benchmark_analyses"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    account_name     = Column(String(200), nullable=True)
    sec_user_id      = Column(String(200), nullable=True)
    top10_content    = Column(Text, nullable=True)
    recent30_content = Column(Text, nullable=True)
    profile_result   = Column(Text, nullable=True)
    plan_result      = Column(Text, nullable=True)
    model_used       = Column(String(100), nullable=True)
    tokens_used      = Column(Integer, nullable=True)
    duration_ms      = Column(Integer, nullable=True)
    status           = Column(String(20), nullable=False, default="pending")
    created_by       = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at       = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at       = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
