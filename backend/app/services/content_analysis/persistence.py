"""内容分析结构化结果与业务表的事务写入。"""
import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from math import isfinite
from pathlib import PurePosixPath
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit
from weakref import WeakKeyDictionary

from sqlalchemy import or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.models.content_analysis import (
    ContentAnalysisAccountBaseline,
    ContentAnalysisCrossProjectOpportunity,
    ContentAnalysisDelivery,
    ContentAnalysisLibraryItem,
    ContentAnalysisResult,
)
from app.models.material_library import KolReference
from app.models.output import Output
from app.models.task import TaskJob
from app.models.user import User
from app.services.agent_task_execution_contract import (
    is_valid_content_analysis_system_user,
)

from .domain import (
    ConfidenceLevel,
    LikeBaseline,
    RelativePerformanceLevel,
    WeeklyPersonaBaseline,
)
from .engine import (
    CrossProjectSignal,
    SavedBusinessState,
    SavedLibraryRecord,
    is_reusable_method_safe,
    is_source_limited_text,
    is_visual_claim,
)
from .model_analyzer import parse_reusable_method, parse_source_information

from .runtime_contract import ContentAnalysisTaskEnvelope, DeliveryScope


class InternalResultStatus(str, Enum):
    """结构化分析结果闭集。"""

    SUCCESS = "success"
    NO_CONTENT = "no_content"


_SAFE_ACCOUNT_FAILURE_REASON_CODES = frozenset(
    {
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
        "EXECUTOR_CONTRACT_INVALID",
        "DELIVERY_FAILED",
        "DATA_SOURCE_FAILED",
        "ANALYSIS_FAILED",
        "NOT_RUN",
        "ACCOUNT_FAILED",
    }
)

_GUARD_SEMAPHORES: WeakKeyDictionary[AsyncEngine, asyncio.Semaphore] = (
    WeakKeyDictionary()
)


def _guard_semaphore(engine: AsyncEngine) -> asyncio.Semaphore:
    semaphore = _GUARD_SEMAPHORES.get(engine)
    if semaphore is not None:
        return semaphore
    size = getattr(engine.sync_engine.pool, "size", None)
    try:
        pool_size = int(size()) if callable(size) else 3
    except (TypeError, ValueError):
        pool_size = 3
    semaphore = asyncio.Semaphore(max(1, pool_size - 1))
    _GUARD_SEMAPHORES[engine] = semaphore
    return semaphore


@dataclass(frozen=True)
class LibraryItemWrite:
    """一条项目专属内容库原子写入。"""

    project_id: int
    account_id: str
    platform: str
    platform_content_id: str | None
    external_url: str | None
    category: str
    title: str
    transcript: str
    analysis: Mapping[str, Any]
    project_assessment: Mapping[str, Any]
    latest_metrics: Mapping[str, Any]
    confidence: str
    priority: int | None
    opening_status: str
    opening_fragment: str | None
    opening_unavailable_reason: str | None

    def __post_init__(self) -> None:
        if type(self.project_id) is not int or self.project_id <= 0:
            raise ValueError("项目编号必须是正整数")
        if not self.platform_content_id and not self.external_url:
            raise ValueError("内容库候选必须至少包含一个稳定身份")
        if self.category not in {"persona", "qianchuan"}:
            raise ValueError("内容库分类不受支持")


@dataclass(frozen=True)
class CrossProjectOpportunityWrite:
    """跨项目规范化方法写入。"""

    method_key: str
    method_payload: Mapping[str, Any]
    applicable_boundaries: list[str]
    sources: list[Mapping[str, Any]]

    def __post_init__(self) -> None:
        if not isinstance(self.method_key, str) or not self.method_key.strip():
            raise ValueError("跨项目方法键不能为空")


@dataclass(frozen=True)
class LibraryRefreshWrite:
    """只刷新已入库内容的可变分析投影，不新建记录。"""

    project_id: int
    platform_content_id: str | None
    external_url: str | None
    analysis: Mapping[str, Any]
    project_assessment: Mapping[str, Any]
    latest_metrics: Mapping[str, Any]
    confidence: str
    priority: int | None

    def __post_init__(self) -> None:
        if type(self.project_id) is not int or self.project_id <= 0:
            raise ValueError("项目编号必须是正整数")
        if not self.platform_content_id and not self.external_url:
            raise ValueError("项目库刷新必须包含稳定身份")


@dataclass(frozen=True)
class ManualOpeningCandidate:
    """当前项目中等待自动补标的人工千川内容。"""

    item_id: int
    project_id: int
    title: str
    transcript: str


@dataclass(frozen=True)
class ManualOpeningWrite:
    """人工千川内容的一次确定性开头补标结果。"""

    item_id: int
    project_id: int
    status: str
    fragment: str | None
    unavailable_reason: str | None
    opening_payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.status not in {"available", "unavailable"}:
            raise ValueError("人工内容补标状态不受支持")
        if self.status == "available":
            if not self.fragment or self.unavailable_reason:
                raise ValueError("可用人工开头必须只包含开头片段")
        elif self.fragment or not self.unavailable_reason:
            raise ValueError("不可用人工开头必须只包含明确原因")


@dataclass(frozen=True)
class AccountBaselineWrite:
    """账号窗口基准，或一条明确的不可计算原因。"""

    sec_uid: str
    window_start: datetime
    window_end: datetime
    related_project_ids: tuple[str, ...]
    mean_likes: float | None = None
    median_likes: float | None = None
    sample_count: int = 0
    maximum_likes: int | None = None
    minimum_likes: int | None = None
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.sec_uid.strip() or not self.related_project_ids:
            raise ValueError("账号基准必须包含账号和关联项目")
        if self.window_start >= self.window_end:
            raise ValueError("账号基准窗口无效")
        values = (
            self.mean_likes,
            self.median_likes,
            self.maximum_likes,
            self.minimum_likes,
        )
        if self.sample_count == 0:
            if any(value is not None for value in values) or not self.unavailable_reason:
                raise ValueError("不可计算基准必须只提供明确原因")
        elif (
            type(self.sample_count) is not int
            or self.sample_count < 0
            or any(value is None for value in values)
            or self.unavailable_reason is not None
        ):
            raise ValueError("可计算基准必须提供完整五项统计")


@dataclass(frozen=True)
class ResultWrite:
    """一个不可变结构化 Output 及其同事务业务投影。"""

    title: str
    status: InternalResultStatus
    payload: Mapping[str, Any]
    context_versions: Mapping[str, str]
    source_receipts: Mapping[str, Any]
    library_items: tuple[LibraryItemWrite, ...] = ()
    library_refreshes: tuple[LibraryRefreshWrite, ...] = ()
    cross_project_opportunities: tuple[CrossProjectOpportunityWrite, ...] = ()
    account_baseline: AccountBaselineWrite | None = None
    manual_opening_updates: tuple[ManualOpeningWrite, ...] = ()

    def __post_init__(self) -> None:
        if not self.title.strip() or not isinstance(self.status, InternalResultStatus):
            raise ValueError("结构化结果标题或状态无效")
        if (
            not isinstance(self.library_items, tuple)
            or not isinstance(self.library_refreshes, tuple)
            or not isinstance(self.cross_project_opportunities, tuple)
            or not isinstance(self.manual_opening_updates, tuple)
        ):
            raise ValueError("业务投影必须使用不可变元组")


@dataclass(frozen=True)
class PersistedResult:
    """持久化完成后的稳定身份。"""

    internal_result_id: int
    output_id: int
    result_key: str
    created: bool
    status: InternalResultStatus = InternalResultStatus.SUCCESS


@dataclass(frozen=True)
class DailyHistoricalInputs:
    """日报引擎需要的已保存业务状态、项目库和周度基准。"""

    saved_states: tuple[SavedBusinessState, ...] = ()
    saved_library_records: tuple[SavedLibraryRecord, ...] = ()
    persona_baselines: tuple[WeeklyPersonaBaseline, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "saved_states",
            "saved_library_records",
            "persona_baselines",
        ):
            if not isinstance(getattr(self, field_name), tuple):
                raise ValueError("日报历史输入必须使用不可变元组")


class SqlContentAnalysisStore:
    """同一事务保存 Output、结果索引及正式业务投影。"""

    def __init__(
        self,
        session: AsyncSession,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._session = session
        self._clock = clock
        self._guard_connection: AsyncConnection | None = None
        self._guard_lock_names: set[str] = set()

    def _lock_engine(self) -> AsyncEngine:
        bind = self._session.bind
        if isinstance(bind, AsyncEngine):
            return bind
        if isinstance(bind, AsyncConnection):
            return bind.engine
        raise RuntimeError("内容分析数据库锁缺少异步引擎")

    def _lock_timeout(self, deadline_at: datetime, monotonic_deadline: float) -> float:
        current = self._clock()
        if not isinstance(current, datetime) or current.tzinfo is None:
            raise ValueError("内容分析数据库锁时钟无效")
        remaining = min(
            (deadline_at - current).total_seconds(),
            monotonic_deadline - asyncio.get_running_loop().time(),
        )
        if remaining <= 0:
            raise TimeoutError("内容分析任务等待数据库锁超过截止时间")
        return remaining

    async def _unlock_names(
        self,
        connection: AsyncConnection,
        lock_names: tuple[str, ...],
    ) -> None:
        try:
            for lock_name in reversed(lock_names):
                unlocked = await connection.scalar(
                    text(
                        "SELECT pg_advisory_unlock("
                        "hashtextextended(:lock_name, 0))"
                    ),
                    {"lock_name": lock_name},
                )
                if unlocked is not True:
                    raise RuntimeError("内容分析数据库锁释放失败")
        except BaseException:
            if not connection.invalidated:
                await connection.invalidate()
            raise

    async def _try_lock_names(
        self,
        connection: AsyncConnection,
        lock_names: tuple[str, ...],
    ) -> bool:
        acquired: list[str] = []
        try:
            for lock_name in lock_names:
                locked = await connection.scalar(
                    text(
                        "SELECT pg_try_advisory_lock("
                        "hashtextextended(:lock_name, 0))"
                    ),
                    {"lock_name": lock_name},
                )
                if locked is not True:
                    await self._unlock_names(connection, tuple(acquired))
                    return False
                acquired.append(lock_name)
            return True
        except BaseException:
            if acquired and not connection.invalidated:
                try:
                    await self._unlock_names(connection, tuple(acquired))
                except BaseException:
                    pass
            if not connection.invalidated:
                try:
                    await connection.invalidate()
                except BaseException:
                    pass
            raise

    @asynccontextmanager
    async def _advisory_guard(
        self,
        lock_names: tuple[str, ...],
        deadline_at: datetime,
    ):
        names = tuple(sorted(set(lock_names) - self._guard_lock_names))
        lock_engine = self._lock_engine()
        current = self._clock()
        if not isinstance(current, datetime) or current.tzinfo is None:
            raise ValueError("内容分析数据库锁时钟无效")
        monotonic_deadline = (
            asyncio.get_running_loop().time()
            + max(0.0, (deadline_at - current).total_seconds())
        )
        owns_connection = self._guard_connection is None
        connection = self._guard_connection
        semaphore = _guard_semaphore(lock_engine) if owns_connection else None
        slot_acquired = False
        names_acquired = False
        try:
            if semaphore is not None:
                await asyncio.wait_for(
                    semaphore.acquire(),
                    timeout=self._lock_timeout(deadline_at, monotonic_deadline),
                )
                slot_acquired = True
            while connection is None:
                connection = await asyncio.wait_for(
                    lock_engine.connect(),
                    timeout=self._lock_timeout(deadline_at, monotonic_deadline),
                )
                if await self._try_lock_names(connection, names):
                    self._guard_connection = connection
                    names_acquired = True
                    break
                await connection.close()
                connection = None
                await asyncio.sleep(
                    min(0.05, self._lock_timeout(deadline_at, monotonic_deadline))
                )
            while (
                names
                and not names_acquired
                and not await self._try_lock_names(connection, names)
            ):
                await asyncio.sleep(
                    min(0.05, self._lock_timeout(deadline_at, monotonic_deadline))
                )
            names_acquired = True
            self._guard_lock_names.update(names)
            yield
        finally:
            cleanup_error: BaseException | None = None
            if (
                connection is not None
                and names_acquired
                and names
                and not connection.invalidated
            ):
                try:
                    await self._unlock_names(connection, names)
                except BaseException as exc:
                    cleanup_error = exc
            self._guard_lock_names.difference_update(names)
            if owns_connection:
                self._guard_connection = None
                self._guard_lock_names.clear()
                if connection is not None:
                    try:
                        await connection.close()
                    except BaseException as exc:
                        if cleanup_error is None:
                            cleanup_error = exc
                if semaphore is not None and slot_acquired:
                    semaphore.release()
            if self._session.in_transaction():
                try:
                    await self._session.rollback()
                except BaseException as exc:
                    if cleanup_error is None:
                        cleanup_error = exc
            if cleanup_error is not None:
                raise cleanup_error

    def analysis_guard(self, envelope: ContentAnalysisTaskEnvelope):
        """跨进程串行化同一分析幂等键。"""
        lock_names = [
            f"content-analysis:analysis:{envelope.idempotency.analysis_key}"
        ]
        if envelope.execution.kind.value == "weekly_batch_finalize":
            lock_names.append(
                "content-analysis:weekly-batch:"
                f"{envelope.execution.weekly_batch_id}"
            )
        return self._advisory_guard(tuple(lock_names), envelope.deadline_at)

    def delivery_guard(self, envelope: ContentAnalysisTaskEnvelope):
        """串行化共享目录创建以及同一周报文档更新。"""
        root_ref = envelope.delivery_target.report_root_ref
        relative_parts = PurePosixPath(
            envelope.delivery_target.relative_directory
        ).parts
        directory_keys: list[str] = []
        for index in range(1, len(relative_parts) + 1):
            directory_keys.append(
                "content-analysis:directory-path:"
                f"{root_ref}:{'/'.join(relative_parts[:index])}"
            )
        return self._advisory_guard(
            tuple(
                directory_keys
                + [
                    "content-analysis:document:"
                    f"{envelope.idempotency.document_key}"
                ]
            ),
            envelope.deadline_at,
        )

    async def _existing(self, result_key: str) -> ContentAnalysisResult | None:
        return await self._session.scalar(
            select(ContentAnalysisResult).where(
                ContentAnalysisResult.result_key == result_key
            )
        )

    async def validate_system_user(self, user_id: int) -> bool:
        if type(user_id) is not int or user_id <= 0:
            return False
        user = await self._session.get(User, user_id)
        return is_valid_content_analysis_system_user(user)

    async def validate_internal_retry_origin(
        self,
        envelope: ContentAnalysisTaskEnvelope,
    ) -> bool:
        """把系统内部重试绑定到当前 TaskJob 已保存的不可变输入。"""
        if (
            envelope.run_type.value != "retry"
            or envelope.trigger_source.value != "system"
            or envelope.retry_of_task_id != envelope.task_id
        ):
            return False
        task = await self._session.get(TaskJob, envelope.task_id)
        if task is None or task.task_no != envelope.task_no:
            return False
        expected_tool = {
            "content_analysis_daily": "content-analysis-daily",
            "content_analysis_weekly": "content-analysis-weekly",
        }[envelope.task_code.value]
        if task.tool_code != expected_tool:
            return False
        payload = task.input_payload
        if not isinstance(payload, Mapping):
            return False
        execution = envelope.execution
        if execution.kind.value == "project":
            expected_execution = {
                "object_type": "project",
                "project_id": int(execution.project_id),
            }
        elif execution.kind.value == "account":
            expected_execution = {
                "object_type": "account",
                "account_key": execution.sec_uid,
                "project_ids": [int(item) for item in execution.project_ids],
                "weekly_batch_id": execution.weekly_batch_id,
                "batch_size": execution.batch_size,
                "batch_position": execution.batch_position,
            }
        else:
            expected_execution = {
                "object_type": "weekly_batch_finalize",
                "project_ids": [int(item) for item in execution.project_ids],
                "weekly_batch_id": execution.weekly_batch_id,
                "batch_size": execution.batch_size,
                "finalize_version": execution.finalize_version,
            }
        stored_execution = payload.get("execution")
        stored_delivery = payload.get("delivery_target")
        stored_keys = payload.get("idempotency")
        expected_window = {
            "start": envelope.window_start.isoformat(),
            "end": envelope.window_end.isoformat(),
            "timezone": "Asia/Shanghai",
            "end_exclusive": True,
        }
        expected_keys = {
            "run_key": envelope.idempotency.analysis_key,
            "internal_result_key": envelope.idempotency.result_key,
            "document_key": envelope.idempotency.document_key,
        }
        matches_original = bool(
            payload.get("contract_version") == "2.0"
            and payload.get("agent_code") == "content-analysis"
            and payload.get("task_code")
            == ("daily" if envelope.task_code.value.endswith("daily") else "weekly")
            and payload.get("business_date") == envelope.business_date.isoformat()
            and payload.get("analysis_window") == expected_window
            and payload.get("triggered_at") == envelope.triggered_at.isoformat()
            and payload.get("deadline_at") == envelope.deadline_at.isoformat()
            and isinstance(stored_execution, Mapping)
            and dict(stored_execution) == expected_execution
            and isinstance(stored_delivery, Mapping)
            and stored_delivery.get("report_root_ref")
            == envelope.delivery_target.report_root_ref
            and stored_delivery.get("scope") == envelope.delivery_target.scope.value
            and (
                envelope.delivery_target.scope is not DeliveryScope.TEST
                or stored_delivery.get("test_subdirectory")
                == envelope.delivery_target.relative_directory
            )
            and isinstance(stored_keys, Mapping)
            and all(stored_keys.get(key) == value for key, value in expected_keys.items())
        )
        if not matches_original:
            return False
        if execution.kind.value == "weekly_batch_finalize":
            return await self._is_current_finalize_version(envelope)
        return True

    async def validate_manual_finalize_retry_origin(
        self,
        envelope: ContentAnalysisTaskEnvelope,
    ) -> bool:
        """只允许对仍是当前版本的失败收尾任务做完整人工重试。"""
        execution = envelope.execution
        if not (
            execution.kind.value == "weekly_batch_finalize"
            and envelope.run_type.value == "retry"
            and envelope.retry_mode is not None
            and envelope.retry_mode.value == "full"
            and envelope.trigger_source.value == "user"
            and envelope.delivery_target.scope is DeliveryScope.FORMAL
            and type(envelope.retry_of_task_id) is int
            and envelope.retry_of_task_id > 0
        ):
            return False
        original = await self._session.get(TaskJob, envelope.retry_of_task_id)
        if (
            original is None
            or original.status != "failed"
            or original.tool_code != "content-analysis-weekly"
            or not isinstance(original.input_payload, Mapping)
            or not isinstance(original.result_summary, Mapping)
            or original.result_summary.get("failure_stage") in {None, "delivery"}
            or self._is_delivery_only_retry(original.input_payload)
        ):
            return False
        if not await self._manual_retry_task_matches(envelope):
            return False
        if not self._finalize_origin_matches(envelope, original):
            return False
        return await self._is_current_finalize_version(envelope)

    async def validate_manual_retry_origin(
        self,
        envelope: ContentAnalysisTaskEnvelope,
    ) -> bool:
        """把日报/账号人工完整重试绑定到同隔离域的失败原任务。"""
        execution = envelope.execution
        if not (
            execution.kind.value in {"project", "account"}
            and envelope.run_type.value == "retry"
            and envelope.retry_mode is not None
            and envelope.retry_mode.value == "full"
            and envelope.trigger_source.value == "user"
            and type(envelope.retry_of_task_id) is int
            and envelope.retry_of_task_id > 0
        ):
            return False
        original = await self._session.get(TaskJob, envelope.retry_of_task_id)
        expected_tool = (
            "content-analysis-daily"
            if execution.kind.value == "project"
            else "content-analysis-weekly"
        )
        if (
            original is None
            or original.status != "failed"
            or original.tool_code != expected_tool
            or not isinstance(original.input_payload, Mapping)
            or not isinstance(original.result_summary, Mapping)
            or original.result_summary.get("failure_stage") in {None, "delivery"}
            or self._is_delivery_only_retry(original.input_payload)
        ):
            return False
        return bool(
            await self._manual_retry_task_matches(envelope)
            and self._task_origin_matches(envelope, original)
        )

    async def validate_manual_redelivery_origin(
        self,
        envelope: ContentAnalysisTaskEnvelope,
        internal_result_id: int,
    ) -> bool:
        """把日报/账号人工补投绑定到投递失败原任务及其不可变结果。"""
        execution = envelope.execution
        if not (
            execution.kind.value in {"project", "account"}
            and envelope.run_type.value == "retry"
            and envelope.retry_mode is not None
            and envelope.retry_mode.value == "delivery_only"
            and envelope.trigger_source.value == "user"
            and type(envelope.retry_of_task_id) is int
            and envelope.retry_of_task_id > 0
            and type(internal_result_id) is int
            and internal_result_id > 0
        ):
            return False
        original = await self._session.get(TaskJob, envelope.retry_of_task_id)
        expected_tool = (
            "content-analysis-daily"
            if execution.kind.value == "project"
            else "content-analysis-weekly"
        )
        summary = (
            original.result_summary
            if original is not None and isinstance(original.result_summary, Mapping)
            else {}
        )
        internal = summary.get("internal_result")
        delivery = summary.get("delivery")
        if (
            original is None
            or original.status != "failed"
            or original.tool_code != expected_tool
            or summary.get("failure_stage") != "delivery"
            or not isinstance(internal, Mapping)
            or internal.get("status") != "success"
            or internal.get("internal_result_id") != str(internal_result_id)
            or not isinstance(delivery, Mapping)
            or delivery.get("status") != "failed"
            or not await self._manual_retry_task_matches(envelope)
            or not self._task_origin_matches(envelope, original)
        ):
            return False
        try:
            result_owner = await self._delivery_retry_result_owner(
                original,
                internal_result_id,
                expected_tool=expected_tool,
                allow_latest_success=False,
            )
        except ValueError:
            return False
        result = await self._session.get(ContentAnalysisResult, internal_result_id)
        output = (
            await self._session.get(Output, result.output_id)
            if result is not None
            else None
        )
        if (
            result is None
            or result.task_id != result_owner.id
            or output is None
            or output.id != result.output_id
            or output.task_id != result_owner.id
            or output.deleted_at is not None
        ):
            return False
        try:
            self._assert_result_matches_envelope(result, envelope)
        except ValueError:
            return False
        return True

    async def validate_current_finalize_version(
        self,
        envelope: ContentAnalysisTaskEnvelope,
    ) -> bool:
        """自动收尾执行前必须仍是同批次最新权威版本。"""
        if not (
            envelope.execution.kind.value == "weekly_batch_finalize"
            and envelope.run_type.value == "auto"
            and envelope.delivery_target.scope is DeliveryScope.FORMAL
        ):
            return False
        return await self._is_current_finalize_version(envelope)

    @staticmethod
    def _is_delivery_only_retry(payload: Mapping[str, Any]) -> bool:
        retry = payload.get("retry")
        return bool(
            payload.get("run_type") in {"manual_retry", "retry"}
            and isinstance(retry, Mapping)
            and retry.get("mode") == "delivery_only"
        )

    @staticmethod
    def _redelivery_payloads_match(
        retry_payload: Mapping[str, Any],
        parent_payload: Mapping[str, Any],
    ) -> bool:
        """仅投递链每一跳都保持同一业务对象、结果键和投递目标。"""
        retry_delivery = retry_payload.get("delivery_target")
        parent_delivery = parent_payload.get("delivery_target")
        retry_keys = retry_payload.get("idempotency")
        parent_keys = parent_payload.get("idempotency")
        if not all(
            isinstance(value, Mapping)
            for value in (
                retry_delivery,
                parent_delivery,
                retry_keys,
                parent_keys,
            )
        ):
            return False
        if any(
            retry_payload.get(field) != parent_payload.get(field)
            for field in (
                "contract_version",
                "agent_code",
                "task_code",
                "business_date",
                "analysis_window",
                "execution",
            )
        ):
            return False
        if any(
            retry_delivery.get(field) != parent_delivery.get(field)
            for field in ("report_root_ref", "scope")
        ):
            return False
        if (
            retry_delivery.get("scope") == DeliveryScope.TEST.value
            and retry_delivery.get("test_subdirectory")
            != parent_delivery.get("test_subdirectory")
        ):
            return False
        return all(
            retry_keys.get(field) == parent_keys.get(field)
            for field in ("internal_result_key", "document_key")
        )

    @staticmethod
    def _delivery_task_summary_matches(
        task: TaskJob,
        result_id: int,
        *,
        allow_success: bool,
    ) -> bool:
        payload = task.input_payload
        summary = task.result_summary
        if not isinstance(payload, Mapping) or not isinstance(summary, Mapping):
            return False
        identity = payload.get("task_identity")
        internal = summary.get("internal_result")
        delivery = summary.get("delivery")
        if (
            not isinstance(identity, Mapping)
            or identity.get("task_id") != task.id
            or identity.get("task_no") != task.task_no
            or identity.get("agent_code") != "content-analysis"
            or not isinstance(internal, Mapping)
            or internal.get("status") != "success"
            or internal.get("internal_result_id") != str(result_id)
            or not isinstance(delivery, Mapping)
        ):
            return False
        if task.status == "failed":
            return bool(
                summary.get("failure_stage") == "delivery"
                and delivery.get("status") == "failed"
            )
        return bool(
            allow_success
            and task.status == "success"
            and summary.get("failure_stage") is None
            and delivery.get("status") == "success"
        )

    async def _delivery_retry_result_owner(
        self,
        task: TaskJob,
        result_id: int,
        *,
        expected_tool: str,
        allow_latest_success: bool,
    ) -> TaskJob:
        """沿任务配置实际保存的人工补投链定位不可变结果所属任务。"""
        current = task
        visited: set[int] = set()
        first = True
        while True:
            if (
                current.id in visited
                or current.tool_code != expected_tool
                or not self._delivery_task_summary_matches(
                    current,
                    result_id,
                    allow_success=allow_latest_success and first,
                )
            ):
                raise ValueError("仅投递重试链与内部结果不一致")
            visited.add(current.id)
            payload = current.input_payload
            if not isinstance(payload, Mapping) or not self._is_delivery_only_retry(
                payload
            ):
                return current
            retry = payload.get("retry")
            if not (
                isinstance(retry, Mapping)
                and type(retry.get("retry_of_task_id")) is int
                and retry["retry_of_task_id"] > 0
                and isinstance(retry.get("request_id"), str)
                and bool(retry["request_id"].strip())
            ):
                raise ValueError("仅投递重试链缺少来源任务")
            parent = await self._session.get(TaskJob, retry["retry_of_task_id"])
            parent_payload = (
                parent.input_payload
                if parent is not None and isinstance(parent.input_payload, Mapping)
                else None
            )
            if (
                parent is None
                or not isinstance(parent_payload, Mapping)
                or not self._redelivery_payloads_match(payload, parent_payload)
            ):
                raise ValueError("仅投递重试链投递目标或业务身份漂移")
            current = parent
            first = False

    async def _manual_retry_task_matches(
        self,
        envelope: ContentAnalysisTaskEnvelope,
    ) -> bool:
        """把人工重试信封绑定到任务配置实际创建的当前 TaskJob。"""
        task = await self._session.get(TaskJob, envelope.task_id)
        if (
            task is None
            or task.task_no != envelope.task_no
            or task.status not in {"pending", "processing"}
            or task.tool_code
            != (
                "content-analysis-daily"
                if envelope.task_code.value.endswith("daily")
                else "content-analysis-weekly"
            )
            or not isinstance(task.input_payload, Mapping)
        ):
            return False
        payload = task.input_payload
        retry = payload.get("retry")
        identity = payload.get("task_identity")
        keys = payload.get("idempotency")
        precheck = payload.get("database_precheck")
        if not (
            payload.get("run_type") in {"manual_retry", "retry"}
            and payload.get("triggered_at") == envelope.triggered_at.isoformat()
            and payload.get("deadline_at") == envelope.deadline_at.isoformat()
            and isinstance(retry, Mapping)
            and retry.get("retry_of_task_id") == envelope.retry_of_task_id
            and retry.get("mode")
            == (envelope.retry_mode.value if envelope.retry_mode else None)
            and isinstance(envelope.request_id, str)
            and bool(envelope.request_id.strip())
            and retry.get("request_id") == envelope.request_id
            and isinstance(identity, Mapping)
            and identity.get("task_id") == envelope.task_id
            and identity.get("task_no") == envelope.task_no
            and identity.get("agent_code") == "content-analysis"
            and isinstance(keys, Mapping)
            and keys.get("run_key") == envelope.idempotency.analysis_key
            and isinstance(precheck, Mapping)
            and precheck.get("status") == envelope.precheck.status.value
            and precheck.get("input_limited") is envelope.precheck.input_limited
            and precheck.get("input_limited_reasons")
            == list(envelope.precheck.limitation_codes)
        ):
            return False
        return self._task_origin_matches(envelope, task)

    @staticmethod
    def _execution_payload(envelope: ContentAnalysisTaskEnvelope) -> dict[str, Any]:
        execution = envelope.execution
        if execution.kind.value == "project":
            return {
                "object_type": "project",
                "project_id": int(execution.project_id),
            }
        if execution.kind.value == "account":
            return {
                "object_type": "account",
                "account_key": execution.sec_uid,
                "project_ids": [int(item) for item in execution.project_ids],
                "weekly_batch_id": execution.weekly_batch_id,
                "batch_size": execution.batch_size,
                "batch_position": execution.batch_position,
            }
        return {
            "object_type": "weekly_batch_finalize",
            "project_ids": [int(item) for item in execution.project_ids],
            "weekly_batch_id": execution.weekly_batch_id,
            "batch_size": execution.batch_size,
            "finalize_version": execution.finalize_version,
        }

    def _task_origin_matches(
        self,
        envelope: ContentAnalysisTaskEnvelope,
        original: TaskJob,
    ) -> bool:
        payload = original.input_payload
        if not isinstance(payload, Mapping):
            return False
        stored_identity = payload.get("task_identity")
        stored_execution = payload.get("execution")
        stored_delivery = payload.get("delivery_target")
        stored_keys = payload.get("idempotency")
        return bool(
            payload.get("contract_version") == "2.0"
            and payload.get("agent_code") == "content-analysis"
            and payload.get("task_code")
            == (
                "daily"
                if envelope.task_code.value.endswith("daily")
                else "weekly"
            )
            and isinstance(stored_identity, Mapping)
            and stored_identity.get("task_id") == original.id
            and stored_identity.get("task_no") == original.task_no
            and stored_identity.get("agent_code") == "content-analysis"
            and payload.get("business_date") == envelope.business_date.isoformat()
            and payload.get("analysis_window")
            == {
                "start": envelope.window_start.isoformat(),
                "end": envelope.window_end.isoformat(),
                "timezone": "Asia/Shanghai",
                "end_exclusive": True,
            }
            and isinstance(stored_execution, Mapping)
            and dict(stored_execution) == self._execution_payload(envelope)
            and isinstance(stored_delivery, Mapping)
            and stored_delivery.get("report_root_ref")
            == envelope.delivery_target.report_root_ref
            and stored_delivery.get("scope")
            == envelope.delivery_target.scope.value
            and (
                envelope.delivery_target.scope is not DeliveryScope.TEST
                or stored_delivery.get("test_subdirectory")
                == envelope.delivery_target.relative_directory
            )
            and isinstance(stored_keys, Mapping)
            and stored_keys.get("internal_result_key")
            == envelope.idempotency.result_key
            and stored_keys.get("document_key")
            == envelope.idempotency.document_key
        )

    def _finalize_origin_matches(
        self,
        envelope: ContentAnalysisTaskEnvelope,
        original: TaskJob,
    ) -> bool:
        return bool(
            envelope.execution.kind.value == "weekly_batch_finalize"
            and envelope.delivery_target.scope is DeliveryScope.FORMAL
            and self._task_origin_matches(envelope, original)
        )

    async def _is_current_finalize_version(
        self,
        envelope: ContentAnalysisTaskEnvelope,
    ) -> bool:
        """以同批次最新自动收尾为权威版本，人工重试编号不可绕过。"""
        execution = envelope.execution
        latest = await self._session.scalar(
            select(TaskJob)
            .where(
                TaskJob.tool_code == "content-analysis-weekly",
                TaskJob.input_payload["agent_code"].astext == "content-analysis",
                TaskJob.input_payload["task_code"].astext == "weekly",
                TaskJob.input_payload["run_type"].astext == "auto",
                TaskJob.input_payload["business_date"].astext
                == envelope.business_date.isoformat(),
                TaskJob.input_payload["analysis_window"]["start"].astext
                == envelope.window_start.isoformat(),
                TaskJob.input_payload["analysis_window"]["end"].astext
                == envelope.window_end.isoformat(),
                TaskJob.input_payload["analysis_window"]["timezone"].astext
                == "Asia/Shanghai",
                TaskJob.input_payload["analysis_window"]["end_exclusive"].astext
                == "true",
                TaskJob.input_payload["delivery_target"]["scope"].astext
                == "formal",
                TaskJob.input_payload["delivery_target"]["report_root_ref"].astext
                == envelope.delivery_target.report_root_ref,
                TaskJob.input_payload["idempotency"]["document_key"].astext
                == envelope.idempotency.document_key,
                TaskJob.input_payload["execution"]["object_type"].astext
                == "weekly_batch_finalize",
                TaskJob.input_payload["execution"]["weekly_batch_id"].astext
                == execution.weekly_batch_id,
            )
            .order_by(TaskJob.id.desc())
            .limit(1)
        )
        if latest is None or not isinstance(latest.input_payload, Mapping):
            return False
        latest_execution = latest.input_payload.get("execution")
        return bool(
            isinstance(latest_execution, Mapping)
            and latest_execution.get("finalize_version")
            == execution.finalize_version
        )

    async def validate_finalize_redelivery_origin(
        self,
        envelope: ContentAnalysisTaskEnvelope,
        internal_result_id: int,
    ) -> bool:
        """拒绝无来源或已经落后于新收尾版本的周报补投。"""
        execution = envelope.execution
        if not (
            execution.kind.value == "weekly_batch_finalize"
            and envelope.run_type.value == "retry"
            and envelope.retry_mode is not None
            and envelope.retry_mode.value == "delivery_only"
            and envelope.trigger_source.value in {"system", "user"}
            and envelope.delivery_target.scope is DeliveryScope.FORMAL
            and type(envelope.retry_of_task_id) is int
            and envelope.retry_of_task_id > 0
            and type(internal_result_id) is int
            and internal_result_id > 0
        ):
            return False
        original = await self._session.get(TaskJob, envelope.retry_of_task_id)
        result_summary = (
            original.result_summary
            if original is not None and isinstance(original.result_summary, Mapping)
            else {}
        )
        internal_summary = result_summary.get("internal_result")
        delivery_summary = result_summary.get("delivery")
        expected_original_status = (
            {"pending", "processing"}
            if envelope.trigger_source.value == "system"
            else {"failed"}
        )
        if (
            original is None
            or original.status not in expected_original_status
            or original.tool_code != "content-analysis-weekly"
            or result_summary.get("failure_stage") != "delivery"
            or not isinstance(internal_summary, Mapping)
            or internal_summary.get("status") != "success"
            or internal_summary.get("internal_result_id")
            != str(internal_result_id)
            or not isinstance(delivery_summary, Mapping)
            or delivery_summary.get("status") != "failed"
            or not self._finalize_origin_matches(envelope, original)
        ):
            return False
        if envelope.trigger_source.value == "system":
            if envelope.retry_of_task_id != envelope.task_id:
                return False
        elif not await self._manual_retry_task_matches(envelope):
            return False
        return await self._is_current_finalize_version(envelope)

    async def load_pending_manual_openings(
        self,
        project_id: str,
    ) -> tuple[ManualOpeningCandidate, ...]:
        numeric_project_id = int(project_id)
        rows = (
            await self._session.execute(
                select(ContentAnalysisLibraryItem, KolReference)
                .join(
                    KolReference,
                    KolReference.id
                    == ContentAnalysisLibraryItem.kol_reference_id,
                )
                .where(
                    ContentAnalysisLibraryItem.project_id == numeric_project_id,
                    ContentAnalysisLibraryItem.category == "qianchuan",
                    ContentAnalysisLibraryItem.ingestion_source == "manual",
                    ContentAnalysisLibraryItem.opening_status == "unannotated",
                    ContentAnalysisLibraryItem.availability == "enabled",
                    KolReference.deleted_at.is_(None),
                )
                .order_by(ContentAnalysisLibraryItem.id)
            )
        ).all()
        return tuple(
            ManualOpeningCandidate(
                item_id=item.id,
                project_id=item.project_id,
                title=reference.title or "",
                transcript=reference.content or "",
            )
            for item, reference in rows
        )

    async def load_weekly_batch_finalize_summary(
        self,
        envelope: ContentAnalysisTaskEnvelope,
    ) -> Mapping[str, Any]:
        """按严格运行域读取一个周批次各账号的最新终态。"""
        execution = envelope.execution
        if execution.kind.value != "weekly_batch_finalize":
            raise ValueError("只有周批次收尾能够读取批次终态")
        jobs = tuple(
            (
                await self._session.scalars(
                    select(TaskJob)
                    .where(
                        TaskJob.tool_code == "content-analysis-weekly",
                        TaskJob.input_payload["agent_code"].astext
                        == "content-analysis",
                        TaskJob.input_payload["task_code"].astext == "weekly",
                        TaskJob.input_payload["business_date"].astext
                        == envelope.business_date.isoformat(),
                        TaskJob.input_payload["analysis_window"]["start"].astext
                        == envelope.window_start.isoformat(),
                        TaskJob.input_payload["analysis_window"]["end"].astext
                        == envelope.window_end.isoformat(),
                        TaskJob.input_payload["analysis_window"]["timezone"].astext
                        == "Asia/Shanghai",
                        TaskJob.input_payload["analysis_window"]["end_exclusive"].astext
                        == "true",
                        TaskJob.input_payload["delivery_target"]["scope"].astext
                        == envelope.delivery_target.scope.value,
                        TaskJob.input_payload["delivery_target"]["report_root_ref"].astext
                        == envelope.delivery_target.report_root_ref,
                        TaskJob.input_payload["idempotency"]["document_key"].astext
                        == envelope.idempotency.document_key,
                        TaskJob.input_payload["execution"]["object_type"].astext
                        == "account",
                        TaskJob.input_payload["execution"]["weekly_batch_id"].astext
                        == execution.weekly_batch_id,
                    )
                    .order_by(TaskJob.id)
                )
            ).all()
        )
        latest: dict[str, TaskJob] = {}
        for job in jobs:
            payload = job.input_payload
            job_execution = (
                payload.get("execution") if isinstance(payload, Mapping) else None
            )
            if not isinstance(job_execution, Mapping):
                raise ValueError("周账号任务执行对象无效")
            sec_uid = job_execution.get("account_key")
            if not isinstance(sec_uid, str) or not sec_uid.strip():
                raise ValueError("周账号任务缺少稳定账号身份")
            if (
                job_execution.get("batch_size") != execution.batch_size
                or type(job_execution.get("batch_position")) is not int
            ):
                raise ValueError("周账号任务批次位置无效")
            project_ids = job_execution.get("project_ids")
            if (
                not isinstance(project_ids, list)
                or any(type(item) is not int or item <= 0 for item in project_ids)
                or not set(str(item) for item in project_ids).issubset(
                    execution.project_ids
                )
            ):
                raise ValueError("周账号任务项目范围超出收尾范围")
            latest[sec_uid.strip()] = job
        if len(latest) != execution.batch_size:
            raise ValueError("周批次声明账号数量与任务数量不一致")
        positions = {
            job.input_payload["execution"]["batch_position"]
            for job in latest.values()
        }
        if positions != set(range(1, execution.batch_size + 1)):
            raise ValueError("周批次账号位置不完整")

        account_results: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for sec_uid in sorted(latest):
            job = latest[sec_uid]
            if job.status not in {"success", "failed", "not_run"}:
                raise ValueError("周批次仍有账号未进入终态")
            summary = (
                job.result_summary
                if isinstance(job.result_summary, Mapping)
                else {}
            )
            if job.status == "success":
                internal = summary.get("internal_result")
                if (
                    not isinstance(internal, Mapping)
                    or internal.get("status") != "success"
                    or internal.get("outcome") not in {"content", "no_content"}
                ):
                    raise ValueError("周账号成功终态缺少有效内部结果")
                state = (
                    "no_content"
                    if internal.get("outcome") == "no_content"
                    else "success"
                )
                reason_code = None
                baseline = await self._load_weekly_account_baseline(
                    envelope,
                    job,
                    sec_uid,
                    state,
                    internal,
                )
            else:
                state = "failed"
                failure_stage = summary.get("failure_stage")
                failure_layer = {
                    "data_source": summary.get("feishu_relation"),
                    "analysis": summary.get("internal_result"),
                    "internal_result": summary.get("internal_result"),
                    "delivery": summary.get("delivery"),
                }.get(failure_stage)
                failure_layer = (
                    failure_layer if isinstance(failure_layer, Mapping) else {}
                )
                raw_reason_code = (
                    failure_layer.get("reason_code")
                    or summary.get("reason_code")
                    or job.error_code
                    or ("NOT_RUN" if job.status == "not_run" else "ACCOUNT_FAILED")
                )
                reason_code = (
                    raw_reason_code
                    if raw_reason_code in _SAFE_ACCOUNT_FAILURE_REASON_CODES
                    else "ACCOUNT_FAILED"
                )
                failures.append(
                    {
                        "account_hash": self._account_hash(sec_uid),
                        "reason_code": reason_code,
                        "public_message": "账号周任务执行失败",
                    }
                )
                baseline = {
                    "sample_count": None,
                    "mean_likes": None,
                    "median_likes": None,
                    "maximum_likes": None,
                    "minimum_likes": None,
                    "baseline_updated_at": None,
                    "unavailable_reason": "账号周任务执行失败",
                }
            updated_at = job.finished_at or job.updated_at or job.created_at
            if updated_at is None:
                raise ValueError("周账号终态缺少更新时间")
            account_results.append(
                {
                    (
                        "account_hash" if state == "failed" else "sec_uid"
                    ): (
                        self._account_hash(sec_uid)
                        if state == "failed"
                        else sec_uid
                    ),
                    "status": state,
                    "reason_code": reason_code,
                    "updated_at": updated_at.astimezone(
                        envelope.window_end.tzinfo
                    ).isoformat(),
                    "project_ids": [
                        str(item)
                        for item in job.input_payload["execution"]["project_ids"]
                    ],
                    **baseline,
                }
            )
        success_count = sum(
            1 for item in account_results if item["status"] == "success"
        )
        no_content_count = sum(
            1 for item in account_results if item["status"] == "no_content"
        )
        calculable_count = sum(
            1
            for item in account_results
            if type(item["sample_count"]) is int and item["sample_count"] > 0
        )
        return {
            "weekly_batch_id": execution.weekly_batch_id,
            "finalize_version": execution.finalize_version,
            "selected_project_ids": list(execution.project_ids),
            "account_count": execution.batch_size,
            "success_account_count": success_count,
            "no_content_account_count": no_content_count,
            "failed_account_count": len(failures),
            "pending_account_count": 0,
            "calculable_account_count": calculable_count,
            "failures": failures,
            "account_results": account_results,
            "unavailable_reason": (
                "本批次没有账号实例"
                if execution.batch_size == 0
                else "本批次没有可计算账号"
                if calculable_count == 0
                else None
            ),
        }

    @staticmethod
    def _account_hash(sec_uid: str) -> str:
        return "sha256:" + hashlib.sha256(sec_uid.encode("utf-8")).hexdigest()

    async def _load_weekly_account_baseline(
        self,
        envelope: ContentAnalysisTaskEnvelope,
        job: TaskJob,
        sec_uid: str,
        state: str,
        internal: Mapping[str, Any],
    ) -> dict[str, Any]:
        raw_result_id = internal.get("internal_result_id")
        if type(raw_result_id) is int:
            result_id = raw_result_id
        elif (
            isinstance(raw_result_id, str)
            and raw_result_id.isascii()
            and raw_result_id.isdigit()
            and not raw_result_id.startswith("0")
        ):
            result_id = int(raw_result_id)
        else:
            raise ValueError("周账号成功终态缺少有效内部结果编号")
        if result_id <= 0:
            raise ValueError("周账号成功终态缺少有效内部结果编号")

        result_owner = await self._weekly_account_result_owner(
            envelope,
            job,
            result_id,
        )

        result = await self._session.get(ContentAnalysisResult, result_id)
        output = (
            await self._session.get(Output, result.output_id)
            if result is not None
            else None
        )
        project_ids = [
            str(item) for item in job.input_payload["execution"]["project_ids"]
        ]
        expected_status = "no_content" if state == "no_content" else "success"
        if (
            result is None
            or result.task_id != result_owner.id
            or result.task_code != envelope.task_code.value
            or result.execution_kind != "account"
            or result.project_id is not None
            or result.sec_uid != sec_uid
            or sorted(result.related_project_ids, key=int)
            != sorted(project_ids, key=int)
            or result.business_date != envelope.business_date
            or result.window_start != envelope.window_start
            or result.window_end != envelope.window_end
            or result.status != expected_status
            or result.is_test
            != (envelope.delivery_target.scope is DeliveryScope.TEST)
            or output is None
            or output.id != result.output_id
            or output.task_id != result_owner.id
            or output.tool_code != envelope.task_code.value
            or output.deleted_at is not None
            or not isinstance(output.content_json, Mapping)
        ):
            raise ValueError("周账号内部结果与任务、账号或窗口不一致")

        payload = output.content_json
        if (
            payload.get("sec_uid") != sec_uid
            or payload.get("weekly_batch_id") != envelope.execution.weekly_batch_id
            or not isinstance(payload.get("project_ids"), list)
            or sorted(payload["project_ids"], key=int)
            != sorted(project_ids, key=int)
        ):
            raise ValueError("周账号内部结果正文与任务范围不一致")
        baseline = payload.get("baseline")
        if not isinstance(baseline, Mapping):
            raise ValueError("周账号内部结果缺少有效基准结构")
        if (
            baseline.get("account_id") != sec_uid
            or baseline.get("window_start") != envelope.window_start.isoformat()
            or baseline.get("window_end") != envelope.window_end.isoformat()
        ):
            raise ValueError("周账号基准身份或窗口不一致")
        updated_at = self._validated_baseline_updated_at(
            baseline.get("updated_at"),
            envelope,
        )
        status = baseline.get("status")
        values = baseline.get("baseline")
        unavailable_reason = baseline.get("unavailable_reason")
        if status == "unavailable":
            if (
                values is not None
                or not isinstance(unavailable_reason, str)
                or not unavailable_reason.strip()
            ):
                raise ValueError("不可计算账号基准结构无效")
            return {
                "sample_count": 0,
                "mean_likes": None,
                "median_likes": None,
                "maximum_likes": None,
                "minimum_likes": None,
                "baseline_updated_at": updated_at,
                "unavailable_reason": unavailable_reason.strip(),
            }
        if status != "available" or not isinstance(values, Mapping):
            raise ValueError("可计算账号基准结构无效")
        sample_count = values.get("sample_size")
        maximum = values.get("maximum")
        minimum = values.get("minimum")
        mean = values.get("mean")
        median = values.get("median")
        if (
            type(sample_count) is not int
            or sample_count <= 0
            or type(maximum) is not int
            or maximum < 0
            or type(minimum) is not int
            or minimum < 0
            or maximum < minimum
            or type(mean) not in {int, float}
            or not isfinite(float(mean))
            or mean < minimum
            or mean > maximum
            or type(median) not in {int, float}
            or not isfinite(float(median))
            or median < minimum
            or median > maximum
            or unavailable_reason is not None
        ):
            raise ValueError("可计算账号基准五项统计无效")
        return {
            "sample_count": sample_count,
            "mean_likes": float(mean),
            "median_likes": float(median),
            "maximum_likes": maximum,
            "minimum_likes": minimum,
            "baseline_updated_at": updated_at,
            "unavailable_reason": None,
        }

    async def _weekly_account_result_owner(
        self,
        envelope: ContentAnalysisTaskEnvelope,
        job: TaskJob,
        result_id: int,
    ) -> TaskJob:
        """仅投递新任务复用原不可变结果时，返回经过严格校验的原任务。"""
        payload = job.input_payload
        if not isinstance(payload, Mapping) or not self._is_delivery_only_retry(payload):
            return job
        return await self._delivery_retry_result_owner(
            job,
            result_id,
            expected_tool="content-analysis-weekly",
            allow_latest_success=True,
        )

    @staticmethod
    def _validated_baseline_updated_at(
        raw: object,
        envelope: ContentAnalysisTaskEnvelope,
    ) -> str:
        if not isinstance(raw, str):
            raise ValueError("账号基准缺少有效更新时间")
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError("账号基准缺少有效更新时间") from exc
        if parsed.tzinfo is None:
            raise ValueError("账号基准缺少有效更新时间")
        return parsed.astimezone(envelope.window_end.tzinfo).isoformat()

    async def find_persisted_result(
        self,
        envelope: ContentAnalysisTaskEnvelope,
    ) -> PersistedResult | None:
        result = await self._existing(envelope.idempotency.result_key)
        if result is None:
            return None
        self._assert_result_matches_envelope(result, envelope)
        return PersistedResult(
            internal_result_id=result.id,
            output_id=result.output_id,
            result_key=result.result_key,
            created=False,
            status=InternalResultStatus(result.status),
        )

    @staticmethod
    def _library_content_key(item: ContentAnalysisLibraryItem) -> str:
        if item.platform_content_id:
            return f"platform_content_id:{item.platform_content_id}"
        if item.external_url:
            return f"external_url:{item.external_url}"
        return f"library_item_id:{item.id}"

    @staticmethod
    def _library_identity_keys(item: ContentAnalysisLibraryItem) -> tuple[str, ...]:
        keys = []
        if item.platform_content_id:
            keys.append(f"platform_content_id:{item.platform_content_id}")
        if item.external_url:
            keys.append(f"external_url:{item.external_url}")
        return tuple(keys)

    @staticmethod
    def _saved_states_from_payload(
        payload: Mapping[str, Any],
        project_id: str,
        saved_library_keys: set[str],
    ) -> tuple[SavedBusinessState, ...]:
        reports = payload.get("reports")
        if not isinstance(reports, Mapping):
            raise ValueError("历史日报正文缺少项目映射")
        report = reports.get(project_id)
        if not isinstance(report, Mapping):
            raise ValueError("历史日报正文缺少当前项目")

        def sequence(name: str) -> list[Mapping[str, Any]]:
            value = report.get(name, [])
            if not isinstance(value, list) or any(
                not isinstance(item, Mapping) for item in value
            ):
                raise ValueError(f"历史日报 {name} 结构无效")
            return value

        persona = sequence("persona_opportunities")
        qianchuan = sequence("qianchuan_opportunities")
        ranks: dict[str, int] = {}
        for candidates in (persona, qianchuan):
            for rank, item in enumerate(candidates, start=1):
                stable_key = item.get("stable_key")
                if isinstance(stable_key, str) and stable_key.strip():
                    ranks[stable_key] = rank
        opportunity_keys = set(ranks)
        library_keys = set(saved_library_keys)
        for item in sequence("library_candidates"):
            stable_key = item.get("stable_key")
            if isinstance(stable_key, str) and stable_key.strip():
                library_keys.add(stable_key)
        cross_keys: set[str] = set()
        for candidate in sequence("cross_project_candidates"):
            sources = candidate.get("sources", [])
            if not isinstance(sources, list):
                raise ValueError("历史日报跨项目来源结构无效")
            for source in sources:
                if (
                    isinstance(source, Mapping)
                    and source.get("project_id") == project_id
                    and isinstance(source.get("content_key"), str)
                ):
                    cross_keys.add(source["content_key"])

        state_items = (
            sequence("all_window_items")
            if "all_window_items" in report
            else sequence("items")
        )
        states_by_key: dict[str, SavedBusinessState] = {}
        for item in state_items:
            stable_key = item.get("stable_key")
            assessment = item.get("assessment")
            if not isinstance(stable_key, str) or not stable_key.strip():
                continue
            if not isinstance(assessment, Mapping):
                raise ValueError("历史日报项目判断结构无效")
            relative = item.get("persona_relative_like")
            candidate_rank = item.get("candidate_rank", ranks.get(stable_key))
            is_opportunity = item.get(
                "is_opportunity",
                stable_key in opportunity_keys,
            )
            in_library = item.get("in_library", stable_key in library_keys)
            cross_project = item.get(
                "cross_project",
                stable_key in cross_keys,
            )
            if any(
                type(value) is not bool
                for value in (is_opportunity, in_library, cross_project)
            ):
                raise ValueError("历史日报业务状态布尔值无效")
            identity_keys = [stable_key]
            analysis = item.get("analysis")
            content = analysis.get("content") if isinstance(analysis, Mapping) else None
            identity = content.get("identity") if isinstance(content, Mapping) else None
            if isinstance(identity, Mapping):
                for field_name in ("platform_content_id", "external_url"):
                    value = identity.get(field_name)
                    if isinstance(value, str) and value.strip():
                        identity_keys.append(f"{field_name}:{value}")
            for identity_key in dict.fromkeys(identity_keys):
                state = SavedBusinessState(
                    project_id=project_id,
                    stable_key=identity_key,
                    candidate_rank=candidate_rank,
                    is_opportunity=is_opportunity,
                    in_library=in_library,
                    priority=assessment.get("priority"),
                    cross_project=cross_project,
                    conclusion=assessment.get("conclusion"),
                    confidence=ConfidenceLevel(assessment.get("confidence")),
                    persona_relative_like=(
                        RelativePerformanceLevel(relative)
                        if relative is not None
                        else None
                    ),
                )
                previous = states_by_key.get(identity_key)
                if previous is not None and previous != state:
                    raise ValueError("历史日报同一稳定身份存在冲突业务状态")
                states_by_key[identity_key] = state
        return tuple(states_by_key.values())

    async def load_daily_history(
        self,
        envelope: ContentAnalysisTaskEnvelope,
        project_id: str,
        account_ids: tuple[str, ...],
    ) -> DailyHistoricalInputs:
        try:
            numeric_project_id = int(project_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("项目编号必须是整数文本") from exc
        if not account_ids:
            raise ValueError("日报历史输入必须包含账号")

        library_rows = tuple(
            (
                await self._session.scalars(
                    select(ContentAnalysisLibraryItem)
                    .join(
                        KolReference,
                        KolReference.id
                        == ContentAnalysisLibraryItem.kol_reference_id,
                    )
                    .where(KolReference.deleted_at.is_(None))
                )
            ).all()
        )
        saved_library_records: list[SavedLibraryRecord] = []
        for row in library_rows:
            analysis = row.analysis
            assessment = row.project_assessment
            if not isinstance(analysis, Mapping) or not isinstance(
                assessment,
                Mapping,
            ):
                raise ValueError("已保存项目库结构化分析无效")
            methods = analysis.get("reusable_methods", [])
            source_information = analysis.get("source_information", {})
            cross_signals = assessment.get("cross_project_signals", [])
            cross_scenarios = assessment.get("cross_project_scenarios", [])
            if not isinstance(methods, list) or not isinstance(cross_signals, list):
                raise ValueError("已保存项目库方法或信号结构无效")
            scenarios = tuple(
                scenario["statement"]
                for scenario in cross_scenarios
                if isinstance(scenario, Mapping)
                and isinstance(scenario.get("statement"), str)
                and scenario["statement"].strip()
            ) if isinstance(cross_scenarios, list) else ()
            saved_library_records.append(
                SavedLibraryRecord(
                    project_id=str(row.project_id),
                    content_key=self._library_content_key(row),
                    identity_keys=self._library_identity_keys(row),
                    available_for_reuse=row.availability == "enabled",
                    reusable_methods=tuple(
                        parse_reusable_method(method) for method in methods
                    ),
                    source_information=parse_source_information(
                        source_information
                    ),
                    signals=tuple(
                        dict.fromkeys(
                            CrossProjectSignal(value) for value in cross_signals
                        )
                    ),
                    scenarios=scenarios,
                )
            )

        baseline_rows = tuple(
            (
                await self._session.scalars(
                    select(ContentAnalysisAccountBaseline).where(
                        ContentAnalysisAccountBaseline.sec_uid.in_(account_ids),
                        ContentAnalysisAccountBaseline.window_end
                        <= envelope.window_end,
                        ContentAnalysisAccountBaseline.sample_count > 0,
                    )
                    .order_by(
                        ContentAnalysisAccountBaseline.sec_uid,
                        ContentAnalysisAccountBaseline.window_end.desc(),
                        ContentAnalysisAccountBaseline.created_at.desc(),
                    )
                )
            ).all()
        )
        latest_baseline_rows = {}
        for row in baseline_rows:
            latest_baseline_rows.setdefault(row.sec_uid, row)
        persona_baselines = tuple(
            WeeklyPersonaBaseline(
                account_id=row.sec_uid,
                window_start=row.window_start,
                window_end=row.window_end,
                baseline=LikeBaseline(
                    mean=float(row.mean_likes),
                    median=float(row.median_likes),
                    sample_size=row.sample_count,
                    maximum=row.maximum_likes,
                    minimum=row.minimum_likes,
                ),
            )
            for row in latest_baseline_rows.values()
        )

        previous = (
            await self._session.execute(
                select(ContentAnalysisResult, Output)
                .join(Output, Output.id == ContentAnalysisResult.output_id)
                .where(
                    ContentAnalysisResult.project_id == numeric_project_id,
                    ContentAnalysisResult.execution_kind == "project",
                    ContentAnalysisResult.is_test.is_(False),
                    ContentAnalysisResult.business_date < envelope.business_date,
                    Output.deleted_at.is_(None),
                )
                .order_by(
                    ContentAnalysisResult.business_date.desc(),
                    ContentAnalysisResult.created_at.desc(),
                )
                .limit(1)
            )
        ).one_or_none()
        saved_states = ()
        if previous is not None:
            _, output = previous
            if not isinstance(output.content_json, Mapping):
                raise ValueError("历史日报结构化正文无效")
            saved_states = self._saved_states_from_payload(
                output.content_json,
                project_id,
                {
                    key
                    for item in saved_library_records
                    if item.project_id == project_id
                    for key in (item.content_key, *item.identity_keys)
                },
            )
        return DailyHistoricalInputs(
            saved_states=saved_states,
            saved_library_records=tuple(saved_library_records),
            persona_baselines=persona_baselines,
        )

    @staticmethod
    def _assert_result_matches_envelope(
        result: ContentAnalysisResult,
        envelope: ContentAnalysisTaskEnvelope,
    ) -> None:
        execution = envelope.execution
        project_id = int(execution.project_id) if execution.kind.value == "project" else None
        sec_uid = execution.sec_uid if execution.kind.value == "account" else None
        if execution.kind.value == "project":
            related_project_ids = [execution.project_id]
        elif execution.kind.value == "account":
            related_project_ids = list(result.related_project_ids)
        else:
            related_project_ids = list(execution.project_ids)
        weekly_projects_valid = (
            execution.kind.value == "project"
            or result.related_project_ids == list(execution.project_ids)
        )
        finalize_version_valid = (
            execution.kind.value != "weekly_batch_finalize"
            or isinstance(result.source_receipts, Mapping)
            and isinstance(result.source_receipts.get("task_jobs"), Mapping)
            and result.source_receipts["task_jobs"].get("finalize_version")
            == execution.finalize_version
        )
        if (
            result.result_key != envelope.idempotency.result_key
            or (
                envelope.run_type.value != "retry"
                and result.analysis_key != envelope.idempotency.analysis_key
            )
            or result.task_code != envelope.task_code.value
            or result.execution_kind != execution.kind.value
            or result.project_id != project_id
            or result.sec_uid != sec_uid
            or not weekly_projects_valid
            or not finalize_version_valid
            or (
                execution.kind.value == "project"
                and result.related_project_ids != related_project_ids
            )
            or result.business_date != envelope.business_date
            or result.window_start != envelope.window_start
            or result.window_end != envelope.window_end
            or result.is_test
            != (envelope.delivery_target.scope is DeliveryScope.TEST)
        ):
            raise ValueError("内容分析结果与投递信封身份不一致")

    @staticmethod
    def _assert_existing_matches(
        existing: ContentAnalysisResult,
        envelope: ContentAnalysisTaskEnvelope,
        write: ResultWrite,
    ) -> None:
        execution = envelope.execution
        project_id = int(execution.project_id) if execution.kind.value == "project" else None
        sec_uid = execution.sec_uid if execution.kind.value == "account" else None
        if execution.kind.value == "project":
            related_project_ids = [execution.project_id]
        elif execution.kind.value == "account":
            related_project_ids = sorted(write.context_versions)
        else:
            related_project_ids = list(execution.project_ids)
        finalize_source_valid = (
            execution.kind.value != "weekly_batch_finalize"
            or dict(existing.source_receipts or {}) == dict(write.source_receipts)
        )
        expected = (
            envelope.idempotency.analysis_key,
            envelope.task_code.value,
            execution.kind.value,
            project_id,
            sec_uid,
            related_project_ids,
            envelope.business_date,
            envelope.window_start,
            envelope.window_end,
            dict(write.context_versions),
            envelope.delivery_target.scope is DeliveryScope.TEST,
        )
        actual = (
            existing.analysis_key,
            existing.task_code,
            existing.execution_kind,
            existing.project_id,
            existing.sec_uid,
            existing.related_project_ids,
            existing.business_date,
            existing.window_start,
            existing.window_end,
            existing.context_versions,
            existing.is_test,
        )
        if actual != expected or not finalize_source_valid:
            raise ValueError("结果幂等键已绑定到不同业务输入")

    async def persist(
        self,
        envelope: ContentAnalysisTaskEnvelope,
        write: ResultWrite,
        created_by: int,
    ) -> PersistedResult:
        if type(created_by) is not int or created_by <= 0:
            raise ValueError("系统服务账号必须是正整数")
        execution = envelope.execution
        if execution.kind.value == "weekly_batch_finalize":
            task_receipt = (
                write.source_receipts.get("task_jobs")
                if isinstance(write.source_receipts, Mapping)
                else None
            )
            if (
                not isinstance(task_receipt, Mapping)
                or task_receipt.get("finalize_version")
                != execution.finalize_version
            ):
                raise ValueError(
                    "周批次收尾 source_receipts.finalize_version 与信封不一致"
                )
        existing = await self._existing(envelope.idempotency.result_key)
        if existing is not None:
            self._assert_existing_matches(existing, envelope, write)
            return PersistedResult(
                internal_result_id=existing.id,
                output_id=existing.output_id,
                result_key=existing.result_key,
                created=False,
                status=InternalResultStatus(existing.status),
            )
        project_id = int(execution.project_id) if execution.kind.value == "project" else None
        sec_uid = execution.sec_uid if execution.kind.value == "account" else None
        if execution.kind.value == "project":
            related_project_ids = [execution.project_id]
        elif execution.kind.value == "account":
            related_project_ids = sorted(write.context_versions)
        else:
            related_project_ids = list(execution.project_ids)
        try:
            output = Output(
                title=write.title,
                tool_code=envelope.task_code.value,
                tool_name="内容分析智能体",
                task_id=envelope.task_id,
                content_json=dict(write.payload),
                created_by=created_by,
            )
            self._session.add(output)
            await self._session.flush()
            result = ContentAnalysisResult(
                result_key=envelope.idempotency.result_key,
                analysis_key=envelope.idempotency.analysis_key,
                task_id=envelope.task_id,
                task_code=envelope.task_code.value,
                run_type=envelope.run_type.value,
                execution_kind=execution.kind.value,
                project_id=project_id,
                sec_uid=sec_uid,
                related_project_ids=related_project_ids,
                business_date=envelope.business_date,
                window_start=envelope.window_start,
                window_end=envelope.window_end,
                context_versions=dict(write.context_versions),
                source_receipts=dict(write.source_receipts),
                status=write.status.value,
                output_id=output.id,
                is_test=envelope.delivery_target.scope is DeliveryScope.TEST,
            )
            self._session.add(result)
            await self._session.flush()
            if envelope.delivery_target.scope is not DeliveryScope.TEST:
                if (
                    write.library_items
                    or write.library_refreshes
                    or write.cross_project_opportunities
                    or write.manual_opening_updates
                ):
                    await self._lock_cross_project_mutations()
                for item in write.library_items:
                    await self._upsert_library(item, result.id, created_by)
                for item in write.library_refreshes:
                    await self._refresh_library(item, result.id)
                for item in write.cross_project_opportunities:
                    await self._upsert_cross_project(item, result.id)
                if write.library_items or write.library_refreshes:
                    await self._rebuild_cross_project_opportunities(result.id)
                if write.account_baseline is not None:
                    await self._upsert_baseline(write.account_baseline, result.id)
                for item in write.manual_opening_updates:
                    await self._apply_manual_opening(item, result.id)
            current = self._clock()
            if (
                not isinstance(current, datetime)
                or current.tzinfo is None
                or current >= envelope.deadline_at
            ):
                raise TimeoutError("内容分析持久化超过任务截止时间")
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            existing = await self._existing(envelope.idempotency.result_key)
            if existing is None:
                raise
            self._assert_existing_matches(existing, envelope, write)
            return PersistedResult(
                internal_result_id=existing.id,
                output_id=existing.output_id,
                result_key=existing.result_key,
                created=False,
                status=InternalResultStatus(existing.status),
            )
        except Exception:
            await self._session.rollback()
            raise
        return PersistedResult(
            internal_result_id=result.id,
            output_id=output.id,
            result_key=result.result_key,
            created=True,
            status=write.status,
        )

    async def _upsert_library(
        self,
        item: LibraryItemWrite,
        result_id: int,
        created_by: int,
    ) -> None:
        identity_filters = []
        if item.platform_content_id:
            identity_filters.append(
                ContentAnalysisLibraryItem.platform_content_id
                == item.platform_content_id
            )
        if item.external_url:
            identity_filters.append(
                ContentAnalysisLibraryItem.external_url == item.external_url
            )
        existing = list(
            (
                await self._session.scalars(
                    select(ContentAnalysisLibraryItem).where(
                        ContentAnalysisLibraryItem.project_id == item.project_id,
                        or_(*identity_filters),
                    )
                )
            ).all()
        )
        if len(existing) > 1:
            raise ValueError("项目内容的双稳定身份命中不同记录")
        values = {
            "platform": item.platform,
            "account_id": item.account_id,
            "category": item.category,
            "analysis": dict(item.analysis),
            "project_assessment": dict(item.project_assessment),
            "latest_metrics": dict(item.latest_metrics),
            "confidence": item.confidence,
            "priority": item.priority,
            "opening_status": item.opening_status,
            "opening_fragment": item.opening_fragment,
            "opening_unavailable_reason": item.opening_unavailable_reason,
            "latest_result_id": result_id,
            "updated_at": datetime.now(timezone.utc),
        }
        if existing:
            record = existing[0]
            if (
                item.platform_content_id
                and record.platform_content_id
                and item.platform_content_id != record.platform_content_id
            ) or (
                item.external_url
                and record.external_url
                and item.external_url != record.external_url
            ):
                raise ValueError("项目内容的稳定身份别名发生冲突")
            old_analysis = record.analysis
            old_opening = (
                old_analysis.get("opening")
                if isinstance(old_analysis, Mapping)
                else None
            )
            if (
                isinstance(old_opening, Mapping)
                and old_opening.get("source") == "manual"
            ):
                values["analysis"] = {
                    **values["analysis"],
                    "opening": dict(old_opening),
                }
                values["opening_status"] = record.opening_status
                values["opening_fragment"] = record.opening_fragment
                values["opening_unavailable_reason"] = (
                    record.opening_unavailable_reason
                )
            values["platform_content_id"] = record.platform_content_id or item.platform_content_id
            values["external_url"] = record.external_url or item.external_url
            for field_name, value in values.items():
                setattr(record, field_name, value)
            reference = await self._session.get(KolReference, record.kol_reference_id)
            if reference is None:
                raise ValueError("项目内容库扩展缺少原始素材记录")
            reference.likes = item.latest_metrics.get("like_count")
            return
        reference = KolReference(
            kol_id=item.project_id,
            title=item.title,
            likes=item.latest_metrics.get("like_count"),
            source="未知" if item.platform == "unknown" else "抖音",
            type=("红人爆款文案" if item.category == "persona" else "千川爆款文案"),
            content=item.transcript,
            data_description=json.dumps(
                {"source": "content_analysis", "confidence": item.confidence},
                ensure_ascii=False,
            ),
            created_by=created_by,
        )
        self._session.add(reference)
        await self._session.flush()
        self._session.add(
            ContentAnalysisLibraryItem(
                kol_reference_id=reference.id,
                project_id=item.project_id,
                platform_content_id=item.platform_content_id,
                external_url=item.external_url,
                ingestion_source="analysis",
                **values,
            )
        )

    async def _upsert_cross_project(
        self,
        item: CrossProjectOpportunityWrite,
        result_id: int,
    ) -> None:
        existing = await self._session.scalar(
            select(ContentAnalysisCrossProjectOpportunity).where(
                ContentAnalysisCrossProjectOpportunity.method_key == item.method_key
            )
        )
        values = {
            "method_payload": dict(item.method_payload),
            "applicable_boundaries": list(dict.fromkeys(item.applicable_boundaries)),
            "sources": [dict(source) for source in item.sources],
            "latest_result_id": result_id,
            "is_active": True,
            "updated_at": datetime.now(timezone.utc),
        }
        if existing is None:
            self._session.add(
                ContentAnalysisCrossProjectOpportunity(
                    method_key=item.method_key,
                    **values,
                )
            )
        else:
            source_map = {
                (
                    source.get("project_id"),
                    source.get("content_key"),
                ): dict(source)
                for source in values["sources"]
                if isinstance(source, Mapping)
                and isinstance(source.get("project_id"), str)
                and isinstance(source.get("content_key"), str)
            }
            values["sources"] = [source_map[key] for key in sorted(source_map)]
            for field_name, value in values.items():
                setattr(existing, field_name, value)

    async def _refresh_library(
        self,
        item: LibraryRefreshWrite,
        result_id: int,
    ) -> None:
        filters = []
        if item.platform_content_id:
            filters.append(
                ContentAnalysisLibraryItem.platform_content_id
                == item.platform_content_id
            )
        if item.external_url:
            filters.append(ContentAnalysisLibraryItem.external_url == item.external_url)
        rows = list(
            (
                await self._session.scalars(
                    select(ContentAnalysisLibraryItem).where(
                        ContentAnalysisLibraryItem.project_id == item.project_id,
                        or_(*filters),
                    )
                )
            ).all()
        )
        if len(rows) > 1:
            raise ValueError("项目内容的双稳定身份命中不同记录")
        if not rows:
            return
        record = rows[0]
        if (
            item.platform_content_id
            and record.platform_content_id
            and item.platform_content_id != record.platform_content_id
        ) or (
            item.external_url
            and record.external_url
            and item.external_url != record.external_url
        ):
            raise ValueError("项目内容的稳定身份别名发生冲突")
        record.platform_content_id = (
            record.platform_content_id or item.platform_content_id
        )
        record.external_url = record.external_url or item.external_url
        analysis = dict(item.analysis)
        previous_opening = (
            record.analysis.get("opening")
            if isinstance(record.analysis, Mapping)
            else None
        )
        if isinstance(previous_opening, Mapping):
            analysis["opening"] = dict(previous_opening)
        record.analysis = analysis
        record.project_assessment = dict(item.project_assessment)
        record.latest_metrics = dict(item.latest_metrics)
        record.confidence = item.confidence
        record.priority = item.priority
        record.latest_result_id = result_id
        record.updated_at = datetime.now(timezone.utc)
        reference = await self._session.get(KolReference, record.kol_reference_id)
        if reference is None:
            raise ValueError("项目内容库扩展缺少原始素材记录")
        reference.likes = item.latest_metrics.get("like_count")

    async def _lock_cross_project_mutations(self) -> None:
        await self._session.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtext('content-analysis-cross-project'))"
            )
        )

    async def lock_library_mutations(self) -> None:
        """让人工维护与自动刷新在同一事务锁内合并项目库字段。"""
        await self._lock_cross_project_mutations()

    async def _rebuild_cross_project_opportunities(self, result_id: int) -> None:
        await self._lock_cross_project_mutations()
        rows = tuple(
            (
                await self._session.scalars(
                    select(ContentAnalysisLibraryItem)
                    .join(
                        KolReference,
                        KolReference.id
                        == ContentAnalysisLibraryItem.kol_reference_id,
                    )
                    .where(
                        ContentAnalysisLibraryItem.availability == "enabled",
                        KolReference.deleted_at.is_(None),
                    )
                )
            ).all()
        )
        grouped: dict[str, list[tuple[Any, ContentAnalysisLibraryItem, tuple[str, ...], set[CrossProjectSignal]]]] = {}
        for row in rows:
            if not isinstance(row.analysis, Mapping) or not isinstance(
                row.project_assessment,
                Mapping,
            ):
                continue
            try:
                source_information = parse_source_information(
                    row.analysis.get("source_information", {})
                )
                methods = tuple(
                    parse_reusable_method(value)
                    for value in row.analysis.get("reusable_methods", [])
                )
            except (TypeError, ValueError):
                continue
            scenarios = tuple(
                scenario.get("statement")
                for scenario in row.project_assessment.get(
                    "cross_project_scenarios",
                    [],
                )
                if isinstance(scenario, Mapping)
                and isinstance(scenario.get("statement"), str)
                and scenario["statement"].strip()
                and not is_source_limited_text(
                    scenario["statement"],
                    source_information,
                )
                and not is_visual_claim(scenario["statement"])
            )
            try:
                signals = {
                    CrossProjectSignal(value)
                    for value in row.project_assessment.get(
                        "cross_project_signals",
                        [],
                    )
                }
            except ValueError:
                continue
            for method in methods:
                if is_reusable_method_safe(method, source_information):
                    grouped.setdefault(method.method_key, []).append(
                        (method, row, scenarios, signals)
                    )
        active_method_keys: set[str] = set()
        for method_key, entries in grouped.items():
            project_ids = {str(entry[1].project_id) for entry in entries}
            scenarios = tuple(
                sorted({value for entry in entries for value in entry[2]})
            )
            signals = {value for entry in entries for value in entry[3]}
            if not scenarios or (len(project_ids) < 2 and len(signals) < 2):
                continue
            method = min(entries, key=lambda entry: (entry[0].name, entry[0].description))[0]
            sources = []
            for _, row, _, _ in entries:
                try:
                    content_key = self._library_content_key(row)
                except ValueError:
                    continue
                sources.append(
                    {
                        "project_id": str(row.project_id),
                        "content_key": content_key,
                    }
                )
            if not sources:
                continue
            active_method_keys.add(method_key)
            await self._upsert_cross_project(
                CrossProjectOpportunityWrite(
                    method_key=method_key,
                    method_payload={
                        "name": method.name,
                        "description": method.description,
                        "method_key": method.method_key,
                        "evidence": [
                            {
                                "evidence_type": evidence.evidence_type.value,
                                "locator": evidence.locator,
                                "detail": evidence.detail,
                            }
                            for evidence in method.evidence
                        ],
                        "applicable_boundaries": [
                            {"statement": boundary.statement}
                            for boundary in method.applicable_boundaries
                        ],
                    },
                    applicable_boundaries=[
                        boundary.statement for boundary in method.applicable_boundaries
                    ],
                    sources=sources,
                ),
                result_id,
            )
        active_rows = tuple(
            (
                await self._session.scalars(
                    select(ContentAnalysisCrossProjectOpportunity).where(
                        ContentAnalysisCrossProjectOpportunity.is_active.is_(True)
                    )
                )
            ).all()
        )
        for row in active_rows:
            if row.method_key not in active_method_keys:
                row.is_active = False
                row.latest_result_id = result_id
                row.updated_at = datetime.now(timezone.utc)

    async def rebuild_cross_project_opportunities(self, result_id: int) -> None:
        """在调用方事务内按当前可用项目库重建公司级机会池。"""
        await self._rebuild_cross_project_opportunities(result_id)

    async def _upsert_baseline(
        self,
        item: AccountBaselineWrite,
        result_id: int,
    ) -> None:
        existing = await self._session.scalar(
            select(ContentAnalysisAccountBaseline).where(
                ContentAnalysisAccountBaseline.sec_uid == item.sec_uid,
                ContentAnalysisAccountBaseline.window_start == item.window_start,
                ContentAnalysisAccountBaseline.window_end == item.window_end,
            )
        )
        values = {
            "mean_likes": item.mean_likes,
            "median_likes": item.median_likes,
            "sample_count": item.sample_count,
            "maximum_likes": item.maximum_likes,
            "minimum_likes": item.minimum_likes,
            "unavailable_reason": item.unavailable_reason,
            "related_project_ids": list(item.related_project_ids),
            "latest_result_id": result_id,
            "updated_at": datetime.now(timezone.utc),
        }
        if existing is None:
            self._session.add(
                ContentAnalysisAccountBaseline(
                    sec_uid=item.sec_uid,
                    window_start=item.window_start,
                    window_end=item.window_end,
                    **values,
                )
            )
        else:
            for field_name, value in values.items():
                setattr(existing, field_name, value)

    async def _apply_manual_opening(
        self,
        item: ManualOpeningWrite,
        result_id: int,
    ) -> None:
        record = await self._session.get(ContentAnalysisLibraryItem, item.item_id)
        if record is None or record.project_id != item.project_id:
            raise ValueError("人工开头补标目标不存在或项目不一致")
        if record.ingestion_source != "manual" or record.category != "qianchuan":
            raise ValueError("人工开头补标目标类型不受支持")
        if record.availability != "enabled":
            raise ValueError("停用内容不能执行人工开头补标")
        if record.opening_status != "unannotated":
            return
        record.opening_status = item.status
        record.opening_fragment = item.fragment
        record.opening_unavailable_reason = item.unavailable_reason
        record.analysis = {
            **dict(record.analysis or {}),
            "opening": {**dict(item.opening_payload), "source": "content_analysis"},
        }
        record.latest_result_id = result_id
        record.updated_at = datetime.now(timezone.utc)

    async def load_result_payload(self, result_id: int) -> Mapping[str, Any]:
        result = await self._session.get(ContentAnalysisResult, result_id)
        if result is None:
            raise LookupError("内容分析内部结果不存在")
        output = await self._session.get(Output, result.output_id)
        if (
            output is None
            or output.deleted_at is not None
            or not isinstance(output.content_json, Mapping)
        ):
            raise LookupError("内容分析结构化正文不存在")
        return dict(output.content_json)

    async def load_persisted_result(
        self,
        envelope: ContentAnalysisTaskEnvelope,
        result_id: int,
    ) -> PersistedResult:
        result = await self._session.get(ContentAnalysisResult, result_id)
        if result is None:
            raise LookupError("内容分析内部结果不存在")
        self._assert_result_matches_envelope(result, envelope)
        return PersistedResult(
            internal_result_id=result.id,
            output_id=result.output_id,
            result_key=result.result_key,
            created=False,
            status=InternalResultStatus(result.status),
        )

    @staticmethod
    def _target_directory(envelope: ContentAnalysisTaskEnvelope) -> str:
        return (
            f"{envelope.delivery_target.report_root_ref}/"
            f"{envelope.delivery_target.relative_directory}"
        )

    async def _assert_delivery_scope(
        self,
        delivery: ContentAnalysisDelivery,
        envelope: ContentAnalysisTaskEnvelope,
    ) -> None:
        if (
            delivery.is_test
            != (envelope.delivery_target.scope is DeliveryScope.TEST)
            or delivery.target_directory != self._target_directory(envelope)
        ):
            raise ValueError("投递键已绑定到不同的正式或测试目录")
        result_ids = delivery.internal_result_ids or []
        if not result_ids:
            return
        first_result = await self._session.get(ContentAnalysisResult, result_ids[0])
        if first_result is None:
            raise ValueError("投递键关联的内部结果不存在")
        if (
            first_result.task_code != envelope.task_code.value
            or first_result.business_date != envelope.business_date
            or first_result.is_test
            != (envelope.delivery_target.scope is DeliveryScope.TEST)
        ):
            raise ValueError("投递键已绑定到不同业务周期")
        execution = envelope.execution
        if execution.kind.value == "project":
            if (
                first_result.execution_kind != "project"
                or first_result.project_id != int(execution.project_id)
            ):
                raise ValueError("日报投递键已绑定到不同项目")
            return
        if first_result.execution_kind not in {
            "account",
            "weekly_batch_finalize",
        }:
            raise ValueError("周报投递键已绑定到不同执行类型")
        first_output = await self._session.get(Output, first_result.output_id)
        first_payload = first_output.content_json if first_output is not None else None
        if (
            not isinstance(first_payload, Mapping)
            or first_payload.get("weekly_batch_id") != execution.weekly_batch_id
        ):
            raise ValueError("周报投递键已绑定到不同周批次")

    @staticmethod
    def _validate_delivery_identity(envelope, identity, status: str) -> None:
        if identity is None:
            if status == "success":
                raise ValueError("成功投递必须保存完整文档身份")
            return
        if identity.document_key != envelope.idempotency.document_key:
            raise ValueError("投递身份与任务文档键不一致")
        has_id = isinstance(identity.document_id, str) and bool(identity.document_id.strip())
        has_url = isinstance(identity.document_url, str) and bool(identity.document_url.strip())
        if has_id != has_url or (status == "success" and not has_id):
            raise ValueError("投递文档身份不完整")
        if not has_id:
            return
        parsed = urlsplit(identity.document_url)
        host = parsed.hostname.casefold() if parsed.hostname else ""
        if (
            parsed.scheme != "https"
            or not (host == "feishu.cn" or host.endswith(".feishu.cn"))
            or parsed.path.rstrip("/") != f"/docx/{identity.document_id}"
        ):
            raise ValueError("投递文档链接与编号不匹配")

    async def load_delivery_identity(self, envelope: ContentAnalysisTaskEnvelope):
        from .executor import DeliveryIdentity

        delivery = await self._session.scalar(
            select(ContentAnalysisDelivery).where(
                ContentAnalysisDelivery.document_key
                == envelope.idempotency.document_key
            )
        )
        if delivery is None:
            return None
        await self._assert_delivery_scope(delivery, envelope)
        return DeliveryIdentity(
            document_key=delivery.document_key,
            document_id=delivery.document_id,
            document_url=delivery.document_url,
        )

    async def record_delivery(
        self,
        envelope: ContentAnalysisTaskEnvelope,
        result_id: int,
        *,
        status: str,
        identity=None,
        error: str | None = None,
    ) -> None:
        if status not in {"success", "failed"}:
            raise ValueError("投递状态不受支持")
        self._validate_delivery_identity(envelope, identity, status)
        result = await self._session.get(ContentAnalysisResult, result_id)
        if result is None:
            raise LookupError("投递关联的内容分析结果不存在")
        self._assert_result_matches_envelope(result, envelope)
        delivery = await self._session.scalar(
            select(ContentAnalysisDelivery).where(
                ContentAnalysisDelivery.document_key
                == envelope.idempotency.document_key
            )
        )
        if delivery is None:
            delivery = ContentAnalysisDelivery(
                document_key=envelope.idempotency.document_key,
                target_directory=self._target_directory(envelope),
                status=status,
                attempt_count=0,
                internal_result_ids=[],
                is_test=envelope.delivery_target.scope is DeliveryScope.TEST,
            )
            self._session.add(delivery)
        else:
            await self._assert_delivery_scope(delivery, envelope)
        result_ids = list(delivery.internal_result_ids or [])
        if result_id not in result_ids:
            result_ids.append(result_id)
        delivery.internal_result_ids = result_ids
        delivery.status = status
        delivery.attempt_count = int(delivery.attempt_count or 0) + 1
        delivery.updated_at = datetime.now(timezone.utc)
        delivery.last_error = (
            None if status == "success" else "飞书报告投递失败，详见外部服务日志"
        )
        if identity is not None:
            delivery.document_id = identity.document_id
            delivery.document_url = identity.document_url
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
