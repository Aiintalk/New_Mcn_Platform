"""内容分析任务配置与执行器之间的进程内合同。"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import inspect
import logging
from typing import Protocol
from zoneinfo import ZoneInfo


AGENT_CODE = "content-analysis"
CONTRACT_VERSION = "2.0"
SHANGHAI = ZoneInfo("Asia/Shanghai")
logger = logging.getLogger(__name__)


class ContentAnalysisExecutor(Protocol):
    async def execute(self, envelope: dict) -> dict:
        """执行完整分析与投递。"""

    async def redeliver(
        self,
        envelope: dict,
        internal_result_id: str,
        delivery_identity: str,
    ) -> dict:
        """复用内部结果，仅重新投递。"""


_registered_executor: ContentAnalysisExecutor | None = None


def is_valid_content_analysis_executor(executor: object | None) -> bool:
    return bool(
        executor is not None
        and inspect.iscoroutinefunction(getattr(executor, "execute", None))
        and inspect.iscoroutinefunction(getattr(executor, "redeliver", None))
    )


def is_valid_content_analysis_system_user(user: object | None) -> bool:
    """调度与内容执行共同使用的系统服务账号有效性口径。"""
    return bool(
        user is not None
        and getattr(user, "deleted_at", None) is None
        and getattr(user, "status", None) == "enabled"
        and getattr(user, "role", None) == "admin"
    )


def register_content_analysis_executor(executor: ContentAnalysisExecutor | None) -> None:
    """注册最终集成提供的进程内执行器。"""
    global _registered_executor
    if executor is not None and not is_valid_content_analysis_executor(executor):
        logger.error("CONTENT_ANALYSIS_EXECUTOR_CONTRACT_INVALID")
        _registered_executor = None
        return
    _registered_executor = executor


def get_registered_content_analysis_executor() -> ContentAnalysisExecutor | None:
    return _registered_executor if is_valid_content_analysis_executor(_registered_executor) else None


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(SHANGHAI).isoformat()


def calculate_business_window(task_code: str, triggered_at: datetime) -> dict[str, str | bool]:
    """按上海时区返回刚结束业务日与右端排他的完整自然日窗口。"""
    if triggered_at.tzinfo is None:
        raise ValueError("triggered_at must be timezone-aware")
    if task_code not in {"daily", "weekly"}:
        raise ValueError("task_code must be daily or weekly")
    local_now = triggered_at.astimezone(SHANGHAI)
    window_end = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    window_days = 3 if task_code == "daily" else 30
    return {
        "business_date": (window_end - timedelta(days=1)).date().isoformat(),
        "start": _iso(window_end - timedelta(days=window_days)),
        "end": _iso(window_end),
        "timezone": "Asia/Shanghai",
        "end_exclusive": True,
    }


def _normalize_execution(execution: dict) -> dict:
    normalized = deepcopy(execution)
    if normalized.get("object_type") == "account":
        account_key = normalized.get("account_key")
        if not isinstance(account_key, str) or not account_key.strip():
            raise ValueError("account_key must be nonempty")
        normalized["account_key"] = account_key.strip()
        project_ids = normalized.get("project_ids")
        if not isinstance(project_ids, list) or not all(isinstance(item, int) for item in project_ids):
            raise ValueError("project_ids must be integer list")
        normalized["project_ids"] = sorted(set(project_ids))
    elif normalized.get("object_type") == "project":
        if not isinstance(normalized.get("project_id"), int):
            raise ValueError("project_id must be integer")
    elif normalized.get("object_type") == "weekly_batch_finalize":
        allowed_fields = {
            "object_type", "weekly_batch_id", "batch_size", "project_ids", "finalize_version",
        }
        if set(normalized) != allowed_fields:
            raise ValueError("weekly batch finalize execution fields are invalid")
        if not isinstance(normalized.get("weekly_batch_id"), str) or not normalized["weekly_batch_id"].strip():
            raise ValueError("weekly_batch_id must be nonempty")
        if not isinstance(normalized.get("batch_size"), int) or normalized["batch_size"] < 0:
            raise ValueError("batch_size must be a nonnegative integer")
        project_ids = normalized.get("project_ids")
        if (
            not isinstance(project_ids, list)
            or not project_ids
            or not all(isinstance(item, int) for item in project_ids)
        ):
            raise ValueError("project_ids must be a nonempty integer list")
        if not isinstance(normalized.get("finalize_version"), str) or not normalized["finalize_version"].strip():
            raise ValueError("finalize_version must be nonempty")
        normalized["weekly_batch_id"] = normalized["weekly_batch_id"].strip()
        normalized["project_ids"] = sorted(set(project_ids))
        normalized["finalize_version"] = normalized["finalize_version"].strip()
    else:
        raise ValueError("execution object_type must be project, account or weekly_batch_finalize")
    return normalized


def build_task_envelope(
    *,
    task_id: int,
    task_no: str,
    task_code: str,
    run_type: str,
    triggered_at: datetime,
    execution: dict,
    database_precheck: dict,
    report_root_ref: str | None,
    run_key: str,
    internal_result_key: str,
    document_key: str,
    retry_of_task_id: int | None = None,
    retry_mode: str | None = None,
    request_id: str | None = None,
    deadline_at: datetime | None = None,
    business_date: str | None = None,
    analysis_window: dict | None = None,
    delivery_scope: str | None = None,
) -> dict:
    """构造信封 2.0；不装入飞书行或项目上下文正文。"""
    window = calculate_business_window(task_code, triggered_at)
    deadline_at = deadline_at or triggered_at + timedelta(hours=12)
    scope = delivery_scope or ("test" if run_type == "test" else "formal")
    resolved_window = deepcopy(analysis_window) if analysis_window else {
        "start": window["start"],
        "end": window["end"],
        "timezone": window["timezone"],
        "end_exclusive": window["end_exclusive"],
    }
    return {
        "contract_version": CONTRACT_VERSION,
        "task_identity": {
            "task_id": task_id,
            "task_no": task_no,
            "agent_code": AGENT_CODE,
        },
        "task_code": task_code,
        "run_type": run_type,
        "business_date": business_date or str(window["business_date"]),
        "analysis_window": resolved_window,
        "triggered_at": _iso(triggered_at),
        "deadline_at": _iso(deadline_at),
        "retry": {
            "retry_of_task_id": retry_of_task_id,
            "mode": retry_mode,
            "request_id": request_id,
        },
        "database_precheck": deepcopy(database_precheck),
        "delivery_target": {
            "report_root_ref": report_root_ref,
            "scope": scope,
            "test_subdirectory": "测试报告" if scope == "test" else None,
        },
        "execution": _normalize_execution(execution),
        "idempotency": {
            "run_key": run_key,
            "internal_result_key": internal_result_key,
            "document_key": document_key,
        },
    }


def map_execution_result(
    *,
    database_precheck: dict,
    executor_result: dict | None,
    execution_object_type: str | None = None,
    redelivery_context_confirmed: bool = False,
) -> tuple[str, dict]:
    """把执行器结果严格收敛到 TaskJob 状态和四层摘要。"""
    precheck = deepcopy(database_precheck)
    if precheck.get("status") == "missing":
        return "not_run", {
            "failure_stage": None,
            "database_precheck": precheck,
            "feishu_relation": {"status": "skipped"},
            "internal_result": {"status": "skipped"},
            "delivery": {"status": "skipped"},
        }
    try:
        relation, internal, delivery, failure_stage = _validate_executor_result(
            executor_result,
            execution_object_type=execution_object_type,
            redelivery_context_confirmed=redelivery_context_confirmed,
        )
    except (TypeError, ValueError):
        return "failed", {
            "failure_stage": "analysis",
            "database_precheck": precheck,
            "feishu_relation": {"status": "skipped"},
            "internal_result": {
                "status": "failed",
                "reason_code": "EXECUTOR_CONTRACT_INVALID",
            },
            "delivery": {"status": "skipped"},
        }
    if relation.get("status") == "missing":
        status, failure_stage = "not_run", None
    elif relation.get("status") == "failed" or relation.get("content_read_status") == "failed":
        status, failure_stage = "failed", "data_source"
    elif internal.get("status") == "failed":
        status = "failed"
        failure_stage = (
            failure_stage
            if failure_stage in {"analysis", "internal_result", "timeout"}
            else "analysis"
        )
    elif delivery.get("status") == "failed":
        status = "failed"
        failure_stage = "timeout" if failure_stage == "timeout" else "delivery"
    elif internal.get("status") == "success" and delivery.get("status") == "success":
        status, failure_stage = "success", None
    else:
        status, failure_stage = "failed", failure_stage or "analysis"
    return status, {
        "failure_stage": failure_stage,
        "database_precheck": precheck,
        "feishu_relation": relation,
        "internal_result": internal,
        "delivery": delivery,
    }


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_layer_fields(
    relation: dict,
    internal: dict,
    delivery: dict,
) -> None:
    relation_status = relation.get("status")
    if relation_status == "skipped":
        if set(relation) != {"status"}:
            raise ValueError("skipped relation fields are invalid")
    elif relation_status == "missing":
        if set(relation) != {"status", "reason_code"} or not _nonempty(
            relation.get("reason_code")
        ):
            raise ValueError("missing relation fields are invalid")
    elif relation_status == "failed":
        allowed = {"status", "reason_code"}
        if "content_read_status" in relation:
            allowed.add("content_read_status")
        if (
            set(relation) != allowed
            or relation.get("content_read_status") not in {None, "skipped"}
            or not _nonempty(relation.get("reason_code"))
        ):
            raise ValueError("failed relation fields are invalid")
    elif relation_status == "ready":
        content_status = relation.get("content_read_status")
        expected = {"status", "content_read_status"}
        if content_status == "failed":
            expected.add("reason_code")
        if (
            set(relation) != expected
            or content_status not in {"ready", "failed"}
            or (content_status == "failed" and not _nonempty(relation.get("reason_code")))
        ):
            raise ValueError("ready relation fields are invalid")
    else:
        raise ValueError("relation status is invalid")

    internal_status = internal.get("status")
    if internal_status == "skipped":
        if set(internal) not in (
            {"status"},
            {"status", "outcome", "internal_result_id"},
        ):
            raise ValueError("skipped internal result fields are invalid")
        if len(internal) > 1 and (
            internal.get("outcome") not in {"content", "no_content"}
            or not _nonempty(internal.get("internal_result_id"))
        ):
            raise ValueError("skipped internal result context is invalid")
    elif internal_status == "failed":
        if set(internal) != {"status", "reason_code"} or not _nonempty(
            internal.get("reason_code")
        ):
            raise ValueError("failed internal result fields are invalid")
    elif internal_status == "success":
        if (
            set(internal) != {"status", "outcome", "internal_result_id"}
            or internal.get("outcome") not in {"content", "no_content"}
            or not _nonempty(internal.get("internal_result_id"))
        ):
            raise ValueError("successful internal result fields are invalid")
    else:
        raise ValueError("internal status is invalid")

    delivery_status = delivery.get("status")
    if delivery_status == "skipped":
        if set(delivery) != {"status"}:
            raise ValueError("skipped delivery fields are invalid")
    elif delivery_status == "failed":
        expected = {"status", "reason_code"}
        if "delivery_identity" in delivery:
            expected.add("delivery_identity")
        if (
            set(delivery) != expected
            or not _nonempty(delivery.get("reason_code"))
            or (
                "delivery_identity" in delivery
                and not _nonempty(delivery.get("delivery_identity"))
            )
        ):
            raise ValueError("failed delivery fields are invalid")
    elif delivery_status == "success":
        expected = {"status", "delivery_identity"}
        if "document_url" in delivery:
            expected.add("document_url")
        if (
            set(delivery) != expected
            or not _nonempty(delivery.get("delivery_identity"))
            or (
                "document_url" in delivery
                and delivery.get("document_url") is not None
                and not _nonempty(delivery.get("document_url"))
            )
        ):
            raise ValueError("successful delivery fields are invalid")
    else:
        raise ValueError("delivery status is invalid")


def _validate_executor_result(
    executor_result: dict | None,
    *,
    execution_object_type: str | None = None,
    redelivery_context_confirmed: bool = False,
) -> tuple[dict, dict, dict, str | None]:
    if not isinstance(executor_result, dict):
        raise TypeError("executor result must be an object")
    if set(executor_result) - {"failure_stage", "feishu_relation", "internal_result", "delivery"}:
        raise ValueError("executor result has extra fields")
    relation = executor_result.get("feishu_relation")
    internal = executor_result.get("internal_result")
    delivery = executor_result.get("delivery")
    if not all(isinstance(layer, dict) for layer in (relation, internal, delivery)):
        raise TypeError("executor result layers must be objects")
    if set(relation) - {"status", "content_read_status", "reason_code"}:
        raise ValueError("relation has extra fields")
    if set(internal) - {"status", "outcome", "internal_result_id", "reason_code"}:
        raise ValueError("internal result has extra fields")
    if set(delivery) - {"status", "delivery_identity", "document_url", "reason_code"}:
        raise ValueError("delivery has extra fields")
    _validate_layer_fields(relation, internal, delivery)
    relation_status = relation.get("status")
    internal_status = internal.get("status")
    delivery_status = delivery.get("status")
    failure_stage = executor_result.get("failure_stage")
    if failure_stage not in {
        None,
        "data_source",
        "analysis",
        "internal_result",
        "delivery",
        "timeout",
    }:
        raise ValueError("failure stage is invalid")

    if execution_object_type == "weekly_batch_finalize":
        if relation != {"status": "skipped"}:
            raise ValueError("weekly batch finalize must skip input relation")
        if internal_status == "failed":
            if delivery_status != "skipped" or failure_stage not in {
                None,
                "analysis",
                "internal_result",
                "timeout",
            }:
                raise ValueError("internal failure layers are inconsistent")
            if not _nonempty(internal.get("reason_code")):
                raise ValueError("internal failure requires reason")
        elif internal_status == "skipped":
            if (
                not redelivery_context_confirmed
                or len(internal) <= 1
                or delivery_status != "failed"
                or failure_stage not in {"delivery", "timeout"}
                or "delivery_identity" not in delivery
            ):
                raise ValueError("finalize redelivery failure context is incomplete")
        elif internal_status == "success":
            if internal.get("outcome") not in {"content", "no_content"}:
                raise ValueError("internal success requires outcome")
            if not _nonempty(internal.get("internal_result_id")):
                raise ValueError("internal success requires identity")
            if delivery_status == "success":
                if failure_stage is not None or not _nonempty(delivery.get("delivery_identity")):
                    raise ValueError("delivery success is inconsistent")
            elif delivery_status == "failed":
                if failure_stage not in {None, "delivery", "timeout"}:
                    raise ValueError("delivery failure stage is inconsistent")
                if not _nonempty(delivery.get("reason_code")) or not _nonempty(delivery.get("delivery_identity")):
                    raise ValueError("delivery failure requires reason and identity")
            else:
                raise ValueError("internal success requires delivery result")
        else:
            raise ValueError("internal status is invalid")
    elif relation_status == "missing":
        if (
            internal != {"status": "skipped"}
            or delivery != {"status": "skipped"}
            or failure_stage is not None
        ):
            raise ValueError("missing relation must skip later layers")
    elif relation_status == "failed" or relation.get("content_read_status") == "failed":
        if (
            internal != {"status": "skipped"}
            or delivery != {"status": "skipped"}
            or failure_stage not in {None, "data_source"}
        ):
            raise ValueError("data source failure must skip later layers")
        if not _nonempty(relation.get("reason_code")):
            raise ValueError("data source failure requires reason")
    elif relation == {"status": "skipped"}:
        if internal_status == "failed":
            if delivery_status != "skipped" or failure_stage not in {
                "analysis",
                "internal_result",
                "timeout",
            }:
                raise ValueError("pre-input internal failure layers are inconsistent")
            if not _nonempty(internal.get("reason_code")):
                raise ValueError("pre-input internal failure requires reason")
        elif internal_status == "skipped":
            if (
                not redelivery_context_confirmed
                or len(internal) <= 1
                or delivery_status != "failed"
                or failure_stage not in {"delivery", "timeout"}
            ):
                raise ValueError("pre-input delivery failure layers are inconsistent")
            if "delivery_identity" not in delivery:
                raise ValueError("delivery retry context is incomplete")
        else:
            raise ValueError("skipped relation layers are inconsistent")
    elif relation_status == "ready" and relation.get("content_read_status") == "ready":
        if internal_status == "failed":
            if delivery_status != "skipped" or failure_stage not in {
                None,
                "analysis",
                "internal_result",
                "timeout",
            }:
                raise ValueError("internal failure layers are inconsistent")
            if not _nonempty(internal.get("reason_code")):
                raise ValueError("internal failure requires reason")
        elif internal_status == "success":
            if internal.get("outcome") not in {"content", "no_content"}:
                raise ValueError("internal success requires outcome")
            if not _nonempty(internal.get("internal_result_id")):
                raise ValueError("internal success requires identity")
            if delivery_status == "success":
                if failure_stage is not None or not _nonempty(delivery.get("delivery_identity")):
                    raise ValueError("delivery success is inconsistent")
            elif delivery_status == "failed":
                if failure_stage not in {None, "delivery", "timeout"}:
                    raise ValueError("delivery failure stage is inconsistent")
                if not _nonempty(delivery.get("reason_code")) or not _nonempty(delivery.get("delivery_identity")):
                    raise ValueError("delivery failure requires reason and identity")
            else:
                raise ValueError("internal success requires delivery result")
        else:
            raise ValueError("internal status is invalid")
    else:
        raise ValueError("relation status is invalid")
    return deepcopy(relation), deepcopy(internal), deepcopy(delivery), failure_stage
