"""
app/evaluation/services/rubric_resolver.py

把 dimension + rubrics 渲染为评分 prompt 文本。

职责：
- 按 dimension.prompt_template 渲染评分 prompt
- 拼接 rubrics 的 level×criteria 文本（按 level 降序）填入 {{rubric_text}}
- 双花括号占位符渲染（{{generated_output}}/{{persona}}/{{product_info}} 等）
- 一期 scenario_tag 不参与选择——传入的 rubrics 已由调用方选好
- 缺失值 fallback 空串

纯函数：不持 db、不调 AI、不经 registry。
"""
from __future__ import annotations

import re
from typing import Any

__all__ = ["build_scoring_prompt"]


# 双花括号占位符正则：{{key}}，key 为字母/数字/下划线
_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def _format_rubric_text(rubrics: list[Any]) -> str:
    """
    把 rubrics 列表拼接为评分标准文本。

    按 level 降序排列（高分在前），每行格式："{level}分：{criteria}"。
    """
    if not rubrics:
        return ""
    lines: list[str] = []
    for r in sorted(rubrics, key=lambda x: getattr(x, "level", 0), reverse=True):
        level = getattr(r, "level", 0)
        criteria = getattr(r, "criteria", None) or ""
        lines.append(f"{level}分：{criteria}")
    return "\n".join(lines)


def build_scoring_prompt(dimension: Any, rubrics: list[Any], context: dict[str, Any]) -> str:
    """
    按 dimension.prompt_template 渲染评分 prompt。

    Args:
        dimension: EvalDimension 实例（含 .prompt_template / .score_min / .score_max）
        rubrics: EvalRubric 列表（已由调用方按 scenario_tag 选好，本期不做选择）
        context: 占位符取值字典（如 {"generated_output": "...", "persona": "...",
                  "product_info": "..."}）

    Returns:
        渲染后的评分 prompt 字符串。所有 {{xxx}} 占位符均被替换，缺失值 fallback 空串。
    """
    template = ""
    if dimension is not None:
        template = getattr(dimension, "prompt_template", None) or ""

    # 构建 rubric_text 并注入 context
    values: dict[str, str] = {"rubric_text": _format_rubric_text(rubrics)}
    if context:
        for key, val in context.items():
            values[key] = "" if val is None else str(val)

    def _replace(match: re.Match) -> str:
        return values.get(match.group(1), "")

    return _PLACEHOLDER_RE.sub(_replace, template)
