"""冻结匿名样本到稳定领域输入的纯离线适配合同。"""
import copy
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import app.services.content_analysis as content_analysis


SHANGHAI = ZoneInfo("Asia/Shanghai")
FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "fixtures/content_analysis/phase1_anonymized.json"
)


class FixtureAnalyzer:
    def __init__(self) -> None:
        self.basic_calls = []

    async def analyze_content(self, content):
        self.basic_calls.append(content)
        return content_analysis.BasicAnalysis(
            content=content,
            category=content_analysis.ContentCategory.PERSONA,
            confidence=content_analysis.ConfidenceLevel.MEDIUM,
            opening=content_analysis.OpeningAnnotation(
                status=content_analysis.OpeningTagStatus.UNANNOTATED,
            ),
            topic="匿名选题",
        )

    async def assess_project(self, analysis, project_context):
        return content_analysis.ProjectAssessment(
            project_id=project_context.project_id,
            context_version=project_context.version,
            is_fit=False,
            confidence=content_analysis.ConfidenceLevel.MEDIUM,
            conclusion="仅验证标准输入链路",
        )


@pytest.mark.asyncio
async def test_anonymous_fixture_adapts_to_domain_and_runs_through_offline_engine() -> None:
    assert hasattr(content_analysis, "adapt_offline_run_input")
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    run_input = content_analysis.adapt_offline_run_input(payload)
    analyzer = FixtureAnalyzer()
    result = await content_analysis.ContentAnalysisEngine(analyzer).run(run_input)

    assert run_input.run_at == datetime(2026, 9, 4, 9, tzinfo=SHANGHAI)
    assert run_input.sync_results[0].status == content_analysis.SyncStatus.SUCCESS_WITH_CONTENT
    first = run_input.sync_results[0].contents[0]
    assert first.account_id == "account-001"
    assert first.identity.platform_content_id == "sample-work-001"
    assert first.metrics.like_count == 18
    assert first.metrics.comment_count == 2
    assert first.metrics.share_count == 1
    assert first.metrics.favorite_count == 3
    assert first.metrics.play_count is None
    assert first.title == "匿名样本标题一"
    assert first.operations_review_url is None
    assert not hasattr(first, "sync_status")
    assert run_input.relations[0].project_id == "project-001"
    assert run_input.contexts[0].project_id == "project-001"
    assert [item.account_id for item in analyzer.basic_calls] == ["account-001"]
    assert tuple(result.reports) == ("project-001",)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda payload: payload.pop("run_at"),
        lambda payload: payload["sync_results"][0].__setitem__("status", "unknown"),
        lambda payload: payload["sync_results"][0]["contents"][0]["metrics"].__setitem__("like_count", True),
        lambda payload: payload["sync_results"][0]["contents"][0].pop("captured_at"),
        lambda payload: payload["relations"][0].pop("account_id"),
    ),
)
def test_standard_input_adapter_rejects_missing_or_illegal_fields(mutate) -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    invalid = copy.deepcopy(payload)
    mutate(invalid)

    with pytest.raises(ValueError, match="标准输入"):
        content_analysis.adapt_offline_run_input(invalid)


def test_standard_input_adapter_is_data_only_and_does_not_accept_fixture_paths() -> None:
    with pytest.raises(TypeError):
        content_analysis.adapt_offline_run_input(FIXTURE_PATH)


def test_standard_input_does_not_require_unavailable_play_count() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["sync_results"][0]["contents"][0]["metrics"].pop("play_count")

    run_input = content_analysis.adapt_offline_run_input(payload)

    assert run_input.sync_results[0].contents[0].metrics.play_count is None


@pytest.mark.asyncio
async def test_standard_input_allows_content_without_work_id_or_external_link() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    identity = payload["sync_results"][0]["contents"][0]["identity"]
    identity["platform_content_id"] = None
    identity["external_url"] = None
    payload["sync_results"][0]["contents"][0]["published_at"] = (
        "2026-09-03T09:00:00+08:00"
    )
    payload["sync_results"][0]["contents"][0]["captured_at"] = (
        "2026-09-03T12:00:00+08:00"
    )

    run_input = content_analysis.adapt_offline_run_input(payload)
    analyzer = FixtureAnalyzer()
    result = await content_analysis.ContentAnalysisEngine(analyzer).run(run_input)

    content = run_input.sync_results[0].contents[0]
    assert content.identity.stable_keys() == ()
    assert len(analyzer.basic_calls) == 1
    assert result.reports["project-001"].items[0].stable_key is None


def test_standard_input_adapter_preserves_saved_state_library_and_weekly_baseline() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["saved_states"] = [
        {
            "project_id": "project-001",
            "stable_key": "platform_content_id:sample-work-001",
            "candidate_rank": 1,
            "is_opportunity": True,
            "in_library": True,
            "priority": 1,
            "cross_project": False,
            "conclusion": "匿名历史判断",
            "confidence": "high",
            "persona_relative_like": "above",
        }
    ]
    payload["saved_library_records"] = [
        {
            "project_id": "project-001",
            "content_key": "platform_content_id:sample-work-001",
            "reusable_methods": [
                {
                    "name": "问题到证明",
                    "description": "先提出问题再给证明",
                    "method_key": "problem-proof",
                    "evidence": [
                        {
                            "evidence_type": "transcript",
                            "locator": "transcript:1",
                            "detail": "问题、方法和结果",
                        }
                    ],
                    "applicable_boundaries": [
                        {"statement": "只复用结构"}
                    ],
                }
            ],
            "signals": ["novel_content_method"],
            "scenarios": ["匿名口播"],
            "source_information": {
                "facts": [
                    {
                        "statement": "原视频展示匿名品牌",
                        "source": "sample-work-001",
                        "kind": "brand",
                        "restricted_fragments": ["匿名品牌"],
                    }
                ]
            },
        }
    ]
    payload["persona_baselines"] = [
        {
            "account_id": "account-001",
            "window_start": "2026-08-05T00:00:00+08:00",
            "window_end": "2026-09-04T00:00:00+08:00",
            "baseline": {
                "mean": 15.0,
                "median": 15.0,
                "sample_size": 2,
                "maximum": 20,
                "minimum": 10,
            },
        }
    ]

    run_input = content_analysis.adapt_offline_run_input(payload)

    assert run_input.saved_states[0].persona_relative_like.value == "above"
    assert run_input.saved_library_records[0].reusable_methods[0].method_key == "problem-proof"
    assert (
        run_input.saved_library_records[0]
        .source_information.facts[0]
        .restricted_fragments
        == ("匿名品牌",)
    )
    assert run_input.persona_baselines[0].baseline.sample_size == 2


def test_standard_input_adapter_requires_saved_source_information() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["saved_library_records"] = [
        {
            "project_id": "project-001",
            "content_key": "platform_content_id:sample-work-001",
            "reusable_methods": [],
        }
    ]

    with pytest.raises(ValueError, match="source_information"):
        content_analysis.adapt_offline_run_input(payload)


@pytest.mark.parametrize("invalid_number", (float("nan"), float("inf")))
def test_standard_input_adapter_rejects_non_finite_baseline_numbers(
    invalid_number: float,
) -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["persona_baselines"] = [
        {
            "account_id": "account-001",
            "window_start": "2026-08-05T00:00:00+08:00",
            "window_end": "2026-09-04T00:00:00+08:00",
            "baseline": {
                "mean": invalid_number,
                "median": 15.0,
                "sample_size": 2,
                "maximum": 20,
                "minimum": 10,
            },
        }
    ]

    with pytest.raises(ValueError, match="非负数"):
        content_analysis.adapt_offline_run_input(payload)


def test_standard_input_adapter_maps_structured_sync_issue() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    sync_result = payload["sync_results"][0]
    sync_result["status"] = "partial_success"
    sync_result["issue"] = {
        "affected_account_ids": ["account-001"],
        "affected_window": copy.deepcopy(sync_result["coverage_window"]),
        "impact": "content_may_be_incomplete",
    }

    run_input = content_analysis.adapt_offline_run_input(payload)

    issue = run_input.sync_results[0].issue
    assert issue.affected_account_ids == ("account-001",)
    assert issue.affected_window == run_input.sync_results[0].coverage_window
    assert issue.impact == content_analysis.SyncIssueImpact.CONTENT_MAY_BE_INCOMPLETE


def test_standard_input_adapter_redacts_arbitrary_sync_issue_reason() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    sync_result = payload["sync_results"][0]
    sync_result["status"] = "partial_success"
    sync_result["issue"] = {
        "affected_account_ids": ["account-001"],
        "affected_window": copy.deepcopy(sync_result["coverage_window"]),
        "impact": "content_may_be_incomplete",
        "reason": "access_token=SENTINEL_PRIVATE_VALUE",
    }

    run_input = content_analysis.adapt_offline_run_input(payload)

    reason = run_input.sync_results[0].issue.reason
    assert reason == "内容源读取失败，详见上游读取日志"
    assert "SENTINEL_PRIVATE_VALUE" not in reason


def test_standard_input_adapter_rejects_unstructured_sync_issue() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["sync_results"][0]["status"] = "partial_success"
    payload["sync_results"][0]["issue"] = "raw upstream failure"

    with pytest.raises(ValueError, match="标准输入无效.*issue 必须是对象"):
        content_analysis.adapt_offline_run_input(payload)


@pytest.mark.asyncio
async def test_standard_input_allows_missing_project_context_and_reports_limitation() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["contexts"][0]["project_persona"] = ""
    payload["sync_results"][0]["contents"][0]["published_at"] = (
        "2026-09-03T09:00:00+08:00"
    )
    payload["sync_results"][0]["contents"][0]["captured_at"] = (
        "2026-09-03T15:00:00+08:00"
    )

    run_input = content_analysis.adapt_offline_run_input(payload)
    result = await content_analysis.ContentAnalysisEngine(FixtureAnalyzer()).run(run_input)

    assert run_input.contexts[0].project_persona == ""
    assert any(
        "project_persona" in issue
        for issue in result.reports["project-001"].data_issues
    )
    assert result.reports["project-001"].items[0].assessment.confidence == (
        content_analysis.ConfidenceLevel.LOW
    )


def test_public_entrypoint_exposes_all_types_needed_to_construct_standard_input_and_output() -> None:
    required = {
        "AnalysisEvidence",
        "ConfidenceLevel",
        "EvidenceType",
        "SourceAssumption",
        "SourceJudgment",
        "SourceLimitation",
        "CategoryOverview",
        "SyncIssue",
        "SyncIssueImpact",
    }

    assert required <= set(content_analysis.__all__)
    assert all(hasattr(content_analysis, name) for name in required)
