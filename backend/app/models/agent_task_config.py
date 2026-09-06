from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    CheckConstraint,
    Column,
    ForeignKey,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class AgentTaskConfig(Base):
    __tablename__ = "agent_task_configs"
    __table_args__ = (
        CheckConstraint(
            "jsonb_typeof(selected_project_ids) = 'array'",
            name="chk_agent_task_configs_selected_project_ids_array",
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    agent_code = Column(String(64), nullable=False, unique=True)
    selected_project_ids = Column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    report_root_ref = Column(Text, nullable=True)
    updated_by = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
