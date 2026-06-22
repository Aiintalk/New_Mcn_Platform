from sqlalchemy import TIMESTAMP, BigInteger, Column, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class ServiceCredential(Base):
    __tablename__ = "service_credentials"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    provider = Column(String(64), nullable=False)
    label = Column(String(128), nullable=False)
    secret_enc = Column(Text, nullable=False)
    secret_tail = Column(String(16), nullable=False)
    status = Column(String(32), nullable=False, default="enabled")
    weight = Column(Integer, nullable=False, default=1)
    quota_limit = Column(BigInteger, nullable=True)
    quota_used = Column(BigInteger, nullable=True, default=0)
    fail_count = Column(Integer, nullable=False, default=0)
    cooldown_until = Column(TIMESTAMP(timezone=True), nullable=True)
    config = Column(JSONB, nullable=True)
    last_tested_at = Column(TIMESTAMP(timezone=True), nullable=True)
    last_latency_ms = Column(Integer, nullable=True)
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class Credential(Base):
    """AI Key 池（yunwu 等供应商）"""
    __tablename__ = "credentials"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    provider        = Column(String(64),  nullable=False)
    label           = Column(String(128), nullable=True)
    api_key         = Column(Text,        nullable=False)
    base_url        = Column(String(512), nullable=True)
    status          = Column(String(32),  nullable=False, default="active")
    active_requests = Column(Integer,     nullable=False, default=0)
    max_concurrent  = Column(Integer,     nullable=False, default=5)
    max_users       = Column(Integer,     nullable=False, default=10)
    last_tested_at  = Column(TIMESTAMP(timezone=True), nullable=True)
    last_latency_ms = Column(Integer,                  nullable=True)
    created_at      = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at      = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class AiModel(Base):
    """可用 AI 模型配置"""
    __tablename__ = "ai_models"

    id              = Column(BigInteger,  primary_key=True, autoincrement=True)
    name            = Column(String(128), nullable=False)
    provider        = Column(String(64),  nullable=False, default="yunwu")
    model_id        = Column(String(128), nullable=False, unique=True)
    status          = Column(String(32),  nullable=False, default="active")
    last_tested_at  = Column(TIMESTAMP(timezone=True), nullable=True)
    last_latency_ms = Column(Integer,                  nullable=True)
    created_at      = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at      = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
