"""
app/evaluation/models/rubric.py

eval_rubrics — 维度下的评分细则（每等级一条；按 scenario_tag 维护业务场景变体）。

唯一约束：UNIQUE (dimension_id, scenario_tag, level) WHERE is_active = true NULLS NOT DISTINCT
（PG15+ 支持），防止同维度同场景同 level 录两条导致 rubric_resolver 拼接歧义。
"""
from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    func,
)

from app.core.database import Base


class EvalRubric(Base):
    """维度下的评分细则行：(dimension, scenario_tag, level) -> criteria 文本。"""

    __tablename__ = "eval_rubrics"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    dimension_id  = Column(
        BigInteger,
        ForeignKey("eval_dimensions.id", ondelete="CASCADE"),
        nullable=False,
    )
    level         = Column(SmallInteger, nullable=False)
    criteria      = Column(Text, nullable=True)
    scenario_tag  = Column(String(64), nullable=True)
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


# 部分唯一索引：仅对 is_active=true 的行强制 (dim, scenario, level) 唯一；
# NULLS NOT DISTINCT 让 NULL scenario_tag 也算重复（防 default 变体录重）。
Index(
    "uq_eval_rubrics_active_dim_scenario_level",
    EvalRubric.dimension_id,
    EvalRubric.scenario_tag,
    EvalRubric.level,
    unique=True,
    postgresql_where=EvalRubric.is_active.is_(True),
    postgresql_nulls_not_distinct=True,
)
