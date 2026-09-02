"""内容分析阶段一离线引擎的项目隔离和可信边界测试。"""
from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services.content_analysis.analyzer import ProjectAssessment
from app.services.content_analysis.domain import (
    AnalysisEvidence,
    BasicAnalysis,
    ConfidenceLevel,
    ContentCategory,
    ContentIdentity,
    ContentRecord,
    ContentSource,
    EngagementMetrics,
    EvidenceType,
    DataMaturity,
    InteractionMetric,
    InteractionObservation,
    InteractionObservationType,
    OpeningAnnotation,
    OpeningKind,
    OpeningTagStatus,
    ProjectAccountRelation,
    ProjectContextVersion,
    ProjectFact,
    ReusableMethod,
    RelativePerformanceLevel,
    SourceFact,
    SourceInformation,
    SourceJudgment,
    SourceLimitation,
    SyncStatus,
)
from app.services.content_analysis.engine import (
    AccountSyncResult,
    ContentAnalysisEngine,
    OfflineRunInput,
    SavedBusinessState,
    SavedLibraryRecord,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
RUN_AT = datetime(2026, 9, 4, 9, tzinfo=SHANGHAI)
REPORT_DAY = datetime(2026, 9, 3, 10, tzinfo=SHANGHAI)


def record(
    work_id: str | None,
    *,
    account_id: str = "account-001",
    url: str | None = None,
    published_at: datetime = REPORT_DAY,
    transcript: str | None = "匿名转写",
    video_reference: str | None = None,
    likes: int | None = 10,
    comments: int | None = 2,
    shares: int | None = 1,
    favorites: int | None = 3,
) -> ContentRecord:
    return ContentRecord(
        account_id=account_id,
        source=ContentSource.PLATFORM_SYNC,
        identity=ContentIdentity(platform_content_id=work_id, external_url=url),
        published_at=published_at,
        captured_at=RUN_AT,
        metrics=EngagementMetrics(
            like_count=likes,
            comment_count=comments,
            share_count=shares,
            favorite_count=favorites,
        ),
        transcript=transcript,
        video_reference=video_reference,
    )


def context(project_id: str, version: str, *, persona: str = "匿名人设") -> ProjectContextVersion:
    return ProjectContextVersion(
        project_id=project_id,
        version=version,
        effective_at=datetime(2026, 9, 1, tzinfo=SHANGHAI),
        project_persona=persona,
        target_users="匿名目标用户",
        content_plan="匿名内容规划",
        operating_direction="匿名经营方向",
        confirmed_facts=(ProjectFact(key="current_product", value=f"{project_id}-已确认商品"),),
    )


class RecordingAnalyzer:
    """用匿名转写模拟智能分析，调用记录只用于验证引擎边界。"""

    def __init__(self) -> None:
        self.basic_calls: list[ContentRecord] = []
        self.project_calls: list[tuple[BasicAnalysis, ProjectContextVersion]] = []

    async def analyze_content(self, content: ContentRecord) -> BasicAnalysis:
        self.basic_calls.append(content)
        transcript = content.transcript or ""
        is_qianchuan = any(
            marker in transcript
            for marker in ("种草", "使用流程", "卖点证明", "成交促单")
        )
        if is_qianchuan:
            category = ContentCategory.QIANCHUAN
            reason = None
        elif transcript:
            category = ContentCategory.PERSONA
            reason = None
        else:
            category = ContentCategory.UNDETERMINED
            reason = "缺少转写与可判定证据"
        return BasicAnalysis(
            content=content,
            category=category,
            confidence=(
                ConfidenceLevel.LOW
                if category == ContentCategory.UNDETERMINED
                else ConfidenceLevel.HIGH
            ),
            opening=OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
            source_information=SourceInformation(
                facts=(SourceFact(statement="来源商品宣称有效", source="匿名来源"),),
                judgments=(SourceJudgment(statement="来源表达具备说服力"),),
                reusable_methods=(ReusableMethod(name="问题到证明", description="先问题后证明"),),
            ),
            topic="匿名选题",
            structure=("问题", "方法", "证明"),
            persuasion_chain=("痛点", "证据", "行动"),
            interaction_observations=(
                InteractionObservation(
                    InteractionObservationType.CURRENT_COMPOSITION,
                    numerator_metric=InteractionMetric.COMMENT,
                    numerator_value=2,
                    denominator_metric=InteractionMetric.LIKE,
                    denominator_value=10,
                ),
            ),
            undetermined_reason=reason,
        )

    async def assess_project(
        self, analysis: BasicAnalysis, project_context: ProjectContextVersion
    ) -> ProjectAssessment:
        self.project_calls.append((analysis, project_context))
        return ProjectAssessment(
            project_id="analyzer-must-not-own-project",
            context_version="analyzer-must-not-own-version",
            is_fit=True,
            is_opportunity=True,
            should_add_to_library=True,
            priority=1,
            confidence=analysis.confidence,
            conclusion=f"适配 {project_context.project_persona}",
            body_benchmark="问题—方法—证明",
        )


def relation(project_id: str, version: str, account_id: str = "account-001") -> ProjectAccountRelation:
    return ProjectAccountRelation(
        project_id=project_id,
        account_id=account_id,
        context_version=version,
    )


async def run_engine(analyzer: RecordingAnalyzer, **input_values: object):
    return await ContentAnalysisEngine(analyzer).run(OfflineRunInput(**input_values))


@pytest.mark.asyncio
async def test_injected_async_analyzer_reuses_basic_analysis_but_seals_each_project() -> None:
    analyzer = RecordingAnalyzer()
    duplicate_old = replace(record("work-001"), captured_at=RUN_AT - timedelta(hours=1))
    duplicate_new = replace(record("work-001"), transcript="匿名人物故事")
    result = await run_engine(
        analyzer,
        sync_results=(
            AccountSyncResult(
                account_id="account-001",
                status=SyncStatus.SUCCESS_WITH_CONTENT,
                contents=(duplicate_old, duplicate_new),
            ),
        ),
        relations=(relation("project-a", "v1"), relation("project-b", "v2")),
        contexts=(context("project-a", "v1", persona="人设甲"), context("project-b", "v2", persona="人设乙")),
        run_at=RUN_AT,
    )

    assert len(analyzer.basic_calls) == 1
    assert [call[1].project_id for call in analyzer.project_calls] == ["project-a", "project-b"]
    assert result.reports["project-a"].items[0].assessment.project_id == "project-a"
    assert result.reports["project-a"].items[0].assessment.context_version == "v1"
    assert result.reports["project-b"].items[0].assessment.project_id == "project-b"
    assert result.reports["project-b"].items[0].assessment.context_version == "v2"
    assert result.reports["project-a"].items[0].assessment.conclusion == "适配 人设甲"
    assert result.reports["project-b"].items[0].assessment.conclusion == "适配 人设乙"


@pytest.mark.asyncio
@pytest.mark.parametrize("marker", ["种草", "使用流程", "卖点证明", "成交促单"])
async def test_intelligent_analyzer_classifies_explicit_conversion_content(marker: str) -> None:
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001", SyncStatus.SUCCESS_WITH_CONTENT, (record(f"work-{marker}", transcript=marker),)
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    assert result.reports["project-a"].items[0].analysis.category == ContentCategory.QIANCHUAN


@pytest.mark.asyncio
async def test_missing_evidence_remains_undetermined_with_reason() -> None:
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(AccountSyncResult("account-001", SyncStatus.SUCCESS_WITH_CONTENT, (record("work-001", transcript=None),)),),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    analysis = result.reports["project-a"].items[0].analysis
    assert analysis.category == ContentCategory.UNDETERMINED
    assert analysis.undetermined_reason == "缺少转写与可判定证据"
    assert result.reports["project-a"].library_candidates == ()


class VisualClaimAnalyzer(RecordingAnalyzer):
    async def analyze_content(self, content: ContentRecord) -> BasicAnalysis:
        self.basic_calls.append(content)
        return BasicAnalysis(
            content=content,
            category=ContentCategory.PERSONA,
            confidence=ConfidenceLevel.MEDIUM,
            opening=OpeningAnnotation(
                status=OpeningTagStatus.AVAILABLE,
                kind=OpeningKind.FIRST_FRAME,
                fragment="第一画面出现产品",
                evidence=(AnalysisEvidence(EvidenceType.METADATA, "video", "仅有视频引用字符串"),),
            ),
            shot_observations=(AnalysisEvidence(EvidenceType.METADATA, "shot-1", "推测镜头"),),
        )


@pytest.mark.asyncio
async def test_missing_transcript_continues_and_video_reference_is_not_visual_evidence() -> None:
    analyzer = VisualClaimAnalyzer()
    result = await run_engine(
        analyzer,
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001", transcript=None, video_reference="opaque-video-ref"),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    analysis = result.reports["project-a"].items[0].analysis
    assert len(analyzer.basic_calls) == 1
    assert analysis.shot_observations == ()
    assert analysis.opening.status == OpeningTagStatus.UNAVAILABLE
    assert "没有可读画面证据" in analysis.opening.unavailable_reason
    assert any("没有可读画面证据" in item.statement for item in analysis.source_information.limitations)


class TranscriptOpeningAnalyzer(RecordingAnalyzer):
    async def analyze_content(self, content: ContentRecord) -> BasicAnalysis:
        base = await super().analyze_content(content)
        return replace(
            base,
            opening=OpeningAnnotation(
                status=OpeningTagStatus.AVAILABLE,
                kind=OpeningKind.LANGUAGE,
                fragment="语言开头：先问一个问题",
                evidence=(AnalysisEvidence(EvidenceType.TRANSCRIPT, "0-3s", "转写开场"),),
            ),
        )


class MixedEvidenceAnalyzer(RecordingAnalyzer):
    async def analyze_content(self, content: ContentRecord) -> BasicAnalysis:
        self.basic_calls.append(content)
        return BasicAnalysis(
            content=content,
            category=ContentCategory.PERSONA,
            confidence=ConfidenceLevel.MEDIUM,
            opening=OpeningAnnotation(
                status=OpeningTagStatus.AVAILABLE,
                kind=OpeningKind.FIRST_FRAME,
                fragment="仅凭元数据猜测第一画面",
                evidence=(AnalysisEvidence(EvidenceType.METADATA, "video", "引用存在"),),
            ),
            shot_observations=(
                AnalysisEvidence(EvidenceType.VISUAL, "4-6s", "可读画面中的镜头"),
                AnalysisEvidence(EvidenceType.METADATA, "7-9s", "元数据猜测的镜头"),
            ),
        )


class MismatchedOpeningAnalyzer(RecordingAnalyzer):
    def __init__(self, kind: OpeningKind, evidence_type: EvidenceType) -> None:
        super().__init__()
        self.kind = kind
        self.evidence_type = evidence_type

    async def analyze_content(self, content: ContentRecord) -> BasicAnalysis:
        self.basic_calls.append(content)
        return BasicAnalysis(
            content=content,
            category=ContentCategory.PERSONA,
            confidence=ConfidenceLevel.MEDIUM,
            opening=OpeningAnnotation(
                status=OpeningTagStatus.AVAILABLE,
                kind=self.kind,
                fragment="证据类型与开头类型不匹配",
                evidence=(AnalysisEvidence(self.evidence_type, "0-3s", "开头证据"),),
            ),
            shot_observations=(
                AnalysisEvidence(EvidenceType.VISUAL, "4-6s", "其他时间段画面"),
                AnalysisEvidence(EvidenceType.TRANSCRIPT, "4-6s", "其他时间段转写"),
            ),
        )


@pytest.mark.asyncio
async def test_transcript_only_opening_is_kept_without_visual_evidence() -> None:
    result = await run_engine(
        TranscriptOpeningAnalyzer(),
        sync_results=(AccountSyncResult("account-001", SyncStatus.SUCCESS_WITH_CONTENT, (record("work-001"),)),),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    opening = result.reports["project-a"].items[0].analysis.opening
    assert opening.status == OpeningTagStatus.AVAILABLE
    assert opening.kind == OpeningKind.LANGUAGE
    assert opening.fragment == "语言开头：先问一个问题"


@pytest.mark.asyncio
async def test_each_visual_claim_requires_visual_evidence_of_its_own() -> None:
    result = await run_engine(
        MixedEvidenceAnalyzer(),
        sync_results=(AccountSyncResult("account-001", SyncStatus.SUCCESS_WITH_CONTENT, (record("work-001"),)),),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    analysis = result.reports["project-a"].items[0].analysis
    assert analysis.opening.status == OpeningTagStatus.UNAVAILABLE
    assert analysis.shot_observations == (
        AnalysisEvidence(EvidenceType.VISUAL, "4-6s", "可读画面中的镜头"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "wrong_evidence"),
    (
        (OpeningKind.LANGUAGE, EvidenceType.VISUAL),
        (OpeningKind.FIRST_FRAME, EvidenceType.TRANSCRIPT),
    ),
)
async def test_opening_kind_requires_its_own_matching_evidence(
    kind: OpeningKind, wrong_evidence: EvidenceType
) -> None:
    result = await run_engine(
        MismatchedOpeningAnalyzer(kind, wrong_evidence),
        sync_results=(
            AccountSyncResult(
                "account-001", SyncStatus.SUCCESS_WITH_CONTENT, (record("work-001"),)
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    opening = result.reports["project-a"].items[0].analysis.opening
    assert opening.status == OpeningTagStatus.UNAVAILABLE
    assert opening.kind == kind


def test_available_opening_requires_explicit_kind() -> None:
    with pytest.raises(ValueError, match="开头类型"):
        OpeningAnnotation(
            status=OpeningTagStatus.AVAILABLE,
            fragment="缺少类型",
            evidence=(AnalysisEvidence(EvidenceType.TRANSCRIPT, "0-3s", "转写"),),
        )
    with pytest.raises(ValueError, match="开头类型"):
        OpeningAnnotation(
            status=OpeningTagStatus.AVAILABLE,
            kind="language",
            fragment="使用了未受限字符串类型",
            evidence=(AnalysisEvidence(EvidenceType.TRANSCRIPT, "0-3s", "转写"),),
        )


def test_interaction_observations_only_express_current_non_time_series_semantics() -> None:
    assert {item.value for item in InteractionObservationType} == {
        "current_value",
        "current_relative_performance",
        "current_composition",
        "data_maturity",
    }
    with pytest.raises(ValueError, match="互动观察类型"):
        InteractionObservation(observation_type="trend")
    with pytest.raises(ValueError, match="结构化互动观察"):
        BasicAnalysis(
            content=record("work-invalid-observation"),
            category=ContentCategory.PERSONA,
            confidence=ConfidenceLevel.MEDIUM,
            opening=OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
            interaction_observations=("任意字符串",),
        )


def test_legal_interaction_type_cannot_carry_growth_free_text() -> None:
    with pytest.raises(TypeError, match="statement"):
        InteractionObservation(
            InteractionObservationType.CURRENT_VALUE,
            statement="点赞较昨日增长 50%",
        )


def test_interaction_observation_validates_closed_field_combinations() -> None:
    observations = (
        InteractionObservation(
            InteractionObservationType.CURRENT_VALUE,
            metric=InteractionMetric.LIKE,
            current_value=10,
        ),
        InteractionObservation(
            InteractionObservationType.CURRENT_RELATIVE_PERFORMANCE,
            metric=InteractionMetric.COMMENT,
            relative_level=RelativePerformanceLevel.ABOVE,
            benchmark_value=5.0,
            sample_size=8,
        ),
        InteractionObservation(
            InteractionObservationType.CURRENT_COMPOSITION,
            numerator_metric=InteractionMetric.SHARE,
            numerator_value=2,
            denominator_metric=InteractionMetric.FAVORITE,
            denominator_value=4,
        ),
        InteractionObservation(
            InteractionObservationType.DATA_MATURITY,
            maturity=DataMaturity.QUALITATIVE,
        ),
    )

    assert len(observations) == 4
    with pytest.raises(ValueError, match="字段组合"):
        InteractionObservation(
            InteractionObservationType.CURRENT_VALUE,
            metric=InteractionMetric.LIKE,
            current_value=10,
            relative_level=RelativePerformanceLevel.ABOVE,
        )


@pytest.mark.asyncio
async def test_sync_states_are_preserved_and_only_confirmed_all_empty_is_empty_daily() -> None:
    contexts = tuple(context(f"project-{suffix}", "v1") for suffix in ("content", "empty", "partial", "failed"))
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult("account-content", SyncStatus.SUCCESS_WITH_CONTENT, (record("work-001", account_id="account-content"),)),
            AccountSyncResult("account-empty", SyncStatus.SUCCESS_WITHOUT_CONTENT),
            AccountSyncResult("account-partial", SyncStatus.PARTIAL_SUCCESS),
            AccountSyncResult("account-failed", SyncStatus.FAILED, issue="同步失败"),
        ),
        relations=tuple(relation(f"project-{suffix}", "v1", f"account-{suffix}") for suffix in ("content", "empty", "partial", "failed")),
        contexts=contexts,
        run_at=RUN_AT,
    )

    assert result.reports["project-content"].sync_results[0].status == SyncStatus.SUCCESS_WITH_CONTENT
    assert result.reports["project-empty"].is_empty_daily is True
    assert result.reports["project-partial"].is_empty_daily is False
    assert result.reports["project-failed"].is_empty_daily is False
    assert result.reports["project-failed"].sync_results[0].issue == "同步失败"


@pytest.mark.asyncio
async def test_historic_thirty_day_content_is_analyzed_but_does_not_make_three_day_report_nonempty() -> None:
    analyzer = RecordingAnalyzer()
    historic = record("work-historic", published_at=REPORT_DAY - timedelta(days=10))
    result = await run_engine(
        analyzer,
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITHOUT_CONTENT,
                (historic,),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assert len(analyzer.basic_calls) == 1
    assert report.is_empty_daily is True
    assert report.items == ()
    assert report.library_candidates == ()


@pytest.mark.asyncio
async def test_unmatched_relation_is_reported_without_guessing_content_ownership() -> None:
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(AccountSyncResult("account-001", SyncStatus.SUCCESS_WITH_CONTENT, (record("work-001"),)),),
        relations=(relation("project-a", "v1", "account-missing"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assert report.items == ()
    assert report.is_empty_daily is False
    assert report.relation_issues == ("账号关系 account-missing 没有精确匹配的同步结果",)
    assert result.relation_issues == report.relation_issues


@pytest.mark.asyncio
async def test_project_without_account_relation_is_global_issue_and_report_is_skipped() -> None:
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001", SyncStatus.SUCCESS_WITH_CONTENT, (record("work-001"),)
            ),
        ),
        relations=(),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    assert "project-a" not in result.reports
    assert result.relation_issues == ("项目 project-a（v1）没有账号关系",)


@pytest.mark.asyncio
async def test_duplicate_project_context_versions_are_rejected_instead_of_overwritten() -> None:
    with pytest.raises(ValueError, match="项目 project-a.*多个上下文版本"):
        await run_engine(
            RecordingAnalyzer(),
            sync_results=(AccountSyncResult("account-001", SyncStatus.SUCCESS_WITHOUT_CONTENT),),
            relations=(relation("project-a", "v1"),),
            contexts=(context("project-a", "v1"), context("project-a", "v2")),
            run_at=RUN_AT,
        )


@pytest.mark.asyncio
async def test_opportunities_are_capped_library_candidate_is_atomic_and_metrics_keep_missing() -> None:
    records = tuple(
        record(
            f"work-{index}",
            transcript=("卖点证明" if index < 5 else "匿名人物故事"),
            likes=(100 - index if index != 1 else None),
            comments=(index if index != 2 else None),
            shares=(index if index != 3 else None),
            favorites=(index if index != 4 else None),
        )
        for index in range(8)
    )
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(AccountSyncResult("account-001", SyncStatus.SUCCESS_WITH_CONTENT, records),),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assert len(report.qianchuan_opportunities) == 3
    assert len(report.persona_opportunities) == 3
    qianchuan = report.library_candidates[0]
    assert qianchuan.stable_key == "platform_content_id:work-0"
    assert qianchuan.body_benchmark == "问题—方法—证明"
    assert qianchuan.opening_status == OpeningTagStatus.UNANNOTATED
    assert qianchuan.opening_kind is None
    assert qianchuan.opening_fragment is None
    assert qianchuan.opening_unavailable_reason is None
    assert qianchuan.source_information.facts == (
        SourceFact(statement="来源商品宣称有效", source="匿名来源"),
    )
    assert report.interactions.like_count.total == sum(100 - index for index in range(8) if index != 1)
    assert report.interactions.like_count.missing_count == 1
    assert report.interactions.comment_count.missing_count == 1
    assert report.interactions.share_count.missing_count == 1
    assert report.interactions.favorite_count.missing_count == 1
    assert not hasattr(report.interactions, "play_rate")
    assert not hasattr(report.interactions, "trend")


@pytest.mark.asyncio
async def test_unstable_identity_is_analyzed_but_never_automatically_added_to_library() -> None:
    analyzer = RecordingAnalyzer()
    result = await run_engine(
        analyzer,
        sync_results=(AccountSyncResult("account-001", SyncStatus.SUCCESS_WITH_CONTENT, (record(None),)),),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assert len(analyzer.basic_calls) == 1
    assert len(report.items) == 1
    assert report.library_candidates == ()


@pytest.mark.asyncio
async def test_source_claims_never_become_project_facts_and_report_keeps_epistemic_fields() -> None:
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(AccountSyncResult("account-001", SyncStatus.SUCCESS_WITH_CONTENT, (record("work-001"),)),),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    item = result.reports["project-a"].items[0]
    assert item.project_facts == (ProjectFact("current_product", "project-a-已确认商品"),)
    assert item.analysis.source_information.facts == (
        SourceFact(statement="来源商品宣称有效", source="匿名来源"),
    )
    assert item.analysis.source_information.judgments
    assert item.analysis.source_information.assumptions == ()
    assert item.analysis.source_information.limitations
    assert item.assessment.confidence == ConfidenceLevel.HIGH


@pytest.mark.asyncio
async def test_previous_two_days_reenter_only_when_saved_business_state_changes() -> None:
    previous_day = REPORT_DAY - timedelta(days=1)
    unchanged = record("work-unchanged", published_at=previous_day, likes=99)
    changed = record("work-changed", published_at=previous_day, likes=1)
    no_history = record("work-new", published_at=previous_day)
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(AccountSyncResult("account-001", SyncStatus.SUCCESS_WITH_CONTENT, (unchanged, changed, no_history)),),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        saved_states=(
            SavedBusinessState(
                project_id="project-a",
                stable_key="platform_content_id:work-unchanged",
                candidate_rank=1,
                is_opportunity=True,
                in_library=True,
                priority=1,
                cross_project=False,
                conclusion="适配 匿名人设",
                confidence=ConfidenceLevel.HIGH,
            ),
            SavedBusinessState(
                project_id="project-a",
                stable_key="platform_content_id:work-changed",
                candidate_rank=2,
                is_opportunity=False,
                in_library=True,
                priority=1,
                cross_project=False,
                conclusion="适配 匿名人设",
                confidence=ConfidenceLevel.HIGH,
            ),
        ),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assert [item.stable_key for item in report.previous_two_day_changes] == [
        "platform_content_id:work-changed"
    ]
    assert [item.stable_key for item in report.items] == [
        "platform_content_id:work-changed"
    ]
    assert [item.stable_key for item in report.persona_opportunities] == [
        "platform_content_id:work-changed"
    ]
    assert [item.stable_key for item in report.library_candidates] == [
        "platform_content_id:work-changed"
    ]


@pytest.mark.asyncio
async def test_cross_project_methods_require_saved_library_entries_and_strip_source_scope() -> None:
    input_values = dict(
        sync_results=(AccountSyncResult("account-001", SyncStatus.SUCCESS_WITH_CONTENT, (record("work-001"),)),),
        relations=(relation("project-a", "v1"), relation("project-b", "v2")),
        contexts=(context("project-a", "v1"), context("project-b", "v2")),
        run_at=RUN_AT,
    )
    pending_result = await run_engine(RecordingAnalyzer(), **input_values)

    assert pending_result.reports["project-a"].library_candidates
    assert pending_result.reports["project-b"].library_candidates
    assert pending_result.cross_project_candidates == ()

    method = ReusableMethod(name="问题到证明", description="先问题后证明")
    result = await run_engine(
        RecordingAnalyzer(),
        **input_values,
        saved_library_records=(
            SavedLibraryRecord("project-a", "saved-work-a", (method,)),
            SavedLibraryRecord("project-b", "saved-work-b", (method,)),
        ),
    )

    assert len(result.cross_project_candidates) == 1
    candidate = result.cross_project_candidates[0]
    assert candidate.method == method
    assert candidate.project_ids == ("project-a", "project-b")
    assert candidate.auto_written_project_ids == ()
    assert not hasattr(candidate, "source_information")
