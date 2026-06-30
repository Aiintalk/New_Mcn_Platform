"""
livestream-review 核心业务逻辑。

- merge_scripts_and_excel(): 脚本与 Excel 数据合并（Python 等价于原 JS handleGenerate 前段）
- detect_has_excel(): 判断合并结果中是否含有有效的直播数据
- build_user_message(): 构建发给 AI 的 user message（含场次描述 + 脚本截断）
- generate_review_stream(): 从 DB 读取 Prompt + 模型，调用 yunwu adapter 流式生成
"""
import re
import time
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from sqlalchemy import select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import yunwu as yunwu_adapter
from app.models.log import AiCallLog
from app.models.task import TaskJob
from app.tools.livestream_review.prompts import PROMPT_WITH_EXCEL, PROMPT_WITHOUT_EXCEL

DEFAULT_MODEL = "claude-sonnet-4-20250514"
_CONTENT_MAX_CHARS = 3000


# ---------------------------------------------------------------------------
# 文本清洗（与原 JS 逻辑等价）
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """去除标点和空白，取前12字符，用于模糊匹配。"""
    cleaned = re.sub(r'[，。！？、#@\s　]', '', text)
    return cleaned[:12]


def _is_match(a_norm: str, b_norm: str) -> bool:
    """双向 include 检查（取前6字符），与原 JS 逻辑一致。"""
    a6 = a_norm[:6]
    b6 = b_norm[:6]
    return bool(a6) and bool(b6) and (b_norm.find(a6) >= 0 or a_norm.find(b6) >= 0)


# ---------------------------------------------------------------------------
# 核心合并逻辑
# ---------------------------------------------------------------------------

def merge_scripts_and_excel(
    scripts: list[dict],
    excel_data: list[dict],
) -> list[dict]:
    """
    将脚本列表与 Excel 数据按标题模糊匹配合并。

    规则（与原 JS handleGenerate 一致，Q9 确认）：
    - 只保留有脚本内容的场次（未匹配的 Excel 行不追加）
    - 匹配时用 live_theme 替换 title
    - 按 GMV 降序排列（无值排末）
    """
    merged: list[dict] = []

    for script in scripts:
        script_norm = _normalize(script.get("title", ""))
        matched_excel: dict | None = None

        for row in excel_data:
            fields = [
                row.get("live_theme", "") or "",
                row.get("live_date", "") or "",
            ]
            for field in fields:
                if not field:
                    continue
                field_norm = _normalize(field)
                if _is_match(script_norm, field_norm):
                    matched_excel = row
                    break
            if matched_excel:
                break

        item: dict = {
            "title": (matched_excel.get("live_theme") if matched_excel else None) or script.get("title", ""),
            "content": script.get("content", ""),
        }
        if matched_excel:
            for key in [
                "live_date", "duration", "peak_viewers", "avg_viewers",
                "total_uv", "avg_stay_time", "likes", "comments",
                "follows_gained", "conversions", "gmv", "gpm", "ad_spend",
            ]:
                val = matched_excel.get(key)
                if val:
                    item[key] = str(val)

        merged.append(item)

    # GMV 降序排列（无值的排末，用负数倒序）
    def _gmv_key(m: dict) -> float:
        try:
            return -float(m.get("gmv") or "0")
        except (ValueError, TypeError):
            return 0.0

    merged.sort(key=_gmv_key)
    return merged


# ---------------------------------------------------------------------------
# hasExcel 判断
# ---------------------------------------------------------------------------

def detect_has_excel(merged: list[dict]) -> bool:
    """
    判断合并结果中是否含有有效直播数据。
    后端在合并后检查是否存在任意一条含 gmv / peak_viewers / conversions 的项。
    （Q2 确认：不是简单判断 excel_data 是否非空）
    """
    for item in merged:
        for field in ("gmv", "peak_viewers", "conversions"):
            if item.get(field):
                return True
    return False


# ---------------------------------------------------------------------------
# User Message 构建
# ---------------------------------------------------------------------------

def build_user_message(merged: list[dict]) -> str:
    """
    构建发给 AI 的 user message。
    格式与原 JS liveDescriptions 完全等价。
    """
    scenes: list[str] = []
    for i, item in enumerate(merged):
        desc = f"### 场次 {i + 1}：{item.get('title', '')}"

        meta_parts: list[str] = []
        if item.get("live_date"):
            meta_parts.append(f"日期: {item['live_date']}")
        if item.get("duration"):
            meta_parts.append(f"时长: {item['duration']}分钟")
        if item.get("gmv"):
            meta_parts.append(f"GMV: {item['gmv']}元")
        if item.get("gpm"):
            meta_parts.append(f"GPM: {item['gpm']}")
        if item.get("conversions"):
            meta_parts.append(f"成交单数: {item['conversions']}")
        if item.get("peak_viewers"):
            meta_parts.append(f"峰值在线: {item['peak_viewers']}")
        if item.get("avg_viewers"):
            meta_parts.append(f"平均在线: {item['avg_viewers']}")
        if item.get("total_uv"):
            meta_parts.append(f"总UV: {item['total_uv']}")
        if item.get("avg_stay_time"):
            meta_parts.append(f"平均停留: {item['avg_stay_time']}秒")
        if item.get("likes"):
            meta_parts.append(f"点赞: {item['likes']}")
        if item.get("comments"):
            meta_parts.append(f"评论: {item['comments']}")
        if item.get("follows_gained"):
            meta_parts.append(f"涨粉: {item['follows_gained']}")
        if item.get("ad_spend"):
            meta_parts.append(f"投放金额: {item['ad_spend']}元")

        if meta_parts:
            desc += "\n" + " | ".join(meta_parts)

        content = item.get("content", "")
        if content:
            if len(content) > _CONTENT_MAX_CHARS:
                content = content[:_CONTENT_MAX_CHARS] + "\n...(已截断)"
            desc += f"\n\n【完整直播脚本】\n{content}"

        scenes.append(desc)

    body = "\n\n---\n\n".join(scenes)
    return f"以下是本期直播间脚本（共{len(merged)}场）：\n\n{body}\n\n请输出复盘报告。"


# ---------------------------------------------------------------------------
# 流式生成
# ---------------------------------------------------------------------------

async def generate_review_stream(
    merged: list[dict],
    db: AsyncSession,
    user_id: int,
    task_job_id: int,
    override_prompt: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    从 DB 读取激活的 Prompt + 模型，调用 yunwu adapter 流式生成复盘报告。
    override_prompt 非空时优先使用（红人专属 Prompt）。
    在 finally 块更新 task_jobs 状态（success / error）。
    """
    has_excel = detect_has_excel(merged)
    config_key = "with_excel" if has_excel else "without_excel"

    # 读取 DB 配置
    config_row = (await db.execute(sa_text(
        "SELECT system_prompt, ai_model_id FROM livestream_review_configs "
        "WHERE config_key = :key AND is_active = true LIMIT 1"
    ), {"key": config_key})).fetchone()

    if override_prompt:
        system_prompt = override_prompt
    else:
        system_prompt = (config_row[0] if config_row and config_row[0]
                         else (PROMPT_WITH_EXCEL if has_excel else PROMPT_WITHOUT_EXCEL))

    # 解析模型
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
            feature="livestream_review_generate",
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
