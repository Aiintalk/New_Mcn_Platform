import json

import pytest

from app.services.persona_profile_sync import (
    decide_initial_positioning_sync,
    parse_grounded_fact_candidates,
    resolve_positioning_decisions,
)


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (
            {"persona": None, "content_plan": ""},
            {"persona": "auto_written", "content_plan": "auto_written"},
        ),
        (
            {"persona": "旧人格", "content_plan": None},
            {"persona": "pending", "content_plan": "auto_written"},
        ),
        (
            {"persona": None, "content_plan": "旧规划"},
            {"persona": "auto_written", "content_plan": "pending"},
        ),
        (
            {"persona": "旧人格", "content_plan": "旧规划"},
            {"persona": "pending", "content_plan": "pending"},
        ),
        (
            {"persona": "新人格", "content_plan": "新规划"},
            {"persona": "unchanged", "content_plan": "unchanged"},
        ),
        (
            {"persona": " \n\t", "content_plan": "  "},
            {"persona": "auto_written", "content_plan": "auto_written"},
        ),
    ],
)
def test_initial_positioning_sync_classifies_each_field_independently(current, expected):
    generated = {"persona": "新人格", "content_plan": "新规划"}

    assert decide_initial_positioning_sync(current, generated) == expected


def test_initial_positioning_sync_does_not_replace_existing_with_blank_report_value():
    current = {"persona": "人工人格", "content_plan": "人工规划"}
    generated = {"persona": "", "content_plan": " \n"}

    assert decide_initial_positioning_sync(current, generated) == {
        "persona": "kept",
        "content_plan": "kept",
    }


def test_positioning_decisions_default_to_keep_and_apply_overwrite_per_field():
    current = {"persona": "人工人格", "content_plan": "人工规划"}
    generated = {"persona": "报告人格", "content_plan": "报告规划"}

    assert resolve_positioning_decisions(
        current,
        generated,
        {"content_plan": "overwrite"},
    ) == {
        "persona": "kept",
        "content_plan": "overwritten",
    }


def test_positioning_decisions_recalculate_identical_and_newly_empty_values():
    current = {"persona": "报告人格", "content_plan": ""}
    generated = {"persona": "报告人格", "content_plan": "报告规划"}

    assert resolve_positioning_decisions(
        current,
        generated,
        {"persona": "overwrite", "content_plan": "overwrite"},
    ) == {
        "persona": "unchanged",
        "content_plan": "auto_written",
    }


def test_grounded_fact_parser_keeps_only_known_exact_report_excerpts():
    profile = "她在杭州做过三年护士。\n妹妹小周常和她一起出镜。\n口头禅是慢慢来。"
    raw_json = json.dumps({
        "background": ["她在杭州做过三年护士。"],
        "experience": ["她曾在北京创业。"],
        "relationships": ["妹妹小周常和她一起出镜。"],
        "unknown": ["口头禅是慢慢来。"],
    }, ensure_ascii=False)

    assert parse_grounded_fact_candidates(profile, raw_json) == {
        "background": "她在杭州做过三年护士。",
        "experience": "",
        "relationships": "妹妹小周常和她一起出镜。",
        "unique_story": "",
        "extra_notes": "",
    }


def test_grounded_fact_parser_joins_distinct_exact_excerpts_in_source_form():
    profile = "第一段原文。\n第二段原文。"
    raw_json = json.dumps({
        "unique_story": ["第一段原文。", "第一段原文。", "第二段原文。"],
    }, ensure_ascii=False)

    facts = parse_grounded_fact_candidates(profile, raw_json)

    assert facts["unique_story"] == "第一段原文。\n第二段原文。"


@pytest.mark.parametrize("raw_json", ["not json", "[]", "{broken"])
def test_grounded_fact_parser_returns_empty_fixed_shape_for_malformed_json(raw_json):
    assert parse_grounded_fact_candidates("报告原文", raw_json) == {
        "background": "",
        "experience": "",
        "relationships": "",
        "unique_story": "",
        "extra_notes": "",
    }
