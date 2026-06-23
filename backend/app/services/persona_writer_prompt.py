"""
app/services/persona_writer_prompt.py

人设脚本仿写 Prompt 模板渲染。
占位符：
  {{name}}               → kols.name
  {{soul}}               → kols.persona
  {{content_plan}}       → kols.content_plan
  {{transcript}}         → 对标文案
  {{structure_analysis}} → Step 3.1 拆解结果
  {{topic}}              → 选题
  {{is_custom}}          → 'true' / 'false'

双模式语法（仅 writing_prompt 使用）：
  {{is_custom}}...{{/is_custom}}     → is_custom=True 时保留，False 时移除
  {{!is_custom}}...{{/!is_custom}}   → is_custom=False 时保留，True 时移除

处理顺序：
  1. 先处理条件块（{{is_custom}}/{{!is_custom}}）
  2. 再用正则一次性替换所有简单占位符（避免 soul 含 {{name}} 时二次替换）

缺失值 fallback 为空字符串，不抛异常。
"""
import re

# 简单占位符正则：匹配 {{ name }} / {{soul}} / {{ transcript }} 等
_PLACEHOLDER_RE = re.compile(
    r"\{\{\s*(name|soul|content_plan|transcript|structure_analysis|topic|is_custom)\s*\}\}"
)

# 条件块正则：{{is_custom}}...{{/is_custom}} 和 {{!is_custom}}...{{/!is_custom}}
_IF_CUSTOM_RE = re.compile(r"\{\{is_custom\}\}(.*?)\{\{/is_custom\}\}", re.DOTALL)
_IF_NOT_CUSTOM_RE = re.compile(r"\{\{!is_custom\}\}(.*?)\{\{/!is_custom\}\}", re.DOTALL)


def _strip_conditional_blocks(template: str, *, is_custom: bool) -> str:
    """
    处理 writing_prompt 中的双模式条件块。

    - is_custom=True:  保留 {{is_custom}}...{{/is_custom}}，移除 {{!is_custom}}...{{/!is_custom}}
    - is_custom=False: 保留 {{!is_custom}}...{{/!is_custom}}，移除 {{is_custom}}...{{/is_custom}}
    """
    if is_custom:
        # 保留 is_custom 块内容，移除 !is_custom 块
        template = _IF_CUSTOM_RE.sub(r"\1", template)
        template = _IF_NOT_CUSTOM_RE.sub("", template)
    else:
        # 保留 !is_custom 块内容，移除 is_custom 块
        template = _IF_CUSTOM_RE.sub("", template)
        template = _IF_NOT_CUSTOM_RE.sub(r"\1", template)
    return template


def render_prompt(
    template: str,
    *,
    name: str | None = None,
    soul: str | None = None,
    content_plan: str | None = None,
    transcript: str | None = None,
    structure_analysis: str | None = None,
    topic: str | None = None,
    is_custom: bool | None = None,
) -> str:
    """
    渲染 persona-writer Prompt 模板。

    Args:
        template: 含占位符的模板字符串
        name: 达人名称（None → 空字符串）
        soul: 人设/灵魂档案（None → 空字符串）
        content_plan: 内容规划（None → 空字符串）
        transcript: 对标文案（None → 空字符串）
        structure_analysis: 结构拆解结果（None → 空字符串）
        topic: 选题（None → 空字符串）
        is_custom: 是否自定义选题模式（None → 不处理条件块，视为 True）

    Returns:
        渲染后的字符串，所有占位符均被替换，无残留 {{...}}
    """
    # Step 1: 处理条件块（仅在 is_custom 非 None 时）
    effective_is_custom = True if is_custom is None else is_custom
    result = _strip_conditional_blocks(template, is_custom=effective_is_custom)

    # Step 2: 正则一次性替换所有简单占位符
    values = {
        "name": name or "",
        "soul": soul or "",
        "content_plan": content_plan or "",
        "transcript": transcript or "",
        "structure_analysis": structure_analysis or "",
        "topic": topic or "",
        "is_custom": "true" if effective_is_custom else "false",
    }

    def _replace(match: re.Match) -> str:
        return values[match.group(1)]

    result = _PLACEHOLDER_RE.sub(_replace, result)
    return result
