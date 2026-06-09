from sqlalchemy import TIMESTAMP, BigInteger, Column, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base


class Output(Base):
    __tablename__ = "outputs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    tool_code = Column(String(64), nullable=False)
    tool_name = Column(String(128), nullable=False)
    task_id = Column(BigInteger, ForeignKey("task_jobs.id"), nullable=True)
    content = Column(Text, nullable=True)
    content_json = Column(JSONB, nullable=True)
    word_count = Column(Integer, nullable=True)
    file_id = Column(BigInteger, nullable=True)
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    deleted_at = Column(TIMESTAMP(timezone=True), nullable=True)
