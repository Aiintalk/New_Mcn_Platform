"""
app/evaluation/models/human_label.py

eval_human_labels — 人工校准历史（每次校准记一条）。

人工校准写入策略（spec §5.4）：同一事务内 ① 更新 eval_scores.human_score/human_feedback
② 插入 eval_human_labels 历史记录。当前人工分以 eval_scores.human_score 为准。
"""
from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Column,
    ForeignKey,
    Numeric,
    Text,
    func,
)

from app.core.database import Base


class EvalHumanLabel(Base):
    """人工校准历史记录。"""

    __tablename__ = "eval_human_labels"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    score_id    = Column(
        BigInteger,
        ForeignKey("eval_scores.id", ondelete="CASCADE"),
        nullable=False,
    )
    old_score   = Column(Numeric(5, 2), nullable=True)
    new_score   = Column(Numeric(5, 2), nullable=True)
    feedback    = Column(Text, nullable=True)
    labeled_by  = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at  = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
