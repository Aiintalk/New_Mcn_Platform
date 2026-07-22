"""
app/evaluation/schemas/compare.py

GET /operator/evaluation/compare 响应模型，对应 services.comparator.ComparisonReport。
"""
from pydantic import BaseModel, Field


class DimensionDelta(BaseModel):
    dimension_id: int
    dimension_name: str | None
    avg_a: float
    avg_b: float
    delta: float


class CaseDelta(BaseModel):
    test_case_id: int
    test_case_name: str | None
    avg_a: float
    avg_b: float
    delta: float
    direction: str


class CompareResponse(BaseModel):
    """ComparisonReport 序列化结果。"""

    run_a_id: int
    run_b_id: int
    overall_avg_a: float
    overall_avg_b: float
    overall_delta: float
    dimension_deltas: list[DimensionDelta] = Field(default_factory=list)
    case_deltas: list[CaseDelta] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
