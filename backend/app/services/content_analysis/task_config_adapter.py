"""任务配置 2.0 字典信封与内容分析内部合同之间的同进程适配。"""
import json
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from .executor import (
    DeliveryIdentity,
    ExecutionOutcome,
    ExecutionOverallStatus,
)
from .runtime_contract import (
    AccountExecution,
    ContentAnalysisTaskEnvelope,
    DatabasePrecheck,
    DatabasePrecheckStatus,
    DeliveryScope,
    DeliveryTarget,
    IdempotencyKeys,
    ProjectExecution,
    RetryMode,
    RunType,
    TaskCode,
    TriggerSource,
    WeeklyBatchFinalizeExecution,
)


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"任务信封 {field_name} 必须是对象")
    return value


def _reject_unknown_fields(
    value: Mapping[str, Any],
    allowed: frozenset[str],
    field_name: str,
) -> None:
    if set(value) - allowed:
        raise ValueError(f"任务信封 {field_name} 包含未知字段")


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"任务信封 {field_name} 必须是非空文本")
    return value.strip()


def _datetime(value: object, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(_text(value, field_name))
    except ValueError as exc:
        raise ValueError(f"任务信封 {field_name} 时间无效") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"任务信封 {field_name} 必须带时区")
    return parsed


def parse_task_config_envelope(value: object) -> ContentAnalysisTaskEnvelope:
    """严格读取任务配置模块生成的 2.0 信封。"""
    root = _mapping(value, "root")
    _reject_unknown_fields(
        root,
        frozenset(
            {
                "contract_version",
                "task_identity",
                "task_code",
                "run_type",
                "business_date",
                "analysis_window",
                "triggered_at",
                "deadline_at",
                "retry",
                "database_precheck",
                "delivery_target",
                "execution",
                "idempotency",
            }
        ),
        "root",
    )
    if root.get("contract_version") != "2.0":
        raise ValueError("任务信封版本不受支持")
    identity = _mapping(root.get("task_identity"), "task_identity")
    _reject_unknown_fields(
        identity,
        frozenset({"task_id", "task_no", "agent_code"}),
        "task_identity",
    )
    if identity.get("agent_code") != "content-analysis":
        raise ValueError("任务信封智能体编号不受支持")
    task_code_text = _text(root.get("task_code"), "task_code")
    task_code = {
        "daily": TaskCode.DAILY,
        "weekly": TaskCode.WEEKLY,
    }.get(task_code_text)
    if task_code is None:
        raise ValueError("任务信封任务类型不受支持")
    run_type_text = _text(root.get("run_type"), "run_type")
    run_type = {
        "auto": RunType.AUTO,
        "test": RunType.TEST,
        "internal_retry": RunType.RETRY,
        "manual_retry": RunType.RETRY,
        "retry": RunType.RETRY,
    }.get(run_type_text)
    if run_type is None:
        raise ValueError("任务信封运行类型不受支持")
    window = _mapping(root.get("analysis_window"), "analysis_window")
    _reject_unknown_fields(
        window,
        frozenset({"start", "end", "timezone", "end_exclusive"}),
        "analysis_window",
    )
    if window.get("timezone") != "Asia/Shanghai" or window.get("end_exclusive") is not True:
        raise ValueError("任务信封必须使用北京时间右端排他窗口")
    precheck_value = _mapping(root.get("database_precheck"), "database_precheck")
    _reject_unknown_fields(
        precheck_value,
        frozenset(
            {"status", "reason_code", "input_limited", "input_limited_reasons"}
        ),
        "database_precheck",
    )
    precheck_status = {
        "ready": DatabasePrecheckStatus.READY,
        "missing": DatabasePrecheckStatus.MISSING,
        "error": DatabasePrecheckStatus.ERROR,
    }.get(precheck_value.get("status"))
    if precheck_status is None:
        raise ValueError("任务信封数据库预检状态不受支持")
    limitation_values = precheck_value.get("input_limited_reasons", [])
    if not isinstance(limitation_values, list) or any(
        not isinstance(item, str) or not item.strip() for item in limitation_values
    ):
        raise ValueError("任务信封输入限制代码无效")
    limitation_codes = tuple(dict.fromkeys(item.strip() for item in limitation_values))
    input_limited = precheck_value.get("input_limited")
    if type(input_limited) is not bool or input_limited != bool(limitation_codes):
        raise ValueError("任务信封输入受限状态必须与限制代码一致")
    precheck = DatabasePrecheck(
        precheck_status,
        input_limited=input_limited,
        limitation_codes=limitation_codes,
    )
    delivery = _mapping(root.get("delivery_target"), "delivery_target")
    _reject_unknown_fields(
        delivery,
        frozenset({"report_root_ref", "scope", "test_subdirectory"}),
        "delivery_target",
    )
    root_ref = _text(delivery.get("report_root_ref"), "report_root_ref")
    scope = DeliveryScope(delivery.get("scope"))
    execution_value = _mapping(root.get("execution"), "execution")
    if task_code is TaskCode.DAILY:
        _reject_unknown_fields(
            execution_value,
            frozenset({"object_type", "project_id"}),
            "execution.project",
        )
        if execution_value.get("object_type") != "project" or type(
            execution_value.get("project_id")
        ) is not int or execution_value["project_id"] <= 0:
            raise ValueError("日报任务必须携带一个正整数项目编号")
        execution = ProjectExecution(str(execution_value["project_id"]))
        relative_directory = "项目日报"
    else:
        projects = execution_value.get("project_ids")
        if not isinstance(projects, list) or any(
            type(item) is not int or item <= 0 for item in projects
        ):
            raise ValueError("周任务关联项目必须是正整数数组")
        if execution_value.get("object_type") == "account":
            _reject_unknown_fields(
                execution_value,
                frozenset(
                    {
                        "object_type",
                        "account_key",
                        "project_ids",
                        "weekly_batch_id",
                        "batch_size",
                        "batch_position",
                    }
                ),
                "execution.account",
            )
            execution = AccountExecution(
                sec_uid=_text(execution_value.get("account_key"), "account_key"),
                project_ids=tuple(str(item) for item in projects),
                weekly_batch_id=_text(
                    execution_value.get("weekly_batch_id"),
                    "weekly_batch_id",
                ),
                batch_size=execution_value.get("batch_size"),
                batch_position=execution_value.get("batch_position"),
            )
        elif execution_value.get("object_type") == "weekly_batch_finalize":
            _reject_unknown_fields(
                execution_value,
                frozenset(
                    {
                        "object_type",
                        "project_ids",
                        "weekly_batch_id",
                        "batch_size",
                        "finalize_version",
                    }
                ),
                "execution.weekly_batch_finalize",
            )
            execution = WeeklyBatchFinalizeExecution(
                weekly_batch_id=_text(
                    execution_value.get("weekly_batch_id"),
                    "weekly_batch_id",
                ),
                batch_size=execution_value.get("batch_size"),
                project_ids=tuple(str(item) for item in projects),
                finalize_version=_text(
                    execution_value.get("finalize_version"),
                    "finalize_version",
                ),
            )
        else:
            raise ValueError("周任务执行对象不受支持")
        relative_directory = "账号基准周报"
    if scope is DeliveryScope.TEST:
        relative_directory = _text(
            delivery.get("test_subdirectory"),
            "test_subdirectory",
        )
    retry = _mapping(root.get("retry"), "retry")
    _reject_unknown_fields(
        retry,
        frozenset({"retry_of_task_id", "mode", "request_id"}),
        "retry",
    )
    retry_of_task_id = retry.get("retry_of_task_id")
    retry_mode_value = retry.get("mode")
    request_id_value = retry.get("request_id")
    if run_type is RunType.RETRY:
        try:
            retry_mode = RetryMode(retry_mode_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("任务信封 retry.mode 不受支持") from exc
    else:
        if retry_mode_value is not None:
            raise ValueError("非重试任务不能携带 retry.mode")
        retry_mode = None
    request_id = None
    if run_type_text == "auto":
        if retry_of_task_id is not None or request_id_value is not None:
            raise ValueError("自动任务不能携带重试来源")
    elif run_type_text == "test":
        if retry_of_task_id is not None:
            raise ValueError("测试任务不能携带重试来源")
        request_id = _text(request_id_value, "retry.request_id")
    elif run_type_text == "internal_retry":
        if retry_of_task_id != identity.get("task_id"):
            raise ValueError("内部重试必须引用当前持久化原任务")
        if request_id_value is not None:
            raise ValueError("内部重试不能携带用户 request_id")
    else:
        request_id = _text(request_id_value, "retry.request_id")
    idempotency = _mapping(root.get("idempotency"), "idempotency")
    _reject_unknown_fields(
        idempotency,
        frozenset({"run_key", "internal_result_key", "document_key"}),
        "idempotency",
    )
    try:
        business_date = date.fromisoformat(
            _text(root.get("business_date"), "business_date")
        )
    except ValueError as exc:
        raise ValueError("任务信封业务日期无效") from exc
    return ContentAnalysisTaskEnvelope(
        task_id=identity.get("task_id"),
        task_no=_text(identity.get("task_no"), "task_no"),
        task_code=task_code,
        run_type=run_type,
        business_date=business_date,
        window_start=_datetime(window.get("start"), "analysis_window.start"),
        window_end=_datetime(window.get("end"), "analysis_window.end"),
        triggered_at=_datetime(root.get("triggered_at"), "triggered_at"),
        deadline_at=_datetime(root.get("deadline_at"), "deadline_at"),
        retry_of_task_id=retry_of_task_id if run_type is RunType.RETRY else None,
        retry_mode=retry_mode,
        request_id=request_id,
        trigger_source=(
            TriggerSource.SYSTEM
            if run_type_text in {"auto", "internal_retry"}
            else TriggerSource.USER
        ),
        precheck=precheck,
        delivery_target=DeliveryTarget(
            root_ref,
            relative_directory,
            scope=scope,
        ),
        idempotency=IdempotencyKeys(
            _text(idempotency.get("run_key"), "idempotency.run_key"),
            _text(
                idempotency.get("internal_result_key"),
                "idempotency.internal_result_key",
            ),
            _text(idempotency.get("document_key"), "idempotency.document_key"),
        ),
        execution=execution,
    )


def _encode_identity(identity: DeliveryIdentity) -> str:
    return json.dumps(
        {
            "document_key": identity.document_key,
            "document_id": identity.document_id,
            "document_url": identity.document_url,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _decode_identity(value: object) -> DeliveryIdentity:
    try:
        parsed = json.loads(_text(value, "delivery_identity"))
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("仅投递重试文档身份无效") from exc
    identity = _mapping(parsed, "delivery_identity")
    if set(identity) != {"document_key", "document_id", "document_url"}:
        raise ValueError("仅投递重试文档身份字段无效")
    for key in ("document_id", "document_url"):
        if identity.get(key) is not None and not isinstance(identity.get(key), str):
            raise ValueError("仅投递重试文档身份字段无效")
    return DeliveryIdentity(
        document_key=_text(identity.get("document_key"), "document_key"),
        document_id=identity.get("document_id"),
        document_url=identity.get("document_url"),
    )


def task_config_result(
    envelope: ContentAnalysisTaskEnvelope,
    outcome: ExecutionOutcome,
) -> dict[str, Any]:
    """转换成任务配置模块接受的封闭四层结构。"""
    summary = outcome.summary
    reason_code = summary.reason_code or "INTERNAL_EXECUTION_FAILED"
    mapped_failure_stage = (
        "timeout" if summary.failure_stage == "deadline" else summary.failure_stage
    )
    if outcome.overall_status is ExecutionOverallStatus.NOT_RUN:
        return {
            "failure_stage": None,
            "feishu_relation": {
                "status": "missing",
                "reason_code": reason_code,
            },
            "internal_result": {"status": "skipped"},
            "delivery": {"status": "skipped"},
        }
    if summary.failure_stage in {"relation", "content"}:
        return {
            "failure_stage": "data_source",
            "feishu_relation": {
                "status": "failed" if summary.failure_stage == "relation" else "ready",
                "content_read_status": (
                    "failed" if summary.failure_stage == "content" else "skipped"
                ),
                "reason_code": reason_code,
            },
            "internal_result": {"status": "skipped"},
            "delivery": {"status": "skipped"},
        }
    relation = (
        {"status": "skipped"}
        if isinstance(envelope.execution, WeeklyBatchFinalizeExecution)
        or summary.relation == "not_started"
        else {"status": "ready", "content_read_status": "ready"}
    )
    if (
        outcome.internal_result_id is None
        and summary.failure_stage == "delivery"
    ):
        return {
            "failure_stage": "delivery",
            "feishu_relation": relation,
            "internal_result": {"status": "skipped"},
            "delivery": {
                "status": "failed",
                "reason_code": reason_code,
            },
        }
    if outcome.internal_result_id is None:
        return {
            "failure_stage": (
                "timeout" if mapped_failure_stage == "timeout" else "internal_result"
            ),
            "feishu_relation": relation,
            "internal_result": {
                "status": "failed",
                "reason_code": reason_code,
            },
            "delivery": {"status": "skipped"},
        }
    internal = {
        "status": "success",
        "outcome": (
            "no_content" if summary.internal_result == "no_content" else "content"
        ),
        "internal_result_id": str(outcome.internal_result_id),
    }
    identity = outcome.delivery_identity or DeliveryIdentity(
        envelope.idempotency.document_key,
        None,
        None,
    )
    if outcome.overall_status is ExecutionOverallStatus.SUCCESS:
        delivery = {
            "status": "success",
            "delivery_identity": _encode_identity(identity),
            "document_url": identity.document_url,
        }
        failure_stage = None
    else:
        delivery = {
            "status": "failed",
            "delivery_identity": _encode_identity(identity),
            "reason_code": summary.reason_code or "DELIVERY_FAILED",
        }
        failure_stage = (
            "timeout" if mapped_failure_stage == "timeout" else "delivery"
        )
    return {
        "failure_stage": failure_stage,
        "feishu_relation": relation,
        "internal_result": internal,
        "delivery": delivery,
    }


def _contract_failure(
    _raw_envelope: object,
    *,
    delivery_only: bool = False,
) -> dict[str, Any]:
    relation = {"status": "skipped"}
    if delivery_only:
        return {
            "failure_stage": "delivery",
            "feishu_relation": relation,
            "internal_result": {"status": "skipped"},
            "delivery": {
                "status": "failed",
                "reason_code": "EXECUTOR_CONTRACT_INVALID",
            },
        }
    return {
        "failure_stage": "internal_result",
        "feishu_relation": relation,
        "internal_result": {
            "status": "failed",
            "reason_code": "EXECUTOR_CONTRACT_INVALID",
        },
        "delivery": {"status": "skipped"},
    }


class ContentAnalysisTaskConfigAdapter:
    """任务配置侧只看到 execute 和 redeliver 两个字典操作。"""

    def __init__(self, executor) -> None:
        self._executor = executor

    async def execute(self, raw_envelope: dict) -> dict:
        try:
            envelope = parse_task_config_envelope(raw_envelope)
            if envelope.retry_mode is RetryMode.DELIVERY_ONLY:
                raise ValueError("仅投递重试不能调用完整执行")
            if (
                isinstance(envelope.execution, WeeklyBatchFinalizeExecution)
                and envelope.trigger_source is TriggerSource.USER
                and not (
                    envelope.run_type is RunType.RETRY
                    and envelope.retry_mode is RetryMode.FULL
                )
            ):
                raise ValueError("人工周批次收尾必须是已有失败任务的完整重试")
        except Exception:
            return _contract_failure(raw_envelope)
        return task_config_result(envelope, await self._executor.execute(envelope))

    async def redeliver(
        self,
        raw_envelope: dict,
        internal_result_id: str,
        delivery_identity: str,
    ) -> dict:
        try:
            envelope = parse_task_config_envelope(raw_envelope)
            if (
                envelope.run_type is not RunType.RETRY
                or envelope.retry_mode is not RetryMode.DELIVERY_ONLY
            ):
                raise ValueError("仅投递重试必须使用 delivery_only 模式")
            result_id = int(_text(internal_result_id, "internal_result_id"))
            identity = _decode_identity(delivery_identity)
        except Exception:
            return _contract_failure(raw_envelope, delivery_only=True)
        return task_config_result(
            envelope,
            await self._executor.redeliver(envelope, result_id, identity),
        )
