"""
app/evaluation/models/test_case.py

eval_test_cases — 测试集样本（每次运行时按标签/ID 选子集驱动）。
"""
from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from app.core.database import Base


class EvalTestCase(Base):
    """测试样本：input_payload 为工具特定输入；tags 为多场景筛选标签。"""

    __tablename__ = "eval_test_cases"

    id             = Column(BigInteger, primary_key=True, autoincrement=True)
    tool_code      = Column(String(64), nullable=False)
    name           = Column(String(255), nullable=False)
    description    = Column(Text, nullable=True)
    input_payload  = Column(JSONB, nullable=False)
    expected_output = Column(Text, nullable=True)
    tags           = Column(ARRAY(Text), nullable=False, default=list)
    is_active      = Column(Boolean, nullable=False, default=True)
    created_by     = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by     = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at     = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at     = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    deleted_at     = Column(TIMESTAMP(timezone=True), nullable=True)
