"""
app/evaluation/schemas/schedule_policy.py

eval_schedule_policies 请求/响应模型。

cron 字段：服务端用 croniter 校验合法性，非法返回 400（spec §3.4）。
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SchedulePolicyCreate(BaseModel):
    """POST /admin/evaluation/schedule-policies 请求体。"""

    name: str = Field(..., min_length=1, max_length=128)
    cron: str = Field(..., min_length=1, max_length=64, description="cron 表达式")
    version_id: int | None = None
    filter_tags: list[str] = Field(default_factory=list)
    is_active: bool = True


class SchedulePolicyUpdate(BaseModel):
    """PUT /admin/evaluation/schedule-policies/{id} 请求体（所有字段可选）。"""

    name: str | None = Field(None, min_length=1, max_length=128)
    cron: str | None = Field(None, min_length=1, max_length=64)
    version_id: int | None = None
    filter_tags: list[str] | None = None
    is_active: bool | None = None


class SchedulePolicyResponse(BaseModel):
    """eval_schedule_policies 响应模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    cron: str
    version_id: int | None
    filter_tags: list[str]
    is_active: bool
    created_by: int | None
    created_at: datetime | None
    updated_at: datetime | None
    deleted_at: datetime | None
