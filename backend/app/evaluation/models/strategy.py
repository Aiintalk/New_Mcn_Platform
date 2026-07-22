"""
app/evaluation/models/strategy.py

eval_strategies — 评测策略（v2 一期架构预留）。

一个策略 = 从评测超集组合的实例配置：选 test_case 子集 + rubric 场景变体 + 权重覆盖 +
评委三件套覆盖（model/provider/adapter）。一期 seed 一条 default 策略，所有 run 绑定它。

唯一约束：UNIQUE (tool_code, name) WHERE deleted_at IS NULL（防重复 seed default）。
评委三件套 override（B-C3）：策略层 model/provider/adapter 均可覆盖版本快照。
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
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class EvalStrategy(Base):
    """评测策略实例（对应工作台 per-KOL/业务配置概念）。"""

    __tablename__ = "eval_strategies"

    id                          = Column(BigInteger, primary_key=True, autoincrement=True)
    tool_code                   = Column(String(64), nullable=False)
    name                        = Column(String(128), nullable=False)
    description                 = Column(Text, nullable=True)
    test_case_selector          = Column(JSONB, nullable=False, default=dict)
    dimension_weight_overrides  = Column(JSONB, nullable=False, default=dict)
    rubric_selector             = Column(JSONB, nullable=False, default=dict)
    scoring_model_override      = Column(String(128), nullable=True)
    scoring_provider_override   = Column(String(64), nullable=True)
    scoring_adapter_override    = Column(String(64), nullable=True)
    business_type               = Column(String(64), nullable=True)
    kol_id                      = Column(
        BigInteger,
        ForeignKey("kols.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active                   = Column(Boolean, nullable=False, default=True)
    created_by                  = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at                  = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at                  = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    deleted_at                  = Column(TIMESTAMP(timezone=True), nullable=True)


# 部分唯一索引：仅对未软删行强制 (tool_code, name) 唯一，允许软删后重建。
Index(
    "uq_eval_strategies_active_tool_name",
    EvalStrategy.tool_code,
    EvalStrategy.name,
    unique=True,
    postgresql_where=EvalStrategy.deleted_at.is_(None),
)
