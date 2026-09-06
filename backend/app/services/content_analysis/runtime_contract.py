"""内容分析任务配置与执行服务之间的稳定进程内信封。"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import PurePosixPath
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")


class TaskCode(str, Enum):
    """内容分析支持的任务类型。"""

    DAILY = "content_analysis_daily"
    WEEKLY = "content_analysis_weekly"


class RunType(str, Enum):
    """任务运行类型。"""

    AUTO = "auto"
    TEST = "test"
    RETRY = "retry"


class RetryMode(str, Enum):
    """重试只允许完整执行或仅投递。"""

    FULL = "full"
    DELIVERY_ONLY = "delivery_only"


class DeliveryScope(str, Enum):
    """报告投递隔离域；重试必须继承原运行的隔离域。"""

    FORMAL = "formal"
    TEST = "test"


class TriggerSource(str, Enum):
    """任务触发来源。"""

    SYSTEM = "system"
    USER = "user"


class ExecutionKind(str, Enum):
    """任务执行对象类型。"""

    PROJECT = "project"
    ACCOUNT = "account"
    WEEKLY_BATCH_FINALIZE = "weekly_batch_finalize"


class DatabasePrecheckStatus(str, Enum):
    """任务配置侧数据库预检结果。"""

    READY = "ready"
    MISSING = "missing"
    ERROR = "error"


def _non_empty(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空文本")


def _positive_integer(value: object, field_name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field_name} 必须是正整数")


def _non_negative_integer(value: object, field_name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field_name} 必须是非负整数")


def _positive_integer_text(value: object, field_name: str) -> int:
    _non_empty(value, field_name)
    try:
        numeric = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 必须是正整数文本") from exc
    if numeric <= 0 or str(numeric) != value:
        raise ValueError(f"{field_name} 必须是正整数文本")
    return numeric


def _shanghai_datetime(value: object, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} 必须是带时区时间")
    if value.utcoffset() != timedelta(hours=8):
        raise ValueError(f"{field_name} 必须使用北京时间")


@dataclass(frozen=True)
class IdempotencyKeys:
    """分析、结构化结果和报告投递三层幂等键。"""

    analysis_key: str
    result_key: str
    document_key: str

    def __post_init__(self) -> None:
        for field_name in ("analysis_key", "result_key", "document_key"):
            _non_empty(getattr(self, field_name), field_name)
        if "\r" in self.document_key or "\n" in self.document_key:
            raise ValueError("document_key 不能包含换行")


@dataclass(frozen=True)
class DatabasePrecheck:
    """数据库预检事实；不代替飞书运行时关系校验。"""

    status: DatabasePrecheckStatus
    input_limited: bool = False
    limitation_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, DatabasePrecheckStatus):
            raise ValueError("数据库预检状态不受支持")
        if type(self.input_limited) is not bool:
            raise ValueError("input_limited 必须是原生布尔值")
        if not isinstance(self.limitation_codes, tuple):
            raise ValueError("limitation_codes 必须是不可变元组")
        for item in self.limitation_codes:
            _non_empty(item, "limitation_codes")
        if self.input_limited != bool(self.limitation_codes):
            raise ValueError("输入受限状态必须与限制代码一致")


@dataclass(frozen=True)
class DeliveryTarget:
    """任务配置交付的共享报告根目录及确定性子目录。"""

    report_root_ref: str
    relative_directory: str
    scope: DeliveryScope = DeliveryScope.FORMAL

    def __post_init__(self) -> None:
        _non_empty(self.report_root_ref, "report_root_ref")
        _non_empty(self.relative_directory, "relative_directory")
        path = PurePosixPath(self.relative_directory)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("relative_directory 必须是根目录内的相对路径")
        if not isinstance(self.scope, DeliveryScope):
            raise ValueError("报告投递隔离域不受支持")
        is_test_namespace = bool(path.parts) and path.parts[0] in {
            "测试",
            "测试报告",
        }
        if is_test_namespace != (self.scope is DeliveryScope.TEST):
            raise ValueError("报告投递隔离域必须与目录命名空间一致")


@dataclass(frozen=True)
class ProjectExecution:
    """每日按单项目执行。"""

    project_id: str
    kind: ExecutionKind = ExecutionKind.PROJECT

    def __post_init__(self) -> None:
        _positive_integer_text(self.project_id, "项目编号")
        if self.kind is not ExecutionKind.PROJECT:
            raise ValueError("每日执行对象必须是项目")


@dataclass(frozen=True)
class AccountExecution:
    """周任务按单账号执行，并携带该账号关联的项目快照。"""

    sec_uid: str
    project_ids: tuple[str, ...]
    weekly_batch_id: str
    batch_size: int
    batch_position: int
    kind: ExecutionKind = ExecutionKind.ACCOUNT

    def __post_init__(self) -> None:
        _non_empty(self.sec_uid, "sec_uid")
        _non_empty(self.weekly_batch_id, "weekly_batch_id")
        if not isinstance(self.project_ids, tuple) or not self.project_ids:
            raise ValueError("project_ids 必须是非空不可变元组")
        numeric_project_ids = tuple(
            _positive_integer_text(project_id, "关联项目编号")
            for project_id in self.project_ids
        )
        if (
            len(set(numeric_project_ids)) != len(numeric_project_ids)
            or numeric_project_ids != tuple(sorted(numeric_project_ids))
        ):
            raise ValueError("project_ids 必须排序去重")
        _positive_integer(self.batch_size, "batch_size")
        _positive_integer(self.batch_position, "batch_position")
        if self.batch_position > self.batch_size:
            raise ValueError("batch_position 不能超过 batch_size")
        if self.kind is not ExecutionKind.ACCOUNT:
            raise ValueError("周任务执行对象必须是账号")


@dataclass(frozen=True)
class WeeklyBatchFinalizeExecution:
    """周账号实例全部终态后生成公司级不可变汇总。"""

    weekly_batch_id: str
    batch_size: int
    project_ids: tuple[str, ...]
    finalize_version: str
    kind: ExecutionKind = ExecutionKind.WEEKLY_BATCH_FINALIZE

    def __post_init__(self) -> None:
        _non_empty(self.weekly_batch_id, "weekly_batch_id")
        _non_empty(self.finalize_version, "finalize_version")
        _non_negative_integer(self.batch_size, "batch_size")
        if not isinstance(self.project_ids, tuple) or not self.project_ids:
            raise ValueError("project_ids 必须是非空不可变元组")
        numeric_project_ids = tuple(
            _positive_integer_text(project_id, "已选项目编号")
            for project_id in self.project_ids
        )
        if (
            len(set(numeric_project_ids)) != len(numeric_project_ids)
            or numeric_project_ids != tuple(sorted(numeric_project_ids))
        ):
            raise ValueError("project_ids 必须排序去重")
        if self.kind is not ExecutionKind.WEEKLY_BATCH_FINALIZE:
            raise ValueError("周批次收尾执行对象类型错误")


@dataclass(frozen=True)
class ContentAnalysisTaskEnvelope:
    """任务配置模块交给内容分析执行侧的唯一输入。"""

    task_id: int
    task_no: str
    task_code: TaskCode
    run_type: RunType
    business_date: date
    window_start: datetime
    window_end: datetime
    triggered_at: datetime
    deadline_at: datetime
    retry_of_task_id: int | None
    trigger_source: TriggerSource
    precheck: DatabasePrecheck
    delivery_target: DeliveryTarget
    idempotency: IdempotencyKeys
    execution: ProjectExecution | AccountExecution | WeeklyBatchFinalizeExecution
    retry_mode: RetryMode | None = None
    request_id: str | None = None

    def __post_init__(self) -> None:
        _positive_integer(self.task_id, "task_id")
        _non_empty(self.task_no, "task_no")
        if not isinstance(self.task_code, TaskCode):
            raise ValueError("task_code 不受支持")
        if not isinstance(self.run_type, RunType):
            raise ValueError("run_type 不受支持")
        if not isinstance(self.trigger_source, TriggerSource):
            raise ValueError("trigger_source 不受支持")
        if self.run_type is RunType.AUTO and self.trigger_source is not TriggerSource.SYSTEM:
            raise ValueError("自动任务必须由系统触发")
        if not isinstance(self.precheck, DatabasePrecheck):
            raise ValueError("precheck 类型错误")
        if not isinstance(self.delivery_target, DeliveryTarget):
            raise ValueError("delivery_target 类型错误")
        if (
            self.run_type is RunType.AUTO
            and self.delivery_target.scope is not DeliveryScope.FORMAL
        ):
            raise ValueError("自动任务必须投递正式目录")
        if (
            self.run_type is RunType.TEST
            and self.delivery_target.scope is not DeliveryScope.TEST
        ):
            raise ValueError("测试运行必须投递测试目录")
        if not isinstance(self.idempotency, IdempotencyKeys):
            raise ValueError("idempotency 类型错误")
        for field_name in (
            "window_start",
            "window_end",
            "triggered_at",
            "deadline_at",
        ):
            _shanghai_datetime(getattr(self, field_name), field_name)
        start = self.window_start.astimezone(SHANGHAI)
        end = self.window_end.astimezone(SHANGHAI)
        if start.time() != datetime.min.time() or end.time() != datetime.min.time():
            raise ValueError("分析窗口必须由完整自然日组成")
        expected_days = 3 if self.task_code is TaskCode.DAILY else 30
        if end - start != timedelta(days=expected_days):
            raise ValueError("分析窗口天数与任务类型不一致")
        if self.business_date != end.date() - timedelta(days=1):
            raise ValueError("business_date 必须是窗口最后一个完整自然日")
        if self.deadline_at - self.triggered_at != timedelta(hours=12):
            raise ValueError("任务截止时间必须是触发后十二小时")
        if self.run_type is RunType.RETRY:
            _positive_integer(self.retry_of_task_id, "retry_of_task_id")
            if not isinstance(self.retry_mode, RetryMode):
                raise ValueError("重试任务 retry_mode 不受支持")
        elif self.retry_of_task_id is not None:
            raise ValueError("非重试任务不能携带 retry_of_task_id")
        elif self.retry_mode is not None:
            raise ValueError("非重试任务不能携带 retry_mode")
        if self.request_id is not None:
            _non_empty(self.request_id, "request_id")
        if self.task_code is TaskCode.DAILY and not isinstance(
            self.execution,
            ProjectExecution,
        ):
            raise ValueError("每日任务必须按单项目执行")
        if self.task_code is TaskCode.WEEKLY and not isinstance(
            self.execution,
            (AccountExecution, WeeklyBatchFinalizeExecution),
        ):
            raise ValueError("周任务必须按单账号或周批次收尾执行")
        if (
            isinstance(self.execution, WeeklyBatchFinalizeExecution)
            and self.delivery_target.scope is not DeliveryScope.FORMAL
        ):
            raise ValueError("周批次收尾只允许正式隔离域")
