"""
app/evaluation/models/case_result.py

eval_case_results — 单次 case×run 的被测生成结果（归一化存一次，维度评分引用）。

唯一约束：(run_id, test_case_id) 唯一。
"""
from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Column,
    ForeignKey,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class EvalCaseResult(Base):
    """一次运行中一个 test_case 的被测输出 + 元数据 + 输入快照。"""

    __tablename__ = "eval_case_results"
    __table_args__ = (
        UniqueConstraint("run_id", "test_case_id", name="uq_eval_case_results_run_testcase"),
    )

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id           = Column(
        BigInteger,
        ForeignKey("eval_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    test_case_id     = Column(
        BigInteger,
        ForeignKey("eval_test_cases.id", ondelete="RESTRICT"),
        nullable=False,
    )
    generated_output = Column(Text, nullable=True)
    output_payload   = Column(JSONB, nullable=True)
    input_snapshot   = Column(JSONB, nullable=True)
    created_at       = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
