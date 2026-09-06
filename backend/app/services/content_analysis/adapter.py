"""外部字段到内容分析稳定语义的纯内存适配层。"""
from collections.abc import Mapping, Sequence
from datetime import datetime
from math import isfinite
from typing import Any, TypeVar

from .domain import (
    AnalysisEvidence,
    ConfidenceLevel,
    ContentIdentity,
    ContentRecord,
    ContentSource,
    EngagementMetrics,
    EvidenceType,
    LikeBaseline,
    ProjectAccountRelation,
    ProjectContextVersion,
    ProjectFact,
    RelativePerformanceLevel,
    ReusableMethod,
    SourceAssumption,
    SourceConstraint,
    SourceFact,
    SourceFactKind,
    SourceInformation,
    SourceJudgment,
    SourceLimitation,
    SyncStatus,
    WeeklyPersonaBaseline,
)
from .engine import (
    AccountSyncResult,
    CrossProjectSignal,
    OfflineRunInput,
    ReadSource,
    SavedBusinessState,
    SavedLibraryRecord,
    SyncCoverageWindow,
    SyncIssue,
    SyncIssueImpact,
)


EnumType = TypeVar("EnumType")


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} 必须是对象")
    return value


def _sequence(value: object, field_name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field_name} 必须是列表")
    return value


def _required(data: Mapping[str, Any], field_name: str) -> Any:
    if field_name not in data:
        raise ValueError(f"缺少字段 {field_name}")
    return data[field_name]


def _text(value: object, field_name: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空文本")
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} 必须是文本")
    return value


def _timestamp(value: object, field_name: str) -> datetime:
    text = _text(value, field_name)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} 不是合法时间") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} 必须带时区")
    return parsed


def _enum(enum_type: type[EnumType], value: object, field_name: str) -> EnumType:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} 必须是枚举文本")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} 不受支持") from exc


def _boolean(value: object, field_name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{field_name} 必须是布尔值")
    return value


def _integer(
    value: object,
    field_name: str,
    *,
    optional: bool = False,
    positive: bool = False,
) -> int | None:
    if value is None and optional:
        return None
    if type(value) is not int or value < (1 if positive else 0):
        qualifier = "正整数" if positive else "非负整数"
        raise ValueError(f"{field_name} 必须是{qualifier}")
    return value


def _number(value: object, field_name: str) -> float:
    if type(value) not in (int, float) or not isfinite(value) or value < 0:
        raise ValueError(f"{field_name} 必须是非负数")
    return float(value)


def _content(data: Mapping[str, Any]) -> ContentRecord:
    identity_data = _mapping(_required(data, "identity"), "identity")
    platform_content_id = _text(
        identity_data.get("platform_content_id"),
        "identity.platform_content_id",
        optional=True,
    )
    external_url = _text(
        identity_data.get("external_url"),
        "identity.external_url",
        optional=True,
    )
    metrics_data = _mapping(_required(data, "metrics"), "metrics")
    metrics = EngagementMetrics(
        like_count=_required(metrics_data, "like_count"),
        comment_count=_required(metrics_data, "comment_count"),
        share_count=_required(metrics_data, "share_count"),
        favorite_count=_required(metrics_data, "favorite_count"),
        play_count=metrics_data.get("play_count"),
    )
    return ContentRecord(
        account_id=_text(_required(data, "account_id"), "account_id"),
        source=_enum(ContentSource, _required(data, "source"), "source"),
        identity=ContentIdentity(
            platform_content_id=platform_content_id,
            external_url=external_url,
        ),
        published_at=_timestamp(_required(data, "published_at"), "published_at"),
        captured_at=_timestamp(_required(data, "captured_at"), "captured_at"),
        metrics=metrics,
        title=_text(data.get("title"), "title", optional=True),
        transcript=_text(data.get("transcript"), "transcript", optional=True),
        operations_review_url=_text(
            data.get("operations_review_url"),
            "operations_review_url",
            optional=True,
        ),
    )


def _coverage_window(value: object, field_name: str) -> SyncCoverageWindow:
    data = _mapping(value, field_name)
    return SyncCoverageWindow(
        start=_timestamp(_required(data, "start"), f"{field_name}.start"),
        end=_timestamp(_required(data, "end"), f"{field_name}.end"),
    )


def _sync_issue(value: object) -> SyncIssue | None:
    if value is None:
        return None
    data = _mapping(value, "issue")
    return SyncIssue(
        affected_account_ids=tuple(
            _text(account_id, "issue.affected_account_ids[]")
            for account_id in _sequence(
                _required(data, "affected_account_ids"),
                "issue.affected_account_ids",
            )
        ),
        affected_window=_coverage_window(
            _required(data, "affected_window"),
            "issue.affected_window",
        ),
        impact=_enum(
            SyncIssueImpact,
            _required(data, "impact"),
            "issue.impact",
        ),
        reason=_text(data.get("reason"), "issue.reason", optional=True),
    )


def _sync_result(data: Mapping[str, Any]) -> AccountSyncResult:
    return AccountSyncResult(
        account_id=_text(_required(data, "account_id"), "account_id"),
        status=_enum(SyncStatus, _required(data, "status"), "status"),
        contents=tuple(
            _content(_mapping(item, "contents[]"))
            for item in _sequence(_required(data, "contents"), "contents")
        ),
        issue=_sync_issue(data.get("issue")),
        checked_at=_timestamp(_required(data, "checked_at"), "checked_at"),
        coverage_window=_coverage_window(
            _required(data, "coverage_window"),
            "coverage_window",
        ),
        read_source=_enum(
            ReadSource,
            data.get("read_source", ReadSource.STANDARD_INPUT.value),
            "read_source",
        ),
    )


def _relation(data: Mapping[str, Any]) -> ProjectAccountRelation:
    return ProjectAccountRelation(
        project_id=_text(_required(data, "project_id"), "project_id"),
        account_id=_text(_required(data, "account_id"), "account_id"),
        context_version=_text(
            _required(data, "context_version"),
            "context_version",
        ),
    )


def _context(data: Mapping[str, Any]) -> ProjectContextVersion:
    return ProjectContextVersion(
        project_id=_text(_required(data, "project_id"), "project_id"),
        version=_text(_required(data, "version"), "version"),
        effective_at=_timestamp(_required(data, "effective_at"), "effective_at"),
        project_persona=_string(
            _required(data, "project_persona"),
            "project_persona",
        ),
        target_users=_string(_required(data, "target_users"), "target_users"),
        content_plan=_string(_required(data, "content_plan"), "content_plan"),
        operating_direction=_string(
            _required(data, "operating_direction"),
            "operating_direction",
        ),
        confirmed_facts=tuple(
            ProjectFact(
                key=_text(_required(fact, "key"), "confirmed_facts[].key"),
                value=_text(_required(fact, "value"), "confirmed_facts[].value"),
            )
            for item in _sequence(
                _required(data, "confirmed_facts"),
                "confirmed_facts",
            )
            for fact in (_mapping(item, "confirmed_facts[]"),)
        ),
    )


def _analysis_evidence(data: Mapping[str, Any]) -> AnalysisEvidence:
    return AnalysisEvidence(
        evidence_type=_enum(
            EvidenceType,
            _required(data, "evidence_type"),
            "evidence.evidence_type",
        ),
        locator=_text(_required(data, "locator"), "evidence.locator"),
        detail=_text(_required(data, "detail"), "evidence.detail"),
    )


def _source_constraint(data: Mapping[str, Any]) -> SourceConstraint:
    return SourceConstraint(
        statement=_text(_required(data, "statement"), "boundary.statement")
    )


def _source_information(data: Mapping[str, Any]) -> SourceInformation:
    return SourceInformation(
        facts=tuple(
            SourceFact(
                statement=_text(_required(fact, "statement"), "fact.statement"),
                source=_text(_required(fact, "source"), "fact.source"),
                kind=_enum(
                    SourceFactKind,
                    fact.get("kind", SourceFactKind.OTHER.value),
                    "fact.kind",
                ),
                restricted_fragments=tuple(
                    _text(item, "fact.restricted_fragments[]")
                    for item in _sequence(
                        fact.get("restricted_fragments", ()),
                        "fact.restricted_fragments",
                    )
                ),
            )
            for item in _sequence(data.get("facts", ()), "source_information.facts")
            for fact in (_mapping(item, "source_information.facts[]"),)
        ),
        judgments=tuple(
            SourceJudgment(
                statement=_text(
                    _required(item_data, "statement"),
                    "judgment.statement",
                )
            )
            for item in _sequence(
                data.get("judgments", ()),
                "source_information.judgments",
            )
            for item_data in (_mapping(item, "source_information.judgments[]"),)
        ),
        assumptions=tuple(
            SourceAssumption(
                statement=_text(
                    _required(item_data, "statement"),
                    "assumption.statement",
                )
            )
            for item in _sequence(
                data.get("assumptions", ()),
                "source_information.assumptions",
            )
            for item_data in (_mapping(item, "source_information.assumptions[]"),)
        ),
        limitations=tuple(
            SourceLimitation(
                statement=_text(
                    _required(item_data, "statement"),
                    "limitation.statement",
                )
            )
            for item in _sequence(
                data.get("limitations", ()),
                "source_information.limitations",
            )
            for item_data in (_mapping(item, "source_information.limitations[]"),)
        ),
        source_constraints=tuple(
            _source_constraint(_mapping(item, "source_information.source_constraints[]"))
            for item in _sequence(
                data.get("source_constraints", ()),
                "source_information.source_constraints",
            )
        ),
    )


def _reusable_method(data: Mapping[str, Any]) -> ReusableMethod:
    return ReusableMethod(
        name=_text(_required(data, "name"), "reusable_method.name"),
        description=_text(
            _required(data, "description"),
            "reusable_method.description",
        ),
        method_key=_text(
            _required(data, "method_key"),
            "reusable_method.method_key",
        ),
        evidence=tuple(
            _analysis_evidence(_mapping(item, "reusable_method.evidence[]"))
            for item in _sequence(
                _required(data, "evidence"),
                "reusable_method.evidence",
            )
        ),
        applicable_boundaries=tuple(
            _source_constraint(_mapping(item, "applicable_boundaries[]"))
            for item in _sequence(
                _required(data, "applicable_boundaries"),
                "applicable_boundaries",
            )
        ),
    )


def _saved_state(data: Mapping[str, Any]) -> SavedBusinessState:
    relative_value = data.get("persona_relative_like")
    return SavedBusinessState(
        project_id=_text(_required(data, "project_id"), "saved_state.project_id"),
        stable_key=_text(_required(data, "stable_key"), "saved_state.stable_key"),
        candidate_rank=_integer(
            data.get("candidate_rank"),
            "saved_state.candidate_rank",
            optional=True,
            positive=True,
        ),
        is_opportunity=_boolean(
            _required(data, "is_opportunity"),
            "saved_state.is_opportunity",
        ),
        in_library=_boolean(
            _required(data, "in_library"),
            "saved_state.in_library",
        ),
        priority=_integer(
            data.get("priority"),
            "saved_state.priority",
            optional=True,
        ),
        cross_project=_boolean(
            _required(data, "cross_project"),
            "saved_state.cross_project",
        ),
        conclusion=_text(
            _required(data, "conclusion"),
            "saved_state.conclusion",
        ),
        confidence=_enum(
            ConfidenceLevel,
            _required(data, "confidence"),
            "saved_state.confidence",
        ),
        persona_relative_like=(
            None
            if relative_value is None
            else _enum(
                RelativePerformanceLevel,
                relative_value,
                "saved_state.persona_relative_like",
            )
        ),
    )


def _saved_library_record(data: Mapping[str, Any]) -> SavedLibraryRecord:
    return SavedLibraryRecord(
        project_id=_text(
            _required(data, "project_id"),
            "saved_library_record.project_id",
        ),
        content_key=_text(
            _required(data, "content_key"),
            "saved_library_record.content_key",
        ),
        reusable_methods=tuple(
            _reusable_method(_mapping(item, "reusable_methods[]"))
            for item in _sequence(
                _required(data, "reusable_methods"),
                "reusable_methods",
            )
        ),
        signals=tuple(
            _enum(CrossProjectSignal, item, "saved_library_record.signals[]")
            for item in _sequence(data.get("signals", ()), "signals")
        ),
        scenarios=tuple(
            _text(item, "saved_library_record.scenarios[]")
            for item in _sequence(data.get("scenarios", ()), "scenarios")
        ),
        source_information=_source_information(
            _mapping(
                _required(data, "source_information"),
                "saved_library_record.source_information",
            )
        ),
    )


def _weekly_baseline(data: Mapping[str, Any]) -> WeeklyPersonaBaseline:
    baseline_data = _mapping(_required(data, "baseline"), "baseline")
    return WeeklyPersonaBaseline(
        account_id=_text(_required(data, "account_id"), "baseline.account_id"),
        window_start=_timestamp(
            _required(data, "window_start"),
            "baseline.window_start",
        ),
        window_end=_timestamp(
            _required(data, "window_end"),
            "baseline.window_end",
        ),
        baseline=LikeBaseline(
            mean=_number(_required(baseline_data, "mean"), "baseline.mean"),
            median=_number(
                _required(baseline_data, "median"),
                "baseline.median",
            ),
            sample_size=_integer(
                _required(baseline_data, "sample_size"),
                "baseline.sample_size",
                positive=True,
            ),
            maximum=_integer(
                _required(baseline_data, "maximum"),
                "baseline.maximum",
            ),
            minimum=_integer(
                _required(baseline_data, "minimum"),
                "baseline.minimum",
            ),
        ),
    )


def adapt_offline_run_input(payload: Mapping[str, Any]) -> OfflineRunInput:
    """把已解码数据映射为离线内核输入；不读取文件或外部服务。"""
    if not isinstance(payload, Mapping):
        raise TypeError("标准输入适配器只接受已解码的数据对象")
    try:
        if _required(payload, "schema_version") != "phase1":
            raise ValueError("schema_version 不受支持")
        return OfflineRunInput(
            sync_results=tuple(
                _sync_result(_mapping(item, "sync_results[]"))
                for item in _sequence(
                    _required(payload, "sync_results"),
                    "sync_results",
                )
            ),
            relations=tuple(
                _relation(_mapping(item, "relations[]"))
                for item in _sequence(_required(payload, "relations"), "relations")
            ),
            contexts=tuple(
                _context(_mapping(item, "contexts[]"))
                for item in _sequence(_required(payload, "contexts"), "contexts")
            ),
            run_at=_timestamp(_required(payload, "run_at"), "run_at"),
            saved_states=tuple(
                _saved_state(_mapping(item, "saved_states[]"))
                for item in _sequence(payload.get("saved_states", ()), "saved_states")
            ),
            saved_library_records=tuple(
                _saved_library_record(_mapping(item, "saved_library_records[]"))
                for item in _sequence(
                    payload.get("saved_library_records", ()),
                    "saved_library_records",
                )
            ),
            persona_baselines=tuple(
                _weekly_baseline(_mapping(item, "persona_baselines[]"))
                for item in _sequence(
                    payload.get("persona_baselines", ()),
                    "persona_baselines",
                )
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, TypeError) and str(exc).startswith("标准输入适配器"):
            raise
        raise ValueError(f"标准输入无效：{exc}") from exc
