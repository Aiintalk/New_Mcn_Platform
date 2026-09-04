"""v1.8 标题、纯文本分析和无内容日报的收敛合同。"""
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import app.services.content_analysis as content_analysis


SHANGHAI = ZoneInfo("Asia/Shanghai")
RUN_AT = datetime(2026, 9, 4, 9, tzinfo=SHANGHAI)
WINDOW = content_analysis.SyncCoverageWindow(
    start=datetime(2026, 9, 1, tzinfo=SHANGHAI),
    end=datetime(2026, 9, 4, tzinfo=SHANGHAI),
)
CHECKED_AT = datetime(2026, 9, 4, 0, 5, tzinfo=SHANGHAI)


def content(
    *,
    transcript: str | None = "先问问题，再给证明",
    title: str | None = "匿名标题",
) -> content_analysis.ContentRecord:
    return content_analysis.ContentRecord(
        account_id="account-001",
        source=content_analysis.ContentSource.PLATFORM_SYNC,
        identity=content_analysis.ContentIdentity(platform_content_id="work-001"),
        published_at=datetime(2026, 9, 3, 10, tzinfo=SHANGHAI),
        captured_at=datetime(2026, 9, 4, 0, tzinfo=SHANGHAI),
        metrics=content_analysis.EngagementMetrics(
            like_count=100,
            comment_count=10,
            share_count=5,
            favorite_count=8,
        ),
        title=title,
        transcript=transcript,
    )


def context(project_id: str = "project-001") -> content_analysis.ProjectContextVersion:
    return content_analysis.ProjectContextVersion(
        project_id=project_id,
        version="v1",
        effective_at=datetime(2026, 9, 1, tzinfo=SHANGHAI),
        project_persona="匿名人设",
        target_users="匿名用户",
        content_plan="匿名规划",
        operating_direction="匿名经营方向",
    )


def relation(
    project_id: str = "project-001",
    account_id: str = "account-001",
) -> content_analysis.ProjectAccountRelation:
    return content_analysis.ProjectAccountRelation(project_id, account_id, "v1")


class TextAnalyzer:
    def __init__(self) -> None:
        self.basic_calls: list[content_analysis.ContentRecord] = []
        self.project_calls: list[str] = []

    async def analyze_content(
        self,
        record: content_analysis.ContentRecord,
    ) -> content_analysis.BasicAnalysis:
        self.basic_calls.append(record)
        assert record.title == "匿名标题"
        return content_analysis.BasicAnalysis(
            content=record,
            category=content_analysis.ContentCategory.QIANCHUAN,
            confidence=content_analysis.ConfidenceLevel.HIGH,
            opening=content_analysis.OpeningAnnotation(
                status=content_analysis.OpeningTagStatus.AVAILABLE,
                kind=content_analysis.OpeningKind.LANGUAGE,
                fragment="先问问题",
                evidence=(
                    content_analysis.AnalysisEvidence(
                        content_analysis.EvidenceType.TRANSCRIPT,
                        "transcript:opening",
                        "先问问题",
                    ),
                ),
                applicable_boundaries=(
                    content_analysis.SourceConstraint("只复用提问方式"),
                ),
            ),
            reusable_methods=(
                content_analysis.ReusableMethod(
                    name="标题问题切入",
                    description="用标题中的问题建立阅读预期",
                    method_key="title-problem-entry",
                    evidence=(
                        content_analysis.AnalysisEvidence(
                            content_analysis.EvidenceType.TITLE,
                            "title",
                            "匿名标题",
                        ),
                    ),
                    applicable_boundaries=(
                        content_analysis.SourceConstraint("按目标项目改写标题"),
                    ),
                ),
            ),
            topic="匿名选题",
            summary="匿名摘要",
            structure=("问题", "证明"),
            persuasion_chain=("问题", "证明"),
        )

    async def assess_project(
        self,
        analysis: content_analysis.BasicAnalysis,
        project_context: content_analysis.ProjectContextVersion,
    ) -> content_analysis.ProjectAssessment:
        self.project_calls.append(project_context.project_id)
        return content_analysis.ProjectAssessment(
            project_id=project_context.project_id,
            context_version=project_context.version,
            is_fit=True,
            is_opportunity=True,
            confidence=content_analysis.ConfidenceLevel.HIGH,
            conclusion="适合匿名项目",
            priority=1,
            body_benchmark="先问问题，再给证明",
            body_benchmark_evidence=(
                content_analysis.AnalysisEvidence(
                    content_analysis.EvidenceType.TRANSCRIPT,
                    "transcript:body",
                    "先问问题，再给证明",
                ),
            ),
            body_benchmark_boundaries=(
                content_analysis.SourceConstraint("只复用文本结构"),
            ),
            value_signals=(
                content_analysis.CandidateValueSignal.REUSABLE_CONVERSION_STRUCTURE,
            ),
            fit_reasons=tuple(
                content_analysis.ProjectFitReason(dimension, "与项目上下文匹配")
                for dimension in content_analysis.ProjectFitDimension
            ),
            recommended_action="加入项目内容库",
            decision_basis=("标题、转写和互动数据支持",),
        )


@pytest.mark.asyncio
async def test_text_analysis_and_library_candidate_do_not_require_playback_links() -> None:
    analyzer = TextAnalyzer()
    run_input = content_analysis.OfflineRunInput(
        sync_results=(
            content_analysis.AccountSyncResult(
                "account-001",
                content_analysis.SyncStatus.SUCCESS_WITH_CONTENT,
                (content(),),
                checked_at=CHECKED_AT,
                coverage_window=WINDOW,
                read_source=content_analysis.ReadSource.FEISHU,
            ),
        ),
        relations=(relation(),),
        contexts=(context(),),
        run_at=RUN_AT,
    )

    result = await content_analysis.ContentAnalysisEngine(analyzer).run(run_input)

    candidate = result.reports["project-001"].library_candidates[0]
    assert candidate.content.identity.platform_content_id == "work-001"
    assert candidate.content.identity.external_url is None
    assert candidate.content.operations_review_url is None
    assert candidate.analysis.reusable_methods[0].evidence[0].evidence_type == (
        content_analysis.EvidenceType.TITLE
    )


class MustNotAnalyzeMissingTranscript:
    def __init__(self) -> None:
        self.basic_calls = 0
        self.project_calls = 0

    async def analyze_content(self, record):
        self.basic_calls += 1
        raise AssertionError("缺少转写的内容不应调用结构化分析器")

    async def assess_project(self, analysis, project_context):
        self.project_calls += 1
        raise AssertionError("缺少转写的内容不应调用项目判断器")


@pytest.mark.asyncio
async def test_missing_transcript_counts_content_but_is_deterministically_undetermined() -> None:
    analyzer = MustNotAnalyzeMissingTranscript()
    run_input = content_analysis.OfflineRunInput(
        sync_results=(
            content_analysis.AccountSyncResult(
                "account-001",
                content_analysis.SyncStatus.SUCCESS_WITH_CONTENT,
                (content(transcript=None),),
                checked_at=CHECKED_AT,
                coverage_window=WINDOW,
                read_source=content_analysis.ReadSource.FEISHU,
            ),
        ),
        relations=(relation(),),
        contexts=(context(),),
        run_at=RUN_AT,
    )

    result = await content_analysis.ContentAnalysisEngine(analyzer).run(run_input)

    report = result.reports["project-001"]
    assert analyzer.basic_calls == 0
    assert analyzer.project_calls == 0
    assert report.daily_overview.content_count == 1
    assert report.categories.undetermined == 1
    assert report.interactions.like_count.total == 100
    assert report.interactions.comment_count.total == 10
    assert report.interactions.share_count.total == 5
    assert report.interactions.favorite_count.total == 8
    assert report.interactions.like_count.missing_count == 0
    assert report.interactions.comment_count.missing_count == 0
    assert report.interactions.share_count.missing_count == 0
    assert report.interactions.favorite_count.missing_count == 0
    assert report.items[0].analysis.category == content_analysis.ContentCategory.UNDETERMINED
    assert "缺少转写" in report.items[0].analysis.undetermined_reason
    assert report.library_candidates == ()


@pytest.mark.asyncio
async def test_complete_feishu_read_with_all_accounts_empty_has_atomic_empty_receipt() -> None:
    analyzer = TextAnalyzer()
    run_input = content_analysis.OfflineRunInput(
        sync_results=(
            content_analysis.AccountSyncResult(
                "account-001",
                content_analysis.SyncStatus.SUCCESS_WITHOUT_CONTENT,
                checked_at=CHECKED_AT,
                coverage_window=WINDOW,
                read_source=content_analysis.ReadSource.FEISHU,
            ),
        ),
        relations=(relation(),),
        contexts=(context(),),
        run_at=RUN_AT,
    )

    result = await content_analysis.ContentAnalysisEngine(analyzer).run(run_input)

    report = result.reports["project-001"]
    receipt = report.no_content_summary
    assert report.is_empty_daily is True
    assert "飞书读取成功" in report.summary
    assert receipt.read_succeeded is True
    assert receipt.read_source == content_analysis.ReadSource.FEISHU
    assert receipt.checked_account_ids == ("account-001",)
    assert receipt.coverage_window == WINDOW
    assert receipt.read_completed_at == CHECKED_AT
    assert receipt.content_count == 0
    assert receipt.persona_opportunity_count == 0
    assert receipt.qianchuan_opportunity_count == 0
    assert receipt.library_candidate_count == 0
    assert receipt.cross_project_candidate_count == 0
    assert analyzer.basic_calls == []

    with pytest.raises(ValueError, match="同步结果"):
        replace(report, sync_results=())
    with pytest.raises(ValueError, match="内容数"):
        replace(
            report,
            daily_overview=replace(report.daily_overview, content_count=1),
        )
    with pytest.raises(ValueError, match="账号关系"):
        replace(report, relation_issues=("账号关系不完整",))
    with pytest.raises(ValueError, match="重复"):
        replace(
            receipt,
            checked_account_ids=("account-001", "account-001"),
        )


@pytest.mark.asyncio
async def test_failed_feishu_read_never_creates_empty_daily_receipt() -> None:
    issue = content_analysis.SyncIssue(
        affected_account_ids=("account-001",),
        affected_window=WINDOW,
        impact=content_analysis.SyncIssueImpact.CONTENT_UNAVAILABLE,
        reason="飞书分页读取未完成",
    )
    run_input = content_analysis.OfflineRunInput(
        sync_results=(
            content_analysis.AccountSyncResult(
                "account-001",
                content_analysis.SyncStatus.FAILED,
                issue=issue,
                checked_at=CHECKED_AT,
                coverage_window=WINDOW,
                read_source=content_analysis.ReadSource.FEISHU,
            ),
        ),
        relations=(relation(),),
        contexts=(context(),),
        run_at=RUN_AT,
    )

    result = await content_analysis.ContentAnalysisEngine(TextAnalyzer()).run(run_input)

    report = result.reports["project-001"]
    assert report.is_empty_daily is False
    assert report.no_content_summary is None
    assert "飞书读取成功" not in report.summary
    assert any("分页读取未完成" in item for item in report.data_issues)


class EmptyFeishuClient:
    async def authorize_read(self, app_token: str, table_id: str) -> None:
        return None

    async def list_field_names(
        self,
        app_token: str,
        table_id: str,
    ) -> tuple[str, ...]:
        return (
            "SecUid",
            "视频ID",
            "视频标题",
            "字幕全文",
            "发布时间",
            "同步时间",
            "点赞",
            "评论",
            "分享",
            "收藏",
        )

    async def list_records(
        self,
        app_token: str,
        table_id: str,
        *,
        page_token: str | None,
    ) -> content_analysis.FeishuRecordPage:
        return content_analysis.FeishuRecordPage(items=(), total=0)


@pytest.mark.asyncio
async def test_complete_empty_feishu_read_flows_through_engine_as_empty_daily() -> None:
    sync_results = await content_analysis.FeishuContentReader(
        EmptyFeishuClient(),
        content_analysis.FeishuContentTableConfig("base-token", "table-id"),
        clock=lambda: CHECKED_AT,
    ).read_accounts(("account-001",), WINDOW)
    run_input = content_analysis.OfflineRunInput(
        sync_results=sync_results,
        relations=(relation(),),
        contexts=(context(),),
        run_at=RUN_AT,
    )

    result = await content_analysis.ContentAnalysisEngine(TextAnalyzer()).run(run_input)

    report = result.reports["project-001"]
    assert report.is_empty_daily is True
    assert report.no_content_summary.read_source == content_analysis.ReadSource.FEISHU
    assert report.no_content_summary.content_count == 0


def empty_sync(
    account_id: str,
    *,
    read_source: content_analysis.ReadSource = content_analysis.ReadSource.FEISHU,
) -> content_analysis.AccountSyncResult:
    return content_analysis.AccountSyncResult(
        account_id,
        content_analysis.SyncStatus.SUCCESS_WITHOUT_CONTENT,
        checked_at=CHECKED_AT,
        coverage_window=WINDOW,
        read_source=read_source,
    )


@pytest.mark.asyncio
async def test_mixed_empty_read_sources_do_not_block_other_project_reports() -> None:
    run_input = content_analysis.OfflineRunInput(
        sync_results=(
            empty_sync("account-001"),
            empty_sync(
                "account-002",
                read_source=content_analysis.ReadSource.STANDARD_INPUT,
            ),
            empty_sync("account-003"),
        ),
        relations=(
            relation("project-mixed", "account-001"),
            relation("project-mixed", "account-002"),
            relation("project-good", "account-003"),
        ),
        contexts=(context("project-mixed"), context("project-good")),
        run_at=RUN_AT,
    )

    result = await content_analysis.ContentAnalysisEngine(TextAnalyzer()).run(run_input)

    mixed = result.reports["project-mixed"]
    good = result.reports["project-good"]
    assert mixed.is_empty_daily is False
    assert mixed.no_content_summary is None
    assert any("混用多个读取来源" in item for item in mixed.data_issues)
    assert good.is_empty_daily is True
    assert good.no_content_summary is not None


@pytest.mark.asyncio
async def test_empty_daily_requires_valid_result_for_every_related_account() -> None:
    invalid_issue_result = content_analysis.AccountSyncResult(
        "account-002",
        content_analysis.SyncStatus.PARTIAL_SUCCESS,
        checked_at=CHECKED_AT,
        coverage_window=WINDOW,
        read_source=content_analysis.ReadSource.FEISHU,
    )
    run_input = content_analysis.OfflineRunInput(
        sync_results=(empty_sync("account-001"), invalid_issue_result),
        relations=(
            relation("project-001", "account-001"),
            relation("project-001", "account-002"),
        ),
        contexts=(context(),),
        run_at=RUN_AT,
    )

    result = await content_analysis.ContentAnalysisEngine(TextAnalyzer()).run(run_input)

    report = result.reports["project-001"]
    assert report.is_empty_daily is False
    assert report.no_content_summary is None
    assert any("account-002" in item and "同步合同无效" in item for item in report.data_issues)
