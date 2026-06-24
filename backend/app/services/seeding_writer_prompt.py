"""
app/services/seeding_writer_prompt.py

种草内容仿写 Prompt 模板渲染。
占位符（14 个）：
  {{name}}                    → kols.name
  {{soul}}                    → kols.persona
  {{content_plan}}            → kols.content_plan
  {{product_name}}            → products.name
  {{product_category}}        → products.category
  {{product_price}}           → products.price
  {{product_selling_points}}  → products.selling_points
  {{product_target_audience}} → products.target_audience
  {{product_scenario}}        → products.scenario
  {{references}}              → references 拼接文本
  {{transcript}}              → 对标文案
  {{structure_analysis}}      → 结构拆解结果
  {{topic}}                   → 种草角度/选题
  {{raw_text}}                → 产品资料原文

处理方式：单次正则一次性替换（避免 soul / transcript 内容含 {{xxx}} 时二次替换）。
缺失值 fallback 为空字符串，不抛异常。
"""
import re

# 匹配 14 个占位符中的任意一个，支持 {{ name }} / {{\nname\n}} 等空白变体
_PLACEHOLDER_RE = re.compile(
    r"\{\{\s*("
    r"name|soul|content_plan|"
    r"product_name|product_category|product_price|"
    r"product_selling_points|product_target_audience|product_scenario|"
    r"references|transcript|structure_analysis|topic|raw_text"
    r")\s*\}\}"
)

# 全部合法占位符 key，用于 values dict
_ALL_KEYS = (
    "name", "soul", "content_plan",
    "product_name", "product_category", "product_price",
    "product_selling_points", "product_target_audience", "product_scenario",
    "references", "transcript", "structure_analysis", "topic", "raw_text",
)


def render_prompt(
    template: str,
    *,
    name: str | None = None,
    soul: str | None = None,
    content_plan: str | None = None,
    product_name: str | None = None,
    product_category: str | None = None,
    product_price: str | None = None,
    product_selling_points: str | None = None,
    product_target_audience: str | None = None,
    product_scenario: str | None = None,
    references: str | None = None,
    transcript: str | None = None,
    structure_analysis: str | None = None,
    topic: str | None = None,
    raw_text: str | None = None,
) -> str:
    """
    渲染 seeding-writer Prompt 模板。

    单次正则扫描替换所有 14 个占位符。
    缺失值（None）替换为空字符串。

    Args:
        template: 含占位符的模板字符串
        name: 达人名称
        soul: 人设/灵魂档案
        content_plan: 内容规划
        product_name: 产品名称
        product_category: 产品品类
        product_price: 产品价格
        product_selling_points: 核心卖点
        product_target_audience: 目标人群
        product_scenario: 使用场景
        references: 素材参考拼接文本
        transcript: 对标文案
        structure_analysis: 结构拆解结果
        topic: 选题/种草角度
        raw_text: 产品资料原文

    Returns:
        渲染后的字符串，所有占位符均被替换
    """
    values = {
        "name": name or "",
        "soul": soul or "",
        "content_plan": content_plan or "",
        "product_name": product_name or "",
        "product_category": product_category or "",
        "product_price": product_price or "",
        "product_selling_points": product_selling_points or "",
        "product_target_audience": product_target_audience or "",
        "product_scenario": product_scenario or "",
        "references": references or "",
        "transcript": transcript or "",
        "structure_analysis": structure_analysis or "",
        "topic": topic or "",
        "raw_text": raw_text or "",
    }

    def _replace(match: re.Match) -> str:
        return values[match.group(1)]

    return _PLACEHOLDER_RE.sub(_replace, template)
