"""
app/evaluation/schemas/dimension.py

eval_dimensions 请求/响应模型。
"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.evaluation.constants import EVAL_TOOL_QIANCHUAN_WRITER


class DimensionCreate(BaseModel):
    """POST /admin/evaluation/dimensions 请求体。"""

    name: str = Field(..., min_length=1, max_length=64, description="维度英文名")
    display_name: str | None = Field(None, max_length=128)
    description: str | None = None
    default_weight: Decimal = Field(..., ge=0, le=1, description="默认权重 0-1")
    score_min: int = Field(1, ge=0, le=100)
    score_max: int = Field(10, ge=0, le=100)
    prompt_template: str | None = None
    tool_code: str = Field(EVAL_TOOL_QIANCHUAN_WRITER, max_length=64)
    is_active: bool = True


class DimensionUpdate(BaseModel):
    """PUT /admin/evaluation/dimensions/{id} 请求体（所有字段可选）。"""

    display_name: str | None = Field(None, max_length=128)
    description: str | None = None
    default_weight: Decimal | None = Field(None, ge=0, le=1)
    score_min: int | None = Field(None, ge=0, le=100)
    score_max: int | None = Field(None, ge=0, le=100)
    prompt_template: str | None = None
    is_active: bool | None = None


class DimensionResponse(BaseModel):
    """eval_dimensions 响应模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tool_code: str
    name: str
    display_name: str | None
    description: str | None
    default_weight: Decimal
    score_min: int
    score_max: int
    prompt_template: str | None
    is_active: bool
    created_at: datetime | None
    updated_at: datetime | None
    deleted_at: datetime | None
