"""内容分析阶段一的项目隔离离线编排。"""
import asyncio
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from enum import Enum
from math import isfinite
from types import MappingProxyType
from typing import Iterable

from .analyzer import (
    CandidateValueSignal,
    ContentAnalyzer,
    CrossProjectSignal,
    ProjectAssessment,
    ProjectFitReason,
    enforce_analysis_boundaries,
    enforce_project_assessment_boundaries,
    is_reusable_method_safe,
    is_source_limited_text,
    is_visual_claim,
)
from .deterministic import (
    deduplicate_contents,
    derive_data_maturity,
    derive_windows,
    qianchuan_top_three,
)
from .domain import (
    BasicAnalysis,
    ConfidenceLevel,
    ContentCategory,
    ContentRecord,
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
    SourceInformation,
    SourceLimitation,
    SyncStatus,
    WeeklyPersonaBaseline,
)


def _require_tuple_fields(instance: object, *field_names: str) -> None:
    for field_name in field_names:
        if not isinstance(getattr(instance, field_name), tuple):
            raise ValueError(f"{field_name} 必须是不可变元组")


@dataclass(frozen=True)
class SyncCoverageWindow:
    """一次账号同步明确声明的半开覆盖窗口。"""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        for field_name in ("start", "end"):
            value = getattr(self, field_name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"同步覆盖窗口 {field_name} 必须带时区")
        if self.start >= self.end:
            raise ValueError("同步覆盖窗口的开始必须早于结束")


class SyncIssueImpact(str, Enum):
    """同步缺口对当前覆盖窗口的封闭影响。"""

    CONTENT_MAY_BE_INCOMPLETE = "content_may_be_incomplete"
    CONTENT_UNAVAILABLE = "content_unavailable"


class ReadSource(str, Enum):
    """内部读取结果的来源，不要求上游提供同名字段。"""

    STANDARD_INPUT = "standard_input"
    FEISHU = "feishu"


_SAFE_SYNC_ISSUE_REASONS = frozenset(
    {
        "飞书只读鉴权失败",
        "飞书字段校验失败",
        "飞书读取超时",
        "飞书分页读取未完成",
        "飞书读取失败",
        "内容源读取失败",
        "内容源读取失败，详见上游读取日志",
    }
)


@dataclass(frozen=True)
class SyncIssue:
    """不携带上游原始错误的结构化同步缺口。"""

    affected_account_ids: tuple[str, ...]
    affected_window: SyncCoverageWindow
    impact: SyncIssueImpact
    reason: str | None = None

    def __post_init__(self) -> None:
        _require_tuple_fields(self, "affected_account_ids")
        if not self.affected_account_ids or any(
            not isinstance(account_id, str) or not account_id.strip()
            for account_id in self.affected_account_ids
        ):
            raise ValueError("同步缺口必须包含受影响账号")
        if len(set(self.affected_account_ids)) != len(self.affected_account_ids):
            raise ValueError("同步缺口不能重复列出受影响账号")
        if not isinstance(self.affected_window, SyncCoverageWindow):
            raise ValueError("同步缺口必须包含受影响窗口")
        if not isinstance(self.impact, SyncIssueImpact):
            raise ValueError("同步缺口影响不受支持")
        if self.reason is not None and (
            not isinstance(self.reason, str) or not self.reason.strip()
        ):
            raise ValueError("同步缺口原因必须是非空文本或空值")
        if self.reason is not None and self.reason not in _SAFE_SYNC_ISSUE_REASONS:
            object.__setattr__(
                self,
                "reason",
                "内容源读取失败，详见上游读取日志",
            )


@dataclass(frozen=True)
class AccountSyncResult:
    """单个稳定账号的一次同步结果。"""

    account_id: str
    status: SyncStatus
    contents: tuple[ContentRecord, ...] = ()
    issue: SyncIssue | None = None
    checked_at: datetime | None = None
    coverage_window: SyncCoverageWindow | None = None
    read_source: ReadSource = ReadSource.STANDARD_INPUT

    def __post_init__(self) -> None:
        _require_tuple_fields(self, "contents")
        if not isinstance(self.read_source, ReadSource):
            raise ValueError("读取来源不受支持")
        if any(content.account_id != self.account_id for content in self.contents):
            raise ValueError("同步结果不能包含其他账号的内容")


def _validate_daily_sync_contract(
    sync_result: AccountSyncResult,
    expected_window: SyncCoverageWindow,
) -> None:
    """在消费同步载荷前验证本次日报所需的可追溯合同。"""
    if not isinstance(sync_result.status, SyncStatus):
        raise ValueError(f"账号 {sync_result.account_id} 的同步状态不受支持")
    checked_at = sync_result.checked_at
    if checked_at is None or checked_at.tzinfo is None or checked_at.utcoffset() is None:
        raise ValueError(f"账号 {sync_result.account_id} 的同步检查时间缺失或无时区")
    if not isinstance(sync_result.coverage_window, SyncCoverageWindow):
        raise ValueError(f"账号 {sync_result.account_id} 的同步覆盖窗口缺失或无效")
    if sync_result.coverage_window != expected_window:
        raise ValueError(f"账号 {sync_result.account_id} 的同步覆盖窗口与日报窗口不匹配")
    if (
        sync_result.status == SyncStatus.SUCCESS_WITHOUT_CONTENT
        and sync_result.contents
    ):
        raise ValueError("成功无内容状态不能携带内容载荷")
    if sync_result.status == SyncStatus.FAILED and sync_result.contents:
        raise ValueError("同步失败状态不能携带内容载荷")
    if sync_result.status in (SyncStatus.PARTIAL_SUCCESS, SyncStatus.FAILED):
        if not isinstance(sync_result.issue, SyncIssue):
            raise ValueError("部分同步或同步失败原因必须使用结构化同步缺口")
        if sync_result.issue.affected_account_ids != (sync_result.account_id,):
            raise ValueError("结构化同步缺口必须且只能包含当前账号")
        if sync_result.issue.affected_window != sync_result.coverage_window:
            raise ValueError("结构化同步缺口窗口与同步覆盖窗口不匹配")
        expected_impact = (
            SyncIssueImpact.CONTENT_MAY_BE_INCOMPLETE
            if sync_result.status == SyncStatus.PARTIAL_SUCCESS
            else SyncIssueImpact.CONTENT_UNAVAILABLE
        )
        if sync_result.issue.impact != expected_impact:
            raise ValueError("结构化同步缺口影响与同步状态不匹配")
    elif sync_result.issue is not None:
        raise ValueError("同步成功状态不能携带同步缺口")
    if sync_result.status == SyncStatus.SUCCESS_WITH_CONTENT and not any(
        expected_window.start <= content.published_at < expected_window.end
        for content in sync_result.contents
    ):
        raise ValueError("同步成功有内容状态必须携带日报窗口内的成功内容")


@dataclass(frozen=True)
class MetricSummary:
    """单项互动的已知总数和缺失条数。"""

    total: int
    missing_count: int

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value < 0
            for value in (self.total, self.missing_count)
        ):
            raise ValueError("互动汇总必须使用非负整数")


@dataclass(frozen=True)
class InteractionOverview:
    """仅保留四项当前互动值，不派生播放率或趋势。"""

    like_count: MetricSummary
    comment_count: MetricSummary
    share_count: MetricSummary
    favorite_count: MetricSummary

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, MetricSummary)
            for value in (
                self.like_count,
                self.comment_count,
                self.share_count,
                self.favorite_count,
            )
        ):
            raise ValueError("互动概览必须由四项 MetricSummary 组成")


@dataclass(frozen=True)
class CategoryOverview:
    """当日报告内容的三分类计数。"""

    persona: int
    qianchuan: int
    undetermined: int

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value < 0
            for value in (self.persona, self.qianchuan, self.undetermined)
        ):
            raise ValueError("分类概览必须使用非负整数")


@dataclass(frozen=True)
class DailyOverview:
    """项目日报的当日数量、分类和四项互动概览。"""

    content_count: int
    categories: CategoryOverview
    interactions: InteractionOverview

    def __post_init__(self) -> None:
        if type(self.content_count) is not int or self.content_count < 0:
            raise ValueError("当日内容数必须是非负整数")
        if not isinstance(self.categories, CategoryOverview):
            raise ValueError("daily_overview.categories 必须是 CategoryOverview")
        if not isinstance(self.interactions, InteractionOverview):
            raise ValueError("daily_overview.interactions 必须是 InteractionOverview")


@dataclass(frozen=True)
class ReportItem:
    """一条经过项目盖章的日报内容。"""

    run_key: str
    stable_key: str | None
    analysis: BasicAnalysis
    assessment: ProjectAssessment
    project_facts: tuple[ProjectFact, ...]
    persona_relative_like: RelativePerformanceLevel | None = None
    candidate_rank: int | None = None
    is_opportunity: bool = False
    in_library: bool = False
    cross_project: bool = False

    def __post_init__(self) -> None:
        _require_tuple_fields(self, "project_facts")
        if not isinstance(self.run_key, str) or not self.run_key.strip():
            raise ValueError("日报内容必须包含运行内稳定键")
        if self.stable_key is not None and not isinstance(self.stable_key, str):
            raise ValueError("稳定内容键必须是文本或空值")
        if not isinstance(self.analysis, BasicAnalysis):
            raise ValueError("analysis 必须是 BasicAnalysis")
        if not isinstance(self.assessment, ProjectAssessment):
            raise ValueError("assessment 必须是 ProjectAssessment")
        if any(not isinstance(item, ProjectFact) for item in self.project_facts):
            raise ValueError("project_facts 的每一项都必须是 ProjectFact")
        if self.persona_relative_like is not None and not isinstance(
            self.persona_relative_like,
            RelativePerformanceLevel,
        ):
            raise ValueError("人设相对点赞状态不受支持")
        if self.candidate_rank is not None and (
            type(self.candidate_rank) is not int or self.candidate_rank <= 0
        ):
            raise ValueError("候选排名必须是正整数或空值")
        for field_name in ("is_opportunity", "in_library", "cross_project"):
            if type(getattr(self, field_name)) is not bool:
                raise ValueError(f"{field_name} 必须是原生布尔值")


@dataclass(frozen=True)
class LibraryCandidate:
    """项目内容库候选；千川正文与开头信息保持原子绑定。"""

    project_id: str
    context_version: str
    run_key: str
    stable_key: str | None
    analysis: BasicAnalysis
    assessment: ProjectAssessment
    project_facts: tuple[ProjectFact, ...]

    def __post_init__(self) -> None:
        _require_tuple_fields(self, "project_facts")
        for field_name in ("project_id", "context_version", "run_key"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} 必须是非空文本")
        if self.stable_key is not None and not isinstance(self.stable_key, str):
            raise ValueError("stable_key 必须是文本或空值")
        if not isinstance(self.analysis, BasicAnalysis):
            raise ValueError("analysis 必须是 BasicAnalysis")
        if not isinstance(self.assessment, ProjectAssessment):
            raise ValueError("assessment 必须是 ProjectAssessment")
        if any(not isinstance(item, ProjectFact) for item in self.project_facts):
            raise ValueError("project_facts 的每一项都必须是 ProjectFact")

    @property
    def content(self) -> ContentRecord:
        return self.analysis.content

    @property
    def category(self) -> ContentCategory:
        return self.analysis.category

    @property
    def confidence(self) -> ConfidenceLevel:
        return self.assessment.confidence

    @property
    def fit_reasons(self) -> tuple[ProjectFitReason, ...]:
        return self.assessment.fit_reasons

    @property
    def value_signals(self) -> tuple[CandidateValueSignal, ...]:
        return self.assessment.value_signals

    @property
    def body_benchmark(self) -> str | None:
        return self.assessment.body_benchmark

    @property
    def opening_status(self) -> OpeningTagStatus:
        return self.analysis.opening.status

    @property
    def opening_kind(self) -> OpeningKind | None:
        return self.analysis.opening.kind

    @property
    def opening_fragment(self) -> str | None:
        return self.analysis.opening.fragment

    @property
    def opening_unavailable_reason(self) -> str | None:
        return self.analysis.opening.unavailable_reason

    @property
    def reusable_methods(self) -> tuple[ReusableMethod, ...]:
        return self.analysis.reusable_methods

    @property
    def source_information(self) -> SourceInformation:
        return self.analysis.source_information


@dataclass(frozen=True)
class SavedBusinessState:
    """已保存的业务状态快照；不包含互动值。"""

    project_id: str
    stable_key: str
    candidate_rank: int | None
    is_opportunity: bool
    in_library: bool
    priority: int | None
    cross_project: bool
    conclusion: str
    confidence: ConfidenceLevel
    persona_relative_like: RelativePerformanceLevel | None = None


@dataclass(frozen=True)
class CrossProjectSource:
    """跨项目方法的已入库来源，只保留项目与内容稳定键。"""

    project_id: str
    content_key: str

    def __post_init__(self) -> None:
        if not self.project_id.strip() or not self.content_key.strip():
            raise ValueError("跨项目来源必须包含非空项目和内容稳定键")


@dataclass(frozen=True)
class SavedLibraryRecord:
    """已经持久化到明确项目库的最小稳定记录。"""

    project_id: str
    content_key: str
    reusable_methods: tuple[ReusableMethod, ...]
    source_information: SourceInformation = field(kw_only=True)
    identity_keys: tuple[str, ...] = ()
    available_for_reuse: bool = True
    signals: tuple[CrossProjectSignal, ...] = ()
    scenarios: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_tuple_fields(
            self,
            "reusable_methods",
            "identity_keys",
            "signals",
            "scenarios",
        )
        if any(not isinstance(key, str) or not key.strip() for key in self.identity_keys):
            raise ValueError("已保存内容稳定身份不能为空")
        if type(self.available_for_reuse) is not bool:
            raise ValueError("项目库可复用状态必须是原生布尔值")
        if any(
            not isinstance(signal, CrossProjectSignal) for signal in self.signals
        ):
            raise ValueError("跨项目信号必须使用封闭枚举")
        if any(
            not isinstance(scenario, str) or not scenario.strip()
            for scenario in self.scenarios
        ):
            raise ValueError("跨项目适用场景不能为空")
        if not isinstance(self.source_information, SourceInformation):
            raise ValueError("已保存内容必须保留结构化来源限定信息")


@dataclass(frozen=True)
class OfflineRunInput:
    """离线运行的全部显式输入，不从存储或外部服务隐式读取。"""

    sync_results: tuple[AccountSyncResult, ...]
    relations: tuple[ProjectAccountRelation, ...]
    contexts: tuple[ProjectContextVersion, ...]
    run_at: datetime
    saved_states: tuple[SavedBusinessState, ...] = ()
    saved_library_records: tuple[SavedLibraryRecord, ...] = ()
    persona_baselines: tuple[WeeklyPersonaBaseline, ...] = ()

    def __post_init__(self) -> None:
        _require_tuple_fields(
            self,
            "sync_results",
            "relations",
            "contexts",
            "saved_states",
            "saved_library_records",
            "persona_baselines",
        )


@dataclass(frozen=True)
class CrossProjectCandidate:
    """已在多个项目入库的共同方法，不携带来源限定信息。"""

    method: ReusableMethod
    project_ids: tuple[str, ...]
    sources: tuple[CrossProjectSource, ...] = ()
    scenarios: tuple[str, ...] = ()
    signals: tuple[CrossProjectSignal, ...] = ()
    is_strong: bool = False
    auto_written_project_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_tuple_fields(
            self,
            "project_ids",
            "sources",
            "scenarios",
            "signals",
            "auto_written_project_ids",
        )
        if not isinstance(self.method, ReusableMethod):
            raise ValueError("method 必须是 ReusableMethod")
        expected_types = {
            "project_ids": str,
            "sources": CrossProjectSource,
            "scenarios": str,
            "signals": CrossProjectSignal,
            "auto_written_project_ids": str,
        }
        for field_name, expected_type in expected_types.items():
            if any(
                not isinstance(item, expected_type)
                for item in getattr(self, field_name)
            ):
                raise ValueError(
                    f"{field_name} 的每一项都必须是 {expected_type.__name__}"
                )
        if type(self.is_strong) is not bool:
            raise ValueError("is_strong 必须是原生布尔值")


@dataclass(frozen=True)
class ProjectDailyReport:
    """一个项目和一个上下文版本的独立日报。"""

    project_id: str
    context_version: str
    report_date: date
    summary: str
    daily_overview: DailyOverview
    sync_results: tuple[AccountSyncResult, ...]
    is_empty_daily: bool
    relation_issues: tuple[str, ...]
    data_issues: tuple[str, ...]
    categories: CategoryOverview
    interactions: InteractionOverview
    items: tuple[ReportItem, ...]
    previous_two_day_changes: tuple[ReportItem, ...]
    persona_opportunities: tuple[ReportItem, ...]
    qianchuan_opportunities: tuple[ReportItem, ...]
    library_candidates: tuple[LibraryCandidate, ...]
    cross_project_candidates: tuple[CrossProjectCandidate, ...]
    all_window_items: tuple[ReportItem, ...] = ()
    no_content_summary: "NoContentDailySummary | None" = None

    def __post_init__(self) -> None:
        _require_tuple_fields(
            self,
            "sync_results",
            "relation_issues",
            "data_issues",
            "items",
            "previous_two_day_changes",
            "persona_opportunities",
            "qianchuan_opportunities",
            "library_candidates",
            "cross_project_candidates",
            "all_window_items",
        )
        expected_types = {
            "sync_results": AccountSyncResult,
            "relation_issues": str,
            "data_issues": str,
            "items": ReportItem,
            "previous_two_day_changes": ReportItem,
            "persona_opportunities": ReportItem,
            "qianchuan_opportunities": ReportItem,
            "library_candidates": LibraryCandidate,
            "cross_project_candidates": CrossProjectCandidate,
            "all_window_items": ReportItem,
        }
        for field_name, expected_type in expected_types.items():
            if any(
                not isinstance(item, expected_type)
                for item in getattr(self, field_name)
            ):
                raise ValueError(
                    f"{field_name} 的每一项都必须是 {expected_type.__name__}"
                )
        if not isinstance(self.project_id, str) or not self.project_id.strip():
            raise ValueError("项目日报必须包含项目编号")
        if not isinstance(self.context_version, str) or not self.context_version.strip():
            raise ValueError("项目日报必须包含上下文版本")
        if not isinstance(self.report_date, date):
            raise ValueError("项目日报必须包含报告日期")
        if not isinstance(self.summary, str):
            raise ValueError("项目日报摘要必须是文本")
        if not isinstance(self.daily_overview, DailyOverview):
            raise ValueError("daily_overview 必须是 DailyOverview")
        if type(self.is_empty_daily) is not bool:
            raise ValueError("is_empty_daily 必须是原生布尔值")
        if not isinstance(self.categories, CategoryOverview):
            raise ValueError("categories 必须是 CategoryOverview")
        if not isinstance(self.interactions, InteractionOverview):
            raise ValueError("interactions 必须是 InteractionOverview")
        if self.no_content_summary is not None and not isinstance(
            self.no_content_summary,
            NoContentDailySummary,
        ):
            raise ValueError("no_content_summary 必须使用结构化无内容摘要")
        if self.is_empty_daily != (self.no_content_summary is not None):
            raise ValueError("无内容标记与结构化无内容摘要必须一致")
        if self.no_content_summary is not None:
            receipt = self.no_content_summary
            if self.relation_issues:
                raise ValueError("存在账号关系问题时不能确认无内容日报")
            if not self.sync_results:
                raise ValueError("无内容日报必须保留账号同步结果")
            for sync_result in self.sync_results:
                _validate_daily_sync_contract(sync_result, receipt.coverage_window)
            if any(
                sync_result.status != SyncStatus.SUCCESS_WITHOUT_CONTENT
                for sync_result in self.sync_results
            ):
                raise ValueError("无内容日报同步结果必须全部确认无内容")
            if tuple(item.account_id for item in self.sync_results) != (
                receipt.checked_account_ids
            ):
                raise ValueError("无内容日报已检查账号与同步结果不一致")
            if any(
                item.read_source != receipt.read_source
                for item in self.sync_results
            ):
                raise ValueError("无内容日报读取来源与同步结果不一致")
            if max(item.checked_at for item in self.sync_results) != (
                receipt.read_completed_at
            ):
                raise ValueError("无内容日报读取完成时间与同步结果不一致")
            if self.daily_overview.content_count != 0:
                raise ValueError("无内容日报的当日内容数必须为零")
            category_values = (
                self.categories.persona,
                self.categories.qianchuan,
                self.categories.undetermined,
                self.daily_overview.categories.persona,
                self.daily_overview.categories.qianchuan,
                self.daily_overview.categories.undetermined,
            )
            if any(category_values):
                raise ValueError("无内容日报的分类计数必须全部为零")
            if any(
                (metric.total, metric.missing_count) != (0, 0)
                for overview in (self.interactions, self.daily_overview.interactions)
                for metric in (
                    overview.like_count,
                    overview.comment_count,
                    overview.share_count,
                    overview.favorite_count,
                )
            ):
                raise ValueError("无内容日报的互动计数必须全部为零")
            if any(
                (
                    self.items,
                    self.previous_two_day_changes,
                    self.persona_opportunities,
                    self.qianchuan_opportunities,
                    self.library_candidates,
                )
            ):
                raise ValueError("无内容日报不能携带内容或本次机会")


@dataclass(frozen=True)
class NoContentDailySummary:
    """完整读取成功且项目窗口内零内容时的可追溯结果。"""

    read_succeeded: bool
    read_source: ReadSource
    checked_account_ids: tuple[str, ...]
    coverage_window: SyncCoverageWindow
    read_completed_at: datetime
    content_count: int = 0
    persona_opportunity_count: int = 0
    qianchuan_opportunity_count: int = 0
    library_candidate_count: int = 0
    cross_project_candidate_count: int = 0

    def __post_init__(self) -> None:
        _require_tuple_fields(self, "checked_account_ids")
        if self.read_succeeded is not True:
            raise ValueError("无内容日报只能来自完整读取成功")
        if not isinstance(self.read_source, ReadSource):
            raise ValueError("无内容日报读取来源不受支持")
        if not self.checked_account_ids or any(
            not isinstance(item, str) or not item.strip()
            for item in self.checked_account_ids
        ):
            raise ValueError("无内容日报必须列出已检查账号")
        if len(set(self.checked_account_ids)) != len(self.checked_account_ids):
            raise ValueError("无内容日报不能重复列出已检查账号")
        if not isinstance(self.coverage_window, SyncCoverageWindow):
            raise ValueError("无内容日报必须包含分析窗口")
        if (
            self.read_completed_at.tzinfo is None
            or self.read_completed_at.utcoffset() is None
        ):
            raise ValueError("无内容日报读取完成时间必须带时区")
        counts = (
            self.content_count,
            self.persona_opportunity_count,
            self.qianchuan_opportunity_count,
            self.library_candidate_count,
            self.cross_project_candidate_count,
        )
        if any(type(value) is not int or value != 0 for value in counts):
            raise ValueError("无内容日报的内容和新增机会数量必须全部为零")


@dataclass(frozen=True)
class EngineResult:
    """本轮离线分析结果。"""

    reports: Mapping[str, ProjectDailyReport]
    cross_project_candidates: tuple[CrossProjectCandidate, ...]
    relation_issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_tuple_fields(self, "cross_project_candidates", "relation_issues")
        if any(
            not isinstance(item, CrossProjectCandidate)
            for item in self.cross_project_candidates
        ):
            raise ValueError(
                "cross_project_candidates 的每一项都必须是 CrossProjectCandidate"
            )
        if any(not isinstance(item, str) for item in self.relation_issues):
            raise ValueError("relation_issues 的每一项都必须是 str")
        if not isinstance(self.reports, Mapping):
            raise ValueError("reports 必须是项目日报映射")
        if any(
            not isinstance(project_id, str)
            or not isinstance(report, ProjectDailyReport)
            for project_id, report in self.reports.items()
        ):
            raise ValueError("reports 必须以项目编号映射到项目日报")
        object.__setattr__(self, "reports", MappingProxyType(dict(self.reports)))


def _stable_key(content: ContentRecord) -> str | None:
    keys = _stable_keys(content)
    if not keys:
        return None
    return keys[0]


def _stable_keys(content: ContentRecord) -> tuple[str, ...]:
    return tuple(
        f"{kind}:{value}" for kind, value in content.identity.stable_keys()
    )


def build_cross_project_candidates(
    records: tuple[SavedLibraryRecord, ...],
) -> tuple[CrossProjectCandidate, ...]:
    """只从已入库或本次确定入库的记录计算公司级方法机会。"""
    method_records: dict[
        str, list[tuple[ReusableMethod, SavedLibraryRecord]]
    ] = defaultdict(list)
    for saved_record in records:
        if not saved_record.available_for_reuse:
            continue
        for method in saved_record.reusable_methods:
            if is_reusable_method_safe(method, saved_record.source_information):
                method_records[method.method_key].append((method, saved_record))

    candidates: list[CrossProjectCandidate] = []
    for method_key, method_record_pairs in sorted(method_records.items()):
        method = min(
            (pair[0] for pair in method_record_pairs),
            key=lambda item: (item.name, item.description),
        )
        source_records = tuple(pair[1] for pair in method_record_pairs)
        sources = tuple(
            sorted(
                {
                    CrossProjectSource(record.project_id, record.content_key)
                    for record in source_records
                },
                key=lambda source: (source.project_id, source.content_key),
            )
        )
        project_ids = tuple(sorted({source.project_id for source in sources}))
        scenarios = tuple(
            sorted(
                {
                    scenario
                    for record in source_records
                    for scenario in record.scenarios
                    if not is_source_limited_text(
                        scenario,
                        record.source_information,
                    )
                    and not is_visual_claim(scenario)
                }
            )
        )
        signals = tuple(
            sorted(
                {signal for record in source_records for signal in record.signals},
                key=lambda signal: signal.value,
            )
        )
        is_strong = len(project_ids) >= 2
        if scenarios and (is_strong or len(signals) >= 2):
            candidates.append(
                CrossProjectCandidate(
                    method=method,
                    project_ids=project_ids,
                    sources=sources,
                    scenarios=scenarios,
                    signals=signals,
                    is_strong=is_strong,
                )
            )
    return tuple(candidates)


def _content_run_key(content: ContentRecord, position: int) -> str:
    stable_key = _stable_key(content)
    if stable_key is not None:
        return stable_key
    return (
        f"run:{position}:{content.account_id}:"
        f"{content.published_at.isoformat()}:{content.captured_at.isoformat()}"
    )


def _saved_state_for_item(
    project_id: str,
    item: ReportItem,
    saved_by_key: dict[tuple[str, str], SavedBusinessState],
) -> SavedBusinessState | None:
    matching_states = tuple(
        saved_by_key[(project_id, stable_key)]
        for stable_key in _stable_keys(item.analysis.content)
        if (project_id, stable_key) in saved_by_key
    )
    if not matching_states:
        return None
    normalized_states = tuple(
        replace(state, stable_key=item.stable_key) for state in matching_states
    )
    if any(state != normalized_states[0] for state in normalized_states[1:]):
        raise ValueError(
            f"内容 {item.stable_key or '无稳定编号'} 的稳定别名命中了冲突业务状态"
        )
    return normalized_states[0]


def _metric_summary(contents: Iterable[ContentRecord], field_name: str) -> MetricSummary:
    values = [getattr(content.metrics, field_name) for content in contents]
    return MetricSummary(
        total=sum(value for value in values if value is not None),
        missing_count=sum(value is None for value in values),
    )


def _interactions(contents: tuple[ContentRecord, ...]) -> InteractionOverview:
    return InteractionOverview(
        like_count=_metric_summary(contents, "like_count"),
        comment_count=_metric_summary(contents, "comment_count"),
        share_count=_metric_summary(contents, "share_count"),
        favorite_count=_metric_summary(contents, "favorite_count"),
    )


def _item_sort_key(item: ReportItem) -> tuple[int, int, str]:
    priority = item.assessment.priority
    return (
        priority if priority is not None else 2**31,
        -item.analysis.content.metrics.engagement_total,
        item.stable_key or "",
    )


def _opportunities(
    items: tuple[ReportItem, ...], category: ContentCategory
) -> tuple[ReportItem, ...]:
    eligible = [
        item
        for item in items
        if item.analysis.category == category
        and item.assessment.is_fit
        and item.assessment.is_opportunity
    ]
    return tuple(sorted(eligible, key=_item_sort_key)[:3])


def _relative_persona_like(
    analysis: BasicAnalysis,
    baseline_by_account: dict[str, WeeklyPersonaBaseline],
) -> RelativePerformanceLevel | None:
    if analysis.category != ContentCategory.PERSONA:
        return None
    likes = analysis.content.metrics.like_count
    weekly = baseline_by_account.get(analysis.content.account_id)
    if likes is None or weekly is None:
        return None
    if likes > weekly.baseline.mean:
        return RelativePerformanceLevel.ABOVE
    if likes < weekly.baseline.mean:
        return RelativePerformanceLevel.BELOW
    return RelativePerformanceLevel.NEAR


def _library_candidate(
    item: ReportItem,
    saved_content_keys: set[str],
) -> LibraryCandidate | None:
    content = item.analysis.content
    has_traceable_evidence = bool(
        content.identity.stable_keys()
        and content.transcript
        and content.transcript.strip()
    )
    if (
        item.analysis.category == ContentCategory.UNDETERMINED
        or not item.assessment.is_fit
        or not item.assessment.conclusion.strip()
        or not item.assessment.fit_reasons
        or not item.assessment.value_signals
        or not has_traceable_evidence
        or not item.analysis.topic
        or not item.analysis.topic.strip()
        or not item.analysis.summary
        or (
            item.analysis.category == ContentCategory.QIANCHUAN
            and (
                item.analysis.opening.status
                not in (
                    OpeningTagStatus.AVAILABLE,
                    OpeningTagStatus.UNAVAILABLE,
                )
                or not item.assessment.body_benchmark
                or not item.assessment.body_benchmark.strip()
            )
        )
        or bool(set(_stable_keys(content)) & saved_content_keys)
    ):
        return None
    analysis = item.analysis
    return LibraryCandidate(
        project_id=item.assessment.project_id,
        context_version=item.assessment.context_version,
        run_key=item.run_key,
        stable_key=item.stable_key,
        analysis=analysis,
        assessment=item.assessment,
        project_facts=item.project_facts,
    )


class ContentAnalysisEngine:
    """显式依赖分析器的无存储离线引擎。"""

    def __init__(
        self,
        analyzer: ContentAnalyzer,
        *,
        analyzer_timeout_seconds: float = 120.0,
    ) -> None:
        if type(analyzer_timeout_seconds) not in (int, float) or (
            not isfinite(analyzer_timeout_seconds)
            or analyzer_timeout_seconds <= 0
        ):
            raise ValueError("分析器超时时间必须大于零")
        self._analyzer = analyzer
        self._analyzer_timeout_seconds = float(analyzer_timeout_seconds)

    async def run(
        self,
        run_input: OfflineRunInput,
    ) -> EngineResult:
        windows = derive_windows(run_input.run_at)
        context_by_key: dict[tuple[str, str], ProjectContextVersion] = {}
        context_project_ids: set[str] = set()
        for project_context in run_input.contexts:
            if project_context.project_id in context_project_ids:
                raise ValueError(
                    f"项目 {project_context.project_id} 同时提供了多个上下文版本"
                )
            context_project_ids.add(project_context.project_id)
            context_by_key[(project_context.project_id, project_context.version)] = (
                project_context
            )
        relations_by_project: dict[str, list[ProjectAccountRelation]] = defaultdict(list)
        for item in run_input.relations:
            relations_by_project[item.project_id].append(item)
        scoped_account_ids = {
            relation.account_id
            for relation in run_input.relations
            if (relation.project_id, relation.context_version) in context_by_key
        }

        baseline_by_account: dict[str, WeeklyPersonaBaseline] = {}
        baseline_contract_errors: dict[str, str] = {}
        seen_baseline_account_ids: set[str] = set()
        for weekly in run_input.persona_baselines:
            if weekly.account_id not in scoped_account_ids:
                continue
            if weekly.account_id in seen_baseline_account_ids:
                baseline_by_account.pop(weekly.account_id, None)
                baseline_contract_errors[weekly.account_id] = (
                    f"账号 {weekly.account_id} 存在重复周度人设基准"
                )
                continue
            seen_baseline_account_ids.add(weekly.account_id)
            if weekly.account_id in baseline_contract_errors:
                continue
            if (
                weekly.window_end - weekly.window_start != timedelta(days=30)
                or weekly.window_end > windows.thirty_day_end
            ):
                baseline_contract_errors[weekly.account_id] = (
                    f"账号 {weekly.account_id} 的周度人设基准窗口不匹配"
                )
                continue
            baseline_by_account[weekly.account_id] = weekly
        expected_sync_window = SyncCoverageWindow(
            start=windows.three_day_start,
            end=windows.three_day_end,
        )
        sync_by_account: dict[str, AccountSyncResult] = {}
        sync_contract_errors: dict[str, str] = {}
        seen_sync_account_ids: set[str] = set()
        for sync_result in run_input.sync_results:
            if sync_result.account_id not in scoped_account_ids:
                continue
            if sync_result.account_id in seen_sync_account_ids:
                sync_by_account.pop(sync_result.account_id, None)
                sync_contract_errors[sync_result.account_id] = (
                    f"账号 {sync_result.account_id} 存在重复同步结果"
                )
                continue
            seen_sync_account_ids.add(sync_result.account_id)
            if sync_result.account_id in sync_contract_errors:
                continue
            try:
                _validate_daily_sync_contract(sync_result, expected_sync_window)
            except ValueError as exc:
                sync_contract_errors[sync_result.account_id] = str(exc)
                continue
            sync_by_account[sync_result.account_id] = sync_result
        if sync_contract_errors and not sync_by_account:
            raise ValueError(next(iter(sync_contract_errors.values())))
        current_content_account_ids = {
            account_id
            for account_id, sync_result in sync_by_account.items()
            if sync_result.status
            in (SyncStatus.SUCCESS_WITH_CONTENT, SyncStatus.PARTIAL_SUCCESS)
        }
        successful_records_by_account = {
            account_id: sync_result.contents
            for account_id, sync_result in sync_by_account.items()
        }
        daily_records_by_account = {
            account_id: tuple(
                content
                for content in records
                if windows.three_day_start
                <= content.published_at
                < windows.three_day_end
            )
            for account_id, records in successful_records_by_account.items()
        }
        accounts_by_stable_key: dict[tuple[str, str], set[str]] = defaultdict(set)
        for records in daily_records_by_account.values():
            for content in records:
                for stable_key in content.identity.stable_keys():
                    accounts_by_stable_key[stable_key].add(content.account_id)
        conflicting_stable_keys = {
            stable_key
            for stable_key, account_ids in accounts_by_stable_key.items()
            if len(account_ids) > 1
        }
        identity_conflict_counts: Counter[str] = Counter()
        analysis_daily_records_by_account: dict[str, tuple[ContentRecord, ...]] = {}
        for account_id, records in daily_records_by_account.items():
            safe_records: list[ContentRecord] = []
            for content in records:
                if any(
                    stable_key in conflicting_stable_keys
                    for stable_key in content.identity.stable_keys()
                ):
                    identity_conflict_counts[account_id] += 1
                    continue
                safe_records.append(content)
            analysis_daily_records_by_account[account_id] = tuple(safe_records)
        all_contents = [
            content
            for account_id, sync_result in sync_by_account.items()
            if account_id in scoped_account_ids
            for content in analysis_daily_records_by_account[account_id]
            if sync_result.status != SyncStatus.FAILED
            and not (
                sync_result.status == SyncStatus.SUCCESS_WITHOUT_CONTENT
                and content.published_at >= windows.three_day_start
            )
            and windows.three_day_start
            <= content.published_at
            < windows.three_day_end
        ]
        deduplicated = deduplicate_contents(all_contents)
        content_entries = tuple(
            (_content_run_key(content, position), content)
            for position, content in enumerate(deduplicated, start=1)
        )
        analyses_by_run_key: dict[str, BasicAnalysis] = {}
        analysis_failures_by_run_key: dict[str, str] = {}
        analyses: list[BasicAnalysis] = []
        for run_key, content in content_entries:
            try:
                if not (content.transcript and content.transcript.strip()):
                    analysis = BasicAnalysis(
                        content=content,
                        category=ContentCategory.UNDETERMINED,
                        confidence=ConfidenceLevel.LOW,
                        opening=OpeningAnnotation(
                            status=OpeningTagStatus.UNAVAILABLE,
                            kind=OpeningKind.LANGUAGE,
                            unavailable_reason="缺少转写，无法判断语言开头",
                        ),
                        source_information=SourceInformation(
                            limitations=(
                                SourceLimitation(
                                    "缺少转写，本期不做结构化内容分析"
                                ),
                            ),
                        ),
                        undetermined_reason="缺少转写，本期不做结构化内容分析",
                    )
                else:
                    raw_analysis = await asyncio.wait_for(
                        self._analyzer.analyze_content(content),
                        timeout=self._analyzer_timeout_seconds,
                    )
                    if not isinstance(raw_analysis, BasicAnalysis):
                        raise ValueError("基础分析器返回类型无效")
                    if raw_analysis.content != content:
                        raw_analysis = replace(raw_analysis, content=content)
                    analysis = enforce_analysis_boundaries(raw_analysis)
                maturity = derive_data_maturity(
                    content.published_at,
                    content.captured_at,
                )
                relative_like = _relative_persona_like(
                    analysis,
                    baseline_by_account,
                )
                deterministic_observations = tuple(
                    observation
                    for observation in analysis.interaction_observations
                    if observation.observation_type
                    not in (
                        InteractionObservationType.DATA_MATURITY,
                        InteractionObservationType.CURRENT_RELATIVE_PERFORMANCE,
                    )
                ) + (
                    InteractionObservation(
                        InteractionObservationType.DATA_MATURITY,
                        maturity=maturity,
                    ),
                )
                if relative_like is not None:
                    weekly = baseline_by_account[content.account_id]
                    deterministic_observations += (
                        InteractionObservation(
                            InteractionObservationType.CURRENT_RELATIVE_PERFORMANCE,
                            metric=InteractionMetric.LIKE,
                            relative_level=relative_like,
                            benchmark_value=weekly.baseline.mean,
                            sample_size=weekly.baseline.sample_size,
                        ),
                    )
                analysis = replace(
                    analysis,
                    data_maturity=maturity,
                    interaction_observations=deterministic_observations,
                )
            except Exception as exc:
                analysis_failures_by_run_key[run_key] = type(exc).__name__
                continue
            analyses_by_run_key[run_key] = analysis
            analyses.append(analysis)

        qianchuan_pool_by_account = qianchuan_top_three(
            (
                analysis
                for analysis in analyses
                if analysis.content.account_id in current_content_account_ids
            ),
            windows.three_day_start,
            windows.three_day_end,
        )
        available_run_keys_by_content: dict[ContentRecord, list[str]] = defaultdict(list)
        for run_key, analysis in analyses_by_run_key.items():
            available_run_keys_by_content[analysis.content].append(run_key)
        qianchuan_rank_by_run_key: dict[str, int] = {}
        for contents in qianchuan_pool_by_account.values():
            for rank, content in enumerate(contents, start=1):
                run_key = available_run_keys_by_content[content].pop(0)
                qianchuan_rank_by_run_key[run_key] = rank
        qianchuan_pool_run_keys = set(qianchuan_rank_by_run_key)

        project_items: dict[str, tuple[ReportItem, ...]] = {}
        project_syncs: dict[str, tuple[AccountSyncResult, ...]] = {}
        project_relation_issues: dict[str, tuple[str, ...]] = {}
        project_data_issues: dict[str, tuple[str, ...]] = {}
        project_empty_daily_eligible: dict[str, bool] = {}
        global_relation_issues: list[str] = []
        skipped_project_ids: set[str] = set()

        for (project_id, version), project_context in context_by_key.items():
            matching_relations = [
                item
                for item in relations_by_project.get(project_id, ())
                if item.context_version == version
            ]
            if not matching_relations:
                global_relation_issues.append(
                    f"项目 {project_id}（{version}）没有账号关系"
                )
                skipped_project_ids.add(project_id)
                continue
            matched_syncs: list[AccountSyncResult] = []
            relation_issues: list[str] = []
            data_issues: list[str] = []
            account_ids: set[str] = set()
            for relation in matching_relations:
                if relation.account_id in baseline_contract_errors:
                    data_issues.append(baseline_contract_errors[relation.account_id])
                if relation.account_id in sync_contract_errors:
                    data_issues.append(
                        f"账号 {relation.account_id} 同步合同无效，未使用其内容："
                        f"{sync_contract_errors[relation.account_id]}"
                    )
                    continue
                conflict_count = identity_conflict_counts[relation.account_id]
                if conflict_count:
                    data_issues.append(
                        f"账号 {relation.account_id} 有 {conflict_count} 条稳定内容身份"
                        "与其他账号冲突，冲突内容未分析"
                    )
                sync_result = sync_by_account.get(relation.account_id)
                if sync_result is None:
                    issue = f"账号关系 {relation.account_id} 没有精确匹配的同步结果"
                    relation_issues.append(issue)
                    global_relation_issues.append(issue)
                    continue
                if relation.account_id not in account_ids:
                    safe_contents = daily_records_by_account[relation.account_id]
                    matched_syncs.append(
                        replace(sync_result, contents=())
                        if sync_result.status
                        in (SyncStatus.FAILED, SyncStatus.SUCCESS_WITHOUT_CONTENT)
                        else replace(
                            sync_result,
                            contents=safe_contents,
                        )
                    )
                    account_ids.add(relation.account_id)
                    if sync_result.status == SyncStatus.FAILED:
                        failure_reason = (
                            sync_result.issue.reason
                            if sync_result.issue and sync_result.issue.reason
                            else "内容源读取失败"
                        )
                        data_issues.append(
                            f"账号 {relation.account_id} 读取失败，未使用其内容："
                            f"{failure_reason}"
                        )
                    elif sync_result.status == SyncStatus.PARTIAL_SUCCESS:
                        data_issues.append(
                            f"账号 {relation.account_id} 部分同步成功，当前内容可能不完整"
                        )
            missing_fields = [
                field_name
                for field_name in (
                    "project_persona",
                    "target_users",
                    "content_plan",
                    "operating_direction",
                )
                if not getattr(project_context, field_name).strip()
            ]
            if missing_fields:
                data_issues.append("项目资料缺失：" + "、".join(missing_fields))

            items: list[ReportItem] = []
            for run_key, content in content_entries:
                if content.account_id not in account_ids:
                    continue
                if run_key in analysis_failures_by_run_key:
                    data_issues.append(
                        "内容 "
                        f"{_stable_key(content) or '无稳定编号'} 基础分析失败："
                        f"{analysis_failures_by_run_key[run_key]}"
                    )
                    continue
                analysis = analyses_by_run_key[run_key]
                try:
                    if not (
                        analysis.content.transcript
                        and analysis.content.transcript.strip()
                    ):
                        assessment = ProjectAssessment(
                            project_id=project_id,
                            context_version=version,
                            is_fit=False,
                            is_opportunity=False,
                            confidence=ConfidenceLevel.LOW,
                            conclusion="缺少转写，无法完成项目适配判断",
                            limitations=("缺少转写，本期不做结构化内容分析",),
                        )
                    else:
                        raw_assessment = await asyncio.wait_for(
                            self._analyzer.assess_project(
                                analysis,
                                project_context,
                            ),
                            timeout=self._analyzer_timeout_seconds,
                        )
                        if not isinstance(raw_assessment, ProjectAssessment):
                            raise ValueError("项目判断器返回类型无效")
                        assessment = replace(
                            raw_assessment,
                            project_id=project_id,
                            context_version=version,
                        )
                        assessment = enforce_project_assessment_boundaries(
                            assessment,
                            analysis,
                        )
                    if missing_fields and assessment.confidence in (
                        ConfidenceLevel.HIGH,
                        ConfidenceLevel.MEDIUM,
                    ):
                        assessment = replace(
                            assessment,
                            confidence=ConfidenceLevel.LOW,
                        )
                except Exception as exc:
                    data_issues.append(
                        "内容 "
                        f"{_stable_key(content) or '无稳定编号'} 项目判断失败："
                        f"{type(exc).__name__}"
                    )
                    continue
                if assessment.confidence in (
                    ConfidenceLevel.LOW,
                    ConfidenceLevel.UNVERIFIED,
                ):
                    data_issues.append(
                        f"内容 {_stable_key(content) or '无稳定编号'} 的项目判断可信程度较低"
                    )
                items.append(
                    ReportItem(
                        run_key=run_key,
                        stable_key=_stable_key(content),
                        analysis=analysis,
                        assessment=assessment,
                        project_facts=project_context.confirmed_facts,
                        persona_relative_like=_relative_persona_like(
                            analysis,
                            baseline_by_account,
                        ),
                    )
                )
            project_items[project_id] = tuple(items)
            project_syncs[project_id] = tuple(matched_syncs)
            project_relation_issues[project_id] = tuple(relation_issues)
            project_data_issues[project_id] = tuple(dict.fromkeys(data_issues))
            related_account_ids = {
                relation.account_id for relation in matching_relations
            }
            project_empty_daily_eligible[project_id] = (
                not relation_issues
                and not (related_account_ids & set(sync_contract_errors))
                and account_ids == related_account_ids
            )

        scoped_saved_library_records = tuple(run_input.saved_library_records)
        saved_content_keys_by_project: dict[str, set[str]] = defaultdict(set)
        reusable_saved_content_keys_by_project: dict[str, set[str]] = defaultdict(set)
        for saved_record in scoped_saved_library_records:
            identity_keys = (saved_record.content_key, *saved_record.identity_keys)
            saved_content_keys_by_project[saved_record.project_id].update(identity_keys)
            if saved_record.available_for_reuse:
                reusable_saved_content_keys_by_project[saved_record.project_id].update(
                    identity_keys
                )

        cross_project_candidates = build_cross_project_candidates(
            scoped_saved_library_records
        )
        cross_method_keys_by_project: dict[str, set[str]] = defaultdict(set)
        for candidate in cross_project_candidates:
            for project_id in candidate.project_ids:
                cross_method_keys_by_project[project_id].add(
                    candidate.method.method_key
                )

        saved_by_key: dict[tuple[str, str], SavedBusinessState] = {}
        conflicting_saved_state_keys: set[tuple[str, str]] = set()
        for state in run_input.saved_states:
            key = (state.project_id, state.stable_key)
            if key in conflicting_saved_state_keys:
                continue
            previous = saved_by_key.get(key)
            if previous is None:
                saved_by_key[key] = state
            elif previous != state:
                saved_by_key.pop(key)
                conflicting_saved_state_keys.add(key)
        conflicting_saved_state_projects = {
            project_id for project_id, _stable_key_value in conflicting_saved_state_keys
        }
        reports: dict[str, ProjectDailyReport] = {}
        report_start = windows.three_day_end - timedelta(days=1)
        for (project_id, version), _project_context in context_by_key.items():
            if project_id in skipped_project_ids:
                continue
            all_items = project_items.get(project_id, ())
            report_data_issues = list(project_data_issues.get(project_id, ()))
            three_day_items = tuple(
                item
                for item in all_items
                if windows.three_day_start
                <= item.analysis.content.published_at
                < windows.three_day_end
                and item.analysis.content.account_id in current_content_account_ids
            )
            current_items = tuple(
                item
                for item in three_day_items
                if report_start <= item.analysis.content.published_at < windows.three_day_end
            )
            previous_items = tuple(
                item
                for item in three_day_items
                if windows.three_day_start
                <= item.analysis.content.published_at
                < report_start
            )
            calculated_persona_opportunities = _opportunities(
                three_day_items, ContentCategory.PERSONA
            )
            calculated_qianchuan_opportunities = _opportunities(
                tuple(
                    item
                    for item in three_day_items
                    if item.run_key in qianchuan_pool_run_keys
                ),
                ContentCategory.QIANCHUAN,
            )
            opportunity_run_keys = {
                item.run_key
                for item in (
                    calculated_persona_opportunities
                    + calculated_qianchuan_opportunities
                )
            }
            project_library_candidates = tuple(
                candidate
                for item in three_day_items
                if item.run_key in opportunity_run_keys
                for candidate in (
                    _library_candidate(
                        item,
                        saved_content_keys_by_project.get(project_id, set()),
                    ),
                )
                if candidate is not None
            )
            ranks = {
                item.run_key: rank
                for rank, item in enumerate(
                    calculated_persona_opportunities, start=1
                )
            }
            ranks.update(
                {
                    item.run_key: qianchuan_rank_by_run_key[item.run_key]
                    for item in three_day_items
                    if item.run_key in qianchuan_rank_by_run_key
                }
            )
            library_keys = {
                candidate.stable_key for candidate in project_library_candidates
            } | reusable_saved_content_keys_by_project.get(project_id, set())
            enriched_by_run_key = {}
            for item in three_day_items:
                identity_keys = set(_stable_keys(item.analysis.content))
                method_keys = {
                    method.method_key for method in item.analysis.reusable_methods
                }
                is_in_library = bool(identity_keys & library_keys)
                enriched_by_run_key[item.run_key] = replace(
                    item,
                    candidate_rank=ranks.get(item.run_key),
                    is_opportunity=item.run_key in opportunity_run_keys,
                    in_library=is_in_library,
                    cross_project=is_in_library
                    and bool(
                        method_keys
                        & cross_method_keys_by_project.get(project_id, set())
                    ),
                )
            three_day_items = tuple(
                enriched_by_run_key[item.run_key] for item in three_day_items
            )
            current_items = tuple(
                enriched_by_run_key[item.run_key] for item in current_items
            )
            previous_items = tuple(
                enriched_by_run_key[item.run_key] for item in previous_items
            )
            calculated_persona_opportunities = tuple(
                enriched_by_run_key[item.run_key]
                for item in calculated_persona_opportunities
            )
            calculated_qianchuan_opportunities = tuple(
                enriched_by_run_key[item.run_key]
                for item in calculated_qianchuan_opportunities
            )
            changed_previous: list[ReportItem] = []
            for item in previous_items:
                if item.stable_key is None:
                    continue
                try:
                    old_state = _saved_state_for_item(project_id, item, saved_by_key)
                except ValueError as exc:
                    report_data_issues.append(str(exc))
                    continue
                if old_state is None:
                    continue
                current_state = SavedBusinessState(
                    project_id=project_id,
                    stable_key=item.stable_key,
                    candidate_rank=item.candidate_rank,
                    is_opportunity=item.is_opportunity,
                    in_library=item.in_library,
                    priority=item.assessment.priority,
                    cross_project=item.cross_project,
                    conclusion=item.assessment.conclusion,
                    confidence=item.assessment.confidence,
                    persona_relative_like=item.persona_relative_like,
                )
                if current_state != old_state:
                    changed_previous.append(item)

            display_items = current_items + tuple(changed_previous)
            display_run_keys = {item.run_key for item in display_items}
            persona_opportunities = tuple(
                item
                for item in calculated_persona_opportunities
                if item.run_key in display_run_keys
            )
            qianchuan_opportunities = tuple(
                item
                for item in calculated_qianchuan_opportunities
                if item.run_key in display_run_keys
            )
            library_candidates = project_library_candidates

            category_counts = Counter(item.analysis.category for item in current_items)
            current_contents = tuple(item.analysis.content for item in current_items)
            matched_syncs = project_syncs.get(project_id, ())
            relation_issues = project_relation_issues.get(project_id, ())
            has_window_content = bool(three_day_items)
            is_empty_daily = (
                bool(matched_syncs)
                and not relation_issues
                and project_empty_daily_eligible.get(project_id, False)
                and not has_window_content
                and all(
                    item.status == SyncStatus.SUCCESS_WITHOUT_CONTENT
                    for item in matched_syncs
                )
            )
            no_content_summary = None
            if is_empty_daily:
                read_sources = {item.read_source for item in matched_syncs}
                if len(read_sources) != 1:
                    is_empty_daily = False
                    report_data_issues.append(
                        "同一项目无内容结果混用多个读取来源，不能确认无内容"
                    )
                else:
                    no_content_summary = NoContentDailySummary(
                        read_succeeded=True,
                        read_source=next(iter(read_sources)),
                        checked_account_ids=tuple(
                            item.account_id for item in matched_syncs
                        ),
                        coverage_window=expected_sync_window,
                        read_completed_at=max(
                            item.checked_at for item in matched_syncs if item.checked_at
                        ),
                    )
            categories = CategoryOverview(
                persona=category_counts[ContentCategory.PERSONA],
                qianchuan=category_counts[ContentCategory.QIANCHUAN],
                undetermined=category_counts[ContentCategory.UNDETERMINED],
            )
            interactions = _interactions(current_contents)
            daily_overview = DailyOverview(
                content_count=len(current_items),
                categories=categories,
                interactions=interactions,
            )
            reports[project_id] = ProjectDailyReport(
                project_id=project_id,
                context_version=version,
                report_date=windows.report_date,
                summary=(
                    (
                        f"{'飞书' if no_content_summary.read_source == ReadSource.FEISHU else '内容源'}"
                        "读取成功；发布内容 0 条，人设机会 0 条，千川机会 0 条，"
                        "内容库新增 0 条，跨项目机会新增 0 条"
                    )
                    if no_content_summary is not None
                    else (
                        f"当日 {len(current_items)} 条，前两天变化 {len(changed_previous)} 条；"
                        f"人设机会 {len(persona_opportunities)} 条，"
                        f"千川机会 {len(qianchuan_opportunities)} 条"
                    )
                ),
                daily_overview=daily_overview,
                sync_results=matched_syncs,
                is_empty_daily=is_empty_daily,
                relation_issues=relation_issues,
                data_issues=tuple(
                    dict.fromkeys(
                        tuple(report_data_issues)
                        + (
                            ("历史业务状态冲突：同一内容有多份不同状态，已跳过前两天变化比较",)
                            if project_id in conflicting_saved_state_projects
                            else ()
                        )
                    )
                ),
                categories=categories,
                interactions=interactions,
                items=display_items,
                previous_two_day_changes=tuple(changed_previous),
                persona_opportunities=persona_opportunities,
                qianchuan_opportunities=qianchuan_opportunities,
                library_candidates=library_candidates,
                cross_project_candidates=(
                    ()
                    if no_content_summary is not None
                    else tuple(
                        candidate
                        for candidate in cross_project_candidates
                        if project_id in candidate.project_ids
                    )
                ),
                all_window_items=three_day_items,
                no_content_summary=no_content_summary,
            )

        return EngineResult(
            reports=reports,
            cross_project_candidates=cross_project_candidates,
            relation_issues=tuple(global_relation_issues),
        )
