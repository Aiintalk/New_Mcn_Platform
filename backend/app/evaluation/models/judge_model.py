"""
app/evaluation/models/judge_model.py

eval_judge_models — 评委模型候选池（v2 一期建表预留、内容后填）。

评测自管模型身份（§2.9.1）：model_id 当字符串自存，不 FK 引用 ai_models，
不走 credentials 表（适配器内部解决凭证）。一期 seed 极简或留空。

唯一约束：UNIQUE (model_id, adapter) WHERE deleted_at IS NULL（同模型同适配器不重复登记）。
"""
from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)

from app.core.database import Base


class EvalJudgeModel(Base):
    """评委模型候选池登记行。"""

    __tablename__ = "eval_judge_models"

    id                     = Column(BigInteger, primary_key=True, autoincrement=True)
    model_id               = Column(String(128), nullable=False)
    provider               = Column(String(64), nullable=False)
    adapter                = Column(String(64), nullable=False)
    applicable_output_type = Column(String(64), nullable=False)
    note                   = Column(Text, nullable=True)
    is_active              = Column(Boolean, nullable=False, default=True)
    created_by             = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at             = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at             = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    deleted_at             = Column(TIMESTAMP(timezone=True), nullable=True)


# 部分唯一索引：同 model_id 同 adapter 仅在未软删时唯一。
Index(
    "uq_eval_judge_models_active_model_adapter",
    EvalJudgeModel.model_id,
    EvalJudgeModel.adapter,
    unique=True,
    postgresql_where=EvalJudgeModel.deleted_at.is_(None),
)
