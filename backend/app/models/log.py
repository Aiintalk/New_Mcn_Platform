from sqlalchemy import TIMESTAMP, BigInteger, Column, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    username = Column(String(64), nullable=True)
    role = Column(String(32), nullable=True)
    action = Column(String(128), nullable=False)
    target_type = Column(String(64), nullable=True)
    target_id = Column(BigInteger, nullable=True)
    detail = Column(JSONB, nullable=True)
    ip = Column(String(64), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class ExternalServiceLog(Base):
    __tablename__ = "external_service_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    service = Column(String(64), nullable=False)
    action = Column(String(128), nullable=False)
    task_id = Column(BigInteger, ForeignKey("task_jobs.id"), nullable=True)
    credential_id = Column(BigInteger, ForeignKey("service_credentials.id"), nullable=True)
    request_body = Column(JSONB, nullable=True)
    response_body = Column(JSONB, nullable=True)
    tokens_in = Column(Integer, nullable=True)
    tokens_out = Column(Integer, nullable=True)
    tokens_used = Column(Integer, nullable=True)
    credits = Column(Numeric, nullable=True)
    audio_seconds = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    status = Column(String(32), nullable=False)
    error_code = Column(String(128), nullable=True)
    error_message = Column(Text, nullable=True)
    request_hash = Column(String(128), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class AiCallLog(Base):
    """yunwu AI 调用明细日志"""
    __tablename__ = "ai_call_logs"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id       = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    feature       = Column(String(128), nullable=True)
    model_id      = Column(String(128), nullable=True)
    credential_id = Column(BigInteger, ForeignKey("credentials.id"), nullable=True)
    input_tokens  = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    latency_ms    = Column(Integer, nullable=True)
    status        = Column(String(32), nullable=False, default="success")
    error_message = Column(Text, nullable=True)
    created_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
