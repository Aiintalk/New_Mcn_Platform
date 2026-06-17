"""
人设脚本复盘核心业务逻辑。

- merge_scripts_and_excel(): 脚本与 Excel 数据合并（Python 等价于原 JS handleGenerate 前段）
- detect_has_excel(): 判断合并结果中是否含有有效运营数据
- build_user_message(): 构建发给 AI 的 user message（含视频描述 + 脚本截断）
- generate_review_stream(): 从 DB 读取 Prompt + 模型，调用 yunwu adapter 流式生成

与 livestream_review 的关键差异：
- 匹配字段：video_theme（非 live_theme）
- Excel 侧清洗：无 #@；脚本侧清洗：有 #@
- 未匹配 Excel 行：追加到末尾（content=""）
- 排序依据：点赞数降序（非 GMV）
- 内容截断：2000 字（非 3000）
- hasExcel 判断字段：completion_rate | ad_spend | likes
"""
import re
import time
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import yunwu as yunwu_adapter
from app.models.task import TaskJob
from app.tools.persona_review.prompts import PROMPT_WITH_EXCEL, PROMPT_WITHOUT_EXCEL

DEFAULT_MODEL = "claude-sonnet-4-20250514"
_CONTENT_MAX_CHARS = 2000


# ---------------------------------------------------------------------------
# 文本清洗（与原 JS 逻辑等价，两侧规则不同）
# ---------------------------------------------------------------------------

def _normalize_excel(text: str) -> str:
    """Excel 侧清洗：去除标点和空白（无 #@），取前12字符。"""
    cleaned = re.sub(r'[，。！？、\s　]', '', text)
    return cleaned[:12]


def _normalize_script(text: str) -> str:
    """脚本侧清洗：去除标点、空白和 #@，取前12字符。"""
    cleaned = re.sub(r'[，。！？、#@\s　]', '', text)
    return cleaned[:12]


def _is_match(excel_norm: str, script_norm: str) -> bool:
    """双向 include 检查（取前6字符），与原 JS 逻辑一致。"""
    e6 = excel_norm[:6]
    s6 = script_norm[:6]
    return bool(e6) and bool(s6) and (excel_norm.find(s6) >= 0 or script_norm.find(e6) >= 0)


# ---------------------------------------------------------------------------
# 核心合并逻辑
# ---------------------------------------------------------------------------

def merge_scripts_and_excel(
    scripts: list[dict],
    excel_data: list[dict],
) -> list[dict]:
    """
    将脚本列表与 Excel 数据按 video_theme 模糊匹配合并。

    规则（与原 JS handleGenerate 一致，需求文档 Q7 确认）：
    - 匹配到时 title 用 Excel 的 video_theme
    - 未匹配的 Excel 行（有 video_theme 的）追加到末尾，content=""
    - 按点赞数降序排列（无值排末）
    """
    merged: list[dict] = []
    matched_excel_indices: set[int] = set()

    for script in scripts:
        script_norm = _normalize_script(script.get("title", ""))
        matched_excel: dict | None = None
        matched_idx: int | None = None

        for idx, row in enumerate(excel_data):
            video_theme = row.get("video_theme", "") or ""
            if not video_theme:
                continue
            excel_norm = _normalize_excel(video_theme)
            if _is_match(excel_norm, script_norm):
                matched_excel = row
                matched_idx = idx
                break

        item: dict = {
            "title": (matched_excel.get("video_theme") if matched_excel else None) or script.get("title", ""),
            "content": script.get("content", ""),
        }
        if matched_excel:
            matched_excel_indices.add(matched_idx)
            for key in [
                "date", "live_theme", "video_theme", "video_type",
                "total_plays", "completion_rate", "five_sec_rate",
                "likes", "comments", "ad_spend",
            ]:
                val = matched_excel.get(key)
                if val:
                    item[key] = str(val)

        merged.append(item)

    # 点赞数降序排列（仅对有脚本内容的行，无值排末）
    def _likes_key(m: dict) -> int:
        try:
            return -(int(m.get("likes") or "0") if m.get("likes") else 0)
        except (ValueError, TypeError):
            return 0

    merged.sort(key=_likes_key)

    # 追加未匹配的 Excel 行到末尾（不参与排序，content=""）
    for idx, row in enumerate(excel_data):
        if idx in matched_excel_indices:
            continue
        video_theme = row.get("video_theme", "") or ""
        if not video_theme:
            continue
        extra: dict = {
            "title": video_theme,
            "content": "",
        }
        for key in [
            "date", "live_theme", "video_type", "total_plays",
            "completion_rate", "five_sec_rate", "likes", "comments", "ad_spend",
        ]:
            val = row.get(key)
            if val:
                extra[key] = str(val)
        merged.append(extra)

    return merged


# ---------------------------------------------------------------------------
# hasExcel 判断
# ---------------------------------------------------------------------------

def detect_has_excel(merged: list[dict]) -> bool:
    """
    判断合并结果中是否含有有效运营数据。
    检查是否有任意一条含 completion_rate / ad_spend / likes。
    """
    for item in merged:
        for field in ("completion_rate", "ad_spend", "likes"):
            if item.get(field):
                return True
    return False


# ---------------------------------------------------------------------------
# User Message 构建
# ---------------------------------------------------------------------------

def build_user_message(merged: list[dict]) -> str:
    """
    构建发给 AI 的 user message。
    格式与原 JS videoDescriptions 完全等价（需求文档 1.2 节）。
    """
    video_parts: list[str] = []
    for i, item in enumerate(merged):
        desc = f"### 视频 {i + 1}：{item.get('title', '')}"

        meta_parts: list[str] = []
        if item.get("date"):
            meta_parts.append(f"发布日期: {item['date']}")
        if item.get("video_type"):
            meta_parts.append(f"类型: {item['video_type']}")
        if item.get("likes"):
            meta_parts.append(f"点赞: {item['likes']}")
        if item.get("comments"):
            meta_parts.append(f"评论: {item['comments']}")
        if item.get("total_plays"):
            meta_parts.append(f"播放量: {item['total_plays']}万")
        if item.get("completion_rate"):
            meta_parts.append(f"完播率: {item['completion_rate']}")
        if item.get("five_sec_rate"):
            meta_parts.append(f"5s完播率: {item['five_sec_rate']}")
        if item.get("ad_spend"):
            meta_parts.append(f"投放金额: {item['ad_spend']}")
        if item.get("live_theme"):
            meta_parts.append(f"所属直播场: {item['live_theme']}")

        if meta_parts:
            desc += "\n" + " | ".join(meta_parts)

        content = item.get("content", "")
        if content:
            if len(content) > _CONTENT_MAX_CHARS:
                content = content[:_CONTENT_MAX_CHARS] + "\n...(已截断)"
            desc += f"\n\n【完整脚本】\n{content}"

        video_parts.append(desc)

    body = "\n\n---\n\n".join(video_parts)
    return f"以下是本期发布的人设内容视频（共{len(merged)}条）：\n\n{body}\n\n请输出复盘报告。"


# ---------------------------------------------------------------------------
# 流式生成
# ---------------------------------------------------------------------------

async def generate_review_stream(
    merged: list[dict],
    db: AsyncSession,
    user_id: int,
    task_job_id: int,
) -> AsyncGenerator[str, None]:
    """
    从 DB 读取激活的 Prompt + 模型，调用 yunwu adapter 流式生成复盘报告。
    在 finally 块更新 task_jobs 状态（success / error）。
    """
    has_excel = detect_has_excel(merged)
    config_key = "with_excel" if has_excel else "without_excel"

    config_row = (await db.execute(sa_text(
        "SELECT system_prompt, ai_model_id FROM persona_review_configs "
        "WHERE config_key = :key AND is_active = true LIMIT 1"
    ), {"key": config_key})).fetchone()

    system_prompt = (config_row[0] if config_row and config_row[0]
                     else (PROMPT_WITH_EXCEL if has_excel else PROMPT_WITHOUT_EXCEL))

    model_id = DEFAULT_MODEL
    if config_row and config_row[1]:
        model_row = (await db.execute(sa_text(
            "SELECT model_id FROM ai_models WHERE id = :id AND status = 'active'"
        ), {"id": config_row[1]})).fetchone()
        if model_row:
            model_id = model_row[0]

    user_content = build_user_message(merged)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    status = "success"
    try:
        async for chunk in yunwu_adapter.chat_stream(
            messages=messages,
            db=db,
            model_id=model_id,
            user_id=user_id,
            feature="persona_review_generate",
        ):
            yield chunk
    except Exception as e:
        status = "error"
        yield f"\n\n[ERROR] {str(e)}"
    finally:
        try:
            await db.execute(sa_text(
                "UPDATE task_jobs SET status=:s, finished_at=:t WHERE id=:id"
            ), {"s": status, "t": datetime.now(timezone.utc), "id": task_job_id})
            await db.commit()
        except Exception:
            pass
