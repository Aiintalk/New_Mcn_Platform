from sqlalchemy import TIMESTAMP, BigInteger, Column, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base


class TaskJob(Base):
    __tablename__ = "task_jobs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_no = Column(String(64), nullable=False, unique=True)
    tool_code = Column(String(64), nullable=False)
    tool_name = Column(String(128), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    input_payload = Column(JSONB, nullable=True)
    result_summary = Column(JSONB, nullable=True)
    error_code = Column(String(128), nullable=True)
    error_message = Column(Text, nullable=True)
    session_id = Column(BigInteger, ForeignKey("tool_sessions.id"), nullable=True)
    output_id = Column(BigInteger, nullable=True)
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    started_at = Column(TIMESTAMP(timezone=True), nullable=True)
    finished_at = Column(TIMESTAMP(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class TaskLog(Base):
    __tablename__ = "task_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, ForeignKey("task_jobs.id", ondelete="CASCADE"), nullable=False)
    step_code = Column(String(64), nullable=False)
    step_name = Column(String(128), nullable=False)
    status = Column(String(32), nullable=False)
    message = Column(Text, nullable=True)
    payload = Column(JSONB, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
