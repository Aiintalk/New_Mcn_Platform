"""
app/evaluation/schemas/test_case.py

eval_test_cases 请求/响应模型。
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.evaluation.constants import EVAL_TOOL_QIANCHUAN_WRITER


class TestCaseCreate(BaseModel):
    """POST /operator/evaluation/test-cases 请求体。"""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    input_payload: dict[str, Any] = Field(..., description="工具特定输入 JSON")
    expected_output: str | None = None
    tags: list[str] = Field(default_factory=list)
    tool_code: str = Field(EVAL_TOOL_QIANCHUAN_WRITER, max_length=64)
    is_active: bool = True


class TestCaseUpdate(BaseModel):
    """PUT /operator/evaluation/test-cases/{id} 请求体（所有字段可选）。"""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    input_payload: dict[str, Any] | None = None
    expected_output: str | None = None
    tags: list[str] | None = None
    is_active: bool | None = None


class TestCaseResponse(BaseModel):
    """eval_test_cases 响应模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tool_code: str
    name: str
    description: str | None
    input_payload: dict[str, Any]
    expected_output: str | None
    tags: list[str]
    is_active: bool
    created_by: int | None
    updated_by: int | None
    created_at: datetime | None
    updated_at: datetime | None
    deleted_at: datetime | None
