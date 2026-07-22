"""
app/evaluation/schemas/version.py

eval_versions 请求/响应模型。

config_payload 来源（spec §4.4）：
- 无 source_kol_id：admin 直接填 config_payload（或用顶层的 scoring_* 字段合并）
- 有 source_kol_id：服务端执行「关联维护三步」固化为 system_prompt_template
  （resolve_prompt → QianchuanWriterConfig.system_prompt 兜底 → kol_ctx 校验）

顶层 scoring_model_id/provider/adapter 字段是为了方便前端直接填，
服务端会合并进 config_payload 后落库。
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.evaluation.constants import DEFAULT_ADAPTER, EVAL_TOOL_QIANCHUAN_WRITER


class VersionCreate(BaseModel):
    """POST /admin/evaluation/versions 请求体。

    若提供 source_kol_id：服务端执行「关联维护三步」（resolve_prompt + cfg 兜底 +
    kol_ctx 校验），固化为 config_payload.system_prompt_template（带占位符模板）。
    若 source_kol_id 为空：跳过三步，admin 直接填 config_payload。
    scoring_model_id/provider/adapter 由请求体直接传，服务端合并进 config_payload。
    """

    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    config_payload: dict[str, Any] = Field(default_factory=dict)
    parent_version_id: int | None = None
    source_kol_id: int | None = Field(
        None, description="可选：执行关联维护三步抠 system_prompt 模板"
    )
    auto_run_on_create: bool = False
    auto_run_tags: list[str] = Field(default_factory=list)
    tool_code: str = Field(EVAL_TOOL_QIANCHUAN_WRITER, max_length=64)
    is_active: bool = True
    # 评委身份三件套（v2，spec §2.9.2）：顶层便利字段，服务端合并入 config_payload
    scoring_model_id: str | None = None
    scoring_provider: str | None = None
    scoring_adapter: str | None = Field(DEFAULT_ADAPTER, max_length=64)


class VersionClone(BaseModel):
    """POST /admin/evaluation/versions/{id}/clone 请求体。

    服务端自动拷贝 parent 的 config_payload 并设置 parent_version_id。
    """

    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    auto_run_on_create: bool = False
    auto_run_tags: list[str] = Field(default_factory=list)
    is_active: bool = True
    # 可选覆盖
    config_payload_overrides: dict[str, Any] = Field(default_factory=dict)


class VersionResponse(BaseModel):
    """eval_versions 响应模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tool_code: str
    name: str
    description: str | None
    config_payload: dict[str, Any]
    parent_version_id: int | None
    source_kol_id: int | None
    auto_run_on_create: bool
    auto_run_tags: list[str]
    is_active: bool
    created_by: int | None
    created_at: datetime | None
    updated_at: datetime | None
    deleted_at: datetime | None
