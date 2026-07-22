"""
app/evaluation/schemas/__init__.py

AIGC 评测模块的 Pydantic 请求/响应模型聚合（spec §9 接口契约 + plan Phase 4 Task 1）。
"""
from app.evaluation.schemas.compare import CompareResponse
from app.evaluation.schemas.dimension import (
    DimensionCreate,
    DimensionResponse,
    DimensionUpdate,
)
from app.evaluation.schemas.rubric import (
    RubricBatchUpdate,
    RubricItemInput,
    RubricResponse,
)
from app.evaluation.schemas.run import RunResponse, RunTrigger
from app.evaluation.schemas.schedule_policy import (
    SchedulePolicyCreate,
    SchedulePolicyResponse,
    SchedulePolicyUpdate,
)
from app.evaluation.schemas.score import (
    HumanLabelRequest,
    ScoreResponse,
)
from app.evaluation.schemas.test_case import (
    TestCaseCreate,
    TestCaseResponse,
    TestCaseUpdate,
)
from app.evaluation.schemas.version import (
    VersionClone,
    VersionCreate,
    VersionResponse,
)

__all__ = [
    "CompareResponse",
    "DimensionCreate",
    "DimensionResponse",
    "DimensionUpdate",
    "HumanLabelRequest",
    "RubricBatchUpdate",
    "RubricItemInput",
    "RubricResponse",
    "RunResponse",
    "RunTrigger",
    "SchedulePolicyCreate",
    "SchedulePolicyResponse",
    "SchedulePolicyUpdate",
    "ScoreResponse",
    "TestCaseCreate",
    "TestCaseResponse",
    "TestCaseUpdate",
    "VersionClone",
    "VersionCreate",
    "VersionResponse",
]
