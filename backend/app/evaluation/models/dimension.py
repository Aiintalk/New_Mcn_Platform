"""
app/evaluation/models/dimension.py

eval_dimensions — 评分维度（文案质量 / 种草力 / 人设一致性 等）。
"""
from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    Column,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)

from app.core.database import Base


class EvalDimension(Base):
    """评分维度：定义一种评分视角及其默认权重/分数范围/prompt 模板。"""

    __tablename__ = "eval_dimensions"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    tool_code       = Column(String(64), nullable=False)
    name            = Column(String(64), nullable=False)
    display_name    = Column(String(128), nullable=True)
    description     = Column(Text, nullable=True)
    default_weight  = Column(Numeric(5, 4), nullable=False)
    score_min       = Column(SmallInteger, nullable=False, default=1)
    score_max       = Column(SmallInteger, nullable=False, default=10)
    prompt_template = Column(Text, nullable=True)
    is_active       = Column(Boolean, nullable=False, default=True)
    created_at      = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at      = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    deleted_at      = Column(TIMESTAMP(timezone=True), nullable=True)
