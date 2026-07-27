"""
app/evaluation/services/scorer.py

AI 评分解析器：渲染评分 prompt + 调用注入的 score_fn + 解析 JSON 响应。

设计要点（spec §6.4/§6.5）：
- parse_score_response 三策略解析：
  ① 直接 json.loads → ② 正则提取 {...} → ③ 代码块提取
- score 范围校验 [score_min, score_max]，超出 clamp
- 缺失字段默认（strengths/weaknesses 空 list）
- score_fn 是 runner 注入的 callable（方案 B），scorer 不调 registry、不持 db

纯函数：不持 db、不经 registry、不 import yunwu。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.evaluation.services.rubric_resolver import build_scoring_prompt

__all__ = ["ParsedScore", "parse_score_response", "score"]


@dataclass
class ParsedScore:
    """AI 评分解析结果。"""

    score: float
    reasoning: str = ""
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)


def _clamp(val: float, lo: float, hi: float) -> float:
    """将 val 限制在 [lo, hi] 范围内。"""
    return max(lo, min(hi, val))


def _safe_float(val: Any, default: float = 0.0) -> float:
    """安全转 float，失败返回 default。"""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def parse_score_response(raw: str, score_min: int, score_max: int) -> ParsedScore:
    """
    解析 AI 评分响应为 ParsedScore。

    三策略（spec §6.5）：
      ① 直接 json.loads
      ② 正则提取第一个 {...} 子串再 json.loads
      ③ 代码块 ```json ... ``` 提取再 json.loads

    字段校验：score ∈ [score_min, score_max]，超出 clamp；缺失字段默认。
    """
    if raw is None:
        raw = ""

    data: dict[str, Any] | None = None

    # 策略 ①：直接 json.loads
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            data = parsed
    except (json.JSONDecodeError, TypeError):
        pass

    # 策略 ②：正则/子串提取第一个 {...}
    if data is None:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(raw[start : end + 1])
                if isinstance(parsed, dict):
                    data = parsed
            except (json.JSONDecodeError, TypeError):
                pass

    # 策略 ③：代码块提取
    if data is None:
        match = re.search(r"```(?:json)?\s*(.+?)\s*```", raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
                if isinstance(parsed, dict):
                    data = parsed
            except (json.JSONDecodeError, TypeError):
                pass

    # 全部解析失败 → 返回默认（score clamp 到 score_min）
    if data is None:
        return ParsedScore(
            score=float(score_min),
            reasoning="Failed to parse AI response",
            strengths=[],
            weaknesses=[],
        )

    # 字段提取 + 校验
    raw_score = data.get("score", 0)
    if raw_score is None:
        raw_score = 0
    score_val = _clamp(_safe_float(raw_score), score_min, score_max)

    reasoning = data.get("reasoning", "") or ""
    strengths = data.get("strengths", []) or []
    weaknesses = data.get("weaknesses", []) or []
    if not isinstance(strengths, list):
        strengths = []
    if not isinstance(weaknesses, list):
        weaknesses = []

    return ParsedScore(
        score=score_val,
        reasoning=str(reasoning),
        strengths=[str(s) for s in strengths],
        weaknesses=[str(w) for w in weaknesses],
    )


async def score(
    score_fn: Callable[..., Awaitable[str]],
    dimension: Any,
    rubrics: list[Any],
    generated_output: str,
    context: dict[str, Any],
) -> ParsedScore:
    """
    主入口：渲染评分 prompt → 调 score_fn → 解析响应。

    Args:
        score_fn: runner 注入的 async callable（签名: messages=[...] -> str）
        dimension: EvalDimension 实例（含 .prompt_template / .score_min / .score_max）
        rubrics: EvalRubric 列表（已选好）
        generated_output: 被测输出文本
        context: 占位符取值（如 {"persona": "...", "product_info": "..."}）

    Returns:
        ParsedScore 解析结果
    """
    full_context = {**(context or {}), "generated_output": generated_output or ""}
    scoring_prompt = build_scoring_prompt(dimension, rubrics, full_context)

    raw = await score_fn(messages=[{"role": "user", "content": scoring_prompt}])

    score_min = getattr(dimension, "score_min", 1) or 1
    score_max = getattr(dimension, "score_max", 10) or 10
    return parse_score_response(raw, score_min, score_max)
