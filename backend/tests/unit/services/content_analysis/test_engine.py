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
    OpeningAnnotation,
    OpeningTagStatus,
    ProjectAccountRelation,
    ProjectContextVersion,
    ProjectFact,
    ReusableMethod,
    SourceFact,
    SourceInformation,
    SourceJudgment,
    SourceLimitation,
    SyncStatus,
)
from app.services.content_analysis.engine import (
    AccountSyncResult,
    ContentAnalysisEngine,
    SavedBusinessState,
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
            interaction_observations=("评论关注使用方法",),
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


@pytest.mark.asyncio
async def test_injected_async_analyzer_reuses_basic_analysis_but_seals_each_project() -> None:
    analyzer = RecordingAnalyzer()
    duplicate_old = replace(record("work-001"), captured_at=RUN_AT - timedelta(hours=1))
    duplicate_new = replace(record("work-001"), transcript="匿名人物故事")
    engine = ContentAnalysisEngine(analyzer)

    result = await engine.run(
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
    result = await ContentAnalysisEngine(RecordingAnalyzer()).run(
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
    result = await ContentAnalysisEngine(RecordingAnalyzer()).run(
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
                fragment="第一画面出现产品",
                evidence=(AnalysisEvidence(EvidenceType.METADATA, "video", "仅有视频引用字符串"),),
            ),
            shot_observations=(AnalysisEvidence(EvidenceType.METADATA, "shot-1", "推测镜头"),),
        )


@pytest.mark.asyncio
async def test_missing_transcript_continues_and_video_reference_is_not_visual_evidence() -> None:
    analyzer = VisualClaimAnalyzer()
    result = await ContentAnalysisEngine(analyzer).run(
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
                fragment="仅凭元数据猜测第一画面",
                evidence=(AnalysisEvidence(EvidenceType.METADATA, "video", "引用存在"),),
            ),
            shot_observations=(
                AnalysisEvidence(EvidenceType.VISUAL, "4-6s", "可读画面中的镜头"),
                AnalysisEvidence(EvidenceType.METADATA, "7-9s", "元数据猜测的镜头"),
            ),
        )


@pytest.mark.asyncio
async def test_transcript_only_opening_is_kept_without_visual_evidence() -> None:
    result = await ContentAnalysisEngine(TranscriptOpeningAnalyzer()).run(
        sync_results=(AccountSyncResult("account-001", SyncStatus.SUCCESS_WITH_CONTENT, (record("work-001"),)),),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    opening = result.reports["project-a"].items[0].analysis.opening
    assert opening.status == OpeningTagStatus.AVAILABLE
    assert opening.fragment == "语言开头：先问一个问题"


@pytest.mark.asyncio
async def test_each_visual_claim_requires_visual_evidence_of_its_own() -> None:
    result = await ContentAnalysisEngine(MixedEvidenceAnalyzer()).run(
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
async def test_sync_states_are_preserved_and_only_confirmed_all_empty_is_empty_daily() -> None:
    engine = ContentAnalysisEngine(RecordingAnalyzer())
    contexts = tuple(context(f"project-{suffix}", "v1") for suffix in ("content", "empty", "partial", "failed"))
    result = await engine.run(
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
    result = await ContentAnalysisEngine(analyzer).run(
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
    result = await ContentAnalysisEngine(RecordingAnalyzer()).run(
        sync_results=(AccountSyncResult("account-001", SyncStatus.SUCCESS_WITH_CONTENT, (record("work-001"),)),),
        relations=(relation("project-a", "v1", "account-missing"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assert report.items == ()
    assert report.is_empty_daily is False
    assert report.relation_issues == ("账号关系 account-missing 没有精确匹配的同步结果",)


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
    result = await ContentAnalysisEngine(RecordingAnalyzer()).run(
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
    result = await ContentAnalysisEngine(analyzer).run(
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
    result = await ContentAnalysisEngine(RecordingAnalyzer()).run(
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
    result = await ContentAnalysisEngine(RecordingAnalyzer()).run(
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


@pytest.mark.asyncio
async def test_cross_project_methods_require_two_actual_library_entries_and_strip_source_scope() -> None:
    result = await ContentAnalysisEngine(RecordingAnalyzer()).run(
        sync_results=(AccountSyncResult("account-001", SyncStatus.SUCCESS_WITH_CONTENT, (record("work-001"),)),),
        relations=(relation("project-a", "v1"), relation("project-b", "v2")),
        contexts=(context("project-a", "v1"), context("project-b", "v2")),
        run_at=RUN_AT,
    )

    assert len(result.cross_project_candidates) == 1
    candidate = result.cross_project_candidates[0]
    assert candidate.method == ReusableMethod(name="问题到证明", description="先问题后证明")
    assert candidate.project_ids == ("project-a", "project-b")
    assert candidate.auto_written_project_ids == ()
    assert not hasattr(candidate, "source_information")
