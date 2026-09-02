"""内容分析阶段一的项目隔离离线编排。"""
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Iterable

from .analyzer import ContentAnalyzer, ProjectAssessment, enforce_analysis_boundaries
from .deterministic import deduplicate_contents, derive_windows
from .domain import (
    BasicAnalysis,
    ConfidenceLevel,
    ContentCategory,
    ContentRecord,
    OpeningTagStatus,
    ProjectAccountRelation,
    ProjectContextVersion,
    ProjectFact,
    ReusableMethod,
    SourceInformation,
    SyncStatus,
)


@dataclass(frozen=True)
class AccountSyncResult:
    """单个稳定账号的一次同步结果。"""

    account_id: str
    status: SyncStatus
    contents: tuple[ContentRecord, ...] = ()
    issue: str | None = None

    def __post_init__(self) -> None:
        if any(content.account_id != self.account_id for content in self.contents):
            raise ValueError("同步结果不能包含其他账号的内容")


@dataclass(frozen=True)
class MetricSummary:
    """单项互动的已知总数和缺失条数。"""

    total: int
    missing_count: int


@dataclass(frozen=True)
class InteractionOverview:
    """仅保留四项当前互动值，不派生播放率或趋势。"""

    like_count: MetricSummary
    comment_count: MetricSummary
    share_count: MetricSummary
    favorite_count: MetricSummary


@dataclass(frozen=True)
class CategoryOverview:
    """当日报告内容的三分类计数。"""

    persona: int
    qianchuan: int
    undetermined: int


@dataclass(frozen=True)
class ReportItem:
    """一条经过项目盖章的日报内容。"""

    stable_key: str | None
    analysis: BasicAnalysis
    assessment: ProjectAssessment
    project_facts: tuple[ProjectFact, ...]


@dataclass(frozen=True)
class LibraryCandidate:
    """项目内容库候选；千川正文与开头信息保持原子绑定。"""

    project_id: str
    context_version: str
    stable_key: str
    content: ContentRecord
    category: ContentCategory
    confidence: ConfidenceLevel
    body_benchmark: str | None
    opening_status: OpeningTagStatus
    opening_fragment: str | None
    opening_unavailable_reason: str | None
    reusable_methods: tuple[ReusableMethod, ...]
    source_information: SourceInformation


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


@dataclass(frozen=True)
class CrossProjectCandidate:
    """已在多个项目入库的共同方法，不携带来源限定信息。"""

    method: ReusableMethod
    project_ids: tuple[str, ...]
    auto_written_project_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectDailyReport:
    """一个项目和一个上下文版本的独立日报。"""

    project_id: str
    context_version: str
    report_date: date
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


@dataclass(frozen=True)
class EngineResult:
    """本轮离线分析结果。"""

    reports: dict[str, ProjectDailyReport]
    cross_project_candidates: tuple[CrossProjectCandidate, ...]


def _stable_key(content: ContentRecord) -> str | None:
    keys = content.identity.stable_keys()
    if not keys:
        return None
    kind, value = keys[0]
    return f"{kind}:{value}"


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
        if item.analysis.category == category and item.assessment.is_opportunity
    ]
    return tuple(sorted(eligible, key=_item_sort_key)[:3])


def _library_candidate(item: ReportItem) -> LibraryCandidate | None:
    if (
        item.analysis.category == ContentCategory.UNDETERMINED
        or not item.assessment.should_add_to_library
        or item.stable_key is None
    ):
        return None
    analysis = item.analysis
    return LibraryCandidate(
        project_id=item.assessment.project_id,
        context_version=item.assessment.context_version,
        stable_key=item.stable_key,
        content=analysis.content,
        category=analysis.category,
        confidence=item.assessment.confidence,
        body_benchmark=item.assessment.body_benchmark,
        opening_status=analysis.opening.status,
        opening_fragment=analysis.opening.fragment,
        opening_unavailable_reason=analysis.opening.unavailable_reason,
        reusable_methods=analysis.source_information.reusable_methods,
        source_information=analysis.source_information,
    )


class ContentAnalysisEngine:
    """显式依赖分析器的无存储离线引擎。"""

    def __init__(self, analyzer: ContentAnalyzer) -> None:
        self._analyzer = analyzer

    async def run(
        self,
        *,
        sync_results: Iterable[AccountSyncResult],
        relations: Iterable[ProjectAccountRelation],
        contexts: Iterable[ProjectContextVersion],
        run_at: datetime,
        saved_states: Iterable[SavedBusinessState] = (),
    ) -> EngineResult:
        windows = derive_windows(run_at)
        sync_by_account: dict[str, AccountSyncResult] = {}
        for sync_result in sync_results:
            if sync_result.account_id in sync_by_account:
                raise ValueError(f"账号 {sync_result.account_id} 存在重复同步结果")
            sync_by_account[sync_result.account_id] = sync_result

        context_by_key = {
            (project_context.project_id, project_context.version): project_context
            for project_context in contexts
        }
        relations_by_project: dict[str, list[ProjectAccountRelation]] = defaultdict(list)
        for item in relations:
            relations_by_project[item.project_id].append(item)

        all_contents = [
            content
            for sync_result in sync_by_account.values()
            for content in sync_result.contents
            if windows.thirty_day_start <= content.published_at < windows.thirty_day_end
        ]
        deduplicated = deduplicate_contents(all_contents)
        analyses_by_object: dict[int, BasicAnalysis] = {}
        for content in deduplicated:
            raw_analysis = await self._analyzer.analyze_content(content)
            if raw_analysis.content != content:
                raw_analysis = replace(raw_analysis, content=content)
            analyses_by_object[id(content)] = enforce_analysis_boundaries(raw_analysis)

        project_items: dict[str, tuple[ReportItem, ...]] = {}
        project_syncs: dict[str, tuple[AccountSyncResult, ...]] = {}
        project_relation_issues: dict[str, tuple[str, ...]] = {}
        project_data_issues: dict[str, tuple[str, ...]] = {}

        for (project_id, version), project_context in context_by_key.items():
            matching_relations = [
                item
                for item in relations_by_project.get(project_id, ())
                if item.context_version == version
            ]
            matched_syncs: list[AccountSyncResult] = []
            relation_issues: list[str] = []
            data_issues: list[str] = []
            account_ids: set[str] = set()
            for relation in matching_relations:
                sync_result = sync_by_account.get(relation.account_id)
                if sync_result is None:
                    relation_issues.append(
                        f"账号关系 {relation.account_id} 没有精确匹配的同步结果"
                    )
                    continue
                if relation.account_id not in account_ids:
                    matched_syncs.append(sync_result)
                    account_ids.add(relation.account_id)

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
            for content in deduplicated:
                if content.account_id not in account_ids:
                    continue
                analysis = analyses_by_object[id(content)]
                raw_assessment = await self._analyzer.assess_project(
                    analysis, project_context
                )
                assessment = replace(
                    raw_assessment,
                    project_id=project_id,
                    context_version=version,
                )
                if assessment.confidence in (
                    ConfidenceLevel.LOW,
                    ConfidenceLevel.UNVERIFIED,
                ):
                    data_issues.append(
                        f"内容 {_stable_key(content) or '无稳定编号'} 的项目判断可信程度较低"
                    )
                items.append(
                    ReportItem(
                        stable_key=_stable_key(content),
                        analysis=analysis,
                        assessment=assessment,
                        project_facts=project_context.confirmed_facts,
                    )
                )
            project_items[project_id] = tuple(items)
            project_syncs[project_id] = tuple(matched_syncs)
            project_relation_issues[project_id] = tuple(relation_issues)
            project_data_issues[project_id] = tuple(dict.fromkeys(data_issues))

        library_by_project: dict[str, tuple[LibraryCandidate, ...]] = {}
        method_projects: dict[ReusableMethod, set[str]] = defaultdict(set)
        for project_id, items in project_items.items():
            recent_items = (
                item
                for item in items
                if windows.three_day_start
                <= item.analysis.content.published_at
                < windows.three_day_end
            )
            candidates = tuple(
                candidate
                for candidate in (_library_candidate(item) for item in recent_items)
                if candidate is not None
            )
            library_by_project[project_id] = candidates
            for candidate in candidates:
                for method in candidate.reusable_methods:
                    method_projects[method].add(project_id)

        cross_project_candidates = tuple(
            CrossProjectCandidate(method=method, project_ids=tuple(sorted(project_ids)))
            for method, project_ids in sorted(
                method_projects.items(), key=lambda pair: (pair[0].name, pair[0].description)
            )
            if len(project_ids) >= 2
        )
        cross_methods_by_project: dict[str, set[ReusableMethod]] = defaultdict(set)
        for candidate in cross_project_candidates:
            for project_id in candidate.project_ids:
                cross_methods_by_project[project_id].add(candidate.method)

        saved_by_key = {
            (state.project_id, state.stable_key): state for state in saved_states
        }
        reports: dict[str, ProjectDailyReport] = {}
        report_start = windows.three_day_end - timedelta(days=1)
        for (project_id, version), _project_context in context_by_key.items():
            all_items = project_items.get(project_id, ())
            three_day_items = tuple(
                item
                for item in all_items
                if windows.three_day_start
                <= item.analysis.content.published_at
                < windows.three_day_end
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
            persona_opportunities = _opportunities(three_day_items, ContentCategory.PERSONA)
            qianchuan_opportunities = _opportunities(
                three_day_items, ContentCategory.QIANCHUAN
            )
            ranks = {
                id(item): rank
                for opportunities in (persona_opportunities, qianchuan_opportunities)
                for rank, item in enumerate(opportunities, start=1)
            }
            library_keys = {
                candidate.stable_key for candidate in library_by_project.get(project_id, ())
            }
            changed_previous: list[ReportItem] = []
            for item in previous_items:
                if item.stable_key is None:
                    continue
                old_state = saved_by_key.get((project_id, item.stable_key))
                if old_state is None:
                    continue
                reusable_methods = set(item.analysis.source_information.reusable_methods)
                current_state = SavedBusinessState(
                    project_id=project_id,
                    stable_key=item.stable_key,
                    candidate_rank=ranks.get(id(item)),
                    is_opportunity=item.assessment.is_opportunity,
                    in_library=item.stable_key in library_keys,
                    priority=item.assessment.priority,
                    cross_project=bool(
                        reusable_methods & cross_methods_by_project.get(project_id, set())
                    ),
                    conclusion=item.assessment.conclusion,
                    confidence=item.assessment.confidence,
                )
                if current_state != old_state:
                    changed_previous.append(item)

            category_counts = Counter(item.analysis.category for item in current_items)
            current_contents = tuple(item.analysis.content for item in current_items)
            matched_syncs = project_syncs.get(project_id, ())
            relation_issues = project_relation_issues.get(project_id, ())
            has_window_content = bool(three_day_items)
            is_empty_daily = (
                bool(matched_syncs)
                and not relation_issues
                and not has_window_content
                and all(
                    item.status == SyncStatus.SUCCESS_WITHOUT_CONTENT
                    for item in matched_syncs
                )
            )
            reports[project_id] = ProjectDailyReport(
                project_id=project_id,
                context_version=version,
                report_date=windows.report_date,
                sync_results=matched_syncs,
                is_empty_daily=is_empty_daily,
                relation_issues=relation_issues,
                data_issues=project_data_issues.get(project_id, ()),
                categories=CategoryOverview(
                    persona=category_counts[ContentCategory.PERSONA],
                    qianchuan=category_counts[ContentCategory.QIANCHUAN],
                    undetermined=category_counts[ContentCategory.UNDETERMINED],
                ),
                interactions=_interactions(current_contents),
                items=current_items + tuple(changed_previous),
                previous_two_day_changes=tuple(changed_previous),
                persona_opportunities=persona_opportunities,
                qianchuan_opportunities=qianchuan_opportunities,
                library_candidates=library_by_project.get(project_id, ()),
            )

        return EngineResult(
            reports=reports,
            cross_project_candidates=cross_project_candidates,
        )
