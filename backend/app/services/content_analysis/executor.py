"""任务配置模块可调用的内容分析完整执行与仅投递重试入口。"""
import asyncio
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import date, datetime
from enum import Enum
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlsplit
from weakref import WeakValueDictionary

from .analyzer import (
    ContentAnalyzer,
    CrossProjectSignal,
    ProjectAssessment,
    enforce_analysis_boundaries,
)
from .deterministic import build_weekly_persona_baselines, deduplicate_contents
from .domain import (
    BasicAnalysis,
    ConfidenceLevel,
    ContentCategory,
    ContentIdentity,
    ContentRecord,
    ContentSource,
    EngagementMetrics,
    OpeningAnnotation,
    OpeningKind,
    OpeningTagStatus,
    SourceInformation,
    SourceLimitation,
    SyncStatus,
)
from .engine import (
    AccountSyncResult,
    ContentAnalysisEngine,
    OfflineRunInput,
    ProjectAccountRelation,
    SyncCoverageWindow,
    SavedLibraryRecord,
    build_cross_project_candidates,
)
from .feishu_relation import FeishuRelationReadStatus
from .persistence import (
    AccountBaselineWrite,
    CrossProjectOpportunityWrite,
    InternalResultStatus,
    LibraryItemWrite,
    LibraryRefreshWrite,
    ManualOpeningWrite,
    PersistedResult,
    ResultWrite,
)
from .runtime_contract import (
    AccountExecution,
    ContentAnalysisTaskEnvelope,
    DatabasePrecheckStatus,
    DeliveryScope,
    ProjectExecution,
    RetryMode,
    RunType,
    WeeklyBatchFinalizeExecution,
)


class ExecutionOverallStatus(str, Enum):
    """内容分析执行结果；任务表仍使用既有总状态。"""

    SUCCESS = "success"
    FAILED = "failed"
    NOT_RUN = "not_run"


_ANALYSIS_LOCKS: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()


@asynccontextmanager
async def _local_analysis_guard(key: str, timeout_seconds: float):
    """同一进程内按分析幂等键单飞，等待时间不超过任务截止时间。"""
    lock = _ANALYSIS_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _ANALYSIS_LOCKS[key] = lock
    acquired = False
    try:
        try:
            await asyncio.wait_for(lock.acquire(), timeout=timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise TimeoutError("内容分析任务等待进程内锁超过截止时间") from exc
        acquired = True
        yield
    finally:
        if acquired:
            lock.release()


@dataclass(frozen=True)
class ExecutionLayerSummary:
    """数据库预检、关系、内部结果和投递四层封闭状态。"""

    precheck: str
    relation: str
    internal_result: str
    delivery: str
    failure_stage: str | None = None
    reason_code: str | None = None
    public_message: str | None = None
    input_limited: bool = False
    limitation_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        allowed = {
            "precheck": {"ready", "not_run", "failed"},
            "relation": {"not_started", "complete", "not_run", "failed"},
            "internal_result": {"not_started", "success", "no_content", "failed"},
            "delivery": {"not_started", "success", "failed"},
        }
        labels = {
            "precheck": "预检状态",
            "relation": "关系状态",
            "internal_result": "内部结果状态",
            "delivery": "投递状态",
        }
        for field_name, choices in allowed.items():
            if getattr(self, field_name) not in choices:
                raise ValueError(f"{labels[field_name]}不受支持")
        if self.failure_stage not in {
            None,
            "system_config",
            "deadline",
            "precheck",
            "relation",
            "content",
            "analysis_or_persistence",
            "delivery",
        }:
            raise ValueError("失败阶段不受支持")
        allowed_reasons = {
            None,
            "SYSTEM_ACCOUNT_MISSING",
            "SYSTEM_ACCOUNT_INVALID",
            "CLOCK_INVALID",
            "DEADLINE_EXCEEDED",
            "PRECHECK_MISSING",
            "PRECHECK_ERROR",
            "FEISHU_RELATION_READ_FAILED",
            "FEISHU_RELATION_NOT_FOUND",
            "FEISHU_RELATION_SCOPE_MISMATCH",
            "FEISHU_CONTENT_READ_FAILED",
            "INTERNAL_EXECUTION_FAILED",
            "DELIVERY_FAILED",
            "EXECUTOR_CONTRACT_INVALID",
        }
        if self.reason_code not in allowed_reasons:
            raise ValueError("失败原因代码不受支持")
        if self.public_message is not None and (
            not isinstance(self.public_message, str)
            or not self.public_message.strip()
        ):
            raise ValueError("公开失败说明必须是非空文本")
        if type(self.input_limited) is not bool:
            raise ValueError("输入受限标记必须是原生布尔值")
        if not isinstance(self.limitation_codes, tuple):
            raise ValueError("限制代码必须是不可变元组")


@dataclass(frozen=True)
class DeliveryIdentity:
    """可复用的飞书文档身份。"""

    document_key: str
    document_id: str | None
    document_url: str | None

    def __post_init__(self) -> None:
        if not self.document_key.strip():
            raise ValueError("document_key 不能为空")


@dataclass(frozen=True)
class ExecutionOutcome:
    """调用方更新 TaskJob 所需的执行事实。"""

    overall_status: ExecutionOverallStatus
    summary: ExecutionLayerSummary
    internal_result_id: int | None = None
    output_id: int | None = None
    delivery_identity: DeliveryIdentity | None = None

    @property
    def task_status(self) -> str:
        return {
            ExecutionOverallStatus.SUCCESS: "success",
            ExecutionOverallStatus.FAILED: "failed",
            ExecutionOverallStatus.NOT_RUN: "not_run",
        }[self.overall_status]

    def to_result_summary(
        self,
        envelope: ContentAnalysisTaskEnvelope,
    ) -> dict[str, Any]:
        """生成 TaskJob.result_summary 的四层封闭状态。"""
        identity = self.delivery_identity
        return {
            "trigger_source": envelope.trigger_source.value,
            "overall_status": self.overall_status.value,
            "precheck": self.summary.precheck,
            "feishu_relation": self.summary.relation,
            "internal_result": self.summary.internal_result,
            "feishu_delivery": self.summary.delivery,
            "failure_stage": self.summary.failure_stage,
            "reason_code": self.summary.reason_code,
            "public_message": self.summary.public_message,
            "input_limited": self.summary.input_limited,
            "limitation_codes": list(self.summary.limitation_codes),
            "internal_result_id": self.internal_result_id,
            "output_id": self.output_id,
            "delivery_identity": (
                {
                    "document_key": identity.document_key,
                    "document_id": identity.document_id,
                    "document_url": identity.document_url,
                }
                if identity is not None
                else None
            ),
        }


class RuntimeStore(Protocol):
    async def validate_system_user(self, user_id: int) -> bool: ...

    async def validate_internal_retry_origin(
        self,
        envelope: ContentAnalysisTaskEnvelope,
    ) -> bool: ...

    async def validate_manual_retry_origin(
        self,
        envelope: ContentAnalysisTaskEnvelope,
    ) -> bool: ...

    async def validate_manual_finalize_retry_origin(
        self,
        envelope: ContentAnalysisTaskEnvelope,
    ) -> bool: ...

    async def validate_current_finalize_version(
        self,
        envelope: ContentAnalysisTaskEnvelope,
    ) -> bool: ...

    async def validate_finalize_redelivery_origin(
        self,
        envelope: ContentAnalysisTaskEnvelope,
        internal_result_id: int,
    ) -> bool: ...

    async def validate_manual_redelivery_origin(
        self,
        envelope: ContentAnalysisTaskEnvelope,
        internal_result_id: int,
    ) -> bool: ...

    def analysis_guard(self, envelope: ContentAnalysisTaskEnvelope): ...

    def delivery_guard(self, envelope: ContentAnalysisTaskEnvelope): ...

    async def load_pending_manual_openings(self, project_id: str): ...

    async def find_persisted_result(
        self,
        envelope: ContentAnalysisTaskEnvelope,
    ) -> PersistedResult | None: ...

    async def persist(
        self,
        envelope: ContentAnalysisTaskEnvelope,
        write: ResultWrite,
        created_by: int,
    ) -> PersistedResult: ...

    async def load_result_payload(self, result_id: int) -> Mapping[str, Any]: ...

    async def load_persisted_result(
        self,
        envelope: ContentAnalysisTaskEnvelope,
        result_id: int,
    ) -> PersistedResult: ...

    async def load_daily_history(
        self,
        envelope: ContentAnalysisTaskEnvelope,
        project_id: str,
        account_ids: tuple[str, ...],
    ): ...

    async def lock_library_mutations(self) -> None: ...

    async def load_delivery_identity(
        self,
        envelope: ContentAnalysisTaskEnvelope,
    ) -> DeliveryIdentity | None: ...

    async def record_delivery(
        self,
        envelope: ContentAnalysisTaskEnvelope,
        result_id: int,
        *,
        status: str,
        identity: DeliveryIdentity | None = None,
        error: str | None = None,
    ) -> None: ...


class ReportDelivery(Protocol):
    async def deliver(
        self,
        envelope: ContentAnalysisTaskEnvelope,
        result_id: int,
        payload: Mapping[str, Any],
        identity: DeliveryIdentity | None,
    ) -> DeliveryIdentity: ...


def _json_value(value: object) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if is_dataclass(value):
        return {item.name: _json_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def infer_source_platform(external_url: str | None) -> tuple[str, str | None]:
    """仅在链接能够证明时识别抖音，否则明确保持未知。"""
    hostname = None
    if external_url:
        try:
            hostname = urlsplit(external_url).hostname
        except ValueError:
            hostname = None
    normalized = hostname.casefold() if hostname else ""
    if any(
        normalized == domain or normalized.endswith(f".{domain}")
        for domain in ("douyin.com", "iesdouyin.com")
    ):
        return "douyin", None
    return "unknown", "来源平台无法由表字段或链接确认"


class _InputLimitedAnalyzer:
    def __init__(self, delegate: ContentAnalyzer) -> None:
        self._delegate = delegate
        self.basic_attempts = 0
        self.basic_successes = 0
        self.project_attempts = 0
        self.project_successes = 0

    async def analyze_content(self, content):
        self.basic_attempts += 1
        result = await self._delegate.analyze_content(content)
        self.basic_successes += 1
        return result

    async def assess_project(self, analysis, project_context):
        self.project_attempts += 1
        assessment = await self._delegate.assess_project(analysis, project_context)
        missing = []
        if not project_context.target_users.strip():
            missing.append("缺少目标用户正式字段，相关适配判断受限")
        if not project_context.operating_direction.strip():
            missing.append("缺少整体经营方向正式字段，相关适配判断受限")
        if missing:
            confidence = (
                ConfidenceLevel.MEDIUM
                if assessment.confidence is ConfidenceLevel.HIGH
                else assessment.confidence
            )
            assessment = replace(
                assessment,
                confidence=confidence,
                limitations=tuple(
                    dict.fromkeys(assessment.limitations + tuple(missing))
                ),
            )
        self.project_successes += 1
        return assessment


def _daily_write(
    result,
    context_load,
    relation_read,
    syncs,
    envelope,
    limitation_codes,
) -> ResultWrite:
    payload = _json_value(result)
    payload["run_metadata"] = {
        "task_no": envelope.task_no,
        "project_name": context_load.project_name,
        "run_type": envelope.run_type.value,
        "business_date": envelope.business_date.isoformat(),
        "window_start": envelope.window_start.isoformat(),
        "window_end": envelope.window_end.isoformat(),
        "generated_at": max(
            (
                relation_read.checked_at,
                *(item.checked_at for item in syncs if item.checked_at is not None),
            )
        ).isoformat(),
        "relation_read_at": relation_read.checked_at.isoformat(),
        "content_read_at": max(
            item.checked_at for item in syncs if item.checked_at is not None
        ).isoformat(),
        "data_complete": not bool(limitation_codes),
        "limitation_codes": list(limitation_codes),
    }
    reports = tuple(result.reports.values())
    status = (
        InternalResultStatus.NO_CONTENT
        if reports and all(report.is_empty_daily for report in reports)
        else InternalResultStatus.SUCCESS
    )
    library_items: list[LibraryItemWrite] = []
    library_refreshes: list[LibraryRefreshWrite] = []
    for report in reports:
        for report_item in report.all_window_items:
            content = report_item.analysis.content
            if not content.identity.stable_keys():
                continue
            library_refreshes.append(
                LibraryRefreshWrite(
                    project_id=int(report.project_id),
                    platform_content_id=content.identity.platform_content_id,
                    external_url=content.identity.external_url,
                    analysis=_json_value(report_item.analysis),
                    project_assessment=_json_value(report_item.assessment),
                    latest_metrics=_json_value(content.metrics),
                    confidence=report_item.assessment.confidence.value,
                    priority=report_item.assessment.priority,
                )
            )
        for candidate in report.library_candidates:
            content = candidate.content
            platform, _ = infer_source_platform(content.identity.external_url)
            library_items.append(
                LibraryItemWrite(
                    project_id=int(candidate.project_id),
                    account_id=content.account_id,
                    platform=platform,
                    platform_content_id=content.identity.platform_content_id,
                    external_url=content.identity.external_url,
                    category=candidate.category.value,
                    title=content.title or "未命名内容",
                    transcript=content.transcript or "",
                    analysis=_json_value(candidate.analysis),
                    project_assessment=_json_value(candidate.assessment),
                    latest_metrics=_json_value(content.metrics),
                    confidence=candidate.confidence.value,
                    priority=candidate.assessment.priority,
                    opening_status=candidate.opening_status.value,
                    opening_fragment=candidate.opening_fragment,
                    opening_unavailable_reason=candidate.opening_unavailable_reason,
                )
            )
    cross_items = tuple(
        CrossProjectOpportunityWrite(
            method_key=candidate.method.method_key,
            method_payload=_json_value(candidate.method),
            applicable_boundaries=[
                item.statement for item in candidate.method.applicable_boundaries
            ],
            sources=[_json_value(item) for item in candidate.sources],
        )
        for candidate in result.cross_project_candidates
    )
    source_receipts = {
        "relation": {
            "status": relation_read.status.value,
            "checked_at": relation_read.checked_at.isoformat(),
        },
        "content": [
            {
                "sec_uid": item.account_id,
                "status": item.status.value,
                "checked_at": item.checked_at.isoformat() if item.checked_at else None,
            }
            for item in syncs
        ],
    }
    return ResultWrite(
        title=f"内容分析日报-{reports[0].report_date.isoformat()}",
        status=status,
        payload=payload,
        context_versions={
            context_load.context.project_id: context_load.context.version
        },
        source_receipts=source_receipts,
        library_items=tuple(library_items),
        library_refreshes=tuple(library_refreshes),
        cross_project_opportunities=cross_items,
    )


def _report_item_saved_record(project_id, item) -> SavedLibraryRecord | None:
    if not item.stable_key or not item.in_library:
        return None
    content = item.analysis.content
    return SavedLibraryRecord(
        project_id=project_id,
        content_key=item.stable_key,
        identity_keys=tuple(
            f"{kind}:{value}" for kind, value in content.identity.stable_keys()
        ),
        reusable_methods=item.analysis.reusable_methods,
        source_information=item.analysis.source_information,
        signals=tuple(item.assessment.cross_project_signals),
        scenarios=tuple(
            scenario.statement
            for scenario in item.assessment.cross_project_scenarios
        ),
    )


def _with_saved_availability(item, records):
    aliases = {
        item.stable_key,
        *(
            f"{kind}:{value}"
            for kind, value in item.analysis.content.identity.stable_keys()
        ),
    } - {None}
    matches = tuple(
        record
        for record in records
        if aliases
        & {record.content_key, *record.identity_keys}
    )
    if not matches:
        return item
    available = all(record.available_for_reuse for record in matches)
    return replace(
        item,
        in_library=available,
        cross_project=item.cross_project and available,
    )


def _with_current_library_availability(result, history):
    records_by_project: dict[str, tuple[SavedLibraryRecord, ...]] = {
        project_id: tuple(
            record
            for record in history.saved_library_records
            if record.project_id == project_id
        )
        for project_id in result.reports
    }

    def mark_items(project_id, items):
        records = records_by_project[project_id]
        return tuple(_with_saved_availability(item, records) for item in items)

    def current_candidates(project_id, candidates):
        records = records_by_project[project_id]
        saved_aliases = {
            key
            for record in records
            for key in (record.content_key, *record.identity_keys)
        }
        return tuple(
            candidate
            for candidate in candidates
            if not (
                {
                    candidate.stable_key,
                    *(
                        f"{kind}:{value}"
                        for kind, value in candidate.content.identity.stable_keys()
                    ),
                }
                & saved_aliases
            )
        )

    return replace(
        result,
        reports={
            project_id: replace(
                report,
                all_window_items=mark_items(project_id, report.all_window_items),
                items=mark_items(project_id, report.items),
                previous_two_day_changes=mark_items(
                    project_id,
                    report.previous_two_day_changes,
                ),
                persona_opportunities=mark_items(
                    project_id,
                    report.persona_opportunities,
                ),
                qianchuan_opportunities=mark_items(
                    project_id,
                    report.qianchuan_opportunities,
                ),
                library_candidates=current_candidates(
                    project_id,
                    report.library_candidates,
                ),
            )
            for project_id, report in result.reports.items()
        },
    )


def _with_current_cross_project_candidates(result, history):
    current_records = tuple(
        record
        for project_id, report in result.reports.items()
        for item in report.all_window_items
        for record in (_report_item_saved_record(project_id, item),)
        if record is not None
    )
    current_aliases = {
        (record.project_id, key)
        for record in current_records
        for key in (record.content_key, *record.identity_keys)
    }
    historical_records = tuple(
        record
        for record in history.saved_library_records
        if not any(
            (record.project_id, key) in current_aliases
            for key in (record.content_key, *record.identity_keys)
        )
    )
    all_candidates = build_cross_project_candidates(
        historical_records + current_records
    )
    current_sources = {
        (record.project_id, record.content_key) for record in current_records
    }
    changed = tuple(
        candidate
        for candidate in all_candidates
        if any(
            (source.project_id, source.content_key) in current_sources
            for source in candidate.sources
        )
    )
    cross_method_keys_by_project = {
        project_id: {
            candidate.method.method_key
            for candidate in changed
            if project_id in candidate.project_ids
        }
        for project_id in result.reports
    }

    def mark_items(project_id, items):
        method_keys = cross_method_keys_by_project[project_id]
        return tuple(
            replace(
                item,
                cross_project=item.in_library
                and bool(
                    {method.method_key for method in item.analysis.reusable_methods}
                    & method_keys
                ),
            )
            for item in items
        )

    return replace(
        result,
        cross_project_candidates=changed,
        reports={
            project_id: replace(
                report,
                all_window_items=mark_items(project_id, report.all_window_items),
                items=mark_items(project_id, report.items),
                previous_two_day_changes=mark_items(
                    project_id,
                    report.previous_two_day_changes,
                ),
                persona_opportunities=mark_items(
                    project_id,
                    report.persona_opportunities,
                ),
                qianchuan_opportunities=mark_items(
                    project_id,
                    report.qianchuan_opportunities,
                ),
                cross_project_candidates=(
                    ()
                    if report.is_empty_daily
                    else tuple(
                        candidate
                        for candidate in changed
                        if project_id in candidate.project_ids
                    )
                ),
            )
            for project_id, report in result.reports.items()
        },
    )


class ContentAnalysisExecutor:
    """只暴露完整执行与仅投递重试。"""

    def __init__(
        self,
        *,
        relation_reader,
        content_reader,
        context_reader,
        analyzer: ContentAnalyzer,
        store: RuntimeStore,
        delivery: ReportDelivery,
        system_user_id: int | None,
        clock: Callable[[], datetime],
    ) -> None:
        self._relation_reader = relation_reader
        self._content_reader = content_reader
        self._context_reader = context_reader
        self._analyzer = analyzer
        self._store = store
        self._delivery = delivery
        self._system_user_id = system_user_id
        self._clock = clock

    def _deadline_status(self, deadline_at: datetime) -> str | None:
        return self._deadline_observation(deadline_at)[0]

    def _deadline_observation(
        self,
        deadline_at: datetime,
    ) -> tuple[str | None, float | None]:
        try:
            current = self._clock()
        except Exception:
            return "invalid", None
        if (
            not isinstance(current, datetime)
            or current.tzinfo is None
            or current.utcoffset() is None
        ):
            return "invalid", None
        remaining = (deadline_at - current).total_seconds()
        if remaining <= 0:
            return "expired", None
        return None, remaining

    def _remaining_seconds(self, deadline_at: datetime) -> float:
        current = self._clock()
        if (
            not isinstance(current, datetime)
            or current.tzinfo is None
            or current.utcoffset() is None
        ):
            raise ValueError("执行时钟必须返回带时区时间")
        remaining = (deadline_at - current).total_seconds()
        if remaining <= 0:
            raise TimeoutError("内容分析任务已超过截止时间")
        return remaining

    async def _internal_retry_is_valid(
        self,
        envelope: ContentAnalysisTaskEnvelope,
    ) -> bool:
        if not (
            envelope.run_type is RunType.RETRY
            and envelope.trigger_source.value == "system"
        ):
            return True
        try:
            return await self._store.validate_internal_retry_origin(envelope)
        except Exception:
            return False

    async def _manual_full_retry_is_valid(
        self,
        envelope: ContentAnalysisTaskEnvelope,
    ) -> bool:
        if envelope.trigger_source.value != "user":
            return True
        if isinstance(envelope.execution, WeeklyBatchFinalizeExecution):
            if not (
                envelope.run_type is RunType.RETRY
                and envelope.retry_mode is RetryMode.FULL
            ):
                return False
            validator = self._store.validate_manual_finalize_retry_origin
        elif (
            envelope.run_type is RunType.RETRY
            and envelope.retry_mode is RetryMode.FULL
        ):
            validator = self._store.validate_manual_retry_origin
        else:
            return True
        try:
            return await validator(envelope)
        except Exception:
            return False

    async def _auto_finalize_version_is_current(
        self,
        envelope: ContentAnalysisTaskEnvelope,
    ) -> bool:
        if not (
            isinstance(envelope.execution, WeeklyBatchFinalizeExecution)
            and envelope.run_type is RunType.AUTO
        ):
            return True
        try:
            return await self._store.validate_current_finalize_version(envelope)
        except Exception:
            return False

    @staticmethod
    def _assert_successful_delivery_identity(
        envelope: ContentAnalysisTaskEnvelope,
        identity: object,
    ) -> DeliveryIdentity:
        if not isinstance(identity, DeliveryIdentity):
            raise ValueError("飞书投递未返回文档身份")
        if identity.document_key != envelope.idempotency.document_key:
            raise ValueError("飞书投递返回了错误的文档键")
        if not isinstance(identity.document_id, str) or not identity.document_id.strip():
            raise ValueError("飞书投递未返回文档编号")
        if not isinstance(identity.document_url, str) or not identity.document_url.strip():
            raise ValueError("飞书投递未返回文档链接")
        parsed = urlsplit(identity.document_url)
        host = parsed.hostname.casefold() if parsed.hostname else ""
        if (
            parsed.scheme != "https"
            or not (host == "feishu.cn" or host.endswith(".feishu.cn"))
            or parsed.path.rstrip("/") != f"/docx/{identity.document_id}"
        ):
            raise ValueError("飞书投递文档链接与文档编号不匹配")
        return identity

    @staticmethod
    def _delivery_envelope(
        envelope: ContentAnalysisTaskEnvelope,
        payload: Mapping[str, Any],
    ) -> ContentAnalysisTaskEnvelope:
        """正式日报目录由结构化结果中的数据库项目名称稳定派生。"""
        if (
            not isinstance(envelope.execution, ProjectExecution)
            or envelope.delivery_target.scope is DeliveryScope.TEST
        ):
            return envelope
        metadata = payload.get("run_metadata")
        metadata = metadata if isinstance(metadata, Mapping) else {}
        project_name = metadata.get("project_name")
        if not isinstance(project_name, str) or not project_name.strip():
            project_name = "未命名项目"
        safe_name = re.sub(r"[\x00-\x1f/\\]+", "_", project_name).strip(" .")
        safe_name = (safe_name or "未命名项目")[:80]
        relative_directory = (
            f"项目日报/{envelope.execution.project_id}-{safe_name}"
        )
        return replace(
            envelope,
            delivery_target=replace(
                envelope.delivery_target,
                relative_directory=relative_directory,
            ),
        )

    @staticmethod
    def _outcome(
        status: ExecutionOverallStatus,
        *,
        precheck="ready",
        relation="not_started",
        internal="not_started",
        delivery="not_started",
        failure_stage=None,
        input_limited=False,
        limitation_codes=(),
        reason_code=None,
        public_message=None,
        persisted=None,
        identity=None,
    ) -> ExecutionOutcome:
        return ExecutionOutcome(
            overall_status=status,
            summary=ExecutionLayerSummary(
                precheck=precheck,
                relation=relation,
                internal_result=internal,
                delivery=delivery,
                failure_stage=failure_stage,
                reason_code=reason_code,
                public_message=public_message,
                input_limited=input_limited,
                limitation_codes=tuple(limitation_codes),
            ),
            internal_result_id=(persisted.internal_result_id if persisted else None),
            output_id=(persisted.output_id if persisted else None),
            delivery_identity=identity,
        )

    async def execute(self, envelope: ContentAnalysisTaskEnvelope) -> ExecutionOutcome:
        deadline_status, remaining_seconds = self._deadline_observation(
            envelope.deadline_at
        )
        if deadline_status is not None:
            return self._deadline_failure(deadline_status)
        if remaining_seconds is None:
            return self._deadline_failure("invalid")
        try:
            async with _local_analysis_guard(
                envelope.idempotency.analysis_key,
                remaining_seconds,
            ):
                async with self._store.analysis_guard(envelope):
                    return await self._execute_once(envelope)
        except TimeoutError:
            deadline_status = self._deadline_status(envelope.deadline_at)
            if deadline_status is None:
                raise
            return self._deadline_failure(deadline_status)

    def _deadline_failure(
        self,
        deadline_status: str,
        *,
        persisted: PersistedResult | None = None,
        delivery_retry: bool = False,
    ) -> ExecutionOutcome:
        return self._outcome(
            ExecutionOverallStatus.FAILED,
            precheck="failed" if deadline_status == "invalid" else "ready",
            internal=(persisted.status.value if persisted else "not_started"),
            delivery="failed" if delivery_retry else "not_started",
            failure_stage=(
                "system_config" if deadline_status == "invalid" else "deadline"
            ),
            reason_code=(
                "CLOCK_INVALID"
                if deadline_status == "invalid"
                else "DEADLINE_EXCEEDED"
            ),
            public_message=(
                "内容分析执行时钟配置无效"
                if deadline_status == "invalid"
                else "内容分析任务已超过截止时间"
            ),
            persisted=persisted,
        )

    async def _execute_once(
        self,
        envelope: ContentAnalysisTaskEnvelope,
    ) -> ExecutionOutcome:
        if envelope.retry_mode is RetryMode.DELIVERY_ONLY:
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                precheck="failed",
                failure_stage="system_config",
                reason_code="EXECUTOR_CONTRACT_INVALID",
                public_message="仅投递重试不能调用完整执行",
            )
        if not await self._manual_full_retry_is_valid(envelope):
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                precheck="failed",
                failure_stage="system_config",
                reason_code="EXECUTOR_CONTRACT_INVALID",
                public_message="人工完整重试与失败原任务不一致",
            )
        if not await self._internal_retry_is_valid(envelope):
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                precheck="failed",
                failure_stage="system_config",
                reason_code="EXECUTOR_CONTRACT_INVALID",
                public_message="内部重试信封与原任务不一致",
            )
        if not await self._auto_finalize_version_is_current(envelope):
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                precheck="failed",
                failure_stage="system_config",
                reason_code="EXECUTOR_CONTRACT_INVALID",
                public_message="自动周批次收尾不是当前权威版本",
            )
        if (
            self._system_user_id is None
            or type(self._system_user_id) is not int
            or self._system_user_id <= 0
        ):
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                precheck="failed",
                failure_stage="system_config",
                reason_code="SYSTEM_ACCOUNT_MISSING",
                public_message="内容分析系统服务账号未配置",
            )
        try:
            valid_system_user = await self._store.validate_system_user(
                self._system_user_id
            )
        except Exception:
            valid_system_user = False
        if not valid_system_user:
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                precheck="failed",
                failure_stage="system_config",
                reason_code="SYSTEM_ACCOUNT_INVALID",
                public_message="内容分析系统服务账号不可用",
            )
        deadline_status = self._deadline_status(envelope.deadline_at)
        if deadline_status is not None:
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                precheck="failed" if deadline_status == "invalid" else "ready",
                failure_stage=(
                    "system_config" if deadline_status == "invalid" else "deadline"
                ),
                reason_code=(
                    "CLOCK_INVALID"
                    if deadline_status == "invalid"
                    else "DEADLINE_EXCEEDED"
                ),
                public_message=(
                    "内容分析执行时钟配置无效"
                    if deadline_status == "invalid"
                    else "内容分析任务已超过截止时间"
                ),
            )
        if envelope.precheck.status is DatabasePrecheckStatus.MISSING:
            return self._outcome(
                ExecutionOverallStatus.NOT_RUN,
                precheck="not_run",
                failure_stage="precheck",
                reason_code="PRECHECK_MISSING",
                public_message="项目任务必要配置缺失，未运行内容分析",
                input_limited=envelope.precheck.input_limited,
                limitation_codes=envelope.precheck.limitation_codes,
            )
        if envelope.precheck.status is DatabasePrecheckStatus.ERROR:
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                precheck="failed",
                failure_stage="precheck",
                reason_code="PRECHECK_ERROR",
                public_message="项目任务数据库预检失败",
                input_limited=envelope.precheck.input_limited,
                limitation_codes=envelope.precheck.limitation_codes,
            )
        try:
            existing = await self._store.find_persisted_result(envelope)
        except Exception:
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                internal="failed",
                failure_stage="analysis_or_persistence",
                reason_code="INTERNAL_EXECUTION_FAILED",
                public_message="内容分析历史结果读取失败",
            )
        if existing is not None:
            try:
                payload = await self._store.load_result_payload(
                    existing.internal_result_id
                )
            except Exception:
                return self._outcome(
                    ExecutionOverallStatus.FAILED,
                    relation="complete",
                    internal=existing.status.value,
                    delivery="failed",
                    failure_stage="delivery",
                    reason_code="DELIVERY_FAILED",
                    public_message="已保存内容分析结果读取失败，无法投递",
                    persisted=existing,
                )
            return await self._deliver(
                envelope,
                existing,
                payload,
                input_limited=envelope.precheck.input_limited,
                limitation_codes=envelope.precheck.limitation_codes,
                internal_status=existing.status.value,
                relation_status=(
                    "not_started"
                    if isinstance(envelope.execution, WeeklyBatchFinalizeExecution)
                    else "complete"
                ),
            )
        if isinstance(envelope.execution, WeeklyBatchFinalizeExecution):
            return await self._execute_weekly_batch_finalize(envelope)
        try:
            relation_read = await self._relation_reader.read()
        except Exception:
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                relation="failed",
                failure_stage="relation",
                reason_code="FEISHU_RELATION_READ_FAILED",
                public_message="飞书对标关系读取失败",
            )
        if relation_read.status is FeishuRelationReadStatus.FAILED:
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                relation="failed",
                failure_stage="relation",
                reason_code="FEISHU_RELATION_READ_FAILED",
                public_message=relation_read.error_reason or "飞书对标关系读取失败",
            )
        if isinstance(envelope.execution, ProjectExecution):
            matched = relation_read.for_project(envelope.execution.project_id)
        else:
            allowed = set(envelope.execution.project_ids)
            matched = tuple(
                item
                for item in relation_read.for_account(envelope.execution.sec_uid)
                if item.project_id in allowed
            )
            if matched and {item.project_id for item in matched} != allowed:
                return self._outcome(
                    ExecutionOverallStatus.NOT_RUN,
                    relation="not_run",
                    failure_stage="relation",
                    reason_code="FEISHU_RELATION_SCOPE_MISMATCH",
                    public_message="飞书关系与周任务关联项目范围不一致",
                )
        if not matched:
            return self._outcome(
                ExecutionOverallStatus.NOT_RUN,
                relation="not_run",
                failure_stage="relation",
                reason_code="FEISHU_RELATION_NOT_FOUND",
                public_message="飞书关系完整读取，但当前任务没有有效对标关系",
            )
        account_ids = tuple(sorted({item.sec_uid for item in matched}))
        coverage = SyncCoverageWindow(envelope.window_start, envelope.window_end)
        try:
            syncs = await self._content_reader.read_accounts(account_ids, coverage)
        except Exception:
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                relation="complete",
                internal="failed",
                failure_stage="content",
                reason_code="FEISHU_CONTENT_READ_FAILED",
                public_message="飞书内容读取失败",
            )
        if (
            tuple(item.account_id for item in syncs) != account_ids
            or any(
                item.status
                not in (
                    SyncStatus.SUCCESS_WITH_CONTENT,
                    SyncStatus.SUCCESS_WITHOUT_CONTENT,
                )
                for item in syncs
            )
        ):
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                relation="complete",
                internal="failed",
                failure_stage="content",
                reason_code="FEISHU_CONTENT_READ_FAILED",
                public_message=next(
                    (
                        item.issue.reason
                        for item in syncs
                        if item.issue is not None and item.issue.reason
                    ),
                    "飞书内容读取未形成完整账号结果",
                ),
            )
        try:
            if isinstance(envelope.execution, ProjectExecution):
                write, limited, limitations = await self._run_daily(
                    envelope,
                    relation_read,
                    matched,
                    syncs,
                )
            else:
                write, limited, limitations = await self._run_weekly(
                    envelope,
                    relation_read,
                    matched,
                    syncs,
                )
            if self._deadline_status(envelope.deadline_at) is not None:
                return self._outcome(
                    ExecutionOverallStatus.FAILED,
                    relation="complete",
                    internal="failed",
                    failure_stage="deadline",
                    reason_code="DEADLINE_EXCEEDED",
                    public_message="内容分析任务已超过截止时间",
                    input_limited=limited,
                    limitation_codes=limitations,
                )
            persisted = await self._store.persist(
                envelope,
                write,
                self._system_user_id,
            )
        except Exception:
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                relation="complete",
                internal="failed",
                failure_stage="analysis_or_persistence",
                reason_code="INTERNAL_EXECUTION_FAILED",
                public_message="内容分析或结构化结果持久化失败",
            )
        try:
            delivery_payload = (
                write.payload
                if persisted.created
                else await self._store.load_result_payload(
                    persisted.internal_result_id
                )
            )
        except Exception:
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                relation="complete",
                internal=persisted.status.value,
                failure_stage="analysis_or_persistence",
                reason_code="INTERNAL_EXECUTION_FAILED",
                public_message="内容分析结构化结果读取失败",
                input_limited=limited,
                limitation_codes=limitations,
                persisted=persisted,
            )
        return await self._deliver(
            envelope,
            persisted,
            delivery_payload,
            input_limited=limited,
            limitation_codes=limitations,
            internal_status=persisted.status.value,
        )

    async def _execute_weekly_batch_finalize(self, envelope):
        try:
            batch_summary = await self._store.load_weekly_batch_finalize_summary(
                envelope
            )
            if batch_summary.get("pending_account_count") != 0:
                raise ValueError("周批次仍有未终态账号")
            write = ResultWrite(
                title=f"账号基准周报汇总-{envelope.business_date.isoformat()}",
                status=InternalResultStatus.SUCCESS,
                payload={
                    "weekly_batch_id": envelope.execution.weekly_batch_id,
                    "finalize_version": envelope.execution.finalize_version,
                    "batch_summary": dict(batch_summary),
                    "run_metadata": {
                        "task_no": envelope.task_no,
                        "run_type": envelope.run_type.value,
                        "business_date": envelope.business_date.isoformat(),
                        "window_start": envelope.window_start.isoformat(),
                        "window_end": envelope.window_end.isoformat(),
                        "generated_at": self._clock().isoformat(),
                    },
                },
                context_versions={},
                source_receipts={
                    "task_jobs": {
                        "status": "complete",
                        "account_count": batch_summary.get("account_count"),
                        "finalize_version": envelope.execution.finalize_version,
                    }
                },
            )
            persisted = await self._store.persist(
                envelope,
                write,
                self._system_user_id,
            )
            payload = (
                write.payload
                if persisted.created
                else await self._store.load_result_payload(
                    persisted.internal_result_id
                )
            )
        except Exception:
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                internal="failed",
                failure_stage="analysis_or_persistence",
                reason_code="INTERNAL_EXECUTION_FAILED",
                public_message="周批次终态汇总或结构化结果持久化失败",
            )
        return await self._deliver(
            envelope,
            persisted,
            payload,
            input_limited=envelope.precheck.input_limited,
            limitation_codes=envelope.precheck.limitation_codes,
            internal_status=persisted.status.value,
            relation_status="not_started",
        )

    async def _run_daily(self, envelope, relation_read, matched, syncs):
        context_load = await self._context_reader.load(envelope.execution.project_id)
        account_ids = tuple(sorted({item.sec_uid for item in matched}))
        history = await self._store.load_daily_history(
            envelope,
            envelope.execution.project_id,
            account_ids,
        )
        manual_opening_updates: list[ManualOpeningWrite] = []
        manual_opening_failures: list[dict[str, Any]] = []
        for pending in await self._store.load_pending_manual_openings(
            envelope.execution.project_id
        ):
            try:
                manual_analysis = enforce_analysis_boundaries(
                    await self._analyzer.analyze_content(
                        ContentRecord(
                            account_id=f"manual-library-{pending.item_id}",
                            source=ContentSource.CONTENT_LIBRARY,
                            identity=ContentIdentity(
                                platform_content_id=f"manual-library-{pending.item_id}"
                            ),
                            published_at=envelope.window_end,
                            captured_at=envelope.window_end,
                            metrics=EngagementMetrics(),
                            title=pending.title or None,
                            transcript=pending.transcript or None,
                        )
                    )
                )
                opening = manual_analysis.opening
                if opening.status is OpeningTagStatus.AVAILABLE:
                    status = "available"
                    fragment = opening.fragment
                    unavailable_reason = None
                else:
                    status = "unavailable"
                    fragment = None
                    unavailable_reason = (
                        opening.unavailable_reason
                        or "现有标题和正文不足以形成可靠开头标注"
                    )
            except Exception:
                manual_opening_failures.append(
                    {
                        "item_id": pending.item_id,
                        "project_id": pending.project_id,
                        "reason_code": "MANUAL_OPENING_ANALYSIS_FAILED",
                    }
                )
                continue
            manual_opening_updates.append(
                ManualOpeningWrite(
                    item_id=pending.item_id,
                    project_id=pending.project_id,
                    status=status,
                    fragment=fragment,
                    unavailable_reason=unavailable_reason,
                    opening_payload=_json_value(opening),
                )
            )
        relations = tuple(
            ProjectAccountRelation(
                project_id=item.project_id,
                account_id=item.sec_uid,
                context_version=context_load.context.version,
            )
            for item in matched
        )
        analyzer = _InputLimitedAnalyzer(self._analyzer)
        engine = ContentAnalysisEngine(analyzer)
        result = await engine.run(
            OfflineRunInput(
                sync_results=tuple(syncs),
                relations=relations,
                contexts=(context_load.context,),
                run_at=envelope.window_end,
                saved_states=history.saved_states,
                saved_library_records=history.saved_library_records,
                persona_baselines=history.persona_baselines,
            )
        )
        if analyzer.basic_attempts != analyzer.basic_successes:
            raise RuntimeError("日报窗口内存在基础分析失败")
        if analyzer.project_attempts != analyzer.project_successes:
            raise RuntimeError("日报窗口内存在项目判断失败")
        await self._store.lock_library_mutations()
        current_history = await self._store.load_daily_history(
            envelope,
            envelope.execution.project_id,
            account_ids,
        )
        result = _with_current_library_availability(result, current_history)
        result = _with_current_cross_project_candidates(result, current_history)
        current_pending_ids = {
            item.item_id
            for item in await self._store.load_pending_manual_openings(
                envelope.execution.project_id
            )
        }
        manual_opening_updates = [
            item
            for item in manual_opening_updates
            if item.item_id in current_pending_ids
        ]
        manual_opening_failures = [
            item
            for item in manual_opening_failures
            if item["item_id"] in current_pending_ids
        ]
        limitations = tuple(
            dict.fromkeys(
                envelope.precheck.limitation_codes
                + context_load.limitation_codes
                + (
                    ("MANUAL_OPENING_ANALYSIS_FAILED",)
                    if manual_opening_failures
                    else ()
                )
            )
        )
        daily_write = _daily_write(
            result,
            context_load,
            relation_read,
            syncs,
            envelope,
            limitations,
        )
        return (
            replace(
                daily_write,
                manual_opening_updates=tuple(manual_opening_updates),
                payload={
                    **daily_write.payload,
                    "manual_opening_supplements": [
                        {
                            "item_id": item.item_id,
                            "project_id": item.project_id,
                            "status": item.status,
                            "unavailable_reason": item.unavailable_reason,
                        }
                        for item in manual_opening_updates
                    ],
                    "manual_opening_failures": manual_opening_failures,
                    "run_metadata": {
                        **daily_write.payload["run_metadata"],
                        "data_complete": not bool(limitations),
                        "limitation_codes": list(limitations),
                    },
                },
            ),
            bool(limitations),
            limitations,
        )

    async def _run_weekly(self, envelope, relation_read, matched, syncs):
        execution: AccountExecution = envelope.execution
        matched_project_ids = tuple(sorted({item.project_id for item in matched}))
        context_loads = tuple(
            [await self._context_reader.load(project_id) for project_id in matched_project_ids]
        )
        analyses: list[BasicAnalysis] = []
        failures = 0
        records = deduplicate_contents(
            content for sync in syncs for content in sync.contents
        )
        for content in records:
            try:
                if not content.transcript or not content.transcript.strip():
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
                            limitations=(SourceLimitation("缺少转写，本期不做结构化内容分析"),)
                        ),
                        undetermined_reason="缺少转写，本期不做结构化内容分析",
                    )
                else:
                    analysis = enforce_analysis_boundaries(
                        await self._analyzer.analyze_content(content)
                    )
                analyses.append(analysis)
            except Exception:
                failures += 1
        if failures:
            raise RuntimeError("账号窗口内存在内容分析失败")
        baselines = build_weekly_persona_baselines(analyses, envelope.window_end)
        baseline = next(
            (item for item in baselines if item.account_id == execution.sec_uid),
            None,
        )
        if baseline is None:
            baseline_write = AccountBaselineWrite(
                sec_uid=execution.sec_uid,
                window_start=envelope.window_start,
                window_end=envelope.window_end,
                related_project_ids=matched_project_ids,
                unavailable_reason="窗口内没有可计算的人设点赞样本",
            )
            status = InternalResultStatus.NO_CONTENT if not records else InternalResultStatus.SUCCESS
        else:
            values = baseline.baseline
            baseline_write = AccountBaselineWrite(
                sec_uid=execution.sec_uid,
                window_start=envelope.window_start,
                window_end=envelope.window_end,
                related_project_ids=matched_project_ids,
                mean_likes=values.mean,
                median_likes=values.median,
                sample_count=values.sample_size,
                maximum_likes=values.maximum,
                minimum_likes=values.minimum,
            )
            status = InternalResultStatus.SUCCESS
        updated_at = max(
            relation_read.checked_at,
            *(item.checked_at for item in syncs if item.checked_at is not None),
        )
        if baseline is None:
            baseline_payload = {
                "account_id": execution.sec_uid,
                "window_start": envelope.window_start.isoformat(),
                "window_end": envelope.window_end.isoformat(),
                "baseline": None,
                "status": "unavailable",
                "updated_at": updated_at.isoformat(),
                "unavailable_reason": "窗口内没有可计算的人设点赞样本",
            }
        else:
            baseline_payload = {
                **_json_value(baseline),
                "status": "available",
                "updated_at": updated_at.isoformat(),
                "unavailable_reason": None,
            }
        limitations = tuple(
            dict.fromkeys(
                envelope.precheck.limitation_codes
                + tuple(
                    limitation
                    for load in context_loads
                    for limitation in load.limitation_codes
                )
            )
        )
        payload = {
            "sec_uid": execution.sec_uid,
            "project_ids": list(matched_project_ids),
            "weekly_batch_id": execution.weekly_batch_id,
            "batch_size": execution.batch_size,
            "batch_position": execution.batch_position,
            "content_count": len(records),
            "analysis_failure_count": failures,
            "baseline": baseline_payload,
            "limitations": list(limitations),
            "run_metadata": {
                "task_no": envelope.task_no,
                "run_type": envelope.run_type.value,
                "business_date": envelope.business_date.isoformat(),
                "window_start": envelope.window_start.isoformat(),
                "window_end": envelope.window_end.isoformat(),
                "generated_at": updated_at.isoformat(),
                "relation_read_at": relation_read.checked_at.isoformat(),
                "content_read_at": max(
                    item.checked_at for item in syncs if item.checked_at is not None
                ).isoformat(),
                "data_complete": not bool(limitations),
                "limitation_codes": list(limitations),
            },
        }
        write = ResultWrite(
            title=f"内容分析周报-{envelope.business_date.isoformat()}",
            status=status,
            payload=payload,
            context_versions={
                item.context.project_id: item.context.version for item in context_loads
            },
            source_receipts={
                "relation": {
                    "status": relation_read.status.value,
                    "checked_at": relation_read.checked_at.isoformat(),
                },
                "content": [
                    {
                        "sec_uid": item.account_id,
                        "status": item.status.value,
                        "checked_at": (
                            item.checked_at.isoformat()
                            if item.checked_at is not None
                            else None
                        ),
                        "window_start": (
                            item.coverage_window.start.isoformat()
                            if item.coverage_window is not None
                            else None
                        ),
                        "window_end": (
                            item.coverage_window.end.isoformat()
                            if item.coverage_window is not None
                            else None
                        ),
                        "content_count": len(item.contents),
                    }
                    for item in syncs
                ],
            },
            account_baseline=baseline_write,
        )
        return write, bool(limitations), limitations

    async def _deliver(
        self,
        envelope,
        persisted,
        payload,
        *,
        input_limited,
        limitation_codes,
        internal_status,
        relation_status="complete",
        identity=None,
    ):
        if self._deadline_status(envelope.deadline_at) is not None:
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                relation=relation_status,
                internal=internal_status,
                delivery="failed",
                failure_stage="deadline",
                reason_code="DEADLINE_EXCEEDED",
                public_message="内容分析任务已超过截止时间",
                input_limited=input_limited,
                limitation_codes=limitation_codes,
                persisted=persisted,
            )
        delivery_envelope = envelope
        known_identity = identity
        try:
            delivery_envelope = self._delivery_envelope(envelope, payload)
            async with self._store.delivery_guard(delivery_envelope):
                try:
                    stored_identity = await self._store.load_delivery_identity(
                        delivery_envelope
                    )
                    if (
                        identity is not None
                        and identity.document_id is not None
                        and (
                            stored_identity is None
                            or stored_identity.document_id is None
                            or identity != stored_identity
                        )
                    ):
                        raise ValueError("投递文档身份未经持久化确认")
                    known_identity = stored_identity or identity
                    remaining_seconds = self._remaining_seconds(envelope.deadline_at)
                    delivered = await asyncio.wait_for(
                        self._delivery.deliver(
                            delivery_envelope,
                            persisted.internal_result_id,
                            payload,
                            known_identity,
                        ),
                        timeout=remaining_seconds,
                    )
                    delivered = self._assert_successful_delivery_identity(
                        delivery_envelope,
                        delivered,
                    )
                    known_identity = delivered
                    if self._deadline_status(envelope.deadline_at) is not None:
                        raise TimeoutError("飞书报告投递超过任务截止时间")
                    await self._store.record_delivery(
                        delivery_envelope,
                        persisted.internal_result_id,
                        status="success",
                        identity=delivered,
                    )
                except Exception as exc:
                    partial_identity = getattr(exc, "delivery_identity", None)
                    if not isinstance(partial_identity, DeliveryIdentity):
                        partial_identity = known_identity
                    try:
                        await self._store.record_delivery(
                            delivery_envelope,
                            persisted.internal_result_id,
                            status="failed",
                            identity=partial_identity,
                            error="飞书报告投递失败",
                        )
                    except Exception:
                        pass
                    return self._outcome(
                        ExecutionOverallStatus.FAILED,
                        relation=relation_status,
                        internal=internal_status,
                        delivery="failed",
                        failure_stage=(
                            "deadline"
                            if isinstance(exc, (asyncio.TimeoutError, TimeoutError))
                            else "delivery"
                        ),
                        reason_code=(
                            "DEADLINE_EXCEEDED"
                            if isinstance(exc, (asyncio.TimeoutError, TimeoutError))
                            else "DELIVERY_FAILED"
                        ),
                        public_message=(
                            "飞书报告投递超过任务截止时间"
                            if isinstance(exc, (asyncio.TimeoutError, TimeoutError))
                            else "飞书报告投递失败"
                        ),
                        input_limited=input_limited,
                        limitation_codes=limitation_codes,
                        persisted=persisted,
                        identity=partial_identity,
                    )
        except Exception:
            try:
                await self._store.record_delivery(
                    delivery_envelope,
                    persisted.internal_result_id,
                    status="failed",
                    identity=known_identity,
                    error="飞书报告投递失败",
                )
            except Exception:
                pass
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                relation=relation_status,
                internal=internal_status,
                delivery="failed",
                failure_stage="delivery",
                reason_code="DELIVERY_FAILED",
                public_message="飞书报告投递失败",
                input_limited=input_limited,
                limitation_codes=limitation_codes,
                persisted=persisted,
                identity=known_identity,
            )
        return self._outcome(
            ExecutionOverallStatus.SUCCESS,
            relation=relation_status,
            internal=internal_status,
            delivery="success",
            input_limited=input_limited,
            limitation_codes=limitation_codes,
            persisted=persisted,
            identity=delivered,
        )

    async def redeliver(
        self,
        envelope: ContentAnalysisTaskEnvelope,
        internal_result_id: int,
        delivery_identity: DeliveryIdentity,
    ) -> ExecutionOutcome:
        if isinstance(envelope.execution, WeeklyBatchFinalizeExecution):
            try:
                async with self._store.analysis_guard(envelope):
                    return await self._redeliver_once(
                        envelope,
                        internal_result_id,
                        delivery_identity,
                    )
            except TimeoutError:
                deadline_status = self._deadline_status(envelope.deadline_at)
                if deadline_status is None:
                    raise
                return self._outcome(
                    ExecutionOverallStatus.FAILED,
                    precheck="failed" if deadline_status == "invalid" else "ready",
                    internal="not_started",
                    delivery="failed",
                    failure_stage=(
                        "system_config"
                        if deadline_status == "invalid"
                        else "deadline"
                    ),
                    reason_code=(
                        "CLOCK_INVALID"
                        if deadline_status == "invalid"
                        else "DEADLINE_EXCEEDED"
                    ),
                    public_message=(
                        "内容分析执行时钟配置无效"
                        if deadline_status == "invalid"
                        else "内容分析任务已超过截止时间"
                    ),
                )
        return await self._redeliver_once(
            envelope,
            internal_result_id,
            delivery_identity,
        )

    async def _redeliver_once(
        self,
        envelope: ContentAnalysisTaskEnvelope,
        internal_result_id: int,
        delivery_identity: DeliveryIdentity,
    ) -> ExecutionOutcome:
        if not await self._internal_retry_is_valid(envelope):
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                precheck="failed",
                internal="not_started",
                delivery="failed",
                failure_stage="delivery",
                reason_code="EXECUTOR_CONTRACT_INVALID",
                public_message="内部重试信封与原任务不一致",
            )
        if isinstance(envelope.execution, WeeklyBatchFinalizeExecution):
            try:
                finalize_origin_valid = (
                    await self._store.validate_finalize_redelivery_origin(
                        envelope,
                        internal_result_id,
                    )
                )
            except Exception:
                finalize_origin_valid = False
            if not finalize_origin_valid:
                return self._outcome(
                    ExecutionOverallStatus.FAILED,
                    precheck="failed",
                    delivery="failed",
                    failure_stage="delivery",
                    reason_code="EXECUTOR_CONTRACT_INVALID",
                    public_message="周批次收尾补投来源或版本无效",
                )
        elif envelope.trigger_source.value == "user":
            try:
                manual_origin_valid = (
                    await self._store.validate_manual_redelivery_origin(
                        envelope,
                        internal_result_id,
                    )
                )
            except Exception:
                manual_origin_valid = False
            if not manual_origin_valid:
                return self._outcome(
                    ExecutionOverallStatus.FAILED,
                    precheck="failed",
                    internal="not_started",
                    delivery="failed",
                    failure_stage="delivery",
                    reason_code="EXECUTOR_CONTRACT_INVALID",
                    public_message="仅投递重试来源与已保存结果不一致",
                )
        try:
            persisted = await self._store.load_persisted_result(
                envelope,
                internal_result_id,
            )
        except Exception:
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                internal="not_started",
                delivery="failed",
                failure_stage="delivery",
                reason_code="EXECUTOR_CONTRACT_INVALID",
                public_message="仅投递重试无法确认已保存结果",
            )
        deadline_status = self._deadline_status(envelope.deadline_at)
        if deadline_status is not None:
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                precheck="failed" if deadline_status == "invalid" else "ready",
                internal=persisted.status.value,
                delivery="failed",
                failure_stage=(
                    "system_config" if deadline_status == "invalid" else "deadline"
                ),
                reason_code=(
                    "CLOCK_INVALID"
                    if deadline_status == "invalid"
                    else "DEADLINE_EXCEEDED"
                ),
                public_message=(
                    "内容分析执行时钟配置无效"
                    if deadline_status == "invalid"
                    else "内容分析任务已超过截止时间"
                ),
                persisted=persisted,
            )
        if delivery_identity.document_key != envelope.idempotency.document_key:
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                internal=persisted.status.value,
                delivery="failed",
                failure_stage="delivery",
                reason_code="DELIVERY_FAILED",
                public_message="投递文档身份与任务不一致",
                persisted=persisted,
            )
        try:
            if persisted.result_key != envelope.idempotency.result_key:
                raise ValueError("结果键与任务不一致")
            payload = await self._store.load_result_payload(internal_result_id)
        except Exception:
            return self._outcome(
                ExecutionOverallStatus.FAILED,
                internal=persisted.status.value,
                delivery="failed",
                failure_stage="delivery",
                reason_code="DELIVERY_FAILED",
                public_message="仅投递重试无法读取已保存结果",
                persisted=persisted,
            )
        return await self._deliver(
            envelope,
            persisted,
            payload,
            input_limited=envelope.precheck.input_limited,
            limitation_codes=envelope.precheck.limitation_codes,
            internal_status=persisted.status.value,
            relation_status=(
                "not_started"
                if isinstance(envelope.execution, WeeklyBatchFinalizeExecution)
                else "complete"
            ),
            identity=delivery_identity,
        )
