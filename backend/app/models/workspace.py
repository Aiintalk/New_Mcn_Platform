from sqlalchemy import TIMESTAMP, BigInteger, Column, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base


class WorkspaceTool(Base):
    __tablename__ = "workspace_tools"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tool_code = Column(String(64), nullable=False, unique=True)
    tool_name = Column(String(128), nullable=False)
    category = Column(String(64), nullable=True)
    description = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="dev")
    tags = Column(JSONB, nullable=True)
    config = Column(JSONB, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
