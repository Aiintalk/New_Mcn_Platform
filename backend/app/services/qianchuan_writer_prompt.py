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
    profile_sections: list[tuple[str, str]] | None = None,
    product_fields: dict[str, str] | None = None,
) -> str:
    """
    渲染千川文案写作 system_prompt 模板。

    Args:
        template: 含 {{name}} / {{soul}} / {{content_plan}} 占位符的模板字符串
        name: 达人名称（None → 空字符串）
        soul: 人设/灵魂档案（None → 空字符串）
        content_plan: 内容规划（None → 空字符串）

    Returns:
        渲染后的字符串，所有占位符均被替换，无残留 {{...}}。
        工作台调用会在模板后追加完整红人档案和数据库商品事实。
    """
    values = {
        "name": name or "",
        "soul": soul or "",
        "content_plan": content_plan or "",
    }

    def _replace(match: re.Match) -> str:
        return values[match.group(1)]

    rendered = _PLACEHOLDER_RE.sub(_replace, template)
    sections: list[str] = [rendered]
    if profile_sections:
        profile_text = "\n\n".join(
            f"### {label}\n{value}" for label, value in profile_sections if value.strip()
        )
        if profile_text:
            sections.append(f"## {name or '红人'}完整档案\n{profile_text}")
    if product_fields:
        product_text = "\n".join(
            f"- {label}：{value}" for label, value in product_fields.items() if value.strip()
        )
        if product_text:
            sections.append(
                "## 当前商品事实（必须以此为准，不得编造）\n"
                f"{product_text}\n"
                "“只有我有”为是时，必须遵守独家权益约束。"
            )
    return "\n\n".join(section for section in sections if section)
