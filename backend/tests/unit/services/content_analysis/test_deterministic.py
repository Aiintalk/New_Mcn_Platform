"""阶段一确定性内容分析规则的测试。"""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import app.services.content_analysis as content_analysis
import app.services.content_analysis.domain as content_domain
from app.services.content_analysis.deterministic import (
    deduplicate_contents,
    derive_windows,
    normalize_play_count,
    persona_like_baseline,
    qianchuan_top_three,
)
from app.services.content_analysis.domain import (
    AnalysisEvidence,
    AnalysisWindows,
    BasicAnalysis,
    ConfidenceLevel,
    ContentCategory,
    ContentIdentity,
    ContentRecord,
    ContentSource,
    EngagementMetrics,
    EvidenceType,
    OpeningAnnotation,
    OpeningKind,
    OpeningTagStatus,
    ProjectContextVersion,
    ProjectFact,
    ReusableMethod,
    SourceAssumption,
    SourceConstraint,
    SourceFact,
    SourceInformation,
    SourceJudgment,
    SourceLimitation,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "fixtures/content_analysis/phase1_anonymized.json"
)


def content(
    *,
    account_id: str = "account-001",
    platform_content_id: str | None = None,
    external_url: str | None = None,
    published_at: datetime = datetime(2026, 9, 1, 8, tzinfo=SHANGHAI),
    captured_at: datetime = datetime(2026, 9, 2, 8, tzinfo=SHANGHAI),
    likes: int | None = 10,
    play_count: int | None = 100,
    transcript: str | None = "合成短文案",
) -> ContentRecord:
    """创建仅用于断言领域规则的合成标准输入。"""
    return ContentRecord(
        account_id=account_id,
        source=ContentSource.MANUAL,
        identity=ContentIdentity(
            platform_content_id=platform_content_id,
            external_url=external_url,
        ),
        published_at=published_at,
        captured_at=captured_at,
        metrics=EngagementMetrics(
            like_count=likes,
            comment_count=2,
            share_count=3,
            favorite_count=4,
            play_count=play_count,
        ),
        title="合成标题",
        transcript=transcript,
    )


def analysis(
    record: ContentRecord,
    *,
    category: ContentCategory = ContentCategory.PERSONA,
    undetermined_reason: str | None = None,
    source_information: SourceInformation = SourceInformation(),
) -> BasicAnalysis:
    return BasicAnalysis(
        content=record,
        category=category,
        confidence=ConfidenceLevel.MEDIUM,
        opening=OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
        source_information=source_information,
        undetermined_reason=undetermined_reason,
    )


def test_derive_windows_converts_to_china_timezone_and_uses_completed_days() -> None:
    run_at = datetime(2026, 9, 3, 16, 0, tzinfo=timezone.utc)

    windows = derive_windows(run_at)

    assert windows.report_date.isoformat() == "2026-09-03"
    assert windows.three_day_start == datetime(2026, 9, 1, tzinfo=SHANGHAI)
    assert windows.three_day_end == datetime(2026, 9, 4, tzinfo=SHANGHAI)
    assert windows.thirty_day_start == datetime(2026, 8, 5, tzinfo=SHANGHAI)
    assert windows.thirty_day_end == datetime(2026, 9, 4, tzinfo=SHANGHAI)


def test_derive_windows_changes_report_date_at_china_day_boundary() -> None:
    before_midnight = derive_windows(datetime(2026, 9, 3, 15, 59, tzinfo=timezone.utc))
    at_midnight = derive_windows(datetime(2026, 9, 3, 16, 0, tzinfo=timezone.utc))

    assert before_midnight.report_date.isoformat() == "2026-09-02"
    assert at_midnight.report_date.isoformat() == "2026-09-03"


def test_analysis_windows_reject_naive_or_misaligned_intervals() -> None:
    end = datetime(2026, 9, 4, tzinfo=SHANGHAI)

    with pytest.raises(ValueError):
        AnalysisWindows(
            report_date=date(2026, 9, 3),
            three_day_start=datetime(2026, 9, 1),
            three_day_end=end,
            thirty_day_start=datetime(2026, 8, 5, tzinfo=SHANGHAI),
            thirty_day_end=end,
        )
    with pytest.raises(ValueError):
        AnalysisWindows(
            report_date=date(2026, 9, 3),
            three_day_start=datetime(2026, 9, 4, tzinfo=SHANGHAI),
            three_day_end=datetime(2026, 9, 1, tzinfo=SHANGHAI),
            thirty_day_start=datetime(2026, 8, 5, tzinfo=SHANGHAI),
            thirty_day_end=end,
        )
    with pytest.raises(ValueError):
        AnalysisWindows(
            report_date=date(2026, 9, 3),
            three_day_start=datetime(2026, 9, 1, tzinfo=SHANGHAI),
            three_day_end=end,
            thirty_day_start=datetime(2026, 8, 5, tzinfo=SHANGHAI),
            thirty_day_end=datetime(2026, 9, 5, tzinfo=SHANGHAI),
        )


def test_deduplicate_contents_keeps_newest_capture_for_platform_id_or_link() -> None:
    older_id = content(
        platform_content_id="sample-work-001",
        captured_at=datetime(2026, 9, 2, 8, tzinfo=SHANGHAI),
        likes=10,
    )
    newer_id = content(
        platform_content_id="sample-work-001",
        captured_at=datetime(2026, 9, 2, 9, tzinfo=SHANGHAI),
        likes=20,
    )
    older_link = content(
        platform_content_id="sample-work-002",
        external_url="https://example.invalid/video/sample-002",
        captured_at=datetime(2026, 9, 2, 8, tzinfo=SHANGHAI),
        likes=30,
    )
    newer_link = content(
        platform_content_id="sample-work-003",
        external_url="https://example.invalid/video/sample-002",
        captured_at=datetime(2026, 9, 2, 10, tzinfo=SHANGHAI),
        likes=40,
    )

    result = deduplicate_contents([older_id, newer_id, older_link, newer_link])

    assert [item.metrics.like_count for item in result] == [20, 40]


def test_deduplicate_contents_does_not_merge_text_when_stable_identity_is_missing() -> None:
    first = content(platform_content_id=None, external_url=None, transcript="相同合成文案")
    second = content(
        platform_content_id=None,
        external_url=None,
        transcript="相同合成文案",
        captured_at=datetime(2026, 9, 2, 9, tzinfo=SHANGHAI),
    )

    result = deduplicate_contents([first, second])

    assert result == [first, second]


def test_normalized_input_marks_non_positive_play_count_unavailable_and_excludes_it_from_engagement() -> None:
    item = content(play_count=0)

    assert item.metrics.play_count is None
    assert item.metrics.engagement_total == 19
    assert normalize_play_count(0) is None
    assert normalize_play_count(-1) is None
    assert normalize_play_count(101) == 101


@pytest.mark.parametrize("invalid", (-1, True, 1.5, "1"))
def test_four_engagement_metrics_reject_non_integer_or_negative_values(invalid) -> None:
    with pytest.raises(ValueError, match="互动值"):
        EngagementMetrics(like_count=invalid)


def test_persona_like_baseline_uses_only_thirty_day_analyzed_persona_contents_with_likes() -> None:
    window_start = datetime(2026, 8, 5, tzinfo=SHANGHAI)
    window_end = datetime(2026, 9, 4, tzinfo=SHANGHAI)
    records = [
        analysis(content(likes=10, published_at=datetime(2026, 8, 5, tzinfo=SHANGHAI))),
        analysis(content(likes=20, published_at=datetime(2026, 8, 10, tzinfo=SHANGHAI))),
        analysis(content(likes=40, published_at=datetime(2026, 9, 3, 23, tzinfo=SHANGHAI))),
        analysis(content(likes=None, published_at=datetime(2026, 8, 12, tzinfo=SHANGHAI))),
        analysis(
            content(likes=99, published_at=datetime(2026, 8, 12, tzinfo=SHANGHAI)),
            category=ContentCategory.QIANCHUAN,
        ),
        analysis(content(likes=88, published_at=datetime(2026, 9, 4, tzinfo=SHANGHAI))),
    ]

    baseline = persona_like_baseline(records, window_start, window_end)

    assert baseline["account-001"].mean == 70 / 3
    assert baseline["account-001"].median == 20
    assert baseline["account-001"].sample_size == 3
    assert baseline["account-001"].maximum == 40
    assert baseline["account-001"].minimum == 10


@pytest.mark.parametrize("invalid_number", (float("nan"), float("inf")))
def test_like_baseline_rejects_non_finite_statistics(invalid_number: float) -> None:
    with pytest.raises(ValueError, match="有限"):
        content_analysis.LikeBaseline(
            mean=invalid_number,
            median=10.0,
            sample_size=1,
            maximum=10,
            minimum=10,
        )


def test_qianchuan_top_three_uses_current_likes_with_left_boundary_and_account_isolation() -> None:
    window_start = datetime(2026, 9, 1, tzinfo=SHANGHAI)
    window_end = datetime(2026, 9, 4, tzinfo=SHANGHAI)
    records = [
        analysis(
            content(platform_content_id="sample-q1", likes=30),
            category=ContentCategory.QIANCHUAN,
        ),
        analysis(
            content(platform_content_id="sample-q2", likes=90),
            category=ContentCategory.QIANCHUAN,
        ),
        analysis(
            content(platform_content_id="sample-q3", likes=60),
            category=ContentCategory.QIANCHUAN,
        ),
        analysis(
            content(platform_content_id="sample-q4", likes=20),
            category=ContentCategory.QIANCHUAN,
        ),
        analysis(
            content(
                platform_content_id="sample-left-boundary",
                likes=70,
                published_at=window_start,
            ),
            category=ContentCategory.QIANCHUAN,
        ),
        analysis(
            content(
                platform_content_id="sample-outside",
                likes=999,
                published_at=window_end,
            ),
            category=ContentCategory.QIANCHUAN,
        ),
        analysis(
            content(
                account_id="account-002",
                platform_content_id="sample-account-002",
                likes=50,
            ),
            category=ContentCategory.QIANCHUAN,
        ),
    ]

    top_three = qianchuan_top_three(records, window_start, window_end)

    assert [item.identity.platform_content_id for item in top_three["account-001"]] == [
        "sample-q2",
        "sample-left-boundary",
        "sample-q3",
    ]
    assert [item.identity.platform_content_id for item in top_three["account-002"]] == [
        "sample-account-002"
    ]


def test_qianchuan_top_three_excludes_unknown_likes_instead_of_backfilling() -> None:
    window_start = datetime(2026, 9, 1, tzinfo=SHANGHAI)
    window_end = datetime(2026, 9, 4, tzinfo=SHANGHAI)
    records = [
        analysis(
            content(platform_content_id=f"known-{index}", likes=likes),
            category=ContentCategory.QIANCHUAN,
        )
        for index, likes in enumerate((30, 20), start=1)
    ] + [
        analysis(
            content(platform_content_id="unknown", likes=None, play_count=999999),
            category=ContentCategory.QIANCHUAN,
        )
    ]

    result = qianchuan_top_three(records, window_start, window_end)

    assert [item.identity.platform_content_id for item in result["account-001"]] == [
        "known-1",
        "known-2",
    ]


def test_qianchuan_like_tie_never_uses_play_count_as_a_ranking_signal() -> None:
    low_play = content(platform_content_id=None, likes=50, play_count=10)
    high_play = content(platform_content_id=None, likes=50, play_count=999999)

    result = qianchuan_top_three(
        (
            analysis(low_play, category=ContentCategory.QIANCHUAN),
            analysis(high_play, category=ContentCategory.QIANCHUAN),
        ),
        datetime(2026, 9, 1, tzinfo=SHANGHAI),
        datetime(2026, 9, 4, tzinfo=SHANGHAI),
    )

    assert result["account-001"] == (low_play, high_play)


def test_weekly_persona_baseline_and_data_maturity_have_independent_public_entrypoints() -> None:
    assert hasattr(content_analysis, "build_weekly_persona_baselines")
    assert hasattr(content_analysis, "derive_data_maturity")

    records = (
        analysis(
            content(
                account_id="account-001",
                platform_content_id="persona-1",
                likes=10,
                published_at=datetime(2026, 8, 5, tzinfo=SHANGHAI),
            )
        ),
        analysis(
            content(
                account_id="account-001",
                platform_content_id="persona-2",
                likes=30,
                published_at=datetime(2026, 9, 3, 23, tzinfo=SHANGHAI),
            )
        ),
    )

    weekly = content_analysis.build_weekly_persona_baselines(
        records,
        datetime(2026, 9, 4, 9, tzinfo=SHANGHAI),
    )

    assert len(weekly) == 1
    assert weekly[0].account_id == "account-001"
    assert weekly[0].baseline.mean == 20
    assert weekly[0].baseline.median == 20
    assert weekly[0].baseline.sample_size == 2
    assert weekly[0].baseline.maximum == 30
    assert weekly[0].baseline.minimum == 10
    assert weekly[0].window_start == datetime(2026, 8, 5, tzinfo=SHANGHAI)
    assert weekly[0].window_end == datetime(2026, 9, 4, tzinfo=SHANGHAI)


def test_weekly_persona_baseline_deduplicates_stable_content_before_statistics() -> None:
    older = content(
        platform_content_id="duplicate-persona",
        likes=10,
        captured_at=datetime(2026, 9, 2, 8, tzinfo=SHANGHAI),
    )
    newer = content(
        platform_content_id="duplicate-persona",
        likes=30,
        captured_at=datetime(2026, 9, 3, 8, tzinfo=SHANGHAI),
    )

    result = content_analysis.build_weekly_persona_baselines(
        (analysis(older), analysis(newer)),
        datetime(2026, 9, 4, 9, tzinfo=SHANGHAI),
    )

    assert result[0].baseline.sample_size == 1
    assert result[0].baseline.mean == 30


@pytest.mark.parametrize(
    ("age", "expected"),
    (
        (timedelta(hours=5, minutes=59), "early"),
        (timedelta(hours=6), "initial"),
        (timedelta(hours=11, minutes=59), "initial"),
        (timedelta(hours=12), "qualitative"),
    ),
)
def test_data_maturity_uses_published_to_current_capture_boundaries(
    age: timedelta,
    expected: str,
) -> None:
    published_at = datetime(2026, 9, 3, 8, tzinfo=SHANGHAI)

    maturity = content_analysis.derive_data_maturity(
        published_at,
        published_at + age,
    )

    assert maturity.value == expected


def test_qianchuan_equal_likes_use_publish_time_then_stable_identity() -> None:
    window_start = datetime(2026, 9, 1, tzinfo=SHANGHAI)
    window_end = datetime(2026, 9, 4, tzinfo=SHANGHAI)
    records = [
        analysis(
            content(
                platform_content_id="sample-z",
                likes=50,
                published_at=datetime(2026, 9, 3, tzinfo=SHANGHAI),
            ),
            category=ContentCategory.QIANCHUAN,
        ),
        analysis(
            content(
                platform_content_id="sample-b",
                likes=50,
                published_at=datetime(2026, 9, 2, tzinfo=SHANGHAI),
            ),
            category=ContentCategory.QIANCHUAN,
        ),
        analysis(
            content(
                platform_content_id="sample-a",
                likes=50,
                published_at=datetime(2026, 9, 2, tzinfo=SHANGHAI),
            ),
            category=ContentCategory.QIANCHUAN,
        ),
    ]

    forward = qianchuan_top_three(records, window_start, window_end)["account-001"]
    backward = qianchuan_top_three(
        reversed(records), window_start, window_end
    )["account-001"]

    assert forward == backward
    assert [item.identity.platform_content_id for item in forward] == [
        "sample-z",
        "sample-a",
        "sample-b",
    ]


def test_qianchuan_equal_records_without_stable_identity_do_not_use_input_order() -> None:
    window_start = datetime(2026, 9, 1, tzinfo=SHANGHAI)
    window_end = datetime(2026, 9, 4, tzinfo=SHANGHAI)
    records = [
        analysis(
            content(
                likes=50,
                transcript="较早采集",
                captured_at=datetime(2026, 9, 2, 8, tzinfo=SHANGHAI),
            ),
            category=ContentCategory.QIANCHUAN,
        ),
        analysis(
            content(
                likes=50,
                transcript="最新采集",
                captured_at=datetime(2026, 9, 2, 10, tzinfo=SHANGHAI),
            ),
            category=ContentCategory.QIANCHUAN,
        ),
        analysis(
            content(
                likes=50,
                transcript="中间采集",
                captured_at=datetime(2026, 9, 2, 9, tzinfo=SHANGHAI),
            ),
            category=ContentCategory.QIANCHUAN,
        ),
    ]

    forward = qianchuan_top_three(records, window_start, window_end)["account-001"]
    backward = qianchuan_top_three(
        reversed(records), window_start, window_end
    )["account-001"]

    assert forward == backward
    assert [item.transcript for item in forward] == ["最新采集", "中间采集", "较早采集"]


def test_basic_analysis_requires_reason_for_undetermined_category() -> None:
    with pytest.raises(ValueError):
        analysis(content(), category=ContentCategory.UNDETERMINED)

    result = analysis(
        content(),
        category=ContentCategory.UNDETERMINED,
        undetermined_reason="缺少可判定标签",
    )

    assert result.undetermined_reason == "缺少可判定标签"


@pytest.mark.parametrize("invalid", (1, "  "))
def test_undetermined_reason_must_be_non_empty_text(invalid) -> None:
    with pytest.raises(ValueError, match="无法判断原因"):
        BasicAnalysis(
            content=content(),
            category=ContentCategory.UNDETERMINED,
            confidence=ConfidenceLevel.LOW,
            opening=OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
            undetermined_reason=invalid,
        )


def test_determined_analysis_rejects_mutable_undetermined_reason() -> None:
    with pytest.raises(ValueError, match="无法判断原因"):
        BasicAnalysis(
            content=content(),
            category=ContentCategory.PERSONA,
            confidence=ConfidenceLevel.HIGH,
            opening=OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
            undetermined_reason=[],
        )


@pytest.mark.parametrize(
    ("field", "invalid"),
    (
        ("category", "persona"),
        ("confidence", "high"),
        ("opening", "available"),
        ("source_information", {}),
        ("reusable_methods", ("自由文本方法",)),
        ("structure", (1,)),
        ("persuasion_chain", ("",)),
    ),
)
def test_basic_analysis_strictly_validates_model_nested_output(field, invalid) -> None:
    values = {
        "content": content(),
        "category": ContentCategory.PERSONA,
        "confidence": ConfidenceLevel.MEDIUM,
        "opening": OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
        field: invalid,
    }

    with pytest.raises(ValueError):
        BasicAnalysis(**values)


def test_opening_annotation_represents_available_evidence_or_unavailable_reason() -> None:
    available = OpeningAnnotation(
        status=OpeningTagStatus.AVAILABLE,
        kind=OpeningKind.LANGUAGE,
        fragment="前三秒语言提问",
        evidence=(
            AnalysisEvidence(
                evidence_type=EvidenceType.TRANSCRIPT,
                locator="transcript:0-3s",
                detail="转写中出现提问",
            ),
        ),
    )
    unavailable = OpeningAnnotation(
        status=OpeningTagStatus.UNAVAILABLE,
        kind=OpeningKind.LANGUAGE,
        unavailable_reason="没有可用的转写依据",
    )

    assert available.fragment == "前三秒语言提问"
    assert available.evidence[0].evidence_type == EvidenceType.TRANSCRIPT
    assert available.evidence[0].locator == "transcript:0-3s"
    assert unavailable.unavailable_reason == "没有可用的转写依据"


@pytest.mark.parametrize(
    ("evidence_type", "locator", "detail"),
    (
        ("visual", "frame:0-3s", "画面证据"),
        (EvidenceType.TITLE, "  ", "标题证据"),
        (EvidenceType.TRANSCRIPT, "0-3s", "  "),
    ),
)
def test_analysis_evidence_requires_closed_type_and_nonempty_location(
    evidence_type: object,
    locator: str,
    detail: str,
) -> None:
    with pytest.raises(ValueError, match="分析依据"):
        AnalysisEvidence(evidence_type, locator, detail)


def test_project_context_keeps_confirmed_facts_separate_from_source_limited_information() -> None:
    source_information = SourceInformation(
        facts=(SourceFact(statement="素材显示单一场景", source="sample-work-001"),),
        judgments=(SourceJudgment(statement="开头可能吸引目标用户"),),
        assumptions=(SourceAssumption(statement="样本可代表当前表达方式"),),
        limitations=(SourceLimitation(statement="没有完整画面来源"),),
        source_constraints=(SourceConstraint(statement="只适用于该合成样本"),),
    )
    context = ProjectContextVersion(
        project_id="project-001",
        version="context-v1",
        effective_at=datetime(2026, 9, 3, tzinfo=SHANGHAI),
        project_persona="项目角色",
        target_users="目标用户",
        content_plan="内容规划",
        operating_direction="经营方向",
        confirmed_facts=(ProjectFact(key="product_scope", value="合成产品范围"),),
    )

    result = BasicAnalysis(
        content=content(),
        category=ContentCategory.PERSONA,
        confidence=ConfidenceLevel.MEDIUM,
        opening=OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
        source_information=source_information,
        reusable_methods=(
            ReusableMethod(
                name="问题-方法-结果",
                description="按三段结构整理",
                method_key="problem-method-result",
                evidence=(
                    AnalysisEvidence(
                        EvidenceType.METADATA,
                        "sample-work-001",
                        "合成样本结构",
                    ),
                ),
                applicable_boundaries=(SourceConstraint("仅复用结构"),),
            ),
        ),
    )

    assert result.source_information.facts[0].source == "sample-work-001"
    assert result.source_information.limitations[0].statement == "没有完整画面来源"
    assert context.confirmed_facts[0].key == "product_scope"
    assert context.project_persona == "项目角色"


@pytest.mark.parametrize(
    ("field", "invalid"),
    (
        ("facts", ("事实",)),
        ("judgments", ("判断",)),
        ("assumptions", ("假设",)),
        ("limitations", ("限制",)),
        ("source_constraints", ("边界",)),
    ),
)
def test_source_information_rejects_unstructured_nested_values(field, invalid) -> None:
    with pytest.raises(ValueError, match="来源限定信息"):
        SourceInformation(**{field: invalid})


@pytest.mark.parametrize(
    "factory",
    (
        lambda: SourceJudgment(statement=""),
        lambda: SourceAssumption(statement=1),
        lambda: SourceLimitation(statement="  "),
        lambda: SourceConstraint(statement=None),
    ),
)
def test_source_information_nested_objects_require_non_empty_text(factory) -> None:
    with pytest.raises(ValueError):
        factory()


def test_sensitive_source_fact_requires_explicit_restricted_fragments() -> None:
    with pytest.raises(ValueError, match="来源限定片段"):
        SourceFact(
            statement="原视频展示欧莱雅商品",
            source="sample-work-source",
            kind=content_analysis.SourceFactKind.BRAND,
        )


def test_source_fact_restricted_fragments_must_be_immutable_and_bound_to_statement() -> None:
    with pytest.raises(ValueError, match="来源限定片段"):
        SourceFact(
            statement="原视频展示欧莱雅商品",
            source="sample-work-source",
            kind=content_analysis.SourceFactKind.BRAND,
            restricted_fragments=["欧莱雅"],
        )
    with pytest.raises(ValueError, match="来源限定片段"):
        SourceFact(
            statement="原视频展示欧莱雅商品",
            source="sample-work-source",
            kind=content_analysis.SourceFactKind.BRAND,
            restricted_fragments=("另一个品牌",),
        )


@pytest.mark.parametrize("generic_fragment", ("原视频", "展示", "商品", "来源内容"))
def test_sensitive_source_fact_rejects_generic_context_as_restricted_fragment(
    generic_fragment: str,
) -> None:
    statement = f"来源内容原视频展示欧莱雅商品"
    with pytest.raises(ValueError, match="具体来源实体"):
        SourceFact(
            statement=statement,
            source="sample-work-source",
            kind=content_analysis.SourceFactKind.BRAND,
            restricted_fragments=(generic_fragment,),
        )


def test_source_fact_kind_members_remain_distinct_enum_values() -> None:
    assert content_analysis.SourceFactKind.PRICE != content_analysis.SourceFactKind.OTHER
    assert len(set(content_analysis.SourceFactKind)) == len(tuple(content_analysis.SourceFactKind))


@pytest.mark.parametrize(
    "field",
    (
        "reusable_methods",
        "structure",
        "persuasion_chain",
        "interaction_observations",
    ),
)
def test_basic_analysis_rejects_mutable_nested_collections(field) -> None:
    values = {
        "content": content(),
        "category": ContentCategory.PERSONA,
        "confidence": ConfidenceLevel.MEDIUM,
        "opening": OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
        field: [],
    }

    with pytest.raises(ValueError, match="不可变元组"):
        BasicAnalysis(**values)


@pytest.mark.parametrize(
    "factory",
    (
        lambda: SourceInformation(facts=[]),
        lambda: OpeningAnnotation(
            status=OpeningTagStatus.UNANNOTATED,
            evidence=[],
        ),
        lambda: ReusableMethod(
            name="方法",
            description="结构",
            method_key="method",
            evidence=[],
            applicable_boundaries=(),
        ),
        lambda: ProjectContextVersion(
            project_id="project-001",
            version="v1",
            effective_at=datetime(2026, 9, 1, tzinfo=SHANGHAI),
            project_persona="匿名人设",
            target_users="匿名用户",
            content_plan="匿名规划",
            operating_direction="匿名方向",
            confirmed_facts=[],
        ),
    ),
)
def test_frozen_domain_objects_reject_mutable_nested_collections(factory) -> None:
    with pytest.raises(ValueError, match="不可变元组"):
        factory()


def test_phase1_fixture_is_small_anonymous_standard_input_without_category_or_local_path() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    contents = [
        content
        for sync_result in fixture["sync_results"]
        for content in sync_result["contents"]
    ]

    assert 1 <= len(contents) <= 10
    assert all(item["account_id"].startswith("account-") for item in contents)
    assert all(
        item["identity"].get("platform_content_id", "").startswith("sample-")
        for item in contents
    )
    assert all("category" not in item for item in contents)
    assert all(len(item.get("transcript") or "") <= 120 for item in contents)
    assert fixture["relations"]
    assert fixture["contexts"]
    assert "/Users/" not in FIXTURE_PATH.read_text(encoding="utf-8")
    assert "C:\\" not in FIXTURE_PATH.read_text(encoding="utf-8")


def test_domain_has_only_one_daily_report_and_candidate_model_family() -> None:
    assert not hasattr(content_domain, "DailyReport")
    assert not hasattr(content_domain, "ContentCandidate")
    assert not hasattr(content_domain, "ProjectJudgment")
    assert not hasattr(content_domain, "ContentStatistics")
