"""正式模型适配器使用现有调用设施并严格解析结构化结果。"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import app.services.content_analysis as ca


SHANGHAI = ZoneInfo("Asia/Shanghai")


def record():
    return ca.ContentRecord(
        account_id="account-001",
        source=ca.ContentSource.PLATFORM_SYNC,
        identity=ca.ContentIdentity(platform_content_id="work-001"),
        published_at=datetime(2026, 9, 3, tzinfo=SHANGHAI),
        captured_at=datetime(2026, 9, 4, tzinfo=SHANGHAI),
        metrics=ca.EngagementMetrics(like_count=10, comment_count=2, share_count=1, favorite_count=3),
        title="匿名标题",
        transcript="先提出问题，再解释匿名方法",
    )


class Model:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def complete_json(self, messages, *, feature):
        self.calls.append((messages, feature))
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_structured_analyzer_uses_title_transcript_metrics_and_project_context() -> None:
    model = Model(
        [
            json.dumps(
                {
                    "category": "persona",
                    "confidence": "medium",
                    "opening": {
                        "status": "available",
                        "kind": "language",
                        "fragment": "先提出问题",
                        "evidence": [{"evidence_type": "transcript", "locator": "transcript:0-6", "detail": "先提出问题"}],
                        "applicable_boundaries": [{"statement": "只复用提问结构"}],
                    },
                    "source_information": {"facts": [], "judgments": [], "assumptions": [], "limitations": [], "source_constraints": []},
                    "reusable_methods": [],
                    "topic": "匿名选题",
                    "summary": "匿名摘要",
                    "structure": ["问题", "方法"],
                    "persuasion_chain": [],
                    "interaction_observations": [],
                    "undetermined_reason": None,
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "is_fit": True,
                    "confidence": "medium",
                    "conclusion": "与项目人设相关",
                    "is_opportunity": True,
                    "priority": 1,
                    "body_benchmark": None,
                    "value_signals": ["novel_topic_or_structure"],
                    "fit_reasons": [{"dimension": "project_persona", "statement": "符合项目人设"}],
                    "limitations": [],
                    "recommended_action": "进入选题池",
                    "decision_basis": ["内容主题与人设一致"],
                },
                ensure_ascii=False,
            ),
        ]
    )
    analyzer = ca.StructuredModelContentAnalyzer(model)

    analysis = await analyzer.analyze_content(record())
    assessment = await analyzer.assess_project(
        analysis,
        ca.ProjectContextVersion(
            project_id="1001",
            version="v1",
            effective_at=datetime(2026, 9, 5, tzinfo=SHANGHAI),
            project_persona="项目人设",
            target_users="",
            content_plan="内容规划",
            operating_direction="",
        ),
    )

    assert analysis.category is ca.ContentCategory.PERSONA
    assert assessment.fit_reasons[0].dimension is ca.ProjectFitDimension.PROJECT_PERSONA
    first_call = json.dumps(model.calls[0], ensure_ascii=False)
    second_call = json.dumps(model.calls[1], ensure_ascii=False)
    assert all(text in first_call for text in ("匿名标题", "先提出问题", "like_count"))
    assert all(
        text in second_call
        for text in (
            "匿名标题",
            "先提出问题",
            "like_count",
            "opening",
            "source_information",
            "reusable_methods",
            "interaction_observations",
            "项目人设",
            "内容规划",
        )
    )
    joined = json.dumps(model.calls, ensure_ascii=False)
    assert all(
        field_name in joined
        for field_name in (
            "source_information",
            "reusable_methods",
            "value_signals",
            "fit_reasons",
        )
    )
    assert not any(text in joined for text in ("首帧", "镜头", "画面动作", "构图", "剪辑"))


@pytest.mark.asyncio
async def test_structured_analyzer_rejects_invalid_json_and_string_boolean() -> None:
    with pytest.raises(ValueError, match="JSON"):
        await ca.StructuredModelContentAnalyzer(Model(["not-json"])).analyze_content(record())

    minimal = ca.BasicAnalysis(
        content=record(),
        category=ca.ContentCategory.PERSONA,
        confidence=ca.ConfidenceLevel.MEDIUM,
        opening=ca.OpeningAnnotation(status=ca.OpeningTagStatus.UNANNOTATED),
    )
    response = json.dumps({"is_fit": "false", "confidence": "low", "conclusion": "不适配", "is_opportunity": False})
    with pytest.raises(ValueError, match="布尔"):
        await ca.StructuredModelContentAnalyzer(Model([response])).assess_project(
            minimal,
            ca.ProjectContextVersion("1001", "v1", datetime(2026, 9, 5, tzinfo=SHANGHAI), "人设", "", "规划", ""),
        )

    missing_opportunity = json.dumps(
        {
            "is_fit": False,
            "confidence": "low",
            "conclusion": "不适配",
        }
    )
    with pytest.raises(ValueError, match="机会标记"):
        await ca.StructuredModelContentAnalyzer(
            Model([missing_opportunity])
        ).assess_project(
            minimal,
            ca.ProjectContextVersion(
                "1001",
                "v1",
                datetime(2026, 9, 5, tzinfo=SHANGHAI),
                "人设",
                "",
                "规划",
                "",
            ),
        )


@pytest.mark.asyncio
async def test_prompt_documented_fact_and_observation_enums_parse_without_translation() -> None:
    response = {
        "category": "persona",
        "confidence": "medium",
        "opening": {
            "status": "unavailable",
            "kind": "language",
            "fragment": None,
            "evidence": [],
            "unavailable_reason": "没有可复用开头",
            "applicable_boundaries": [],
        },
        "source_information": {
            "facts": [
                {
                    "statement": "原内容提到匿名品牌",
                    "source": "transcript",
                    "kind": "brand",
                    "restricted_fragments": ["匿名品牌"],
                }
            ],
            "judgments": [],
            "assumptions": [],
            "limitations": [],
            "source_constraints": [],
        },
        "reusable_methods": [],
        "topic": "匿名选题",
        "summary": "匿名摘要",
        "structure": [],
        "persuasion_chain": [],
        "interaction_observations": [
            {
                "observation_type": "current_relative_performance",
                "metric": "like",
                "relative_level": "above",
                "benchmark_value": 8,
                "sample_size": 3,
            },
            {"observation_type": "data_maturity", "maturity": "qualitative"},
        ],
        "undetermined_reason": None,
    }
    model = Model([json.dumps(response, ensure_ascii=False)])

    result = await ca.StructuredModelContentAnalyzer(model).analyze_content(record())

    assert result.source_information.facts[0].kind is ca.SourceFactKind.BRAND
    assert result.interaction_observations[0].relative_level is ca.RelativePerformanceLevel.ABOVE
    assert result.interaction_observations[1].maturity is ca.DataMaturity.QUALITATIVE


def test_model_runtime_config_fails_explicitly_when_model_is_missing() -> None:
    with pytest.raises(ValueError, match="模型配置"):
        ca.YunwuContentAnalysisModelClient(None, model_id="", provider="yunwu", user_id=1)


@pytest.mark.asyncio
async def test_model_client_reuses_shared_yunwu_adapter(monkeypatch) -> None:
    calls = []

    async def fake_chat(messages, db, model_id, **kwargs):
        calls.append((messages, db, model_id, kwargs))
        return '{"ok": true}'

    monkeypatch.setattr(
        "app.services.content_analysis.model_analyzer.yunwu.chat",
        fake_chat,
    )
    session = object()
    client = ca.YunwuContentAnalysisModelClient(
        session,
        model_id="configured-model",
        provider="yunwu",
        user_id=100,
    )

    result = await client.complete_json(
        [{"role": "user", "content": "匿名输入"}],
        feature="content_analysis_basic",
    )

    assert result == '{"ok": true}'
    assert calls[0][1:3] == (session, "configured-model")
    assert calls[0][3] == {
        "provider": "yunwu",
        "user_id": 100,
        "feature": "content_analysis_basic",
        "temperature": 0.1,
        "max_tokens": 4096,
    }
