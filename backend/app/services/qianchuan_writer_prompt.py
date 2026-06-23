"""
app/services/qianchuan_writer_prompt.py

千川文案写作 Prompt 模板渲染。
占位符：{{name}} / {{soul}} / {{content_plan}}
缺失值 fallback 为空字符串，不抛异常。
"""
import re

_PLACEHOLDER_RE = re.compile(r"\{\{\s*(name|soul|content_plan)\s*\}\}")


def render_system_prompt(
    template: str,
    *,
    name: str | None,
    soul: str | None,
    content_plan: str | None,
) -> str:
    """
    渲染千川文案写作 system_prompt 模板。

    Args:
        template: 含 {{name}} / {{soul}} / {{content_plan}} 占位符的模板字符串
        name: 达人名称（None → 空字符串）
        soul: 人设/灵魂档案（None → 空字符串）
        content_plan: 内容规划（None → 空字符串）

    Returns:
        渲染后的字符串，所有占位符均被替换，无残留 {{...}}
    """
    values = {
        "name": name or "",
        "soul": soul or "",
        "content_plan": content_plan or "",
    }

    def _replace(match: re.Match) -> str:
        return values[match.group(1)]

    return _PLACEHOLDER_RE.sub(_replace, template)
