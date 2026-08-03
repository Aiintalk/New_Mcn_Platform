"""人格报告同步到正式达人档案时使用的纯决策函数。"""
import json
from collections.abc import Mapping


POSITIONING_FIELDS = ("persona", "content_plan")
FACT_FIELDS = (
    "background",
    "experience",
    "relationships",
    "unique_story",
    "extra_notes",
)


def build_grounded_fact_messages(profile_result: str) -> list[dict[str, str]]:
    """要求模型仅返回报告正文中的逐字片段，服务端仍会再次逐条校验。"""
    keys = ", ".join(FACT_FIELDS)
    return [
        {
            "role": "system",
            "content": (
                "你只做报告原文摘录，不推断、不改写、不补充。"
                f"只返回 JSON 对象，固定键为 {keys}；每个值必须是字符串数组，"
                "数组里的每一项都必须能在报告正文中逐字找到，找不到就返回空数组。"
            ),
        },
        {"role": "user", "content": f"报告正文：\n{profile_result}"},
    ]


def _has_text(value: str | None) -> bool:
    return bool(value and value.strip())


def decide_initial_positioning_sync(
    current: Mapping[str, str | None],
    generated: Mapping[str, str | None],
) -> dict[str, str]:
    """逐字段判断生成完成后的自动写入或待覆盖动作。"""
    actions: dict[str, str] = {}
    for field in POSITIONING_FIELDS:
        old_value = current.get(field)
        new_value = generated.get(field)
        if not _has_text(new_value):
            actions[field] = "kept" if _has_text(old_value) else "unchanged"
        elif old_value == new_value:
            actions[field] = "unchanged"
        elif not _has_text(old_value):
            actions[field] = "auto_written"
        else:
            actions[field] = "pending"
    return actions


def resolve_positioning_decisions(
    current: Mapping[str, str | None],
    generated: Mapping[str, str | None],
    decisions: Mapping[str, str],
) -> dict[str, str]:
    """按提交时的最新正式值重新计算；没有显式覆盖时默认保留。"""
    initial = decide_initial_positioning_sync(current, generated)
    actions: dict[str, str] = {}
    for field in POSITIONING_FIELDS:
        action = initial[field]
        if action == "pending":
            action = "overwritten" if decisions.get(field) == "overwrite" else "kept"
        actions[field] = action
    return actions


def parse_grounded_fact_candidates(
    profile_result: str,
    raw_json: str,
) -> dict[str, str]:
    """只保留固定字段中能在报告正文逐字找到的原文片段。"""
    empty_result = {field: "" for field in FACT_FIELDS}
    try:
        parsed = json.loads(raw_json)
    except (TypeError, json.JSONDecodeError):
        return empty_result
    if not isinstance(parsed, dict):
        return empty_result

    result = empty_result.copy()
    for field in FACT_FIELDS:
        excerpts = parsed.get(field)
        if not isinstance(excerpts, list):
            continue
        accepted: list[str] = []
        for excerpt in excerpts:
            if (
                isinstance(excerpt, str)
                and excerpt
                and excerpt in profile_result
                and excerpt not in accepted
            ):
                accepted.append(excerpt)
        result[field] = "\n".join(accepted)
    return result
