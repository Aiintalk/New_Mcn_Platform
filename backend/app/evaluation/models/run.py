"""
app/evaluation/models/run.py

eval_runs — 一次评测运行。

strategy_id 一期恒指 default 策略，二期切换策略无需改 run 结构。
metadata.resolved_scoring 在 run 启动时由 runner 写入，固化实际评委身份（B-C2）。
"""
from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from app.core.database import Base


class EvalRun(Base):
    """一次评测运行：pending -> running -> completed/failed。"""

    __tablename__ = "eval_runs"

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    version_id       = Column(
        BigInteger,
        ForeignKey("eval_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    strategy_id      = Column(
        BigInteger,
        ForeignKey("eval_strategies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name             = Column(String(255), nullable=False)
    trigger_type     = Column(String(32), nullable=False)
    status           = Column(String(32), nullable=False, default="pending")
    filter_tags      = Column(ARRAY(Text), nullable=False, default=list)
    total_cases      = Column(Integer, nullable=False, default=0)
    completed_cases  = Column(Integer, nullable=False, default=0)
    failed_cases     = Column(Integer, nullable=False, default=0)
    metadata_        = Column("metadata", JSONB, nullable=False, default=dict)
    created_by       = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    started_at       = Column(TIMESTAMP(timezone=True), nullable=True)
    finished_at      = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at       = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
