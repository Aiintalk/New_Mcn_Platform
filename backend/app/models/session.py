from sqlalchemy import TIMESTAMP, BigInteger, Column, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base


class ToolSession(Base):
    __tablename__ = "tool_sessions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tool_code = Column(String(64), nullable=False)
    current_step = Column(String(64), nullable=True)
    context = Column(JSONB, nullable=True)
    drafts = Column(JSONB, nullable=True)
    messages = Column(JSONB, nullable=True)
    status = Column(String(32), nullable=False, default="draft")
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
