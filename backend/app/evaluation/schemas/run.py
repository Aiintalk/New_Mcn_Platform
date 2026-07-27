"""
app/evaluation/schemas/run.py

eval_runs 请求/响应模型。
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.evaluation.constants import TRIGGER_TYPE_MANUAL


class RunTrigger(BaseModel):
    """POST /operator/evaluation/runs 请求体。

    一期自动绑定 default 策略（请求体不传 strategy_id）。
    """

    version_id: int
    filter_tags: list[str] = Field(default_factory=list)
    name: str | None = None
    trigger_type: str = Field(TRIGGER_TYPE_MANUAL, max_length=32)


class RunResponse(BaseModel):
    """eval_runs 响应模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    version_id: int
    strategy_id: int
    name: str
    trigger_type: str
    status: str
    filter_tags: list[str]
    total_cases: int
    completed_cases: int
    failed_cases: int
    metadata_: dict[str, Any] = Field(
        default_factory=dict, alias="metadata_"
    )
    created_by: int | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime | None
