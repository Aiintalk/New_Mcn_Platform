"""阶段一确定性内容分析规则的测试。"""
import json
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

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
    BusinessStatus,
    ConfidenceLevel,
    ContentCandidate,
    ContentCategory,
    ContentIdentity,
    ContentRecord,
    ContentSource,
    DailyReport,
    EngagementMetrics,
    EvidenceType,
    OpeningAnnotation,
    OpeningTagStatus,
    ProjectContextVersion,
    ProjectFact,
    ProjectJudgment,
    ReusableMethod,
    SourceAssumption,
    SourceConstraint,
    SourceFact,
    SourceInformation,
    SourceJudgment,
    SourceLimitation,
    SyncStatus,
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
        transcript=transcript,
        sync_status=SyncStatus.SUCCESS_WITH_CONTENT,
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


def test_basic_analysis_requires_reason_for_undetermined_category() -> None:
    with pytest.raises(ValueError):
        analysis(content(), category=ContentCategory.UNDETERMINED)

    result = analysis(
        content(),
        category=ContentCategory.UNDETERMINED,
        undetermined_reason="缺少可判定标签",
    )

    assert result.undetermined_reason == "缺少可判定标签"


def test_opening_annotation_represents_available_evidence_or_unavailable_reason() -> None:
    available = OpeningAnnotation(
        status=OpeningTagStatus.AVAILABLE,
        fragment="前三秒画面提问",
        evidence=(
            AnalysisEvidence(
                evidence_type=EvidenceType.VISUAL,
                locator="frame:0-3s",
                detail="画面中出现提问字幕",
            ),
        ),
    )
    unavailable = OpeningAnnotation(
        status=OpeningTagStatus.UNAVAILABLE,
        unavailable_reason="没有可用的视频或转写依据",
    )

    assert available.fragment == "前三秒画面提问"
    assert available.evidence[0].evidence_type == EvidenceType.VISUAL
    assert available.evidence[0].locator == "frame:0-3s"
    assert unavailable.unavailable_reason == "没有可用的视频或转写依据"


def test_project_context_keeps_confirmed_facts_separate_from_source_limited_information() -> None:
    source_information = SourceInformation(
        facts=(SourceFact(statement="素材显示单一场景", source="sample-work-001"),),
        judgments=(SourceJudgment(statement="开头可能吸引目标用户"),),
        assumptions=(SourceAssumption(statement="样本可代表当前表达方式"),),
        limitations=(SourceLimitation(statement="没有完整画面来源"),),
        reusable_methods=(ReusableMethod(name="问题-方法-结果", description="按三段结构整理"),),
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

    result = analysis(content(), source_information=source_information)

    assert result.source_information.facts[0].source == "sample-work-001"
    assert result.source_information.limitations[0].statement == "没有完整画面来源"
    assert context.confirmed_facts[0].key == "product_scope"
    assert context.project_persona == "项目角色"


def test_daily_report_rejects_judgments_from_another_project_and_candidate_binds_context() -> None:
    own_judgment = ProjectJudgment(
        project_id="project-001",
        context_version="context-v1",
        status=BusinessStatus.ACTIVE,
        confidence=ConfidenceLevel.HIGH,
        conclusion="项目内判断",
    )
    foreign_judgment = ProjectJudgment(
        project_id="project-002",
        context_version="context-v1",
        status=BusinessStatus.ACTIVE,
        confidence=ConfidenceLevel.HIGH,
        conclusion="其他项目判断",
    )
    report = DailyReport(
        project_id="project-001",
        context_version="context-v1",
        report_date=date(2026, 9, 3),
        generated_at=datetime(2026, 9, 4, tzinfo=SHANGHAI),
        judgments=(own_judgment,),
    )
    candidate = ContentCandidate(
        project_id="project-001",
        context_version="context-v1",
        content=content(),
        status=BusinessStatus.ACTIVE,
        confidence=ConfidenceLevel.MEDIUM,
    )

    with pytest.raises(ValueError):
        DailyReport(
            project_id="project-001",
            context_version="context-v1",
            report_date=date(2026, 9, 3),
            generated_at=datetime(2026, 9, 4, tzinfo=SHANGHAI),
            judgments=(own_judgment, foreign_judgment),
        )

    assert report.judgments == (own_judgment,)
    assert candidate.project_id == "project-001"
    assert candidate.context_version == "context-v1"


def test_phase1_fixture_is_small_anonymous_standard_input_without_category_or_local_path() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    contents = fixture["contents"]

    assert 1 <= len(contents) <= 10
    assert all(item["account_id"].startswith("account-") for item in contents)
    assert all(
        item["identity"].get("platform_content_id", "").startswith("sample-")
        for item in contents
    )
    assert all("category" not in item for item in contents)
    assert all(len(item.get("transcript") or "") <= 120 for item in contents)
    assert "/Users/" not in FIXTURE_PATH.read_text(encoding="utf-8")
    assert "C:\\" not in FIXTURE_PATH.read_text(encoding="utf-8")
