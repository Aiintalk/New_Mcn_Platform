"""
app/evaluation/schemas/score.py

eval_scores / eval_human_labels 请求/响应模型。
"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ScoreResponse(BaseModel):
    """eval_scores 响应模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    case_result_id: int
    dimension_id: int
    weight_used: Decimal | None
    ai_score: Decimal | None
    ai_reasoning: str | None
    ai_strengths: list[str]
    ai_weaknesses: list[str]
    human_score: Decimal | None
    human_feedback: str | None
    created_at: datetime | None
    updated_at: datetime | None


class HumanLabelRequest(BaseModel):
    """PUT /operator/evaluation/scores/{id}/human-label 请求体。

    单事务原子性（spec §5.4）：在同一 db.commit 前完成
    ① 更新 eval_scores.human_score/human_feedback
    ② 插入 eval_human_labels 历史记录
    ③ 写 OperationLog
    """

    human_score: Decimal = Field(..., ge=0, le=100, description="人工校准分数")
    human_feedback: str | None = None
