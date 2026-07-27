"""
app/evaluation/schemas/rubric.py

eval_rubrics 请求/响应模型。
PUT /admin/evaluation/dimensions/{id}/rubrics 整批替换：客户端传完整 rubric 列表，
服务端把旧 active 行置 is_active=False、插入新行。
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RubricItemInput(BaseModel):
    """单条 rubric 输入（整批替换时用）。"""

    level: int = Field(..., ge=0, le=100, description="分数等级")
    criteria: str | None = None
    scenario_tag: str | None = Field(None, max_length=64, description="业务场景变体标记")
    is_active: bool = True


class RubricBatchUpdate(BaseModel):
    """PUT /admin/evaluation/dimensions/{id}/rubrics 请求体。"""

    rubrics: list[RubricItemInput] = Field(default_factory=list)


class RubricResponse(BaseModel):
    """eval_rubrics 响应模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    dimension_id: int
    level: int
    criteria: str | None
    scenario_tag: str | None
    is_active: bool
    created_at: datetime | None
    updated_at: datetime | None
