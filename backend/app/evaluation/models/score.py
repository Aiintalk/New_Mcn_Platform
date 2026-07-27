"""
app/evaluation/models/score.py

eval_scores — 单次 case×维度 评分结果（AI 初评 + 可选人工校准）。

唯一约束：(case_result_id, dimension_id) 唯一。
"""
from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Column,
    ForeignKey,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY

from app.core.database import Base


class EvalScore(Base):
    """一次 case 在一个维度下的评分记录（AI 评分 + 人工校准分）。"""

    __tablename__ = "eval_scores"
    __table_args__ = (
        UniqueConstraint("case_result_id", "dimension_id", name="uq_eval_scores_case_dim"),
    )

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    case_result_id  = Column(
        BigInteger,
        ForeignKey("eval_case_results.id", ondelete="CASCADE"),
        nullable=False,
    )
    dimension_id    = Column(
        BigInteger,
        ForeignKey("eval_dimensions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    weight_used     = Column(Numeric(5, 4), nullable=True)
    ai_score        = Column(Numeric(5, 2), nullable=True)
    ai_reasoning    = Column(Text, nullable=True)
    ai_strengths    = Column(ARRAY(Text), nullable=True)
    ai_weaknesses   = Column(ARRAY(Text), nullable=True)
    human_score     = Column(Numeric(5, 2), nullable=True)
    human_feedback  = Column(Text, nullable=True)
    created_at      = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at      = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
