"""项目上下文只使用正式字段，不用相邻字段冒充缺失输入。"""
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import app.services.content_analysis as content_analysis


SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_context_marks_missing_target_users_and_direction_as_limited() -> None:
    kol = SimpleNamespace(
        id=1001,
        name="匿名项目",
        persona="项目人设",
        content_plan="内容规划",
        style_notes="不能冒充经营方向",
        background="不能冒充目标用户",
        updated_at=datetime(2026, 9, 5, tzinfo=SHANGHAI),
    )

    loaded = content_analysis.build_project_context(kol)

    assert loaded.context.project_id == "1001"
    assert loaded.project_name == "匿名项目"
    assert loaded.context.project_persona == "项目人设"
    assert loaded.context.content_plan == "内容规划"
    assert loaded.context.target_users == ""
    assert loaded.context.operating_direction == ""
    assert loaded.input_limited is True
    assert loaded.limitation_codes == (
        "TARGET_USERS_MISSING",
        "OPERATING_DIRECTION_MISSING",
    )
    assert "style_notes" not in loaded.context.version


def test_context_version_is_deterministic_and_changes_with_used_business_fields() -> None:
    first = SimpleNamespace(
        id=1001,
        name="匿名项目",
        persona="项目人设",
        content_plan="内容规划",
        updated_at=datetime(2026, 9, 5, tzinfo=SHANGHAI),
    )
    same = SimpleNamespace(**vars(first))
    changed = SimpleNamespace(**{**vars(first), "content_plan": "新的内容规划"})

    assert content_analysis.build_project_context(first).context.version == content_analysis.build_project_context(same).context.version
    assert content_analysis.build_project_context(first).context.version != content_analysis.build_project_context(changed).context.version


def test_context_requires_both_persona_and_content_plan_for_dynamic_onboarding() -> None:
    for persona, content_plan in ((None, "内容规划"), ("项目人设", " ")):
        with pytest.raises(ValueError, match="人设和内容规划"):
            content_analysis.build_project_context(
                SimpleNamespace(
                    id=1001,
                    name="匿名项目",
                    persona=persona,
                    content_plan=content_plan,
                    status="deprecated-value-must-not-be-used",
                    updated_at=datetime(2026, 9, 5, tzinfo=SHANGHAI),
                )
            )


def test_context_does_not_use_deprecated_status_as_onboarding_truth() -> None:
    loaded = content_analysis.build_project_context(
        SimpleNamespace(
            id=1001,
            name="匿名项目",
            persona="项目人设",
            content_plan="内容规划",
            status="legacy-stale-value",
            updated_at=datetime(2026, 9, 5, tzinfo=SHANGHAI),
        )
    )

    assert loaded.context.project_id == "1001"


def test_context_requires_formal_project_name_for_report_directory() -> None:
    with pytest.raises(ValueError, match="项目名称"):
        content_analysis.build_project_context(
            SimpleNamespace(
                id=1001,
                name=" ",
                persona="项目人设",
                content_plan="内容规划",
                updated_at=datetime(2026, 9, 5, tzinfo=SHANGHAI),
            )
        )
