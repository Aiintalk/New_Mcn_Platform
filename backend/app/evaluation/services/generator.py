"""
app/evaluation/services/generator.py

被测输出生成器：渲染 system_prompt 模板 + 调用注入的 generate_fn 生成输出。

设计要点（spec §6.1）：
- 两步渲染：
  1. 先调 render_system_prompt 处理 {{name}}/{{soul}}/{{content_plan}}
     （**注意：soul ← input_payload['persona']**，KolContext 字段名是 persona）
  2. 再用 eval 自有渲染器（双花括号 allowlist 正则）处理 {{product_info}}/{{original_script}} 等其余字段
- 缺失值 fallback 空串
- generate_fn 是 runner 注入的 callable（方案 B），generator 不调 registry、不持 db

纯函数：不持 db、不经 registry、不 import yunwu。
"""
from __future__ import annotations

import re
from typing import Any, Awaitable, Callable

from app.services.qianchuan_writer_prompt import render_system_prompt

__all__ = ["render_generation_prompt", "generate"]


# eval 自有渲染器：匹配所有双花括号占位符 {{key}}
_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render_generation_prompt(template: str, input_payload: dict[str, Any]) -> str:
    """
    两步渲染生成 prompt。

    Step 1: render_system_prompt 处理 {{name}}/{{soul}}/{{content_plan}}。
            soul 取 input_payload['persona']（KolContext 字段名是 persona）。
    Step 2: eval 自有渲染器处理其余 {{xxx}} 占位符（如 {{product_info}}）。

    Args:
        template: version.config_payload['system_prompt_template']，含双花括号占位符
        input_payload: test_case.input_payload，提供占位符取值

    Returns:
        渲染后的 prompt 字符串。所有占位符均被替换，缺失值 fallback 空串。
    """
    payload = input_payload or {}

    # Step 1: render_system_prompt（soul ← persona）
    rendered = render_system_prompt(
        template or "",
        name=payload.get("name"),
        soul=payload.get("persona"),  # 注意：soul ← persona
        content_plan=payload.get("content_plan"),
    )

    # Step 2: eval 自有渲染器处理其余 {{xxx}} 占位符
    def _replace(match: re.Match) -> str:
        key = match.group(1)
        val = payload.get(key)
        return "" if val is None else str(val)

    return _PLACEHOLDER_RE.sub(_replace, rendered)


async def generate(
    generate_fn: Callable[..., Awaitable[str]],
    version: Any,
    test_case: Any,
) -> str:
    """
    主入口：渲染 prompt → 调 generate_fn → 返回 generated text。

    Args:
        generate_fn: runner 注入的 async callable（签名: messages=[...] -> str）
        version: EvalVersion 实例（含 .config_payload['system_prompt_template']）
        test_case: EvalTestCase 实例（含 .input_payload）

    Returns:
        AI 生成的文本
    """
    config_payload = getattr(version, "config_payload", None) or {}
    template = config_payload.get("system_prompt_template", "")
    input_payload = getattr(test_case, "input_payload", None) or {}

    rendered_prompt = render_generation_prompt(template, input_payload)

    return await generate_fn(messages=[{"role": "system", "content": rendered_prompt}])
