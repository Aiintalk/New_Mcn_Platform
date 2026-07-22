"""
app/evaluation/models/schedule_policy.py

eval_schedule_policies — 调度策略（cron 表达式触发）。

一期表已建但 scheduler 不消费（B-I4）；二期 scheduler 才读它做定时触发。
写入时必须用 croniter 校验 cron 表达式合法性。
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
from sqlalchemy.dialects.postgresql import ARRAY

from app.core.database import Base


class EvalSchedulePolicy(Base):
    """定时调度策略：按 cron + version_id + filter_tags 触发运行。"""

    __tablename__ = "eval_schedule_policies"

    id           = Column(BigInteger, primary_key=True, autoincrement=True)
    name         = Column(String(128), nullable=False)
    cron         = Column(String(64), nullable=False)
    version_id   = Column(
        BigInteger,
        ForeignKey("eval_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    filter_tags  = Column(ARRAY(Text), nullable=False, default=list)
    is_active    = Column(Boolean, nullable=False, default=True)
    created_by   = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at   = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at   = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    deleted_at   = Column(TIMESTAMP(timezone=True), nullable=True)
