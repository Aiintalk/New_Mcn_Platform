"""
app/services/qianchuan_review_service.py

千川脚本复盘核心业务逻辑：
- 脚本与 Excel 数据合并匹配（Python 等价于原始 JS 逻辑）
- 构建发给 AI 的 User Message
- 流式生成复盘报告（复用 yunwu.chat_stream）
"""
import re
from dataclasses import dataclass
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import yunwu as yunwu_adapter
from app.tools.qianchuan_review.prompts import PROMPT_WITH_EXCEL, PROMPT_WITHOUT_EXCEL

TOOL_CODE = "qianchuan-review"
TOOL_NAME = "千川脚本复盘"
DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_SCRIPTS = 30
CONTENT_TRUNCATE = 2000
MATCH_KEY_LEN = 12
MATCH_SUB_LEN = 6


@dataclass
class ScriptItem:
    title: str
    content: str


@dataclass
class ExcelRow:
    video_theme: str
    spend: str | None = None
    impressions: str | None = None
    ctr: str | None = None
    three_sec_rate: str | None = None
    conversions: str | None = None
    cost_per_conversion: str | None = None
    roi: str | None = None
    cpm: str | None = None
    time_range: str | None = None


def _normalize(text: str) -> str:
    """清除标点、特殊字符、空白，取前 MATCH_KEY_LEN 字，用于模糊匹配。"""
    return re.sub(r"[，。！？、#@\s]", "", text)[:MATCH_KEY_LEN]


def _is_match(a_norm: str, b_norm: str) -> bool:
    """双向 includes 判断（与原始 JS 逻辑等价）。"""
    return (
        a_norm[:MATCH_SUB_LEN] in b_norm
        or b_norm[:MATCH_SUB_LEN] in a_norm
    )


def merge_scripts_and_excel(
    scripts: list[ScriptItem],
    excel_data: list[ExcelRow],
) -> list[dict]:
    """
    将脚本列表与 Excel 数据合并：
    1. 对每条脚本，在 Excel 中找匹配行（模糊匹配前12字）
    2. 匹配到：用 Excel video_theme 覆盖标题，附上所有指标
    3. 未匹配到：保留脚本标题，指标为 None
    4. Excel 中有但脚本无对应的行：追加到末尾，content 为空
    5. 整体按 spend 降序排列，无消耗排后面
    """
    merged: list[dict] = []
    matched_excel_indices: set[int] = set()

    for script in scripts:
        script_norm = _normalize(script.title)
        matched_row: ExcelRow | None = None
        matched_idx: int | None = None

        for idx, row in enumerate(excel_data):
            if not row.video_theme:
                continue
            excel_norm = _normalize(row.video_theme)
            if _is_match(script_norm, excel_norm):
                matched_row = row
                matched_idx = idx
                break

        if matched_row is not None and matched_idx is not None:
            matched_excel_indices.add(matched_idx)
            merged.append({
                "title": matched_row.video_theme,
                "content": script.content,
                "spend": matched_row.spend,
                "impressions": matched_row.impressions,
                "ctr": matched_row.ctr,
                "three_sec_rate": matched_row.three_sec_rate,
                "conversions": matched_row.conversions,
                "cost_per_conversion": matched_row.cost_per_conversion,
                "roi": matched_row.roi,
                "cpm": matched_row.cpm,
                "time_range": matched_row.time_range,
            })
        else:
            merged.append({
                "title": script.title,
                "content": script.content,
                "spend": None,
                "impressions": None,
                "ctr": None,
                "three_sec_rate": None,
                "conversions": None,
                "cost_per_conversion": None,
                "roi": None,
                "cpm": None,
                "time_range": None,
            })

    for idx, row in enumerate(excel_data):
        if idx in matched_excel_indices or not row.video_theme:
            continue
        merged.append({
            "title": row.video_theme,
            "content": "",
            "spend": row.spend,
            "impressions": row.impressions,
            "ctr": row.ctr,
            "three_sec_rate": row.three_sec_rate,
            "conversions": row.conversions,
            "cost_per_conversion": row.cost_per_conversion,
            "roi": row.roi,
            "cpm": row.cpm,
            "time_range": row.time_range,
        })

    def _spend_key(item: dict) -> float:
        try:
            return float(item["spend"]) if item["spend"] else 0.0
        except (ValueError, TypeError):
            return 0.0

    merged.sort(key=_spend_key, reverse=True)
    return merged


def build_user_message(items: list[dict]) -> str:
    """构建发给 AI 的 User Message，格式与原始 JS 逻辑完全等价。"""
    parts = [f"以下是本期千川投放素材（共{len(items)}条）：\n"]

    for i, v in enumerate(items, 1):
        desc = f"### 素材 {i}：{v['title']}"
        meta_parts = []
        if v.get("spend"):
            meta_parts.append(f"消耗: {v['spend']}元")
        if v.get("roi"):
            meta_parts.append(f"ROI: {v['roi']}")
        if v.get("conversions"):
            meta_parts.append(f"转化数: {v['conversions']}")
        if v.get("cost_per_conversion"):
            meta_parts.append(f"转化成本: {v['cost_per_conversion']}元")
        if v.get("ctr"):
            meta_parts.append(f"点击率: {v['ctr']}")
        if v.get("three_sec_rate"):
            meta_parts.append(f"3s完播率: {v['three_sec_rate']}")
        if v.get("impressions"):
            meta_parts.append(f"展示次数: {v['impressions']}")
        if v.get("cpm"):
            meta_parts.append(f"CPM: {v['cpm']}元")
        if v.get("time_range"):
            meta_parts.append(f"投放时段: {v['time_range']}")

        if meta_parts:
            desc += "\n" + " | ".join(meta_parts)

        content = v.get("content") or ""
        if content:
            truncated = (
                content[:CONTENT_TRUNCATE] + "\n...(已截断)"
                if len(content) > CONTENT_TRUNCATE
                else content
            )
            desc += f"\n\n【完整脚本】\n{truncated}"

        parts.append(desc)

    return "\n\n---\n\n".join(parts)


async def generate_review_stream(
    items: list[dict],
    has_excel: bool,
    db: AsyncSession,
    user_id: int,
    task_id: int | None = None,
) -> AsyncGenerator[str, None]:
    """
    调用 AI 流式生成复盘报告。
    has_excel=True 用 PROMPT_WITH_EXCEL，否则用 PROMPT_WITHOUT_EXCEL。
    """
    system_prompt = PROMPT_WITH_EXCEL if has_excel else PROMPT_WITHOUT_EXCEL
    user_message = build_user_message(items)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message + "\n\n请输出复盘报告。"},
    ]

    async for chunk in yunwu_adapter.chat_stream(
        messages=messages,
        db=db,
        model_id=DEFAULT_MODEL,
        user_id=user_id,
        feature="qianchuan_review_generate",
    ):
        yield chunk
