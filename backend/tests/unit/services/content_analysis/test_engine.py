"""内容分析阶段一离线引擎的项目隔离和可信边界测试。"""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import app.services.content_analysis as content_analysis
from app.services.content_analysis import (
    CrossProjectSignal,
    CrossProjectSource,
    ProjectFitDimension,
    ProjectFitReason,
)
from app.services.content_analysis.analyzer import (
    CandidateValueSignal,
    ProjectAssessment,
    is_reusable_method_safe,
)
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
    SourceConstraint,
    SourceAssumption,
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
    video_reference: str | None = "opaque-video-ref",
    likes: int | None = 10,
    comments: int | None = 2,
    shares: int | None = 1,
    favorites: int | None = 3,
    sync_status: SyncStatus = SyncStatus.SUCCESS_WITH_CONTENT,
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
        sync_status=sync_status,
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


def reusable_method(method_key: str, name: str, description: str) -> ReusableMethod:
    return ReusableMethod(
        name=name,
        description=description,
        method_key=method_key,
        evidence=(
            AnalysisEvidence(EvidenceType.METADATA, "method:source", "来源结构证据"),
        ),
        applicable_boundaries=(SourceConstraint("仅复用表达结构，不复用来源商品事实"),),
    )


def test_project_assessment_value_signal_is_closed_enum() -> None:
    with pytest.raises(ValueError, match="候选价值信号"):
        ProjectAssessment(
            project_id="project-a",
            context_version="v1",
            is_fit=True,
            confidence=ConfidenceLevel.HIGH,
            conclusion="适配匿名项目",
            value_signals=("任意自由文本",),
        )


def test_project_assessment_rejects_model_library_veto_field() -> None:
    with pytest.raises(TypeError, match="should_add_to_library"):
        ProjectAssessment(
            project_id="project-a",
            context_version="v1",
            is_fit=True,
            confidence=ConfidenceLevel.HIGH,
            conclusion="适配匿名项目",
            should_add_to_library=False,
        )


def test_project_assessment_rejects_opportunity_that_is_not_project_fit() -> None:
    with pytest.raises(ValueError, match="机会.*适配"):
        ProjectAssessment(
            project_id="project-a",
            context_version="v1",
            is_fit=False,
            is_opportunity=True,
            confidence=ConfidenceLevel.HIGH,
            conclusion="不适配但错误标成机会",
        )


@pytest.mark.parametrize("invalid", ("false", 0, 1, None))
def test_project_assessment_requires_native_booleans(invalid) -> None:
    with pytest.raises(ValueError, match="布尔"):
        ProjectAssessment(
            project_id="project-a",
            context_version="v1",
            is_fit=invalid,
            confidence=ConfidenceLevel.HIGH,
            conclusion="严格校验",
        )


@pytest.mark.parametrize(
    ("field", "invalid"),
    (
        ("confidence", "high"),
        ("priority", "1"),
        ("priority", 1.5),
        ("priority", True),
        ("priority", -1),
        ("conclusion", "  "),
        ("recommended_action", "  "),
    ),
)
def test_project_assessment_rejects_invalid_enum_priority_or_conclusion(
    field: str,
    invalid,
) -> None:
    values = {
        "project_id": "project-a",
        "context_version": "v1",
        "is_fit": True,
        "confidence": ConfidenceLevel.HIGH,
        "conclusion": "严格校验",
        field: invalid,
    }
    with pytest.raises(ValueError):
        ProjectAssessment(**values)


def test_candidate_value_signals_match_the_six_allowed_business_signals() -> None:
    assert {signal.value for signal in CandidateValueSignal} == {
        "early_data_strength",
        "relative_benchmark_outperformance",
        "novel_topic_or_structure",
        "clear_traffic_hook",
        "reusable_conversion_structure",
        "notable_shot_performance",
    }
    with pytest.raises(ValueError):
        CandidateValueSignal("project_relevance")


def test_cross_project_signals_match_the_five_v16_conditions() -> None:
    assert {"CrossProjectSignal", "CrossProjectSource"} <= set(
        content_analysis.__all__
    )
    assert {signal.value for signal in CrossProjectSignal} == {
        "strong_engagement",
        "novel_content_method",
        "reusable_conversion_structure",
        "explicit_cross_project_fit",
        "shared_content_problem_solution",
    }
    with pytest.raises(ValueError):
        CrossProjectSignal("single_source_recency")


def test_saved_library_record_requires_closed_signals_and_nonblank_scenarios() -> None:
    with pytest.raises(ValueError, match="跨项目信号"):
        SavedLibraryRecord(
            "project-a",
            "saved-work-a",
            (),
            source_information=SourceInformation(),
            signals=("任意信号",),
        )
    with pytest.raises(ValueError, match="适用场景"):
        SavedLibraryRecord(
            "project-a",
            "saved-work-a",
            (),
            source_information=SourceInformation(),
            scenarios=("  ",),
        )


def test_saved_library_record_requires_explicit_source_information() -> None:
    with pytest.raises(TypeError, match="source_information"):
        SavedLibraryRecord("project-a", "saved-work-a", ())


def test_project_fit_reason_requires_closed_dimension_and_nonempty_statement() -> None:
    assert {"ProjectFitDimension", "ProjectFitReason"} <= set(
        content_analysis.__all__
    )
    assert {dimension.value for dimension in ProjectFitDimension} == {
        "project_persona",
        "target_users",
        "content_plan",
        "operating_direction",
    }
    with pytest.raises(ValueError, match="项目适配理由维度"):
        ProjectFitReason("free_text_dimension", "任意理由")
    with pytest.raises(ValueError, match="项目适配理由不能为空"):
        ProjectFitReason(ProjectFitDimension.PROJECT_PERSONA, "  ")


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
            opening=(
                OpeningAnnotation(
                    status=OpeningTagStatus.UNAVAILABLE,
                    kind=OpeningKind.FIRST_FRAME,
                    unavailable_reason="没有可读画面证据",
                )
                if category == ContentCategory.QIANCHUAN
                else OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED)
            ),
            source_information=SourceInformation(
                facts=(SourceFact(statement="来源商品宣称有效", source="匿名来源"),),
                judgments=(SourceJudgment(statement="来源表达具备说服力"),),
            ),
            reusable_methods=(
                ReusableMethod(
                    name="问题到证明",
                    description="先问题后证明",
                    method_key="problem-proof",
                    evidence=(
                        AnalysisEvidence(
                            EvidenceType.TRANSCRIPT,
                            "transcript:content",
                            transcript,
                        ),
                    ),
                    applicable_boundaries=(
                        SourceConstraint("仅复用表达结构，不复用来源商品事实"),
                    ),
                ),
            ) if transcript else (),
            topic="匿名选题",
            summary="匿名内容摘要",
            structure=("问题", "方法", "证明"),
            persuasion_chain=("痛点", "证据", "行动"),
            interaction_observations=(
                (
                    InteractionObservation(
                        InteractionObservationType.CURRENT_COMPOSITION,
                        numerator_metric=InteractionMetric.COMMENT,
                        numerator_value=content.metrics.comment_count,
                        denominator_metric=InteractionMetric.LIKE,
                        denominator_value=content.metrics.like_count,
                    ),
                )
                if content.metrics.comment_count is not None
                and content.metrics.like_count not in (None, 0)
                else ()
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
            priority=1,
            confidence=analysis.confidence,
            conclusion=f"适配 {project_context.project_persona}",
            body_benchmark=(
                "问题—方法—证明" if analysis.content.transcript else None
            ),
            body_benchmark_evidence=(
                AnalysisEvidence(
                    EvidenceType.TRANSCRIPT,
                    "body",
                    analysis.content.transcript,
                ),
            ) if analysis.content.transcript else (),
            body_benchmark_boundaries=(
                (SourceConstraint("仅复用表达结构"),)
                if analysis.content.transcript
                else ()
            ),
            value_signals=(CandidateValueSignal.REUSABLE_CONVERSION_STRUCTURE,),
            fit_reasons=(
                ProjectFitReason(
                    ProjectFitDimension.PROJECT_PERSONA,
                    f"内容表达与{project_context.project_persona}一致",
                ),
                ProjectFitReason(
                    ProjectFitDimension.TARGET_USERS,
                    f"内容面向{project_context.target_users}",
                ),
                ProjectFitReason(
                    ProjectFitDimension.CONTENT_PLAN,
                    f"内容符合{project_context.content_plan}",
                ),
                ProjectFitReason(
                    ProjectFitDimension.OPERATING_DIRECTION,
                    f"内容符合{project_context.operating_direction}",
                ),
            ),
            recommended_action="进入项目内容库候选",
            decision_basis=("结构可复用且符合项目人设",),
        )


class ContentPriorityAnalyzer(RecordingAnalyzer):
    async def assess_project(
        self, analysis: BasicAnalysis, project_context: ProjectContextVersion
    ) -> ProjectAssessment:
        assessment = await super().assess_project(analysis, project_context)
        work_id = analysis.content.identity.platform_content_id or ""
        return replace(assessment, priority=0 if work_id.endswith("-4") else 10)


class UnannotatedQianchuanAnalyzer(RecordingAnalyzer):
    async def analyze_content(self, content: ContentRecord) -> BasicAnalysis:
        analysis = await super().analyze_content(content)
        return replace(
            analysis,
            opening=OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
        )


class CandidateGateAnalyzer(RecordingAnalyzer):
    def __init__(
        self,
        *,
        analysis_updates: dict[str, object] | None = None,
        assessment_updates: dict[str, object] | None = None,
    ) -> None:
        super().__init__()
        self.analysis_updates = analysis_updates or {}
        self.assessment_updates = assessment_updates or {}

    async def analyze_content(self, content: ContentRecord) -> BasicAnalysis:
        analysis = await super().analyze_content(content)
        return replace(analysis, **self.analysis_updates)

    async def assess_project(
        self, analysis: BasicAnalysis, project_context: ProjectContextVersion
    ) -> ProjectAssessment:
        assessment = await super().assess_project(analysis, project_context)
        return replace(assessment, **self.assessment_updates)


class TopOpportunityGateAnalyzer(RecordingAnalyzer):
    async def assess_project(
        self, analysis: BasicAnalysis, project_context: ProjectContextVersion
    ) -> ProjectAssessment:
        assessment = await super().assess_project(analysis, project_context)
        if analysis.content.identity.platform_content_id == "work-1":
            return replace(
                assessment,
                body_benchmark=None,
                body_benchmark_evidence=(),
                body_benchmark_boundaries=(),
            )
        return assessment


class SingleContentFailureAnalyzer(RecordingAnalyzer):
    async def analyze_content(self, content: ContentRecord) -> BasicAnalysis:
        if content.identity.platform_content_id == "work-bad":
            self.basic_calls.append(content)
            raise RuntimeError("单内容分析失败")
        return await super().analyze_content(content)


class SingleProjectFailureAnalyzer(RecordingAnalyzer):
    async def assess_project(
        self, analysis: BasicAnalysis, project_context: ProjectContextVersion
    ) -> ProjectAssessment:
        if project_context.project_id == "project-a":
            self.project_calls.append((analysis, project_context))
            raise RuntimeError("单项目判断失败")
        return await super().assess_project(analysis, project_context)


class HangingContentAnalyzer(RecordingAnalyzer):
    async def analyze_content(self, content: ContentRecord) -> BasicAnalysis:
        if content.identity.platform_content_id == "work-hanging":
            self.basic_calls.append(content)
            await asyncio.Event().wait()
        return await super().analyze_content(content)


class HangingProjectAnalyzer(RecordingAnalyzer):
    async def assess_project(
        self, analysis: BasicAnalysis, project_context: ProjectContextVersion
    ) -> ProjectAssessment:
        if project_context.project_id == "project-hanging":
            self.project_calls.append((analysis, project_context))
            await asyncio.Event().wait()
        return await super().assess_project(analysis, project_context)


def relation(project_id: str, version: str, account_id: str = "account-001") -> ProjectAccountRelation:
    return ProjectAccountRelation(
        project_id=project_id,
        account_id=account_id,
        context_version=version,
    )


async def run_engine(analyzer: RecordingAnalyzer, **input_values: object):
    values = dict(input_values)
    values["sync_results"] = tuple(
        replace(
            item,
            checked_at=item.checked_at or RUN_AT,
            coverage_window=item.coverage_window or sync_coverage(),
            issue=(
                item.issue
                if isinstance(item.issue, content_analysis.SyncIssue)
                else content_analysis.SyncIssue(
                    affected_account_ids=(item.account_id,),
                    affected_window=item.coverage_window or sync_coverage(),
                    impact=(
                        content_analysis.SyncIssueImpact.CONTENT_MAY_BE_INCOMPLETE
                        if item.status == SyncStatus.PARTIAL_SUCCESS
                        else content_analysis.SyncIssueImpact.CONTENT_UNAVAILABLE
                    ),
                )
                if item.status in (SyncStatus.PARTIAL_SUCCESS, SyncStatus.FAILED)
                else None
            ),
        )
        for item in values["sync_results"]
    )
    return await ContentAnalysisEngine(analyzer).run(OfflineRunInput(**values))


@pytest.mark.asyncio
async def test_hanging_content_analysis_times_out_without_blocking_other_content() -> None:
    analyzer = HangingContentAnalyzer()
    result = await ContentAnalysisEngine(
        analyzer,
        analyzer_timeout_seconds=0.01,
    ).run(
        OfflineRunInput(
            sync_results=(
                AccountSyncResult(
                    "account-001",
                    SyncStatus.SUCCESS_WITH_CONTENT,
                    (record("work-hanging"), record("work-good")),
                    checked_at=RUN_AT,
                    coverage_window=sync_coverage(),
                ),
            ),
            relations=(relation("project-a", "v1"),),
            contexts=(context("project-a", "v1"),),
            run_at=RUN_AT,
        )
    )

    assert [item.stable_key for item in result.reports["project-a"].items] == [
        "platform_content_id:work-good"
    ]
    assert any(
        "work-hanging" in issue and "基础分析失败" in issue
        for issue in result.reports["project-a"].data_issues
    )


@pytest.mark.parametrize("invalid_timeout", (float("nan"), float("inf")))
def test_content_analysis_engine_rejects_non_finite_timeout(
    invalid_timeout: float,
) -> None:
    with pytest.raises(ValueError, match="超时时间"):
        ContentAnalysisEngine(
            RecordingAnalyzer(),
            analyzer_timeout_seconds=invalid_timeout,
        )


@pytest.mark.asyncio
async def test_hanging_project_assessment_does_not_block_other_project() -> None:
    result = await ContentAnalysisEngine(
        HangingProjectAnalyzer(),
        analyzer_timeout_seconds=0.01,
    ).run(
        OfflineRunInput(
            sync_results=(
                AccountSyncResult(
                    "account-001",
                    SyncStatus.SUCCESS_WITH_CONTENT,
                    (record("work-001"),),
                    checked_at=RUN_AT,
                    coverage_window=sync_coverage(),
                ),
            ),
            relations=(
                relation("project-hanging", "v1"),
                relation("project-good", "v1"),
            ),
            contexts=(
                context("project-hanging", "v1"),
                context("project-good", "v1"),
            ),
            run_at=RUN_AT,
        )
    )

    assert result.reports["project-hanging"].items == ()
    assert [item.stable_key for item in result.reports["project-good"].items] == [
        "platform_content_id:work-001"
    ]


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
async def test_engine_never_analyzes_accounts_outside_received_project_tasks() -> None:
    """删除项目任务范围过滤时，本测试应观察到范围外账号触发基础分析。"""
    analyzer = RecordingAnalyzer()

    result = await run_engine(
        analyzer,
        sync_results=(
            AccountSyncResult(
                "account-in",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-in", account_id="account-in"),),
            ),
            AccountSyncResult(
                "account-out",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-out", account_id="account-out"),),
            ),
        ),
        relations=(
            relation("project-a", "v1", "account-in"),
            relation("project-not-received", "v1", "account-out"),
        ),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    assert [item.account_id for item in analyzer.basic_calls] == ["account-in"]
    assert [call[1].project_id for call in analyzer.project_calls] == ["project-a"]
    assert tuple(result.reports) == ("project-a",)


@pytest.mark.asyncio
async def test_engine_does_not_validate_or_consume_out_of_scope_sync_payloads() -> None:
    analyzer = RecordingAnalyzer()
    result = await ContentAnalysisEngine(analyzer).run(
        OfflineRunInput(
            sync_results=(
                AccountSyncResult(
                    "account-in",
                    SyncStatus.SUCCESS_WITH_CONTENT,
                    (record("work-in", account_id="account-in"),),
                    checked_at=RUN_AT,
                    coverage_window=sync_coverage(),
                ),
                AccountSyncResult(
                    "account-out",
                    "untrusted-status",
                    (record("work-out", account_id="account-out"),),
                ),
            ),
            relations=(relation("project-a", "v1", "account-in"),),
            contexts=(context("project-a", "v1"),),
            run_at=RUN_AT,
            persona_baselines=(
                content_analysis.WeeklyPersonaBaseline(
                    account_id="account-out",
                    window_start=datetime(2026, 1, 1, tzinfo=SHANGHAI),
                    window_end=datetime(2026, 2, 1, tzinfo=SHANGHAI),
                    baseline=content_analysis.LikeBaseline(1, 1, 1, 1, 1),
                ),
            ),
        )
    )

    assert [item.account_id for item in analyzer.basic_calls] == ["account-in"]
    assert tuple(result.reports) == ("project-a",)


@pytest.mark.asyncio
async def test_single_content_analysis_failure_isolated_and_recorded_per_affected_project() -> None:
    analyzer = SingleContentFailureAnalyzer()
    result = await run_engine(
        analyzer,
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-bad"), record("work-good")),
            ),
        ),
        relations=(relation("project-a", "v1"), relation("project-b", "v1")),
        contexts=(context("project-a", "v1"), context("project-b", "v1")),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assert [item.stable_key for item in report.items] == [
        "platform_content_id:work-good"
    ]
    assert any(
        "work-bad" in issue and "基础分析失败" in issue
        for issue in report.data_issues
    )


@pytest.mark.asyncio
async def test_single_project_assessment_failure_does_not_block_other_project() -> None:
    analyzer = SingleProjectFailureAnalyzer()
    result = await run_engine(
        analyzer,
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"), relation("project-b", "v1")),
        contexts=(context("project-a", "v1"), context("project-b", "v1")),
        run_at=RUN_AT,
    )

    assert result.reports["project-a"].items == ()
    assert any(
        "work-001" in issue and "项目判断失败" in issue
        for issue in result.reports["project-a"].data_issues
    )
    assert [item.stable_key for item in result.reports["project-b"].items] == [
        "platform_content_id:work-001"
    ]


@pytest.mark.asyncio
async def test_analyzer_exception_details_are_not_written_to_project_report() -> None:
    class SecretFailureAnalyzer(RecordingAnalyzer):
        async def analyze_content(self, content: ContentRecord) -> BasicAnalysis:
            raise RuntimeError("Bearer secret-token-from-provider")

    result = await run_engine(
        SecretFailureAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-secret"),),
            ),
        ),
        relations=(relation("project-a", "v1"), relation("project-b", "v1")),
        contexts=(context("project-a", "v1"), context("project-b", "v1")),
        run_at=RUN_AT,
    )

    issues = " ".join(result.reports["project-a"].data_issues)
    assert "基础分析失败" in issues
    assert "Bearer" not in issues
    assert "secret-token" not in issues


@pytest.mark.asyncio
async def test_sync_contract_rejects_unstructured_issue_that_could_leak_secrets() -> None:
    with pytest.raises(ValueError, match="结构化同步缺口"):
        await ContentAnalysisEngine(RecordingAnalyzer()).run(
            OfflineRunInput(
                sync_results=(
                    AccountSyncResult(
                        "account-001",
                        SyncStatus.FAILED,
                        issue="Bearer secret-token-from-sync",
                        checked_at=RUN_AT,
                        coverage_window=sync_coverage(),
                    ),
                ),
                relations=(relation("project-a", "v1"),),
                contexts=(context("project-a", "v1"),),
                run_at=RUN_AT,
            )
        )


@pytest.mark.asyncio
async def test_forged_current_interaction_value_invalidates_only_that_content() -> None:
    class ForgedInteractionAnalyzer(RecordingAnalyzer):
        async def analyze_content(self, content: ContentRecord) -> BasicAnalysis:
            analysis = await super().analyze_content(content)
            return replace(
                analysis,
                interaction_observations=(
                    InteractionObservation(
                        InteractionObservationType.CURRENT_VALUE,
                        metric=InteractionMetric.LIKE,
                        current_value=999,
                    ),
                ),
            )

    result = await run_engine(
        ForgedInteractionAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-forged-interaction", likes=10),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assert report.items == ()
    assert any("基础分析失败" in issue for issue in report.data_issues)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unsupported_claim",
    (
        "播放互动率持续上涨",
        "真实转化好且高消耗",
        "互动增长速度出现爆发趋势",
        "开场展示产品，近几天互动越来越好，成交表现优异",
        "成交表现不错",
        "成交表现亮眼",
        "转化表现可观",
        "互动快速攀升",
        "点赞一路飙升",
        "成交效果出色",
        "转化非常强",
        "订单爆棚",
        "互动大幅增长",
        "点赞猛增",
        "评论暴涨",
        "前三秒出现产品",
    ),
)
async def test_unsupported_performance_claim_invalidates_analyzer_output(
    unsupported_claim,
) -> None:
    result = await run_engine(
        CandidateGateAnalyzer(analysis_updates={"summary": unsupported_claim}),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-unsupported-claim"),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assert report.items == ()
    assert report.library_candidates == ()
    assert any("基础分析失败" in issue for issue in report.data_issues)


@pytest.mark.asyncio
async def test_visual_claim_synonym_in_structure_requires_readable_visual() -> None:
    result = await run_engine(
        CandidateGateAnalyzer(
            analysis_updates={"structure": ("前三秒出现产品",)},
        ),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-visual-structure"),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    assert result.reports["project-a"].items == ()
    assert any(
        "基础分析失败" in issue
        for issue in result.reports["project-a"].data_issues
    )


@pytest.mark.asyncio
async def test_unsupported_performance_claim_invalidates_project_assessment_only() -> None:
    result = await run_engine(
        CandidateGateAnalyzer(
            assessment_updates={"conclusion": "已验证成交且高消耗"},
        ),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-unsupported-project-claim"),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assert report.items == ()
    assert any("项目判断失败" in issue for issue in report.data_issues)


@pytest.mark.asyncio
async def test_newer_failed_record_cannot_replace_older_successful_duplicate() -> None:
    analyzer = RecordingAnalyzer()
    older_success = replace(
        record("work-001", transcript="旧成功内容"),
        captured_at=RUN_AT - timedelta(hours=1),
    )
    newer_failed = record(
        "work-001",
        transcript="新失败内容",
        sync_status=SyncStatus.FAILED,
    )

    result = await run_engine(
        analyzer,
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (older_success, newer_failed),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assert analyzer.basic_calls == [older_success]
    assert report.items[0].analysis.content == older_success
    assert report.sync_results[0].contents == (older_success,)
    assert "账号 account-001 忽略了 1 条记录级非成功内容" in report.data_issues


@pytest.mark.asyncio
async def test_success_with_content_rejects_payload_with_only_failed_records() -> None:
    analyzer = RecordingAnalyzer()
    failed_record = record(
        "work-failed",
        sync_status=SyncStatus.FAILED,
    )

    with pytest.raises(ValueError, match="成功有内容.*成功内容"):
        await run_engine(
            analyzer,
            sync_results=(
                AccountSyncResult(
                    "account-001",
                    SyncStatus.SUCCESS_WITH_CONTENT,
                    (failed_record,),
                ),
            ),
            relations=(relation("project-a", "v1"),),
            contexts=(context("project-a", "v1"),),
            run_at=RUN_AT,
        )

    assert analyzer.basic_calls == []
    assert analyzer.project_calls == []


@pytest.mark.asyncio
async def test_partial_sync_uses_and_returns_only_successful_records() -> None:
    analyzer = RecordingAnalyzer()
    successful = record("work-success")
    failed = record("work-failed", sync_status=SyncStatus.FAILED)

    result = await run_engine(
        analyzer,
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.PARTIAL_SUCCESS,
                (successful, failed),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assert analyzer.basic_calls == [successful]
    assert [item.stable_key for item in report.items] == [
        "platform_content_id:work-success"
    ]
    assert report.sync_results[0].contents == (successful,)
    assert report.data_issues == (
        "账号 account-001 部分同步成功，当前内容可能不完整",
        "账号 account-001 忽略了 1 条记录级非成功内容",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("identity_kind", ("platform_content_id", "external_url"))
async def test_same_stable_identity_across_accounts_is_quarantined_before_analysis(
    identity_kind: str,
) -> None:
    analyzer = RecordingAnalyzer()
    if identity_kind == "platform_content_id":
        content_a = record("work-shared", account_id="account-a")
        content_b = record("work-shared", account_id="account-b")
    else:
        shared_url = "https://example.invalid/content/shared"
        content_a = record(None, account_id="account-a", url=shared_url)
        content_b = record(None, account_id="account-b", url=shared_url)

    result = await run_engine(
        analyzer,
        sync_results=(
            AccountSyncResult(
                "account-a", SyncStatus.SUCCESS_WITH_CONTENT, (content_a,)
            ),
            AccountSyncResult(
                "account-b", SyncStatus.SUCCESS_WITH_CONTENT, (content_b,)
            ),
        ),
        relations=(
            relation("project-a", "v1", "account-a"),
            relation("project-a", "v1", "account-b"),
        ),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    assert analyzer.basic_calls == []
    assert result.reports["project-a"].items == ()
    assert any(
        "稳定内容身份" in issue and "冲突" in issue
        for issue in result.reports["project-a"].data_issues
    )


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


class ForgedVisualAnalyzer(RecordingAnalyzer):
    async def analyze_content(self, content: ContentRecord) -> BasicAnalysis:
        self.basic_calls.append(content)
        evidence = AnalysisEvidence(EvidenceType.VISUAL, "frame:0", "分析器自报画面")
        return BasicAnalysis(
            content=content,
            category=ContentCategory.PERSONA,
            confidence=ConfidenceLevel.HIGH,
            opening=OpeningAnnotation(
                status=OpeningTagStatus.AVAILABLE,
                kind=OpeningKind.FIRST_FRAME,
                fragment="伪造第一画面",
                evidence=(evidence,),
                applicable_boundaries=(SourceConstraint("仅复用画面结构"),),
            ),
            shot_observations=(evidence,),
        )


@pytest.mark.asyncio
async def test_unreadable_video_reference_cannot_be_upgraded_by_analyzer_visual_claim() -> None:
    assert hasattr(content_analysis, "MediaReadResult")
    media_result = content_analysis.MediaReadResult(
        status=content_analysis.MediaReadStatus.UNREADABLE,
        issue="解析失败",
    )
    unreadable = replace(
        record("work-unreadable", video_reference="opaque-video-ref"),
        media_read_result=media_result,
    )

    result = await run_engine(
        ForgedVisualAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (unreadable,),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    analysis = result.reports["project-a"].items[0].analysis
    assert analysis.opening.status == OpeningTagStatus.UNAVAILABLE
    assert analysis.shot_observations == ()


@pytest.mark.asyncio
async def test_unreadable_media_issue_is_sanitized_before_report_output() -> None:
    raw_issue = "Bearer media-secret-token /private/source.mov"
    unreadable = replace(
        record("work-unreadable-secret"),
        media_read_result=content_analysis.MediaReadResult(
            status=content_analysis.MediaReadStatus.UNREADABLE,
            issue=raw_issue,
        ),
    )

    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (unreadable,),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    saved_issue = (
        result.reports["project-a"]
        .items[0]
        .analysis.content.media_read_result.issue
    )
    assert saved_issue == "媒体不可读，详见上游媒体解析日志"
    assert "Bearer" not in saved_issue
    assert "/private/" not in saved_issue


@pytest.mark.asyncio
async def test_verified_visual_locator_can_support_shot_and_first_frame_output() -> None:
    readable = replace(
        record("work-readable", video_reference="opaque-video-ref"),
        media_read_result=content_analysis.MediaReadResult(
            status=content_analysis.MediaReadStatus.READABLE,
            evidence_refs=("frame:0",),
        ),
    )

    result = await run_engine(
        ForgedVisualAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (readable,),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    analysis = result.reports["project-a"].items[0].analysis
    assert analysis.opening.status == OpeningTagStatus.AVAILABLE
    assert analysis.shot_observations == (
        AnalysisEvidence(EvidenceType.VISUAL, "frame:0", "分析器自报画面"),
    )


class UnrelatedTranscriptOpeningAnalyzer(RecordingAnalyzer):
    async def analyze_content(self, content: ContentRecord) -> BasicAnalysis:
        base = await super().analyze_content(content)
        return replace(
            base,
            opening=OpeningAnnotation(
                status=OpeningTagStatus.AVAILABLE,
                kind=OpeningKind.LANGUAGE,
                fragment="转写中根本不存在的开头",
                evidence=(
                    AnalysisEvidence(EvidenceType.TRANSCRIPT, "0-3s", "声称来自转写"),
                ),
            ),
        )


@pytest.mark.asyncio
async def test_language_opening_fragment_must_be_found_in_actual_transcript() -> None:
    result = await run_engine(
        UnrelatedTranscriptOpeningAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-language", transcript="真实匿名转写内容"),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    opening = result.reports["project-a"].items[0].analysis.opening
    assert opening.status == OpeningTagStatus.UNAVAILABLE
    assert "无法回到转写" in opening.unavailable_reason


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
                applicable_boundaries=(SourceConstraint("仅复用语言结构"),),
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


class InputlessEvidenceAnalyzer(RecordingAnalyzer):
    def __init__(self, kind: OpeningKind) -> None:
        super().__init__()
        self.kind = kind

    async def analyze_content(self, content: ContentRecord) -> BasicAnalysis:
        self.basic_calls.append(content)
        evidence_type = (
            EvidenceType.TRANSCRIPT
            if self.kind == OpeningKind.LANGUAGE
            else EvidenceType.VISUAL
        )
        evidence = AnalysisEvidence(evidence_type, "0-3s", "分析器自报依据")
        return BasicAnalysis(
            content=content,
            category=ContentCategory.PERSONA,
            confidence=ConfidenceLevel.MEDIUM,
            opening=OpeningAnnotation(
                status=OpeningTagStatus.AVAILABLE,
                kind=self.kind,
                fragment="分析器自报开头",
                evidence=(evidence,),
            ),
            shot_observations=(
                (evidence,) if self.kind == OpeningKind.FIRST_FRAME else ()
            ),
        )


class MixedBoundOpeningEvidenceAnalyzer(RecordingAnalyzer):
    async def analyze_content(self, content: ContentRecord) -> BasicAnalysis:
        self.basic_calls.append(content)
        return BasicAnalysis(
            content=content,
            category=ContentCategory.PERSONA,
            confidence=ConfidenceLevel.MEDIUM,
            opening=OpeningAnnotation(
                status=OpeningTagStatus.AVAILABLE,
                kind=OpeningKind.LANGUAGE,
                fragment="语言开头：先问一个问题",
                evidence=(
                    AnalysisEvidence(EvidenceType.TRANSCRIPT, "0-3s", "转写开场"),
                    AnalysisEvidence(EvidenceType.VISUAL, "frame:0", "无输入的伪视觉证据"),
                ),
                applicable_boundaries=(SourceConstraint("仅复用语言结构"),),
            ),
        )


@pytest.mark.asyncio
async def test_transcript_only_opening_is_kept_without_visual_evidence() -> None:
    result = await run_engine(
        TranscriptOpeningAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (
                    record(
                        "work-001",
                        transcript="语言开头：先问一个问题，然后展开匿名内容",
                    ),
                ),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    opening = result.reports["project-a"].items[0].analysis.opening
    assert opening.status == OpeningTagStatus.AVAILABLE
    assert opening.kind == OpeningKind.LANGUAGE
    assert opening.fragment == "语言开头：先问一个问题"


@pytest.mark.asyncio
async def test_opening_drops_visual_evidence_when_video_input_is_missing() -> None:
    result = await run_engine(
        MixedBoundOpeningEvidenceAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (
                    record(
                        "work-001",
                        transcript="语言开头：先问一个问题，然后展开匿名内容",
                        video_reference=None,
                    ),
                ),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    analysis = result.reports["project-a"].items[0].analysis
    assert analysis.opening.status == OpeningTagStatus.AVAILABLE
    assert analysis.opening.evidence == (
        AnalysisEvidence(EvidenceType.TRANSCRIPT, "0-3s", "转写开场"),
    )
    assert analysis.source_information.limitations == (
        SourceLimitation(statement="没有可读画面证据，镜头与第一画面结论受限"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "content"),
    (
        (OpeningKind.LANGUAGE, record("work-language", transcript=None)),
        (OpeningKind.FIRST_FRAME, record("work-visual", video_reference=None)),
    ),
)
async def test_analyzer_evidence_without_bound_source_input_is_removed(
    kind: OpeningKind,
    content: ContentRecord,
) -> None:
    result = await run_engine(
        InputlessEvidenceAnalyzer(kind),
        sync_results=(
            AccountSyncResult(
                "account-001", SyncStatus.SUCCESS_WITH_CONTENT, (content,)
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    analysis = result.reports["project-a"].items[0].analysis
    assert analysis.opening.status == OpeningTagStatus.UNAVAILABLE
    assert analysis.shot_observations == ()
    assert analysis.source_information.limitations


@pytest.mark.asyncio
async def test_each_visual_claim_requires_visual_evidence_of_its_own() -> None:
    verified_media = content_analysis.MediaReadResult(
        status=content_analysis.MediaReadStatus.READABLE,
        evidence_refs=("4-6s",),
    )
    result = await run_engine(
        MixedEvidenceAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (
                    replace(
                        record("work-001"),
                        media_read_result=verified_media,
                    ),
                ),
            ),
        ),
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


def test_opening_annotation_requires_closed_status_enum() -> None:
    with pytest.raises(ValueError, match="开头状态"):
        OpeningAnnotation(status="available")


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


@pytest.mark.parametrize("invalid", (True, 1.5, "1"))
def test_interaction_observation_rejects_non_integer_current_counts(invalid) -> None:
    with pytest.raises(ValueError, match="互动值"):
        InteractionObservation(
            InteractionObservationType.CURRENT_VALUE,
            metric=InteractionMetric.LIKE,
            current_value=invalid,
        )


@pytest.mark.parametrize("invalid", (float("nan"), float("inf")))
def test_interaction_observation_rejects_non_finite_benchmark(invalid: float) -> None:
    with pytest.raises(ValueError, match="基准值"):
        InteractionObservation(
            InteractionObservationType.CURRENT_RELATIVE_PERFORMANCE,
            metric=InteractionMetric.LIKE,
            relative_level=RelativePerformanceLevel.ABOVE,
            benchmark_value=invalid,
            sample_size=1,
        )


@pytest.mark.parametrize(
    ("field", "invalid"),
    (
        ("limitations", "不是不可变文本元组"),
        ("decision_basis", "不是不可变文本元组"),
    ),
)
def test_project_assessment_rejects_mutable_or_scalar_nested_collections(
    field,
    invalid,
) -> None:
    values = {
        "project_id": "project-a",
        "context_version": "v1",
        "is_fit": True,
        "confidence": ConfidenceLevel.HIGH,
        "conclusion": "严格校验",
        field: invalid,
    }
    with pytest.raises(ValueError):
        ProjectAssessment(**values)


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
    failed_issue = result.reports["project-failed"].sync_results[0].issue
    assert failed_issue.affected_account_ids == ("account-failed",)
    assert failed_issue.affected_window == sync_coverage()
    assert failed_issue.impact == content_analysis.SyncIssueImpact.CONTENT_UNAVAILABLE


def sync_coverage(
    start: datetime = datetime(2026, 9, 1, tzinfo=SHANGHAI),
    end: datetime = datetime(2026, 9, 4, tzinfo=SHANGHAI),
):
    return content_analysis.SyncCoverageWindow(start=start, end=end)


@pytest.mark.asyncio
async def test_empty_daily_keeps_checked_accounts_window_and_completion_time() -> None:
    checked_at = datetime(2026, 9, 4, 8, 30, tzinfo=SHANGHAI)
    sync_result = AccountSyncResult(
        "account-001",
        SyncStatus.SUCCESS_WITHOUT_CONTENT,
        checked_at=checked_at,
        coverage_window=sync_coverage(),
    )

    result = await ContentAnalysisEngine(RecordingAnalyzer()).run(
        OfflineRunInput(
            sync_results=(sync_result,),
            relations=(relation("project-a", "v1"),),
            contexts=(context("project-a", "v1"),),
            run_at=RUN_AT,
        )
    )

    report = result.reports["project-a"]
    assert report.is_empty_daily is True
    assert report.sync_results == (sync_result,)
    assert report.sync_results[0].checked_at == checked_at
    assert report.sync_results[0].coverage_window == sync_coverage()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sync_result",
    (
        AccountSyncResult("account-001", SyncStatus.SUCCESS_WITHOUT_CONTENT),
        AccountSyncResult(
            "account-001",
            SyncStatus.SUCCESS_WITHOUT_CONTENT,
            checked_at=RUN_AT,
            coverage_window=None,
        ),
        AccountSyncResult(
            "account-001",
            SyncStatus.SUCCESS_WITHOUT_CONTENT,
            checked_at=RUN_AT,
            coverage_window="not-a-window",
        ),
    ),
)
async def test_sync_contract_rejects_missing_or_invalid_trace_fields(sync_result) -> None:
    with pytest.raises(ValueError, match="同步.*(时间|窗口)"):
        await ContentAnalysisEngine(RecordingAnalyzer()).run(
            OfflineRunInput(
                sync_results=(sync_result,),
                relations=(relation("project-a", "v1"),),
                contexts=(context("project-a", "v1"),),
                run_at=RUN_AT,
            )
        )


@pytest.mark.asyncio
async def test_partial_success_requires_a_non_empty_upstream_issue() -> None:
    with pytest.raises(ValueError, match="部分同步.*原因"):
        await ContentAnalysisEngine(RecordingAnalyzer()).run(
            OfflineRunInput(
                sync_results=(
                    AccountSyncResult(
                        "account-001",
                        SyncStatus.PARTIAL_SUCCESS,
                        checked_at=RUN_AT,
                        coverage_window=sync_coverage(),
                    ),
                ),
                relations=(relation("project-a", "v1"),),
                contexts=(context("project-a", "v1"),),
                run_at=RUN_AT,
            )
        )


@pytest.mark.asyncio
async def test_partial_success_keeps_structured_account_window_and_impact() -> None:
    issue = content_analysis.SyncIssue(
        affected_account_ids=("account-001",),
        affected_window=sync_coverage(),
        impact=content_analysis.SyncIssueImpact.CONTENT_MAY_BE_INCOMPLETE,
    )
    result = await ContentAnalysisEngine(RecordingAnalyzer()).run(
        OfflineRunInput(
            sync_results=(
                AccountSyncResult(
                    "account-001",
                    SyncStatus.PARTIAL_SUCCESS,
                    issue=issue,
                    checked_at=RUN_AT,
                    coverage_window=sync_coverage(),
                ),
            ),
            relations=(relation("project-a", "v1"),),
            contexts=(context("project-a", "v1"),),
            run_at=RUN_AT,
        )
    )

    saved_issue = result.reports["project-a"].sync_results[0].issue
    assert saved_issue == issue
    assert saved_issue.affected_account_ids == ("account-001",)
    assert saved_issue.affected_window == sync_coverage()


@pytest.mark.asyncio
async def test_sync_issue_cannot_include_another_project_account() -> None:
    with pytest.raises(ValueError, match="同步缺口.*当前账号"):
        await ContentAnalysisEngine(RecordingAnalyzer()).run(
            OfflineRunInput(
                sync_results=(
                    AccountSyncResult(
                        "account-001",
                        SyncStatus.PARTIAL_SUCCESS,
                        issue=content_analysis.SyncIssue(
                            affected_account_ids=("account-001", "account-002"),
                            affected_window=sync_coverage(),
                            impact=(
                                content_analysis.SyncIssueImpact.CONTENT_MAY_BE_INCOMPLETE
                            ),
                        ),
                        checked_at=RUN_AT,
                        coverage_window=sync_coverage(),
                    ),
                ),
                relations=(relation("project-a", "v1"),),
                contexts=(context("project-a", "v1"),),
                run_at=RUN_AT,
            )
        )


@pytest.mark.asyncio
async def test_invalid_sync_contract_for_one_project_does_not_block_valid_project() -> None:
    result = await ContentAnalysisEngine(RecordingAnalyzer()).run(
        OfflineRunInput(
            sync_results=(
                AccountSyncResult(
                    "account-good",
                    SyncStatus.SUCCESS_WITHOUT_CONTENT,
                    checked_at=RUN_AT,
                    coverage_window=sync_coverage(),
                ),
                AccountSyncResult(
                    "account-bad",
                    SyncStatus.PARTIAL_SUCCESS,
                    checked_at=RUN_AT,
                    coverage_window=sync_coverage(),
                ),
            ),
            relations=(
                relation("project-good", "v1", "account-good"),
                relation("project-bad", "v1", "account-bad"),
            ),
            contexts=(
                context("project-good", "v1"),
                context("project-bad", "v1"),
            ),
            run_at=RUN_AT,
        )
    )

    assert result.reports["project-good"].is_empty_daily is True
    bad_report = result.reports["project-bad"]
    assert bad_report.is_empty_daily is False
    assert bad_report.sync_results == ()
    assert any("同步合同无效" in issue for issue in bad_report.data_issues)


@pytest.mark.asyncio
async def test_success_without_content_rejects_recent_content_payload() -> None:
    sync_result = AccountSyncResult(
        "account-001",
        SyncStatus.SUCCESS_WITHOUT_CONTENT,
        (record("contradiction"),),
        checked_at=RUN_AT,
        coverage_window=sync_coverage(),
    )

    with pytest.raises(ValueError, match="成功无内容.*载荷"):
        await ContentAnalysisEngine(RecordingAnalyzer()).run(
            OfflineRunInput(
                sync_results=(sync_result,),
                relations=(relation("project-a", "v1"),),
                contexts=(context("project-a", "v1"),),
                run_at=RUN_AT,
            )
        )


@pytest.mark.asyncio
async def test_sync_contract_rejects_window_that_does_not_match_daily_window() -> None:
    sync_result = AccountSyncResult(
        "account-001",
        SyncStatus.SUCCESS_WITHOUT_CONTENT,
        checked_at=RUN_AT,
        coverage_window=sync_coverage(
            start=datetime(2026, 9, 2, tzinfo=SHANGHAI),
        ),
    )

    with pytest.raises(ValueError, match="日报窗口"):
        await ContentAnalysisEngine(RecordingAnalyzer()).run(
            OfflineRunInput(
                sync_results=(sync_result,),
                relations=(relation("project-a", "v1"),),
                contexts=(context("project-a", "v1"),),
                run_at=RUN_AT,
            )
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sync_result",
    (
        AccountSyncResult(
            "account-001",
            "success_without_content",
            checked_at=RUN_AT,
            coverage_window=None,
        ),
        AccountSyncResult(
            "account-001",
            SyncStatus.SUCCESS_WITH_CONTENT,
            checked_at=RUN_AT,
            coverage_window=None,
        ),
    ),
)
async def test_sync_contract_rejects_untyped_status_or_success_with_empty_payload(
    sync_result,
) -> None:
    normalized = replace(sync_result, coverage_window=sync_coverage())
    with pytest.raises(ValueError, match="同步(状态|成功有内容)"):
        await ContentAnalysisEngine(RecordingAnalyzer()).run(
            OfflineRunInput(
                sync_results=(normalized,),
                relations=(relation("project-a", "v1"),),
                contexts=(context("project-a", "v1"),),
                run_at=RUN_AT,
            )
        )


@pytest.mark.asyncio
async def test_failed_sync_with_content_is_rejected_before_analysis() -> None:
    analyzer = RecordingAnalyzer()
    with pytest.raises(ValueError, match="同步失败状态不能携带内容载荷"):
        await run_engine(
            analyzer,
            sync_results=(
                AccountSyncResult(
                    "account-001",
                    SyncStatus.FAILED,
                    (record("work-stale", transcript=None),),
                    issue="上游超时",
                ),
            ),
            relations=(relation("project-a", "v1"),),
            contexts=(context("project-a", "v1"),),
            run_at=RUN_AT,
        )

    assert analyzer.basic_calls == []
    assert analyzer.project_calls == []


@pytest.mark.asyncio
async def test_success_without_content_never_swallows_recent_payload() -> None:
    analyzer = RecordingAnalyzer()
    with pytest.raises(ValueError, match="成功无内容状态不能携带内容载荷"):
        await run_engine(
            analyzer,
            sync_results=(
                AccountSyncResult(
                    "account-001",
                    SyncStatus.SUCCESS_WITHOUT_CONTENT,
                    (record("work-stale", transcript=None),),
                ),
            ),
            relations=(relation("project-a", "v1"),),
            contexts=(context("project-a", "v1"),),
            run_at=RUN_AT,
        )

    assert analyzer.basic_calls == []
    assert analyzer.project_calls == []


@pytest.mark.asyncio
async def test_partial_success_can_use_content_but_reports_data_limitation() -> None:
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.PARTIAL_SUCCESS,
                (record("work-partial"),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assert [item.stable_key for item in report.items] == [
        "platform_content_id:work-partial"
    ]
    assert [item.stable_key for item in report.library_candidates] == [
        "platform_content_id:work-partial"
    ]
    assert report.data_issues == (
        "账号 account-001 部分同步成功，当前内容可能不完整",
    )


@pytest.mark.asyncio
async def test_daily_engine_does_not_analyze_or_assess_thirty_day_only_history() -> None:
    analyzer = RecordingAnalyzer()
    historic = record("work-historic", published_at=REPORT_DAY - timedelta(days=10))
    recent = record("work-recent")
    result = await run_engine(
        analyzer,
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (historic, recent),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assert len(analyzer.basic_calls) == 1
    assert len(analyzer.project_calls) == 1
    assert analyzer.basic_calls == [recent]
    assert [item.stable_key for item in report.items] == [
        "platform_content_id:work-recent"
    ]
    assert report.sync_results[0].contents == (recent,)


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
    assert qianchuan.opening_status == OpeningTagStatus.UNAVAILABLE
    assert qianchuan.opening_kind == OpeningKind.FIRST_FRAME
    assert qianchuan.opening_fragment is None
    assert qianchuan.opening_unavailable_reason == "没有可读画面证据"
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
async def test_library_candidate_self_contains_project_fit_and_value_evidence() -> None:
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assessment = report.items[0].assessment
    candidate = report.library_candidates[0]
    assert candidate.fit_reasons == assessment.fit_reasons
    assert candidate.value_signals == assessment.value_signals


@pytest.mark.asyncio
async def test_qianchuan_pool_keeps_each_accounts_top_three_before_project_priority() -> None:
    records_a = tuple(
        record(
            f"account-a-{index}",
            account_id="account-a",
            transcript="卖点证明",
            likes=like_count,
        )
        for index, like_count in enumerate((100, 90, 80, 1), start=1)
    )
    records_b = tuple(
        record(
            f"account-b-{index}",
            account_id="account-b",
            transcript="成交促单",
            likes=like_count,
        )
        for index, like_count in enumerate((70, 60, 50, 40), start=1)
    )
    result = await run_engine(
        ContentPriorityAnalyzer(),
        sync_results=(
            AccountSyncResult("account-a", SyncStatus.SUCCESS_WITH_CONTENT, records_a),
            AccountSyncResult("account-b", SyncStatus.SUCCESS_WITH_CONTENT, records_b),
        ),
        relations=(
            relation("project-a", "v1", "account-a"),
            relation("project-a", "v1", "account-b"),
        ),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    opportunity_keys = {
        item.stable_key for item in report.qianchuan_opportunities
    }
    candidate_keys = {item.stable_key for item in report.library_candidates}
    assert opportunity_keys == {
        "platform_content_id:account-a-1",
        "platform_content_id:account-a-2",
        "platform_content_id:account-a-3",
    }
    assert candidate_keys == opportunity_keys
    assert len(report.qianchuan_opportunities) == 3
    assert len(report.library_candidates) == 3


@pytest.mark.asyncio
async def test_library_gate_does_not_backfill_fourth_project_opportunity() -> None:
    sync_results = tuple(
        AccountSyncResult(
            f"account-{index}",
            SyncStatus.SUCCESS_WITH_CONTENT,
            (
                record(
                    f"work-{index}",
                    account_id=f"account-{index}",
                    transcript="卖点证明",
                    likes=110 - index * 10,
                ),
            ),
        )
        for index in range(1, 5)
    )
    result = await run_engine(
        TopOpportunityGateAnalyzer(),
        sync_results=sync_results,
        relations=tuple(
            relation("project-a", "v1", f"account-{index}")
            for index in range(1, 5)
        ),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assert [item.stable_key for item in report.qianchuan_opportunities] == [
        "platform_content_id:work-1",
        "platform_content_id:work-2",
        "platform_content_id:work-3",
    ]
    assert [item.stable_key for item in report.library_candidates] == [
        "platform_content_id:work-2",
        "platform_content_id:work-3",
    ]


@pytest.mark.asyncio
async def test_qianchuan_saved_candidate_rank_is_per_account_top_three_rank() -> None:
    previous_day = REPORT_DAY - timedelta(days=1)
    account_a = tuple(
        record(
            f"account-a-{index}",
            account_id="account-a",
            transcript="卖点证明",
            published_at=previous_day,
            likes=like_count,
        )
        for index, like_count in enumerate((100, 90, 80), start=1)
    )
    account_b = record(
        "account-b-1",
        account_id="account-b",
        transcript="卖点证明",
        published_at=previous_day,
        likes=1000,
    )
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult("account-a", SyncStatus.SUCCESS_WITH_CONTENT, account_a),
            AccountSyncResult("account-b", SyncStatus.SUCCESS_WITH_CONTENT, (account_b,)),
        ),
        relations=(
            relation("project-a", "v1", "account-a"),
            relation("project-a", "v1", "account-b"),
        ),
        contexts=(context("project-a", "v1"),),
        saved_states=(
            SavedBusinessState(
                project_id="project-a",
                stable_key="platform_content_id:account-a-2",
                candidate_rank=2,
                is_opportunity=True,
                in_library=True,
                priority=1,
                cross_project=False,
                conclusion="适配 匿名人设",
                confidence=ConfidenceLevel.HIGH,
            ),
        ),
        run_at=RUN_AT,
    )

    assert result.reports["project-a"].previous_two_day_changes == ()


@pytest.mark.asyncio
async def test_qianchuan_unannotated_opening_is_not_auto_library_candidate() -> None:
    result = await run_engine(
        UnannotatedQianchuanAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001", transcript="卖点证明"),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assert len(report.qianchuan_opportunities) == 1
    assert report.library_candidates == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("gate_name", "content", "analysis_updates", "assessment_updates"),
    (
        (
            "project-fit",
            record("work-not-fit"),
            {},
            {"is_fit": False, "is_opportunity": False},
        ),
        ("fit-conclusion", record("work-blank-conclusion"), {}, {"conclusion": "  "}),
        ("fit-reason", record("work-no-fit-reason"), {}, {"fit_reasons": ()}),
        ("value-signal", record("work-no-signal"), {}, {"value_signals": ()}),
        (
            "transcript",
            record("work-no-transcript", transcript=None),
            {
                "category": ContentCategory.PERSONA,
                "confidence": ConfidenceLevel.HIGH,
                "undetermined_reason": None,
            },
            {},
        ),
        ("topic", record("work-no-topic"), {"topic": None}, {}),
        ("final-opportunity", record("work-not-opportunity"), {}, {"is_opportunity": False}),
    ),
)
async def test_library_candidate_requires_every_common_hard_gate(
    gate_name: str,
    content: ContentRecord,
    analysis_updates: dict[str, object],
    assessment_updates: dict[str, object],
) -> None:
    result = await run_engine(
        CandidateGateAnalyzer(
            analysis_updates=analysis_updates,
            assessment_updates=assessment_updates,
        ),
        sync_results=(
            AccountSyncResult(
                "account-001", SyncStatus.SUCCESS_WITH_CONTENT, (content,)
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assert report.library_candidates == (), gate_name
    if gate_name == "project-fit":
        assert report.persona_opportunities == ()


@pytest.mark.asyncio
async def test_qianchuan_library_candidate_requires_nonempty_body_benchmark() -> None:
    result = await run_engine(
        CandidateGateAnalyzer(assessment_updates={"body_benchmark": "  "}),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001", transcript="卖点证明"),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    assert result.reports["project-a"].library_candidates == ()


@pytest.mark.asyncio
async def test_same_project_saved_content_key_blocks_duplicate_library_candidate() -> None:
    input_values = dict(
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )
    duplicate = await run_engine(
        RecordingAnalyzer(),
        **input_values,
        saved_library_records=(
            SavedLibraryRecord(
                "project-a",
                "platform_content_id:work-001",
                (),
                source_information=SourceInformation(),
            ),
        ),
    )
    other_project = await run_engine(
        RecordingAnalyzer(),
        **input_values,
        saved_library_records=(
            SavedLibraryRecord(
                "project-b",
                "platform_content_id:work-001",
                (),
                source_information=SourceInformation(),
            ),
        ),
    )

    assert duplicate.reports["project-a"].library_candidates == ()
    assert len(other_project.reports["project-a"].library_candidates) == 1


@pytest.mark.asyncio
async def test_any_matching_stable_key_blocks_same_project_library_duplicate() -> None:
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (
                    record(
                        "work-001",
                        url="https://example.invalid/content/shared",
                    ),
                ),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        saved_library_records=(
            SavedLibraryRecord(
                "project-a",
                "external_url:https://example.invalid/content/shared",
                (),
                source_information=SourceInformation(),
            ),
        ),
        run_at=RUN_AT,
    )

    assert result.reports["project-a"].library_candidates == ()


@pytest.mark.asyncio
async def test_saved_library_duplicate_remains_in_library_in_business_state() -> None:
    content = record(
        "work-saved",
        published_at=REPORT_DAY - timedelta(days=1),
    )
    stable_key = "platform_content_id:work-saved"
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001", SyncStatus.SUCCESS_WITH_CONTENT, (content,)
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        saved_states=(
            SavedBusinessState(
                project_id="project-a",
                stable_key=stable_key,
                candidate_rank=1,
                is_opportunity=True,
                in_library=True,
                priority=1,
                cross_project=False,
                conclusion="适配 匿名人设",
                confidence=ConfidenceLevel.HIGH,
            ),
        ),
        saved_library_records=(
            SavedLibraryRecord(
                "project-a",
                stable_key,
                (),
                source_information=SourceInformation(),
            ),
        ),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assert report.previous_two_day_changes == ()
    assert report.library_candidates == ()


@pytest.mark.asyncio
async def test_missing_stable_identity_forms_independent_candidates_without_fake_keys() -> None:
    analyzer = RecordingAnalyzer()
    first = replace(record(None), captured_at=RUN_AT - timedelta(minutes=1))
    second = record(None)
    result = await run_engine(
        analyzer,
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (first, second),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assert analyzer.basic_calls == [first, second]
    assert len(report.items) == 2
    assert len(report.library_candidates) == 2
    assert [candidate.stable_key for candidate in report.library_candidates] == [
        None,
        None,
    ]


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
        "platform_content_id:work-unchanged",
        "platform_content_id:work-changed",
        "platform_content_id:work-new",
    ]


@pytest.mark.asyncio
async def test_previous_day_without_history_stays_out_of_report_but_can_enter_library() -> None:
    previous_day_content = record(
        "work-previous",
        published_at=REPORT_DAY - timedelta(days=1),
    )
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (previous_day_content,),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assert report.items == ()
    assert report.previous_two_day_changes == ()
    assert report.persona_opportunities == ()
    assert [candidate.stable_key for candidate in report.library_candidates] == [
        "platform_content_id:work-previous"
    ]


@pytest.mark.asyncio
async def test_saved_business_state_matches_any_stable_alias() -> None:
    content = record(
        "work-alias",
        url="https://example.invalid/content/work-alias",
        published_at=REPORT_DAY - timedelta(days=1),
    )
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001", SyncStatus.SUCCESS_WITH_CONTENT, (content,)
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        saved_states=(
            SavedBusinessState(
                project_id="project-a",
                stable_key="external_url:https://example.invalid/content/work-alias",
                candidate_rank=1,
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

    assert [
        item.stable_key
        for item in result.reports["project-a"].previous_two_day_changes
    ] == ["platform_content_id:work-alias"]


@pytest.mark.asyncio
async def test_conflicting_saved_business_states_across_aliases_are_reported() -> None:
    content = record(
        "work-alias",
        url="https://example.invalid/content/work-alias",
        published_at=REPORT_DAY - timedelta(days=1),
    )
    common_state = dict(
        project_id="project-a",
        candidate_rank=1,
        in_library=True,
        priority=1,
        cross_project=False,
        conclusion="适配 匿名人设",
        confidence=ConfidenceLevel.HIGH,
    )

    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001", SyncStatus.SUCCESS_WITH_CONTENT, (content,)
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        saved_states=(
            SavedBusinessState(
                stable_key="platform_content_id:work-alias",
                is_opportunity=True,
                **common_state,
            ),
            SavedBusinessState(
                stable_key="external_url:https://example.invalid/content/work-alias",
                is_opportunity=False,
                **common_state,
            ),
        ),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assert report.previous_two_day_changes == ()
    assert any("稳定别名" in issue and "冲突" in issue for issue in report.data_issues)


@pytest.mark.asyncio
async def test_conflicting_saved_aliases_do_not_block_unrelated_project() -> None:
    bad_content = record(
        "work-bad-alias",
        account_id="account-bad",
        url="https://example.invalid/content/work-bad-alias",
        published_at=REPORT_DAY - timedelta(days=1),
    )
    state_values = dict(
        project_id="project-bad",
        candidate_rank=1,
        in_library=True,
        priority=1,
        cross_project=False,
        conclusion="适配 匿名人设",
        confidence=ConfidenceLevel.HIGH,
    )

    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-good",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-good", account_id="account-good"),),
            ),
            AccountSyncResult(
                "account-bad",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (bad_content,),
            ),
        ),
        relations=(
            relation("project-good", "v1", "account-good"),
            relation("project-bad", "v1", "account-bad"),
        ),
        contexts=(context("project-good", "v1"), context("project-bad", "v1")),
        saved_states=(
            SavedBusinessState(
                stable_key="platform_content_id:work-bad-alias",
                is_opportunity=True,
                **state_values,
            ),
            SavedBusinessState(
                stable_key="external_url:https://example.invalid/content/work-bad-alias",
                is_opportunity=False,
                **state_values,
            ),
        ),
        run_at=RUN_AT,
    )

    assert [item.stable_key for item in result.reports["project-good"].items] == [
        "platform_content_id:work-good"
    ]
    assert result.reports["project-bad"].previous_two_day_changes == ()
    assert any(
        "稳定别名" in issue and "冲突" in issue
        for issue in result.reports["project-bad"].data_issues
    )


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

    method = reusable_method("problem-proof", "问题到证明", "先问题后证明")
    result = await run_engine(
        RecordingAnalyzer(),
        **input_values,
        saved_library_records=(
            SavedLibraryRecord(
                "project-a",
                "saved-work-a",
                (method,),
                source_information=SourceInformation(),
                signals=(CrossProjectSignal.STRONG_ENGAGEMENT,),
                scenarios=("银发口播",),
            ),
            SavedLibraryRecord(
                "project-b",
                "saved-work-b",
                (method,),
                source_information=SourceInformation(),
                signals=(CrossProjectSignal.NOVEL_CONTENT_METHOD,),
                scenarios=("美妆讲解",),
            ),
        ),
    )

    assert len(result.cross_project_candidates) == 1
    candidate = result.cross_project_candidates[0]
    assert candidate.method == method
    assert candidate.project_ids == ("project-a", "project-b")
    assert candidate.sources == (
        CrossProjectSource("project-a", "saved-work-a"),
        CrossProjectSource("project-b", "saved-work-b"),
    )
    assert candidate.scenarios == ("美妆讲解", "银发口播")
    assert candidate.signals == (
        CrossProjectSignal.NOVEL_CONTENT_METHOD,
        CrossProjectSignal.STRONG_ENGAGEMENT,
    )
    assert result.reports["project-a"].cross_project_candidates == (candidate,)
    assert result.reports["project-b"].cross_project_candidates == (candidate,)
    assert candidate.is_strong is True
    assert candidate.auto_written_project_ids == ()
    assert not hasattr(candidate, "source_information")


@pytest.mark.asyncio
async def test_cross_project_pool_ignores_saved_projects_outside_received_tasks() -> None:
    method = reusable_method("problem-proof", "问题到证明", "先问题后证明")

    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        saved_library_records=(
            SavedLibraryRecord(
                "project-a",
                "saved-work-a",
                (method,),
                source_information=SourceInformation(),
                signals=(CrossProjectSignal.STRONG_ENGAGEMENT,),
                scenarios=("匿名口播",),
            ),
            SavedLibraryRecord(
                "project-out",
                "saved-work-out",
                (method,),
                source_information=SourceInformation(),
                signals=(CrossProjectSignal.NOVEL_CONTENT_METHOD,),
                scenarios=("范围外场景",),
            ),
        ),
        run_at=RUN_AT,
    )

    assert result.cross_project_candidates == ()
    assert result.reports["project-a"].cross_project_candidates == ()


@pytest.mark.asyncio
async def test_cross_project_pool_ignores_saved_project_without_current_relation() -> None:
    method = reusable_method("problem-proof", "问题到证明", "先问题后证明")

    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"), context("project-no-relation", "v1")),
        saved_library_records=(
            SavedLibraryRecord(
                "project-a",
                "saved-work-a",
                (method,),
                source_information=SourceInformation(),
                signals=(CrossProjectSignal.STRONG_ENGAGEMENT,),
                scenarios=("匿名口播",),
            ),
            SavedLibraryRecord(
                "project-no-relation",
                "saved-work-no-relation",
                (method,),
                source_information=SourceInformation(),
                signals=(CrossProjectSignal.NOVEL_CONTENT_METHOD,),
                scenarios=("无关系场景",),
            ),
        ),
        run_at=RUN_AT,
    )

    assert set(result.reports) == {"project-a"}
    assert result.cross_project_candidates == ()


@pytest.mark.asyncio
async def test_single_project_method_needs_two_signals_and_a_scenario() -> None:
    method = reusable_method("problem-proof", "问题到证明", "先问题后证明")
    input_values = dict(
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    result = await run_engine(
        RecordingAnalyzer(),
        **input_values,
        saved_library_records=(
            SavedLibraryRecord(
                "project-a",
                "saved-work-a",
                (method,),
                source_information=SourceInformation(),
                signals=(
                    CrossProjectSignal.REUSABLE_CONVERSION_STRUCTURE,
                    CrossProjectSignal.EXPLICIT_CROSS_PROJECT_FIT,
                ),
                scenarios=("跨项目商品讲解",),
            ),
        ),
    )

    assert len(result.cross_project_candidates) == 1
    candidate = result.cross_project_candidates[0]
    assert candidate.project_ids == ("project-a",)
    assert candidate.sources == (CrossProjectSource("project-a", "saved-work-a"),)
    assert candidate.scenarios == ("跨项目商品讲解",)
    assert candidate.is_strong is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "saved_record",
    (
        SavedLibraryRecord(
            "project-a",
            "one-signal",
            (reusable_method("problem-proof", "问题到证明", "先问题后证明"),),
            source_information=SourceInformation(),
            signals=(CrossProjectSignal.STRONG_ENGAGEMENT,),
            scenarios=("银发口播",),
        ),
        SavedLibraryRecord(
            "project-a",
            "no-scenario",
            (reusable_method("problem-proof", "问题到证明", "先问题后证明"),),
            source_information=SourceInformation(),
            signals=(
                CrossProjectSignal.STRONG_ENGAGEMENT,
                CrossProjectSignal.NOVEL_CONTENT_METHOD,
            ),
        ),
    ),
)
async def test_single_project_method_excludes_insufficient_signals_or_scenarios(
    saved_record: SavedLibraryRecord,
) -> None:
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        saved_library_records=(saved_record,),
        run_at=RUN_AT,
    )

    assert result.cross_project_candidates == ()


@pytest.mark.asyncio
async def test_daily_analysis_overwrites_model_maturity_with_capture_age() -> None:
    captured_at = datetime(2026, 9, 3, 15, tzinfo=SHANGHAI)
    item = replace(
        record(
            "work-maturity",
            published_at=datetime(2026, 9, 3, 8, tzinfo=SHANGHAI),
        ),
        captured_at=captured_at,
    )

    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (item,),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    analysis = result.reports["project-a"].items[0].analysis
    assert analysis.data_maturity == DataMaturity.INITIAL
    assert [
        observation.maturity
        for observation in analysis.interaction_observations
        if observation.observation_type == InteractionObservationType.DATA_MATURITY
    ] == [DataMaturity.INITIAL]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("saved_relative", "expected_change_count"),
    (
        (RelativePerformanceLevel.BELOW, 0),
        (RelativePerformanceLevel.ABOVE, 1),
    ),
)
async def test_previous_day_reentry_uses_relative_persona_status_not_absolute_likes(
    saved_relative: RelativePerformanceLevel,
    expected_change_count: int,
) -> None:
    previous = record(
        "work-relative",
        published_at=REPORT_DAY - timedelta(days=1),
        likes=50,
    )
    stable_key = "platform_content_id:work-relative"
    baseline = content_analysis.WeeklyPersonaBaseline(
        account_id="account-001",
        window_start=datetime(2026, 8, 5, tzinfo=SHANGHAI),
        window_end=datetime(2026, 9, 4, tzinfo=SHANGHAI),
        baseline=content_analysis.LikeBaseline(
            mean=100,
            median=100,
            sample_size=4,
            maximum=150,
            minimum=50,
        ),
    )

    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (previous,),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        persona_baselines=(baseline,),
        saved_states=(
            SavedBusinessState(
                project_id="project-a",
                stable_key=stable_key,
                candidate_rank=1,
                is_opportunity=True,
                in_library=True,
                priority=1,
                cross_project=False,
                conclusion="适配 匿名人设",
                confidence=ConfidenceLevel.HIGH,
                persona_relative_like=saved_relative,
            ),
        ),
        saved_library_records=(
            SavedLibraryRecord(
                "project-a",
                stable_key,
                (),
                source_information=SourceInformation(),
            ),
        ),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    assert len(report.previous_two_day_changes) == expected_change_count
    if report.previous_two_day_changes:
        assert (
            report.previous_two_day_changes[0].persona_relative_like
            == RelativePerformanceLevel.BELOW
        )


@pytest.mark.asyncio
async def test_candidate_and_daily_report_preserve_complete_atomic_output_contract() -> None:
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-complete"),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    report = result.reports["project-a"]
    item = report.persona_opportunities[0]
    candidate = report.library_candidates[0]

    assert candidate.analysis is item.analysis
    assert candidate.assessment is item.assessment
    assert candidate.project_facts == item.project_facts
    assert candidate.content.identity.platform_content_id == "work-complete"
    assert candidate.content.published_at == REPORT_DAY
    assert candidate.content.captured_at == RUN_AT
    assert candidate.content.metrics.like_count == 10
    assert candidate.content.metrics.comment_count == 2
    assert candidate.content.metrics.share_count == 1
    assert candidate.content.metrics.favorite_count == 3
    assert candidate.category == ContentCategory.PERSONA
    assert candidate.analysis.topic == "匿名选题"
    assert candidate.analysis.summary == "匿名内容摘要"
    assert candidate.analysis.structure == ("问题", "方法", "证明")
    assert candidate.analysis.persuasion_chain == ("痛点", "证据", "行动")
    assert candidate.analysis.data_maturity == DataMaturity.QUALITATIVE
    assert candidate.assessment.recommended_action == "进入项目内容库候选"
    assert candidate.assessment.decision_basis == ("结构可复用且符合项目人设",)
    assert candidate.assessment.fit_reasons
    assert candidate.assessment.value_signals
    assert candidate.source_information.facts
    assert candidate.reusable_methods
    assert report.summary
    assert report.daily_overview.content_count == 1
    assert report.daily_overview.categories == report.categories
    assert report.daily_overview.interactions == report.interactions
    assert report.cross_project_candidates == ()


def test_reusable_methods_are_not_duplicated_inside_source_information() -> None:
    assert "reusable_methods" not in SourceInformation.__dataclass_fields__
    assert "reusable_methods" in BasicAnalysis.__dataclass_fields__


def test_source_brand_fact_is_removed_from_general_summary() -> None:
    source_statement = "雅诗兰黛用户案例"
    analysis = BasicAnalysis(
        content=record("work-source-summary"),
        category=ContentCategory.PERSONA,
        confidence=ConfidenceLevel.HIGH,
        opening=OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
        summary=source_statement,
        source_information=SourceInformation(
            facts=(
                SourceFact(
                    statement=source_statement,
                    source="匿名来源视频",
                    kind=content_analysis.SourceFactKind.BRAND,
                    restricted_fragments=(source_statement,),
                ),
            ),
        ),
    )

    result = content_analysis.enforce_analysis_boundaries(analysis)

    assert result.summary is None


def test_source_brand_fact_cannot_become_project_assessment_conclusion() -> None:
    source_statement = "雅诗兰黛用户案例"
    analysis = BasicAnalysis(
        content=record("work-source-assessment"),
        category=ContentCategory.PERSONA,
        confidence=ConfidenceLevel.HIGH,
        opening=OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
        source_information=SourceInformation(
            facts=(
                SourceFact(
                    statement=source_statement,
                    source="匿名来源视频",
                    kind=content_analysis.SourceFactKind.BRAND,
                    restricted_fragments=(source_statement,),
                ),
            ),
        ),
    )
    assessment = ProjectAssessment(
        project_id="project-a",
        context_version="v1",
        is_fit=True,
        confidence=ConfidenceLevel.HIGH,
        conclusion=f"{source_statement}适合当前项目",
    )

    with pytest.raises(ValueError, match="来源限定"):
        content_analysis.enforce_project_assessment_boundaries(assessment, analysis)


@pytest.mark.asyncio
async def test_same_method_key_merges_different_wording_across_projects() -> None:
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"), relation("project-b", "v1")),
        contexts=(context("project-a", "v1"), context("project-b", "v1")),
        saved_library_records=(
            SavedLibraryRecord(
                "project-a",
                "saved-a",
                (reusable_method("problem-proof", "问题到证明", "先问题后证明"),),
                source_information=SourceInformation(),
                scenarios=("匿名口播",),
            ),
            SavedLibraryRecord(
                "project-b",
                "saved-b",
                (reusable_method("problem-proof", "先抛问题再举证", "问题后接证据"),),
                source_information=SourceInformation(),
                scenarios=("匿名口播",),
            ),
        ),
        run_at=RUN_AT,
    )

    assert len(result.cross_project_candidates) == 1
    candidate = result.cross_project_candidates[0]
    assert candidate.method.method_key == "problem-proof"
    assert candidate.project_ids == ("project-a", "project-b")


@pytest.mark.asyncio
async def test_same_method_name_with_different_semantic_keys_does_not_merge() -> None:
    records = tuple(
        SavedLibraryRecord(
            project_id,
            f"{project_id}-{method_key}",
            (reusable_method(method_key, "三段式", description),),
            source_information=SourceInformation(),
            scenarios=("匿名口播",),
        )
        for method_key, description in (
            ("problem-proof", "问题到证明"),
            ("scene-result", "场景到结果"),
        )
        for project_id in ("project-a", "project-b")
    )

    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"), relation("project-b", "v1")),
        contexts=(context("project-a", "v1"), context("project-b", "v1")),
        saved_library_records=records,
        run_at=RUN_AT,
    )

    assert [
        candidate.method.method_key for candidate in result.cross_project_candidates
    ] == ["problem-proof", "scene-result"]


@pytest.mark.asyncio
async def test_source_limited_product_claim_is_blocked_from_reusable_outputs() -> None:
    assert hasattr(content_analysis, "SourceFactKind")
    restricted_text = "来源品牌限时九十九元并宣称改善睡眠"

    class SourceLeakAnalyzer(RecordingAnalyzer):
        async def analyze_content(self, content: ContentRecord) -> BasicAnalysis:
            self.basic_calls.append(content)
            return BasicAnalysis(
                content=content,
                category=ContentCategory.QIANCHUAN,
                confidence=ConfidenceLevel.HIGH,
                opening=OpeningAnnotation(
                    status=OpeningTagStatus.AVAILABLE,
                    kind=OpeningKind.LANGUAGE,
                    fragment=restricted_text,
                    evidence=(
                        AnalysisEvidence(EvidenceType.TRANSCRIPT, "0-5s", restricted_text),
                    ),
                    applicable_boundaries=(SourceConstraint("仅限来源内容"),),
                ),
                source_information=SourceInformation(
                    facts=(
                        SourceFact(
                            statement=restricted_text,
                            source="sample-work-source",
                            kind=content_analysis.SourceFactKind.PRODUCT_CLAIM,
                            restricted_fragments=(restricted_text,),
                        ),
                    ),
                ),
                reusable_methods=(
                    reusable_method(
                        "price-hook",
                        "价格钩子",
                        f"直接复用{restricted_text}",
                    ),
                ),
                structure=(f"开头直接说{restricted_text}", "行动"),
                persuasion_chain=("来源功效", "行动"),
            )

        async def assess_project(self, analysis, project_context):
            return ProjectAssessment(
                project_id=project_context.project_id,
                context_version=project_context.version,
                is_fit=True,
                is_opportunity=True,
                priority=1,
                confidence=ConfidenceLevel.HIGH,
                conclusion="只复用结构",
                body_benchmark=f"正文直接传播{restricted_text}",
                body_benchmark_evidence=(
                    AnalysisEvidence(EvidenceType.TRANSCRIPT, "body", restricted_text),
                ),
                body_benchmark_boundaries=(SourceConstraint("仅复用结构"),),
                value_signals=(CandidateValueSignal.REUSABLE_CONVERSION_STRUCTURE,),
                fit_reasons=(
                    ProjectFitReason(
                        ProjectFitDimension.CONTENT_PLAN,
                        "结构符合匿名内容规划",
                    ),
                ),
                recommended_action="进入项目内容库候选",
                decision_basis=("结构可复用",),
            )

    result = await run_engine(
        SourceLeakAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-source", transcript=restricted_text),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    item = result.reports["project-a"].items[0]
    assert item.analysis.reusable_methods == ()
    assert item.analysis.structure == ("行动",)
    assert item.analysis.opening.status == OpeningTagStatus.UNAVAILABLE
    assert item.assessment.body_benchmark is None
    assert result.reports["project-a"].library_candidates == ()


def test_source_limited_subfragment_cannot_hide_inside_reusable_method() -> None:
    transcript = "来源品牌限时九十九元并宣称改善睡眠"
    analysis = BasicAnalysis(
        content=record("work-source-fragment", transcript=transcript),
        category=ContentCategory.QIANCHUAN,
        confidence=ConfidenceLevel.HIGH,
        opening=OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
        source_information=SourceInformation(
            facts=(
                SourceFact(
                    statement=transcript,
                    source="sample-work-source",
                    kind=content_analysis.SourceFactKind.PRICE,
                    restricted_fragments=("九十九元",),
                ),
            ),
        ),
        reusable_methods=(
            ReusableMethod(
                name="价格钩子",
                description="直接复用九十九元",
                method_key="price-hook",
                evidence=(
                    AnalysisEvidence(
                        EvidenceType.TRANSCRIPT,
                        "transcript:1",
                        transcript,
                    ),
                ),
                applicable_boundaries=(SourceConstraint("仅限来源内容"),),
            ),
        ),
        topic="九十九元价格钩子",
    )

    result = content_analysis.enforce_analysis_boundaries(analysis)

    assert result.reusable_methods == ()
    assert result.topic is None


def test_source_limited_fact_sentence_cannot_release_its_direct_subfragment() -> None:
    source_fact = "原视频中讲述雅诗兰黛用户案例"
    leaked_fragment = "雅诗兰黛用户案例"
    analysis = BasicAnalysis(
        content=record("work-source-direct-subfragment", transcript=leaked_fragment),
        category=ContentCategory.QIANCHUAN,
        confidence=ConfidenceLevel.HIGH,
        opening=OpeningAnnotation(
            status=OpeningTagStatus.AVAILABLE,
            kind=OpeningKind.LANGUAGE,
            fragment=leaked_fragment,
            evidence=(
                AnalysisEvidence(
                    EvidenceType.TRANSCRIPT,
                    "transcript:1",
                    leaked_fragment,
                ),
            ),
            applicable_boundaries=(SourceConstraint("仅验证语言开头"),),
        ),
        source_information=SourceInformation(
            facts=(
                SourceFact(
                    statement=source_fact,
                    source="sample-work-source",
                    kind=content_analysis.SourceFactKind.BRAND,
                    restricted_fragments=(leaked_fragment,),
                ),
            ),
        ),
        summary=leaked_fragment,
    )

    result = content_analysis.enforce_analysis_boundaries(analysis)

    assert result.summary is None
    assert result.opening.status == OpeningTagStatus.UNAVAILABLE


def test_short_source_entity_is_blocked_by_explicit_restricted_fragment() -> None:
    source_fact = "来源品牌为欧莱雅"
    leaked_fragment = "欧莱雅"
    analysis = BasicAnalysis(
        content=record("work-short-source-entity", transcript=leaked_fragment),
        category=ContentCategory.QIANCHUAN,
        confidence=ConfidenceLevel.HIGH,
        opening=OpeningAnnotation(
            status=OpeningTagStatus.AVAILABLE,
            kind=OpeningKind.LANGUAGE,
            fragment=leaked_fragment,
            evidence=(
                AnalysisEvidence(
                    EvidenceType.TRANSCRIPT,
                    "transcript:1",
                    leaked_fragment,
                ),
            ),
            applicable_boundaries=(SourceConstraint("仅验证语言开头"),),
        ),
        source_information=SourceInformation(
            facts=(
                SourceFact(
                    statement=source_fact,
                    source="sample-work-source",
                    kind=content_analysis.SourceFactKind.BRAND,
                    restricted_fragments=(leaked_fragment,),
                ),
            ),
        ),
        summary=leaked_fragment,
    )

    result = content_analysis.enforce_analysis_boundaries(analysis)

    assert result.summary is None
    assert result.opening.status == OpeningTagStatus.UNAVAILABLE


def test_generic_use_method_is_not_removed_by_arbitrary_three_character_overlap() -> None:
    transcript = "来源产品演示了一套具体使用方法"
    method = ReusableMethod(
        name="使用演示",
        description="提炼使用方法",
        method_key="usage-demo",
        evidence=(
            AnalysisEvidence(EvidenceType.TRANSCRIPT, "transcript:1", transcript),
        ),
        applicable_boundaries=(SourceConstraint("只复用演示结构"),),
    )
    analysis = BasicAnalysis(
        content=record("work-generic-method", transcript=transcript),
        category=ContentCategory.QIANCHUAN,
        confidence=ConfidenceLevel.HIGH,
        opening=OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
        source_information=SourceInformation(
            facts=(
                SourceFact(
                    statement="来源产品演示了一套具体使用方法",
                    source="sample-work-source",
                    kind=content_analysis.SourceFactKind.OTHER,
                ),
            ),
        ),
        reusable_methods=(method,),
    )

    result = content_analysis.enforce_analysis_boundaries(analysis)

    assert result.reusable_methods == (method,)


def test_semantic_price_and_efficacy_rewrite_is_not_a_reusable_method() -> None:
    transcript = "来源品牌九十九元并宣称改善睡眠"
    analysis = BasicAnalysis(
        content=record("work-semantic-leak", transcript=transcript),
        category=ContentCategory.QIANCHUAN,
        confidence=ConfidenceLevel.HIGH,
        opening=OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
        source_information=SourceInformation(
            facts=(
                SourceFact(
                    statement=transcript,
                    source="sample-work-source",
                    kind=content_analysis.SourceFactKind.PRODUCT_CLAIM,
                    restricted_fragments=("九十九元", "改善睡眠"),
                ),
            ),
        ),
        reusable_methods=(
            ReusableMethod(
                name="促单承诺",
                description="百元内助眠承诺",
                method_key="price-efficacy-promise",
                evidence=(
                    AnalysisEvidence(
                        EvidenceType.TRANSCRIPT,
                        "transcript:1",
                        transcript,
                    ),
                ),
                applicable_boundaries=(SourceConstraint("仅限来源内容"),),
            ),
        ),
    )

    result = content_analysis.enforce_analysis_boundaries(analysis)

    assert result.reusable_methods == ()


@pytest.mark.asyncio
async def test_cross_project_pool_rejects_saved_method_with_source_claim_evidence() -> None:
    leaked_method = ReusableMethod(
        name="结构方法",
        description="问题到证明",
        method_key="leaked-method",
        evidence=(
            AnalysisEvidence(
                EvidenceType.TRANSCRIPT,
                "transcript:1",
                "来源品牌九十九元改善睡眠",
            ),
        ),
        applicable_boundaries=(SourceConstraint("仅复用结构"),),
    )
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        saved_library_records=tuple(
            SavedLibraryRecord(
                project_id=project_id,
                content_key=f"{project_id}-source",
                reusable_methods=(leaked_method,),
                source_information=SourceInformation(),
                scenarios=("匿名口播",),
            )
            for project_id in ("project-a", "project-b")
        ),
        run_at=RUN_AT,
    )

    assert result.cross_project_candidates == ()


@pytest.mark.asyncio
async def test_cross_project_pool_rejects_saved_brand_and_person_identity_method() -> None:
    leaked_method = ReusableMethod(
        name="复用蓝海牌用户案例",
        description="用创始人经历证明商品",
        method_key="brand-founder-story",
        evidence=(
            AnalysisEvidence(
                EvidenceType.TRANSCRIPT,
                "transcript:1",
                "蓝海牌创始人张某的亲身经历",
            ),
        ),
        applicable_boundaries=(SourceConstraint("仅复用故事结构"),),
    )
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        saved_library_records=tuple(
            SavedLibraryRecord(
                project_id=project_id,
                content_key=f"{project_id}-source",
                reusable_methods=(leaked_method,),
                source_information=SourceInformation(),
                scenarios=("匿名口播",),
            )
            for project_id in ("project-a", "project-b")
        ),
        run_at=RUN_AT,
    )

    assert result.cross_project_candidates == ()


@pytest.mark.asyncio
async def test_saved_source_fragments_block_brand_method_from_cross_project_pool() -> None:
    method = ReusableMethod(
        name="欧莱雅成分讲解结构",
        description="先成分后证明",
        method_key="brand-ingredient-proof",
        evidence=(
            AnalysisEvidence(
                EvidenceType.TRANSCRIPT,
                "transcript:1",
                "欧莱雅成分讲解",
            ),
        ),
        applicable_boundaries=(SourceConstraint("仅复用表达结构"),),
    )
    source_information = SourceInformation(
        facts=(
            SourceFact(
                statement="原视频展示欧莱雅成分讲解",
                source="sample-work-source",
                kind=content_analysis.SourceFactKind.BRAND,
                restricted_fragments=("欧莱雅",),
            ),
        ),
    )
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"), relation("project-b", "v1")),
        contexts=(context("project-a", "v1"), context("project-b", "v1")),
        saved_library_records=tuple(
            SavedLibraryRecord(
                project_id=project_id,
                content_key=f"{project_id}-source",
                reusable_methods=(method,),
                scenarios=("匿名口播",),
                source_information=source_information,
            )
            for project_id in ("project-a", "project-b")
        ),
        run_at=RUN_AT,
    )

    assert result.cross_project_candidates == ()


@pytest.mark.asyncio
async def test_saved_source_fragment_cannot_leak_through_method_boundary() -> None:
    method = ReusableMethod(
        name="成分讲解结构",
        description="先成分后证明",
        method_key="ingredient-proof",
        evidence=(
            AnalysisEvidence(
                EvidenceType.TRANSCRIPT,
                "transcript:1",
                "先讲成分再提供证明",
            ),
        ),
        applicable_boundaries=(SourceConstraint("仅适用于欧莱雅商品"),),
    )
    source_information = SourceInformation(
        facts=(
            SourceFact(
                statement="原视频展示欧莱雅商品",
                source="sample-work-source",
                kind=content_analysis.SourceFactKind.BRAND,
                restricted_fragments=("欧莱雅",),
            ),
        ),
    )
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"), relation("project-b", "v1")),
        contexts=(context("project-a", "v1"), context("project-b", "v1")),
        saved_library_records=tuple(
            SavedLibraryRecord(
                project_id=project_id,
                content_key=f"{project_id}-source",
                reusable_methods=(method,),
                source_information=source_information,
                scenarios=("匿名口播",),
            )
            for project_id in ("project-a", "project-b")
        ),
        run_at=RUN_AT,
    )

    assert result.cross_project_candidates == ()


def test_saved_source_fragment_cannot_leak_through_method_key() -> None:
    method = ReusableMethod(
        name="成分讲解结构",
        description="先成分后证明",
        method_key="欧莱雅-ingredient-proof",
        evidence=(
            AnalysisEvidence(
                EvidenceType.TRANSCRIPT,
                "transcript:1",
                "先讲成分再提供证明",
            ),
        ),
        applicable_boundaries=(SourceConstraint("仅复用表达结构"),),
    )
    source_information = SourceInformation(
        facts=(
            SourceFact(
                statement="原视频展示欧莱雅商品",
                source="sample-work-source",
                kind=content_analysis.SourceFactKind.BRAND,
                restricted_fragments=("欧莱雅",),
            ),
        ),
    )

    assert not is_reusable_method_safe(method, source_information)


@pytest.mark.asyncio
async def test_saved_source_fragment_cannot_leak_through_cross_project_scenario() -> None:
    method = reusable_method(
        "ingredient-proof",
        "成分讲解结构",
        "先成分后证明",
    )
    source_information = SourceInformation(
        facts=(
            SourceFact(
                statement="原视频展示欧莱雅商品",
                source="sample-work-source",
                kind=content_analysis.SourceFactKind.BRAND,
                restricted_fragments=("欧莱雅",),
            ),
        ),
    )
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"), relation("project-b", "v1")),
        contexts=(context("project-a", "v1"), context("project-b", "v1")),
        saved_library_records=tuple(
            SavedLibraryRecord(
                project_id=project_id,
                content_key=f"{project_id}-source",
                reusable_methods=(method,),
                source_information=source_information,
                scenarios=("欧莱雅商品讲解",),
            )
            for project_id in ("project-a", "project-b")
        ),
        run_at=RUN_AT,
    )

    assert result.cross_project_candidates == ()


def test_source_fragment_in_opening_boundary_makes_opening_unavailable() -> None:
    transcript = "先问痛点"
    analysis = BasicAnalysis(
        content=record("work-opening-boundary", transcript=transcript),
        category=ContentCategory.QIANCHUAN,
        confidence=ConfidenceLevel.HIGH,
        opening=OpeningAnnotation(
            status=OpeningTagStatus.AVAILABLE,
            kind=OpeningKind.LANGUAGE,
            fragment=transcript,
            evidence=(
                AnalysisEvidence(
                    EvidenceType.TRANSCRIPT,
                    "transcript:1",
                    transcript,
                ),
            ),
            applicable_boundaries=(SourceConstraint("仅适用于欧莱雅商品"),),
        ),
        source_information=SourceInformation(
            facts=(
                SourceFact(
                    statement="来源品牌为欧莱雅",
                    source="sample-work-source",
                    kind=content_analysis.SourceFactKind.BRAND,
                    restricted_fragments=("欧莱雅",),
                ),
            ),
        ),
    )

    result = content_analysis.enforce_analysis_boundaries(analysis)

    assert result.opening.status == OpeningTagStatus.UNAVAILABLE


def test_source_fragment_in_body_boundary_removes_body_benchmark() -> None:
    transcript = "先问题后证明"
    analysis = BasicAnalysis(
        content=record("work-body-boundary", transcript=transcript),
        category=ContentCategory.QIANCHUAN,
        confidence=ConfidenceLevel.HIGH,
        opening=OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
        source_information=SourceInformation(
            facts=(
                SourceFact(
                    statement="原视频展示欧莱雅商品",
                    source="sample-work-source",
                    kind=content_analysis.SourceFactKind.BRAND,
                    restricted_fragments=("欧莱雅",),
                ),
            ),
        ),
    )
    assessment = ProjectAssessment(
        project_id="project-a",
        context_version="v1",
        is_fit=True,
        confidence=ConfidenceLevel.HIGH,
        conclusion="结构适配",
        body_benchmark=transcript,
        body_benchmark_evidence=(
            AnalysisEvidence(
                EvidenceType.TRANSCRIPT,
                "transcript:1",
                transcript,
            ),
        ),
        body_benchmark_boundaries=(SourceConstraint("仅适用于欧莱雅商品"),),
    )

    result = content_analysis.enforce_project_assessment_boundaries(
        assessment,
        analysis,
    )

    assert result.body_benchmark is None
    assert result.body_benchmark_evidence == ()
    assert result.body_benchmark_boundaries == ()


@pytest.mark.parametrize(
    "source_claim",
    (
        "原视频宣称成交表现亮眼",
        "原视频自称真实成交",
        "原视频口播说互动持续上涨",
    ),
)
def test_attributed_source_product_claim_is_preserved_as_source_information(
    source_claim: str,
) -> None:
    analysis = BasicAnalysis(
        content=record("work-source-claim", transcript=source_claim),
        category=ContentCategory.QIANCHUAN,
        confidence=ConfidenceLevel.LOW,
        opening=OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
        source_information=SourceInformation(
            facts=(
                SourceFact(
                    statement=source_claim,
                    source="sample-work-source",
                    kind=content_analysis.SourceFactKind.PRODUCT_CLAIM,
                    restricted_fragments=(source_claim,),
                ),
            ),
        ),
    )

    result = content_analysis.enforce_analysis_boundaries(analysis)

    assert result.source_information.facts == analysis.source_information.facts


def test_explicit_prohibition_is_valid_source_and_method_boundary() -> None:
    transcript = "先问题后证明"
    constraint = SourceConstraint("没有成交数据，不能宣称真实成交")
    method = ReusableMethod(
        name="问题到证明",
        description="先问题后证明",
        method_key="problem-proof",
        evidence=(
            AnalysisEvidence(
                EvidenceType.TRANSCRIPT,
                "transcript:1",
                transcript,
            ),
        ),
        applicable_boundaries=(constraint,),
    )
    analysis = BasicAnalysis(
        content=record("work-prohibition-boundary", transcript=transcript),
        category=ContentCategory.QIANCHUAN,
        confidence=ConfidenceLevel.HIGH,
        opening=OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
        reusable_methods=(method,),
        source_information=SourceInformation(source_constraints=(constraint,)),
    )

    result = content_analysis.enforce_analysis_boundaries(analysis)

    assert result.reusable_methods == (method,)
    assert result.source_information.source_constraints == (constraint,)


@pytest.mark.parametrize("boundary_field", ("method", "source", "opening"))
def test_unreadable_visual_fact_cannot_hide_in_analysis_boundary(
    boundary_field: str,
) -> None:
    transcript = "先问题后证明"
    visual_claim = SourceConstraint("已确认首帧展示商品")
    methods = ()
    if boundary_field == "method":
        methods = (
            ReusableMethod(
                name="问题到证明",
                description="先问题后证明",
                method_key="problem-proof",
                evidence=(
                    AnalysisEvidence(
                        EvidenceType.TRANSCRIPT,
                        "transcript:1",
                        transcript,
                    ),
                ),
                applicable_boundaries=(visual_claim,),
            ),
        )
    opening = OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED)
    if boundary_field == "opening":
        opening = OpeningAnnotation(
            status=OpeningTagStatus.AVAILABLE,
            kind=OpeningKind.LANGUAGE,
            fragment=transcript,
            evidence=(
                AnalysisEvidence(
                    EvidenceType.TRANSCRIPT,
                    "transcript:1",
                    transcript,
                ),
            ),
            applicable_boundaries=(visual_claim,),
        )
    analysis = BasicAnalysis(
        content=record("work-visual-boundary", transcript=transcript),
        category=ContentCategory.QIANCHUAN,
        confidence=ConfidenceLevel.HIGH,
        opening=opening,
        reusable_methods=methods,
        source_information=SourceInformation(
            source_constraints=(visual_claim,) if boundary_field == "source" else (),
        ),
    )

    with pytest.raises(ValueError, match="视觉"):
        content_analysis.enforce_analysis_boundaries(analysis)


def test_unreadable_visual_fact_cannot_hide_in_body_boundary() -> None:
    transcript = "先问题后证明"
    analysis = BasicAnalysis(
        content=record("work-body-visual-boundary", transcript=transcript),
        category=ContentCategory.QIANCHUAN,
        confidence=ConfidenceLevel.HIGH,
        opening=OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
    )
    assessment = ProjectAssessment(
        project_id="project-a",
        context_version="v1",
        is_fit=True,
        confidence=ConfidenceLevel.HIGH,
        conclusion="结构适配",
        body_benchmark=transcript,
        body_benchmark_evidence=(
            AnalysisEvidence(
                EvidenceType.TRANSCRIPT,
                "transcript:1",
                transcript,
            ),
        ),
        body_benchmark_boundaries=(SourceConstraint("已确认首帧展示商品"),),
    )

    with pytest.raises(ValueError, match="视觉"):
        content_analysis.enforce_project_assessment_boundaries(assessment, analysis)


@pytest.mark.asyncio
async def test_misclassified_sensitive_source_fact_cannot_release_saved_method() -> None:
    method = reusable_method(
        "brand-ingredient-proof",
        "欧莱雅成分讲解结构",
        "先成分后证明",
    )
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"), relation("project-b", "v1")),
        contexts=(context("project-a", "v1"), context("project-b", "v1")),
        saved_library_records=tuple(
            SavedLibraryRecord(
                project_id=project_id,
                content_key=f"{project_id}-source",
                reusable_methods=(method,),
                source_information=SourceInformation(
                    facts=(
                        SourceFact(
                            statement="原视频展示欧莱雅商品",
                            source="sample-work-source",
                        ),
                    ),
                ),
                scenarios=("匿名口播",),
            )
            for project_id in ("project-a", "project-b")
        ),
        run_at=RUN_AT,
    )

    assert result.cross_project_candidates == ()


@pytest.mark.asyncio
async def test_generic_binary_structure_is_not_misread_as_a_price() -> None:
    method = reusable_method("binary-structure", "二元结构", "用两个视角形成对照")
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"), relation("project-b", "v1")),
        contexts=(context("project-a", "v1"), context("project-b", "v1")),
        saved_library_records=tuple(
            SavedLibraryRecord(
                project_id=project_id,
                content_key=f"{project_id}-source",
                reusable_methods=(method,),
                source_information=SourceInformation(),
                scenarios=("匿名口播",),
            )
            for project_id in ("project-a", "project-b")
        ),
        run_at=RUN_AT,
    )

    assert [item.method.method_key for item in result.cross_project_candidates] == [
        "binary-structure"
    ]


@pytest.mark.asyncio
async def test_saved_institution_identity_and_personal_experience_do_not_cross_projects() -> None:
    method = ReusableMethod(
        name="教授身份建立信任",
        description="用身份经历证明商品",
        method_key="institution-person-story",
        evidence=(
            AnalysisEvidence(
                EvidenceType.TRANSCRIPT,
                "transcript:1",
                "张三是北京大学教授，也是产品创办人的亲身经历",
            ),
        ),
        applicable_boundaries=(SourceConstraint("仅复用故事结构"),),
    )
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"), relation("project-b", "v1")),
        contexts=(context("project-a", "v1"), context("project-b", "v1")),
        saved_library_records=tuple(
            SavedLibraryRecord(
                project_id=project_id,
                content_key=f"{project_id}-source",
                reusable_methods=(method,),
                source_information=SourceInformation(),
                scenarios=("匿名口播",),
            )
            for project_id in ("project-a", "project-b")
        ),
        run_at=RUN_AT,
    )

    assert result.cross_project_candidates == ()


def test_effect_hypothesis_is_allowed_only_in_explicit_assumption_role() -> None:
    analysis = BasicAnalysis(
        content=record("work-hypothesis"),
        category=ContentCategory.PERSONA,
        confidence=ConfidenceLevel.LOW,
        opening=OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
        source_information=SourceInformation(
            assumptions=(
                SourceAssumption("可能转化效果好，仍待经营结果验证"),
            ),
        ),
    )

    result = content_analysis.enforce_analysis_boundaries(analysis)

    assert result.source_information.assumptions == analysis.source_information.assumptions


@pytest.mark.parametrize(
    "source_information",
    (
        SourceInformation(
            assumptions=(
                SourceAssumption("真实成交仍待经营数据验证"),
            ),
        ),
        SourceInformation(
            limitations=(
                SourceLimitation("没有真实成交数据"),
            ),
        ),
    ),
)
def test_explicit_effect_hypothesis_and_data_absence_remain_valid_roles(
    source_information: SourceInformation,
) -> None:
    analysis = BasicAnalysis(
        content=record("work-valid-effect-role"),
        category=ContentCategory.PERSONA,
        confidence=ConfidenceLevel.LOW,
        opening=OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
        source_information=source_information,
    )

    result = content_analysis.enforce_analysis_boundaries(analysis)

    assert result.source_information.assumptions == source_information.assumptions
    assert all(
        limitation in result.source_information.limitations
        for limitation in source_information.limitations
    )


def test_definite_effect_claim_cannot_hide_in_limitation_role() -> None:
    analysis = BasicAnalysis(
        content=record("work-fake-limitation"),
        category=ContentCategory.PERSONA,
        confidence=ConfidenceLevel.HIGH,
        opening=OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
        source_information=SourceInformation(
            limitations=(SourceLimitation("实际转化好且已经成交"),),
        ),
    )

    with pytest.raises(ValueError, match="限制.*效果"):
        content_analysis.enforce_analysis_boundaries(analysis)


@pytest.mark.asyncio
async def test_duplicate_sync_for_one_account_does_not_block_valid_project() -> None:
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-good",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-good", account_id="account-good"),),
            ),
            AccountSyncResult(
                "account-bad",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-bad-1", account_id="account-bad"),),
            ),
            AccountSyncResult(
                "account-bad",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-bad-2", account_id="account-bad"),),
            ),
        ),
        relations=(
            relation("project-good", "v1", "account-good"),
            relation("project-bad", "v1", "account-bad"),
        ),
        contexts=(context("project-good", "v1"), context("project-bad", "v1")),
        run_at=RUN_AT,
    )

    assert [item.stable_key for item in result.reports["project-good"].items] == [
        "platform_content_id:work-good"
    ]
    bad_report = result.reports["project-bad"]
    assert bad_report.items == ()
    assert bad_report.is_empty_daily is False
    assert any("重复同步" in issue for issue in bad_report.data_issues)


@pytest.mark.asyncio
async def test_cross_account_identity_conflict_does_not_block_unrelated_project() -> None:
    analyzer = RecordingAnalyzer()
    result = await run_engine(
        analyzer,
        sync_results=(
            AccountSyncResult(
                "account-good",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-good", account_id="account-good"),),
            ),
            AccountSyncResult(
                "account-bad-a",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-conflict", account_id="account-bad-a"),),
            ),
            AccountSyncResult(
                "account-bad-b",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-conflict", account_id="account-bad-b"),),
            ),
        ),
        relations=(
            relation("project-good", "v1", "account-good"),
            relation("project-bad", "v1", "account-bad-a"),
            relation("project-bad", "v1", "account-bad-b"),
        ),
        contexts=(context("project-good", "v1"), context("project-bad", "v1")),
        run_at=RUN_AT,
    )

    assert [item.account_id for item in analyzer.basic_calls] == ["account-good"]
    assert [item.stable_key for item in result.reports["project-good"].items] == [
        "platform_content_id:work-good"
    ]
    assert result.reports["project-bad"].items == ()
    assert any(
        "稳定内容身份" in issue and "冲突" in issue
        for issue in result.reports["project-bad"].data_issues
    )


@pytest.mark.asyncio
async def test_conflicting_exact_saved_state_is_order_independent_and_project_scoped() -> None:
    previous_content = record(
        "work-state-conflict",
        published_at=REPORT_DAY - timedelta(days=1),
    )
    state_values = dict(
        project_id="project-a",
        stable_key="platform_content_id:work-state-conflict",
        candidate_rank=1,
        in_library=True,
        priority=1,
        cross_project=False,
        conclusion="适配 匿名人设",
        confidence=ConfidenceLevel.HIGH,
    )
    states = (
        SavedBusinessState(is_opportunity=True, **state_values),
        SavedBusinessState(is_opportunity=False, **state_values),
    )

    async def run_with(saved_states):
        return await run_engine(
            RecordingAnalyzer(),
            sync_results=(
                AccountSyncResult(
                    "account-001",
                    SyncStatus.SUCCESS_WITH_CONTENT,
                    (previous_content,),
                ),
            ),
            relations=(relation("project-a", "v1"),),
            contexts=(context("project-a", "v1"),),
            saved_states=saved_states,
            run_at=RUN_AT,
        )

    first = await run_with(states)
    second = await run_with(tuple(reversed(states)))

    for result in (first, second):
        report = result.reports["project-a"]
        assert report.previous_two_day_changes == ()
        assert any("历史业务状态冲突" in issue for issue in report.data_issues)


@pytest.mark.asyncio
async def test_daily_report_rejects_mutable_nested_sync_items() -> None:
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )
    report = result.reports["project-a"]
    mutable_sync_item: list[object] = []

    with pytest.raises(ValueError, match="sync_results.*AccountSyncResult"):
        replace(report, sync_results=(mutable_sync_item,))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name",
    (
        "复用雅诗兰黛用户案例",
        "借鉴雅诗兰黛用户案例",
        "雅诗兰黛用户案例叙事顺序",
        "雅诗兰黛案例叙事顺序",
    ),
)
async def test_named_brand_case_cannot_cross_projects_without_hardcoded_brand_list(
    method_name: str,
) -> None:
    method = ReusableMethod(
        name=method_name,
        description="提炼来源结构",
        method_key="named-brand-case",
        evidence=(
            AnalysisEvidence(
                EvidenceType.TRANSCRIPT,
                "transcript:1",
                "雅诗兰黛用户案例",
            ),
        ),
        applicable_boundaries=(SourceConstraint("仅复用案例结构"),),
    )
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"), relation("project-b", "v1")),
        contexts=(context("project-a", "v1"), context("project-b", "v1")),
        saved_library_records=tuple(
            SavedLibraryRecord(
                project_id=project_id,
                content_key=f"{project_id}-source",
                reusable_methods=(method,),
                source_information=SourceInformation(),
                scenarios=("匿名口播",),
            )
            for project_id in ("project-a", "project-b")
        ),
        run_at=RUN_AT,
    )

    assert result.cross_project_candidates == ()


@pytest.mark.asyncio
async def test_generic_case_story_method_can_cross_projects() -> None:
    method = ReusableMethod(
        name="典型用户案例叙事顺序",
        description="先故事后证明",
        method_key="generic-case-story",
        evidence=(
            AnalysisEvidence(
                EvidenceType.TRANSCRIPT,
                "transcript:1",
                "典型用户案例叙事顺序",
            ),
        ),
        applicable_boundaries=(SourceConstraint("仅复用叙事结构"),),
    )
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"), relation("project-b", "v1")),
        contexts=(context("project-a", "v1"), context("project-b", "v1")),
        saved_library_records=tuple(
            SavedLibraryRecord(
                project_id=project_id,
                content_key=f"{project_id}-source",
                reusable_methods=(method,),
                source_information=SourceInformation(),
                scenarios=("匿名口播",),
            )
            for project_id in ("project-a", "project-b")
        ),
        run_at=RUN_AT,
    )

    assert [item.method.method_key for item in result.cross_project_candidates] == [
        "generic-case-story"
    ]


@pytest.mark.asyncio
async def test_generic_triple_structure_is_not_misread_as_a_price() -> None:
    method = reusable_method("triple-structure", "三元组结构", "用三个要素组织内容")
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"), relation("project-b", "v1")),
        contexts=(context("project-a", "v1"), context("project-b", "v1")),
        saved_library_records=tuple(
            SavedLibraryRecord(
                project_id=project_id,
                content_key=f"{project_id}-source",
                reusable_methods=(method,),
                source_information=SourceInformation(),
                scenarios=("匿名口播",),
            )
            for project_id in ("project-a", "project-b")
        ),
        run_at=RUN_AT,
    )

    assert [item.method.method_key for item in result.cross_project_candidates] == [
        "triple-structure"
    ]


@pytest.mark.parametrize(
    "source_information",
    (
        SourceInformation(
            assumptions=(
                SourceAssumption("可能性很低，但实际转化好且已经成交"),
            ),
        ),
        SourceInformation(
            limitations=(
                SourceLimitation("没有疑问，实际转化好且已经成交"),
            ),
        ),
        SourceInformation(
            assumptions=(
                SourceAssumption("可能转化不好，但实际转化好且已经成交"),
            ),
        ),
        SourceInformation(
            limitations=(
                SourceLimitation("没有数据不代表表现差，实际转化好且已经成交"),
            ),
        ),
        SourceInformation(
            assumptions=(
                SourceAssumption("可能互动下降，但互动持续上涨"),
            ),
        ),
        SourceInformation(
            limitations=(
                SourceLimitation("没有数据不代表下降，互动持续上涨"),
            ),
        ),
        SourceInformation(
            assumptions=(
                SourceAssumption("可能成交较低，但成交表现不错"),
            ),
        ),
        SourceInformation(
            assumptions=(
                SourceAssumption("可能互动下降同时互动持续上涨"),
            ),
        ),
        SourceInformation(
            assumptions=(
                SourceAssumption("可能互动下降并且互动持续上涨"),
            ),
        ),
        SourceInformation(
            assumptions=(
                SourceAssumption("可能成交较低而成交表现不错"),
            ),
        ),
        SourceInformation(
            assumptions=(
                SourceAssumption("可能互动下降以及后续持续上涨"),
            ),
        ),
        SourceInformation(
            assumptions=(SourceAssumption("可能下降但已持续上涨"),),
        ),
        SourceInformation(
            assumptions=(SourceAssumption("可能较差而已持续上涨"),),
        ),
        SourceInformation(
            assumptions=(SourceAssumption("可能不佳却正持续上涨"),),
        ),
        SourceInformation(
            limitations=(SourceLimitation("无法判断但已持续上涨"),),
        ),
        SourceInformation(
            limitations=(SourceLimitation("没有数据但已持续上涨"),),
        ),
        SourceInformation(
            limitations=(SourceLimitation("缺少证据却正持续上涨"),),
        ),
        SourceInformation(
            assumptions=(SourceAssumption("可能差可是已持续上涨"),),
        ),
        SourceInformation(
            assumptions=(SourceAssumption("可能低不过已持续上涨"),),
        ),
        SourceInformation(
            assumptions=(SourceAssumption("可能差但目前持续上涨"),),
        ),
        SourceInformation(
            limitations=(SourceLimitation("没有数据可是已持续上涨"),),
        ),
        SourceInformation(
            limitations=(SourceLimitation("缺少证据不过正持续上涨"),),
        ),
        SourceInformation(
            limitations=(SourceLimitation("无法判断但目前持续上涨"),),
        ),
    ),
)
def test_unrelated_role_markers_cannot_launder_definite_effect_claims(
    source_information: SourceInformation,
) -> None:
    analysis = BasicAnalysis(
        content=record("work-role-laundering"),
        category=ContentCategory.PERSONA,
        confidence=ConfidenceLevel.HIGH,
        opening=OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
        source_information=source_information,
    )

    with pytest.raises(ValueError, match="效果"):
        content_analysis.enforce_analysis_boundaries(analysis)


@pytest.mark.parametrize(
    "reason",
    (
        "无法分类，但成交表现亮眼",
        "信息不足，但互动持续上涨",
        "缺少转写，首帧出现产品",
    ),
)
def test_undetermined_reason_cannot_launder_definite_claims(reason: str) -> None:
    analysis = BasicAnalysis(
        content=record("work-undetermined-role"),
        category=ContentCategory.UNDETERMINED,
        confidence=ConfidenceLevel.LOW,
        opening=OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
        undetermined_reason=reason,
    )

    with pytest.raises(ValueError, match="效果|视觉"):
        content_analysis.enforce_analysis_boundaries(analysis)


@pytest.mark.parametrize(
    "reason",
    (
        "开头不可用，但成交表现亮眼",
        "缺少画面，但互动持续上涨",
        "无法判断开头，首帧出现产品",
    ),
)
def test_unavailable_opening_reason_cannot_launder_definite_claims(
    reason: str,
) -> None:
    analysis = BasicAnalysis(
        content=record("work-opening-unavailable-role"),
        category=ContentCategory.QIANCHUAN,
        confidence=ConfidenceLevel.LOW,
        opening=OpeningAnnotation(
            status=OpeningTagStatus.UNAVAILABLE,
            kind=OpeningKind.LANGUAGE,
            unavailable_reason=reason,
        ),
    )

    with pytest.raises(ValueError, match="效果|视觉"):
        content_analysis.enforce_analysis_boundaries(analysis)


def test_language_opening_cannot_carry_unsupported_effect_claim() -> None:
    claim = "实际转化好且已经成交"
    analysis = BasicAnalysis(
        content=record("work-opening-effect", transcript=claim),
        category=ContentCategory.QIANCHUAN,
        confidence=ConfidenceLevel.HIGH,
        opening=OpeningAnnotation(
            status=OpeningTagStatus.AVAILABLE,
            kind=OpeningKind.LANGUAGE,
            fragment=claim,
            evidence=(
                AnalysisEvidence(EvidenceType.TRANSCRIPT, "transcript:1", claim),
            ),
            applicable_boundaries=(SourceConstraint("仅验证语言开头"),),
        ),
    )

    result = content_analysis.enforce_analysis_boundaries(analysis)

    assert result.opening.status == OpeningTagStatus.UNAVAILABLE
    assert "效果或趋势" in result.opening.unavailable_reason


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    (
        ("fragment", ["开头片段"]),
        ("unavailable_reason", ["没有证据"]),
    ),
)
def test_opening_annotation_rejects_mutable_scalar_fields(
    field_name: str,
    invalid_value: list[str],
) -> None:
    kwargs = {
        "status": OpeningTagStatus.AVAILABLE,
        "kind": OpeningKind.LANGUAGE,
        "fragment": "开头片段",
        "evidence": (
            AnalysisEvidence(EvidenceType.TRANSCRIPT, "transcript:1", "开头片段"),
        ),
        "applicable_boundaries": (SourceConstraint("仅验证语言开头"),),
    }
    if field_name == "unavailable_reason":
        kwargs = {
            "status": OpeningTagStatus.UNAVAILABLE,
            "kind": OpeningKind.LANGUAGE,
            "unavailable_reason": "没有证据",
        }
    kwargs[field_name] = invalid_value

    with pytest.raises(ValueError, match="开头"):
        OpeningAnnotation(**kwargs)


def test_engine_result_rejects_mutable_nested_cross_project_items() -> None:
    mutable_candidate: list[object] = []

    with pytest.raises(ValueError, match="cross_project_candidates.*CrossProjectCandidate"):
        content_analysis.EngineResult(
            reports={},
            cross_project_candidates=(mutable_candidate,),
            relation_issues=(),
        )


@pytest.mark.asyncio
async def test_duplicate_weekly_baseline_does_not_block_valid_project() -> None:
    baseline_values = dict(
        account_id="account-bad",
        window_start=datetime(2026, 8, 5, tzinfo=SHANGHAI),
        window_end=datetime(2026, 9, 4, tzinfo=SHANGHAI),
    )
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-good",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-good", account_id="account-good"),),
            ),
            AccountSyncResult(
                "account-bad",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-bad", account_id="account-bad"),),
            ),
        ),
        relations=(
            relation("project-good", "v1", "account-good"),
            relation("project-bad", "v1", "account-bad"),
        ),
        contexts=(context("project-good", "v1"), context("project-bad", "v1")),
        persona_baselines=(
            content_analysis.WeeklyPersonaBaseline(
                baseline=content_analysis.LikeBaseline(10, 10, 1, 10, 10),
                **baseline_values,
            ),
            content_analysis.WeeklyPersonaBaseline(
                baseline=content_analysis.LikeBaseline(20, 20, 1, 20, 20),
                **baseline_values,
            ),
        ),
        run_at=RUN_AT,
    )

    assert [item.stable_key for item in result.reports["project-good"].items] == [
        "platform_content_id:work-good"
    ]
    assert [item.stable_key for item in result.reports["project-bad"].items] == [
        "platform_content_id:work-bad"
    ]
    assert any(
        "重复周度人设基准" in issue
        for issue in result.reports["project-bad"].data_issues
    )


@pytest.mark.asyncio
async def test_daily_report_rejects_mutable_summary_objects() -> None:
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    with pytest.raises(ValueError, match="categories.*CategoryOverview"):
        replace(result.reports["project-a"], categories=[])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "invalid"),
    (
        ("project_id", []),
        ("context_version", []),
        ("run_key", []),
        ("stable_key", []),
    ),
)
async def test_library_candidate_rejects_mutable_scalar_fields(
    field_name: str,
    invalid: list[object],
) -> None:
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )
    candidate = result.reports["project-a"].library_candidates[0]

    with pytest.raises(ValueError):
        replace(candidate, **{field_name: invalid})


def test_project_fact_rejects_mutable_values() -> None:
    with pytest.raises(ValueError, match="项目事实"):
        ProjectFact(key="current_product", value=[])


@pytest.mark.asyncio
async def test_cross_project_candidate_rejects_mutable_nested_sources() -> None:
    method = reusable_method("shared-structure", "对照结构", "用两个视角对照")
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-001"),),
            ),
        ),
        relations=(relation("project-a", "v1"), relation("project-b", "v1")),
        contexts=(context("project-a", "v1"), context("project-b", "v1")),
        saved_library_records=tuple(
            SavedLibraryRecord(
                project_id=project_id,
                content_key=f"{project_id}-source",
                reusable_methods=(method,),
                source_information=SourceInformation(),
                scenarios=("匿名口播",),
            )
            for project_id in ("project-a", "project-b")
        ),
        run_at=RUN_AT,
    )
    candidate = result.cross_project_candidates[0]

    with pytest.raises(ValueError, match="sources.*CrossProjectSource"):
        replace(candidate, sources=([],))


def test_engine_result_rejects_mutable_nested_collections() -> None:
    with pytest.raises(ValueError, match="不可变元组"):
        content_analysis.EngineResult(
            reports={},
            cross_project_candidates=[],
            relation_issues=[],
        )


@pytest.mark.parametrize(
    ("evidence_type", "detail"),
    (
        (EvidenceType.TRANSCRIPT, "转写里不存在的片段"),
        (EvidenceType.METADATA, "真实转写证据"),
    ),
)
def test_reusable_method_requires_actual_transcript_or_verified_visual_evidence(
    evidence_type,
    detail,
) -> None:
    analysis = BasicAnalysis(
        content=record("work-fake-evidence", transcript="真实转写证据"),
        category=ContentCategory.PERSONA,
        confidence=ConfidenceLevel.HIGH,
        opening=OpeningAnnotation(status=OpeningTagStatus.UNANNOTATED),
        reusable_methods=(
            ReusableMethod(
                name="方法",
                description="结构说明",
                method_key="method",
                evidence=(AnalysisEvidence(evidence_type, "forged", detail),),
                applicable_boundaries=(SourceConstraint("仅复用结构"),),
            ),
        ),
    )

    result = content_analysis.enforce_analysis_boundaries(analysis)

    assert result.reusable_methods == ()


@pytest.mark.asyncio
async def test_library_candidate_requires_video_traceability() -> None:
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-no-video", video_reference=None),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    assert result.reports["project-a"].library_candidates == ()


@pytest.mark.asyncio
async def test_library_candidate_requires_all_project_context_fit_dimensions() -> None:
    result = await run_engine(
        CandidateGateAnalyzer(
            assessment_updates={
                "fit_reasons": (
                    ProjectFitReason(
                        ProjectFitDimension.PROJECT_PERSONA,
                        "只判断了项目人设",
                    ),
                ),
            }
        ),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (record("work-one-fit-dimension"),),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    assert result.reports["project-a"].library_candidates == ()


@pytest.mark.asyncio
async def test_internal_run_keys_are_explicit_and_reports_mapping_is_immutable() -> None:
    first = record(None, transcript="匿名一")
    second = replace(
        record(None, transcript="匿名二"),
        captured_at=RUN_AT - timedelta(minutes=1),
    )
    result = await run_engine(
        RecordingAnalyzer(),
        sync_results=(
            AccountSyncResult(
                "account-001",
                SyncStatus.SUCCESS_WITH_CONTENT,
                (first, second),
            ),
        ),
        relations=(relation("project-a", "v1"),),
        contexts=(context("project-a", "v1"),),
        run_at=RUN_AT,
    )

    run_keys = [item.run_key for item in result.reports["project-a"].items]
    assert len(run_keys) == len(set(run_keys)) == 2
    assert all(key.startswith("run:") for key in run_keys)
    with pytest.raises(TypeError):
        result.reports["project-x"] = result.reports["project-a"]
