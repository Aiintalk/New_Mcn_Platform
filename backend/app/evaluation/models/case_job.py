"""
app/evaluation/models/case_job.py

eval_case_jobs — 异步运行按 case 拆分的 job（方案 C：arq+Redis，Phase 2）。

一个 run 拆成 N 个 case-job（每 test_case 一行）；arq worker 从 Redis 取 job 执行。
status：pending → running → done/failed；cancel → cancelled。
唯一约束：(run_id, test_case_id) 唯一。
"""
from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)

from app.core.database import Base


class EvalCaseJob(Base):
    """一次 run 中一个 test_case 的异步执行 job（worker 消费单元）。"""

    __tablename__ = "eval_case_jobs"
    __table_args__ = (
        UniqueConstraint("run_id", "test_case_id", name="uq_eval_case_jobs_run_testcase"),
    )

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id        = Column(
        BigInteger,
        ForeignKey("eval_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    test_case_id  = Column(
        BigInteger,
        ForeignKey("eval_test_cases.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status        = Column(String(20), nullable=False, default="pending")
    attempts      = Column(Integer, nullable=False, default=0)
    max_attempts  = Column(Integer, nullable=False, default=3)
    last_error    = Column(Text, nullable=True)
    enqueued_at   = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    started_at    = Column(TIMESTAMP(timezone=True), nullable=True)
    finished_at   = Column(TIMESTAMP(timezone=True), nullable=True)
