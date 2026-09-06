"""内容分析任务实例创建、执行回传与重试。"""
from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_task_config import AgentTaskConfig
from app.models.kol import Kol
from app.models.kol_benchmark import KolBenchmark
from app.models.log import OperationLog
from app.models.task import TaskJob, TaskLog
from app.services.agent_task_config_service import (
    AGENT_CODE,
    TOOL_CODE_DAILY,
    TOOL_CODE_WEEKLY,
    get_project_input_status,
    is_project_eligible,
)
from app.services.agent_task_execution_contract import (
    ContentAnalysisExecutor,
    build_task_envelope,
    calculate_business_window,
    map_execution_result,
)


_TOOL_CODES = {"daily": TOOL_CODE_DAILY, "weekly": TOOL_CODE_WEEKLY}


def _task_no() -> str:
    return f"CA-S28-{uuid4().hex}"


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _account_hash(account_key: str) -> str:
    return hashlib.sha256(account_key.encode("utf-8")).hexdigest()[:16]


def _summary_execution(execution: dict | None) -> dict:
    summary_execution = deepcopy(execution or {})
    if summary_execution.get("object_type") == "account":
        account_key = summary_execution.pop("account_key", None)
        if isinstance(account_key, str) and account_key:
            summary_execution["account_key_hash"] = _account_hash(account_key)
    return summary_execution


def _execution_segment(execution: dict) -> str:
    if execution["object_type"] == "project":
        return f"project:{execution['project_id']}"
    if execution["object_type"] == "weekly_batch_finalize":
        batch_hash = hashlib.sha256(execution["weekly_batch_id"].encode("utf-8")).hexdigest()[:16]
        return f"batch-finalize:{batch_hash}:{execution['finalize_version']}"
    return f"account:{_account_hash(execution['account_key'].strip())}"


def make_idempotency_keys(
    *,
    task_code: str,
    run_type: str,
    business_date: str,
    execution: dict,
    request_id: str | None = None,
    document_key: str | None = None,
) -> dict[str, str]:
    segment = _execution_segment(execution)
    logical_key = f"content-analysis:{task_code}:{business_date}:{segment}"
    if run_type == "auto":
        run_key = f"content-analysis:{task_code}:auto:{business_date}:{segment}"
        internal_result_key = logical_key
        resolved_document_key = document_key or logical_key
    elif run_type == "test":
        normalized_request_id = request_id.strip() if isinstance(request_id, str) else ""
        if not normalized_request_id:
            raise ValueError("test request_id is required")
        test_key = (
            f"content-analysis:{task_code}:test:{normalized_request_id}:"
            f"{business_date}:{segment}"
        )
        run_key = f"content-analysis:{task_code}:test:{normalized_request_id}"
        internal_result_key = f"{test_key}:internal"
        resolved_document_key = f"{test_key}:document"
    elif request_id:
        run_key = f"content-analysis:{task_code}:{run_type}:{request_id}"
        internal_result_key = logical_key
        resolved_document_key = document_key or logical_key
    else:
        run_key = f"content-analysis:{task_code}:{run_type}:{uuid4().hex}"
        internal_result_key = logical_key
        resolved_document_key = document_key or logical_key
    return {
        "run_key": run_key,
        "internal_result_key": internal_result_key,
        "document_key": resolved_document_key,
    }


def normalize_report_root_ref(value: str | None) -> str | None:
    normalized = value.strip() if isinstance(value, str) else ""
    return normalized or None


async def load_report_root_ref(db: AsyncSession) -> str | None:
    value = await db.scalar(select(AgentTaskConfig.report_root_ref).where(
        AgentTaskConfig.agent_code == AGENT_CODE,
    ))
    return normalize_report_root_ref(value)


def _precheck_with_report_root(database_precheck: dict, report_root_ref: str | None) -> dict:
    precheck = deepcopy(database_precheck)
    if normalize_report_root_ref(report_root_ref) is None:
        precheck["status"] = "missing"
        precheck["reason_code"] = "REPORT_ROOT_REF_MISSING"
    return precheck


def _preferred_account_name(current: str | None, candidate: str | None) -> str | None:
    names = [name for name in (current, candidate) if isinstance(name, str) and name]
    return min(names) if names else None


async def project_database_precheck(db: AsyncSession, project_id: int) -> tuple[dict, Kol | None]:
    project = await db.scalar(select(Kol).where(Kol.id == project_id))
    if project is None or not is_project_eligible(project):
        return {
            "status": "missing",
            "reason_code": "PROJECT_NOT_ELIGIBLE",
            "input_limited": False,
            "input_limited_reasons": [],
        }, project
    benchmarks = (await db.execute(select(KolBenchmark).where(
        KolBenchmark.kol_id == project_id,
    ))).scalars().all()
    input_status = get_project_input_status(project, list(benchmarks))
    return {
        "status": "ready" if input_status["ready"] else "missing",
        "reason_code": None if input_status["ready"] else "CONTENT_BENCHMARK_SEC_UID_MISSING",
        "input_limited": input_status["input_limited"],
        "input_limited_reasons": input_status["input_limited_reasons"],
    }, project


async def list_weekly_account_candidates(
    db: AsyncSession,
    *,
    project_ids: list[int] | None = None,
) -> list[dict]:
    """None 表示全部合格测试项目；显式 ID 列表用于正式自动调度范围。"""
    query = select(Kol).where(Kol.deleted_at.is_(None))
    if project_ids is not None:
        if not project_ids:
            return []
        query = query.where(Kol.id.in_(project_ids))
    projects = [item for item in (await db.execute(query)).scalars().all() if is_project_eligible(item)]
    if not projects:
        return []
    eligible_ids = [int(item.id) for item in projects]
    benchmarks = (await db.execute(select(KolBenchmark).where(
        KolBenchmark.kol_id.in_(eligible_ids),
        KolBenchmark.account_type == "content",
    ))).scalars().all()
    grouped: dict[str, dict] = {}
    for benchmark in benchmarks:
        account_key = (benchmark.sec_uid or "").strip()
        if not account_key:
            continue
        candidate = grouped.setdefault(account_key, {
            "account_key": account_key,
            "account_name": benchmark.account_name,
            "project_ids": set(),
        })
        candidate["project_ids"].add(int(benchmark.kol_id))
        candidate["account_name"] = _preferred_account_name(
            candidate["account_name"],
            benchmark.account_name,
        )
    return [
        {**grouped[key], "project_ids": sorted(grouped[key]["project_ids"])}
        for key in sorted(grouped)
    ]


def _stored_payload(envelope: dict) -> dict:
    execution = envelope["execution"]
    payload = {
        **deepcopy(envelope),
        "agent_code": AGENT_CODE,
        "run_key": envelope["idempotency"]["run_key"],
        "window_start": envelope["analysis_window"]["start"],
        "window_end": envelope["analysis_window"]["end"],
    }
    if execution["object_type"] == "project":
        payload["project_id"] = execution["project_id"]
    elif execution["object_type"] == "account":
        payload["account_key"] = execution["account_key"]
        payload["project_ids"] = execution["project_ids"]
    else:
        payload["project_ids"] = execution["project_ids"]
    return payload


def _executor_envelope(payload: dict) -> dict:
    envelope = deepcopy(payload)
    for alias in ("agent_code", "run_key", "window_start", "window_end", "project_id", "account_key", "project_ids"):
        envelope.pop(alias, None)
    return envelope


def _log(task_id: int, *, code: str, name: str, status: str, message: str) -> TaskLog:
    return TaskLog(
        task_id=task_id,
        step_code=code,
        step_name=name,
        status=status,
        message=message,
    )


def _reason_code(summary: dict) -> str | None:
    stage = summary.get("failure_stage")
    if stage == "data_source":
        return summary["feishu_relation"].get("reason_code") or "DATA_SOURCE_FAILED"
    if stage in {"analysis", "internal_result"}:
        return summary["internal_result"].get("reason_code") or "ANALYSIS_FAILED"
    if stage == "delivery":
        return summary["delivery"].get("reason_code") or "DELIVERY_FAILED"
    if stage == "timeout":
        return (
            summary["internal_result"].get("reason_code")
            or summary["delivery"].get("reason_code")
            or "DEADLINE_EXCEEDED"
        )
    return None


async def apply_executor_result_if_active(
    db: AsyncSession,
    *,
    task_id: int,
    database_precheck: dict,
    executor_result: dict,
    finished_at: datetime,
    redelivery_context_confirmed: bool = False,
) -> bool:
    task = await db.get(TaskJob, task_id)
    if task is None:
        return False
    execution_object_type = ((task.input_payload or {}).get("execution") or {}).get("object_type")
    status, summary = map_execution_result(
        database_precheck=database_precheck,
        executor_result=executor_result,
        execution_object_type=execution_object_type,
        redelivery_context_confirmed=(
            redelivery_context_confirmed
            or ((task.input_payload or {}).get("retry") or {}).get("mode")
            == "delivery_only"
        ),
    )
    summary["execution"] = _summary_execution((task.input_payload or {}).get("execution"))
    reason_code = _reason_code(summary)
    started_at = task.started_at
    duration_ms = None
    if started_at is not None:
        duration_ms = max(0, int((_utc(finished_at) - _utc(started_at)).total_seconds() * 1000))
    result = await db.execute(update(TaskJob).where(
        TaskJob.id == task_id,
        TaskJob.status.in_(("pending", "processing")),
    ).values(
        status=status,
        result_summary=summary,
        error_code=reason_code,
        error_message=None if status in {"success", "not_run"} else "内容分析任务执行失败",
        finished_at=finished_at,
        duration_ms=duration_ms,
        updated_at=finished_at,
    ))
    if result.rowcount != 1:
        return False
    db.add(_log(
        task_id,
        code="executor_result",
        name="执行结果",
        status="success" if status in {"success", "not_run"} else "failed",
        message="执行器结果已按四层合同保存",
    ))
    return True


async def _find_existing_run(db: AsyncSession, run_key: str) -> TaskJob | None:
    return await db.scalar(select(TaskJob).where(
        TaskJob.tool_code.in_(tuple(_TOOL_CODES.values())),
        TaskJob.input_payload["agent_code"].astext == AGENT_CODE,
        TaskJob.input_payload["run_key"].astext == run_key,
    ).order_by(TaskJob.id.asc()))


async def _insert_task(
    db: AsyncSession,
    *,
    task_code: str,
    run_type: str,
    run_key: str,
    created_by: int,
) -> tuple[TaskJob, bool]:
    if run_type == "test" or ":batch-finalize:" in run_key:
        lock_key = int.from_bytes(
            hashlib.sha256(run_key.encode("utf-8")).digest()[:8],
            byteorder="big",
            signed=True,
        )
        await db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})
    if run_type in {"auto", "test"}:
        existing = await _find_existing_run(db, run_key)
        if existing is not None:
            return existing, False
    task = TaskJob(
        task_no=_task_no(),
        tool_code=_TOOL_CODES[task_code],
        tool_name="内容分析",
        status="pending",
        input_payload={
            "agent_code": AGENT_CODE,
            "task_code": task_code,
            "run_type": run_type,
            "run_key": run_key,
        },
        result_summary={},
        output_id=None,
        created_by=created_by,
    )
    try:
        async with db.begin_nested():
            db.add(task)
            await db.flush()
    except IntegrityError:
        existing = await _find_existing_run(db, run_key)
        if existing is None:
            raise
        return existing, False
    return task, True


async def prepare_execution_task(
    db: AsyncSession,
    *,
    task_code: str,
    run_type: str,
    execution: dict,
    database_precheck: dict,
    report_root_ref: str | None,
    idempotency: dict[str, str],
    created_by: int,
    triggered_at: datetime,
    retry_of_task_id: int | None = None,
    retry_mode: str | None = None,
    request_id: str | None = None,
    business_date: str | None = None,
    analysis_window: dict | None = None,
    delivery_scope: str | None = None,
    operation_log: OperationLog | None = None,
) -> tuple[TaskJob, bool, bool]:
    """持久化完整执行信封；返回任务、是否新建、是否需要调用执行器。"""
    report_root_ref = normalize_report_root_ref(report_root_ref)
    database_precheck = _precheck_with_report_root(database_precheck, report_root_ref)
    task, created = await _insert_task(
        db,
        task_code=task_code,
        run_type=run_type,
        run_key=idempotency["run_key"],
        created_by=created_by,
    )
    if not created:
        if operation_log is not None:
            operation_log.target_id = task.id
            db.add(operation_log)
        return task, False, False
    envelope = build_task_envelope(
        task_id=int(task.id),
        task_no=str(task.task_no),
        task_code=task_code,
        run_type=run_type,
        triggered_at=triggered_at,
        execution=execution,
        database_precheck=database_precheck,
        report_root_ref=report_root_ref,
        run_key=idempotency["run_key"],
        internal_result_key=idempotency["internal_result_key"],
        document_key=idempotency["document_key"],
        retry_of_task_id=retry_of_task_id,
        retry_mode=retry_mode,
        request_id=request_id,
        business_date=business_date,
        analysis_window=analysis_window,
        delivery_scope=delivery_scope,
    )
    task.input_payload = _stored_payload(envelope)
    task.result_summary = {"execution": _summary_execution(envelope["execution"])}
    if operation_log is not None:
        operation_log.target_id = task.id
        db.add(operation_log)
    if database_precheck["status"] == "missing":
        task.status, task.result_summary = map_execution_result(
            database_precheck=database_precheck,
            executor_result=None,
            execution_object_type=execution.get("object_type"),
        )
        task.result_summary["execution"] = _summary_execution(envelope["execution"])
        task.input_payload.pop("deadline_at", None)
        db.add(_log(
            int(task.id),
            code="database_precheck",
            name="数据库预检",
            status="skipped",
            message="必要配置缺失，未调用执行器",
        ))
        return task, True, False

    return task, True, True


async def execute_persisted_task(
    db: AsyncSession,
    *,
    executor: ContentAnalysisExecutor,
    task_id: int,
) -> bool:
    """原子领取一个已持久化自动任务，并在独立会话中执行。"""
    started_at = datetime.now(timezone.utc)
    claimed = await db.execute(update(TaskJob).where(
        TaskJob.id == task_id,
        TaskJob.status == "pending",
    ).values(
        status="processing",
        started_at=started_at,
        updated_at=started_at,
    ))
    if claimed.rowcount != 1:
        await db.commit()
        return False
    task = await db.get(TaskJob, task_id)
    if task is None:
        await db.rollback()
        return False
    envelope = _executor_envelope(task.input_payload or {})
    database_precheck = deepcopy(envelope.get("database_precheck") or {"status": "ready"})
    db.add(_log(
        task_id,
        code="executor_started",
        name="执行开始",
        status="success",
        message="已领取持久任务并调用进程内内容分析执行器",
    ))
    await db.commit()
    try:
        executor_result = await executor.execute(envelope)
    except Exception:
        executor_result = _execution_failure_result(
            envelope.get("execution", {}).get("object_type"),
        )
    await apply_executor_result_if_active(
        db,
        task_id=task_id,
        database_precheck=database_precheck,
        executor_result=executor_result,
        finished_at=datetime.now(timezone.utc),
    )
    await db.commit()
    return True


async def _create_and_execute(
    db: AsyncSession,
    *,
    executor: ContentAnalysisExecutor,
    task_code: str,
    run_type: str,
    execution: dict,
    database_precheck: dict,
    report_root_ref: str | None,
    idempotency: dict[str, str],
    created_by: int,
    triggered_at: datetime,
    retry_of_task_id: int | None = None,
    retry_mode: str | None = None,
    request_id: str | None = None,
    business_date: str | None = None,
    analysis_window: dict | None = None,
    delivery_scope: str | None = None,
    redelivery_context: tuple[str, str, str] | None = None,
    operation_log: OperationLog | None = None,
) -> tuple[TaskJob, bool]:
    task, created, should_execute = await prepare_execution_task(
        db,
        task_code=task_code,
        run_type=run_type,
        execution=execution,
        database_precheck=database_precheck,
        report_root_ref=report_root_ref,
        idempotency=idempotency,
        created_by=created_by,
        triggered_at=triggered_at,
        retry_of_task_id=retry_of_task_id,
        retry_mode=retry_mode,
        request_id=request_id,
        business_date=business_date,
        analysis_window=analysis_window,
        delivery_scope=delivery_scope,
        operation_log=operation_log,
    )
    if not created:
        if operation_log is not None:
            await db.commit()
        return task, False
    if not should_execute:
        await db.commit()
        await db.refresh(task)
        return task, True

    envelope = _executor_envelope(task.input_payload or {})
    task.status = "processing"
    task.started_at = triggered_at
    db.add(_log(
        int(task.id),
        code="executor_started",
        name="执行开始",
        status="success",
        message="已调用进程内内容分析执行器",
    ))
    await db.commit()
    try:
        if redelivery_context is None:
            executor_result = await executor.execute(envelope)
        else:
            executor_result = await executor.redeliver(
                envelope,
                redelivery_context[0],
                redelivery_context[1],
            )
            executor_result = _normalize_redelivery_result(
                executor_result,
                redelivery_context,
                execution_object_type=execution.get("object_type"),
            )
    except Exception:
        executor_result = (
            _redelivery_failure_result(
                *redelivery_context,
                execution_object_type=execution.get("object_type"),
            )
            if redelivery_context is not None
            else _execution_failure_result(execution.get("object_type"))
        )
    await apply_executor_result_if_active(
        db,
        task_id=int(task.id),
        database_precheck=database_precheck,
        executor_result=executor_result,
        finished_at=datetime.now(timezone.utc),
    )
    await db.commit()
    await db.refresh(task)
    return task, True


def _execution_failure_result(execution_object_type: str | None = None) -> dict:
    return {
        "failure_stage": "analysis",
        "feishu_relation": {"status": "skipped"},
        "internal_result": {"status": "failed", "reason_code": "EXECUTOR_ERROR"},
        "delivery": {"status": "skipped"},
    }


def _redelivery_failure_result(
    internal_result_id: str,
    delivery_identity: str,
    outcome: str,
    *,
    execution_object_type: str | None = None,
) -> dict:
    return {
        "failure_stage": "delivery",
        "feishu_relation": {"status": "skipped"},
        "internal_result": {
            "status": "skipped",
            "outcome": outcome if outcome in {"content", "no_content"} else "content",
            "internal_result_id": internal_result_id,
        },
        "delivery": {
            "status": "failed",
            "reason_code": "DELIVERY_FAILED",
            "delivery_identity": delivery_identity,
        },
    }


def _normalize_redelivery_result(
    executor_result: dict | None,
    redelivery_context: tuple[str, str, str],
    *,
    execution_object_type: str | None = None,
) -> dict:
    internal = (
        executor_result.get("internal_result")
        if isinstance(executor_result, dict)
        else None
    )
    normalized_outcome = (
        redelivery_context[2]
        if redelivery_context[2] in {"content", "no_content"}
        else "content"
    )
    internal_was_skipped = internal == {"status": "skipped"}
    internal_matches_context = (
        isinstance(internal, dict)
        and set(internal) == {"status", "outcome", "internal_result_id"}
        and internal.get("status") == "success"
        and internal.get("outcome") == normalized_outcome
        and str(internal.get("internal_result_id")) == redelivery_context[0]
    )
    if (
        isinstance(executor_result, dict)
        and executor_result.get("failure_stage") in {"delivery", "timeout"}
        and executor_result.get("feishu_relation") == {"status": "skipped"}
        and (internal_was_skipped or internal_matches_context)
        and isinstance(executor_result.get("delivery"), dict)
        and executor_result["delivery"].get("status") == "failed"
        and isinstance(executor_result["delivery"].get("reason_code"), str)
        and executor_result["delivery"]["reason_code"].strip()
    ):
        return {
            "failure_stage": executor_result["failure_stage"],
            "feishu_relation": {"status": "skipped"},
            "internal_result": {
                "status": "skipped",
                "outcome": normalized_outcome,
                "internal_result_id": redelivery_context[0],
            },
            "delivery": {
                "status": "failed",
                "reason_code": executor_result["delivery"]["reason_code"],
                "delivery_identity": redelivery_context[1],
            },
        }
    _, summary = map_execution_result(
        database_precheck={"status": "ready"},
        executor_result=executor_result,
        execution_object_type=execution_object_type,
    )
    if (summary.get("internal_result") or {}).get("reason_code") == "EXECUTOR_CONTRACT_INVALID":
        return _redelivery_failure_result(
            *redelivery_context,
            execution_object_type=execution_object_type,
        )
    return executor_result


def _is_delivery_only_retry(summary: dict | None) -> bool:
    summary = summary or {}
    if summary.get("failure_stage") not in {"delivery", "timeout"}:
        return False
    internal = summary.get("internal_result") or {}
    delivery = summary.get("delivery") or {}
    return (
        isinstance(internal.get("internal_result_id"), str)
        and bool(internal["internal_result_id"].strip())
        and isinstance(delivery.get("delivery_identity"), str)
        and bool(delivery["delivery_identity"].strip())
    )


def _safe_failure_reason(task: TaskJob) -> str:
    summary = task.result_summary or {}
    raw = task.error_code or _reason_code(summary) or "TASK_FAILED"
    normalized = "".join(
        character if character.isascii() and (character.isalnum() or character in "_.-") else "_"
        for character in str(raw).upper()
    ).strip("_")
    return (normalized or "TASK_FAILED")[:64]


async def _weekly_batch_account_tasks(
    db: AsyncSession,
    *,
    weekly_batch_id: str,
) -> list[TaskJob]:
    payload = TaskJob.input_payload
    return list((await db.execute(select(TaskJob).where(
        TaskJob.tool_code == TOOL_CODE_WEEKLY,
        payload["agent_code"].astext == AGENT_CODE,
        payload["task_code"].astext == "weekly",
        payload["delivery_target"]["scope"].astext == "formal",
        payload["execution"]["object_type"].astext == "account",
        payload["execution"]["weekly_batch_id"].astext == weekly_batch_id,
        payload["run_type"].astext.in_(("auto", "manual_retry")),
    ).order_by(TaskJob.id.asc()))).scalars().all())


async def get_weekly_batch_terminal_snapshot(
    db: AsyncSession,
    *,
    weekly_batch_id: str,
    batch_size: int | None = None,
) -> dict:
    """读取正式周批账号最新尝试；只返回脱敏、可用于收尾的终态摘要。"""
    if not isinstance(weekly_batch_id, str) or not weekly_batch_id.strip():
        raise ValueError("weekly_batch_id is required")
    if batch_size is not None and (not isinstance(batch_size, int) or batch_size < 0):
        raise ValueError("batch_size must be a nonnegative integer")
    tasks = await _weekly_batch_account_tasks(db, weekly_batch_id=weekly_batch_id.strip())
    latest_by_account: dict[str, TaskJob] = {}
    inferred_sizes: list[int] = []
    project_ids: set[int] = set()
    for task in tasks:
        execution = (task.input_payload or {}).get("execution") or {}
        account_key = execution.get("account_key")
        if not isinstance(account_key, str) or not account_key.strip():
            continue
        latest_by_account[account_key.strip()] = task
        stored_size = execution.get("batch_size")
        if isinstance(stored_size, int) and stored_size >= 0:
            inferred_sizes.append(stored_size)
        for project_id in execution.get("project_ids") or []:
            if isinstance(project_id, int):
                project_ids.add(project_id)
    resolved_batch_size = batch_size if batch_size is not None else (
        max(inferred_sizes) if inferred_sizes else len(latest_by_account)
    )
    status_counts = {"success": 0, "no_content": 0, "failed": 0}
    accounts: list[dict] = []
    nonterminal_count = 0
    state_parts: list[str] = []
    for account_key in sorted(latest_by_account):
        task = latest_by_account[account_key]
        summary = task.result_summary or {}
        outcome = (summary.get("internal_result") or {}).get("outcome")
        account = {"account_key_hash": _account_hash(account_key)}
        if task.status in {"pending", "processing"}:
            nonterminal_count += 1
            account["status"] = "pending"
        elif task.status == "success" and outcome == "no_content":
            status_counts["no_content"] += 1
            account.update({"status": "no_content", "reason_code": None})
        elif task.status == "success":
            status_counts["success"] += 1
            account.update({"status": "success", "reason_code": None})
        else:
            status_counts["failed"] += 1
            account.update({"status": "failed", "reason_code": _safe_failure_reason(task)})
        accounts.append(account)
        state_parts.append(
            f"{account['account_key_hash']}:{task.id}:{account['status']}:{account.get('reason_code') or ''}"
        )
    missing_count = max(0, resolved_batch_size - len(latest_by_account))
    pending = nonterminal_count + missing_count
    ready = pending == 0 and len(latest_by_account) == resolved_batch_size
    state_material = "|".join([
        weekly_batch_id.strip(),
        str(resolved_batch_size),
        *state_parts,
    ])
    return {
        "weekly_batch_id": weekly_batch_id.strip(),
        "batch_size": resolved_batch_size,
        "ready": ready,
        "pending": pending,
        "status_counts": status_counts,
        "accounts": accounts,
        "project_ids": sorted(project_ids),
        "state_version": hashlib.sha256(state_material.encode("utf-8")).hexdigest()[:24],
    }


async def _latest_weekly_finalize_task(
    db: AsyncSession,
    *,
    weekly_batch_id: str,
) -> TaskJob | None:
    payload = TaskJob.input_payload
    return await db.scalar(select(TaskJob).where(
        TaskJob.tool_code == TOOL_CODE_WEEKLY,
        payload["agent_code"].astext == AGENT_CODE,
        payload["task_code"].astext == "weekly",
        payload["delivery_target"]["scope"].astext == "formal",
        payload["execution"]["object_type"].astext == "weekly_batch_finalize",
        payload["execution"]["weekly_batch_id"].astext == weekly_batch_id,
    ).order_by(TaskJob.id.desc()))


async def finalize_weekly_batch(
    db: AsyncSession,
    *,
    executor: ContentAnalysisExecutor,
    weekly_batch_id: str,
    batch_size: int,
    project_ids: list[int] | None,
    report_root_ref: str | None,
    created_by: int,
    triggered_at: datetime,
    business_date: str | None = None,
    analysis_window: dict | None = None,
) -> TaskJob | None:
    """账号实例全部终态后，幂等创建并执行一个正式周批次收尾。"""
    if not isinstance(weekly_batch_id, str) or not weekly_batch_id.strip():
        raise ValueError("weekly_batch_id is required")
    weekly_batch_id = weekly_batch_id.strip()
    lock_name = f"content-analysis:weekly-batch:{weekly_batch_id}"
    try:
        await db.execute(text(
            "SELECT pg_advisory_xact_lock(hashtextextended(:lock_name, 0))"
        ), {"lock_name": lock_name})
        snapshot = await get_weekly_batch_terminal_snapshot(
            db,
            weekly_batch_id=weekly_batch_id,
            batch_size=batch_size,
        )
        if not snapshot["ready"]:
            await db.commit()
            return None
        existing_finalize = await _latest_weekly_finalize_task(
            db,
            weekly_batch_id=weekly_batch_id,
        )
        existing_payload = existing_finalize.input_payload if existing_finalize else {}
        resolved_project_ids = sorted(set(
            project_ids
            if project_ids is not None
            else ((existing_payload.get("execution") or {}).get("project_ids") or snapshot["project_ids"])
        ))
        if not resolved_project_ids:
            raise ValueError("project_ids must be a nonempty integer list")
        resolved_business_date = business_date or existing_payload.get("business_date")
        resolved_window = deepcopy(analysis_window or existing_payload.get("analysis_window"))
        if not isinstance(resolved_business_date, str) or not isinstance(resolved_window, dict):
            window = calculate_business_window("weekly", triggered_at)
            resolved_business_date = str(window["business_date"])
            resolved_window = {
                "start": window["start"],
                "end": window["end"],
                "timezone": window["timezone"],
                "end_exclusive": window["end_exclusive"],
            }
        execution = {
            "object_type": "weekly_batch_finalize",
            "weekly_batch_id": weekly_batch_id,
            "batch_size": batch_size,
            "project_ids": resolved_project_ids,
            "finalize_version": snapshot["state_version"],
        }
        keys = make_idempotency_keys(
            task_code="weekly",
            run_type="auto",
            business_date=resolved_business_date,
            execution=execution,
            document_key=weekly_batch_id,
        )
        task, created, should_execute = await prepare_execution_task(
            db,
            task_code="weekly",
            run_type="auto",
            execution=execution,
            database_precheck={
                "status": "ready",
                "reason_code": None,
                "input_limited": False,
                "input_limited_reasons": [],
            },
            report_root_ref=report_root_ref,
            idempotency=keys,
            created_by=created_by,
            triggered_at=triggered_at,
            business_date=resolved_business_date,
            analysis_window=resolved_window,
            delivery_scope="formal",
        )
        await db.commit()
    except BaseException:
        await db.rollback()
        raise
    if created and should_execute:
        await execute_persisted_task(db, executor=executor, task_id=int(task.id))
    await db.refresh(task)
    return task


async def _refinalize_after_weekly_account_attempt(
    db: AsyncSession,
    *,
    executor: ContentAnalysisExecutor,
    task: TaskJob,
    created_by: int,
    triggered_at: datetime,
) -> None:
    payload = task.input_payload or {}
    execution = payload.get("execution") or {}
    delivery_target = payload.get("delivery_target") or {}
    if (
        payload.get("task_code") != "weekly"
        or execution.get("object_type") != "account"
        or delivery_target.get("scope") != "formal"
        or task.status in {"pending", "processing"}
    ):
        return
    weekly_batch_id = execution.get("weekly_batch_id")
    batch_size = execution.get("batch_size")
    if not isinstance(weekly_batch_id, str) or not isinstance(batch_size, int):
        return
    previous_finalize = await _latest_weekly_finalize_task(
        db,
        weekly_batch_id=weekly_batch_id,
    )
    previous_payload = previous_finalize.input_payload if previous_finalize else {}
    previous_execution = previous_payload.get("execution") or {}
    project_ids = previous_execution.get("project_ids")
    if not isinstance(project_ids, list):
        snapshot = await get_weekly_batch_terminal_snapshot(
            db,
            weekly_batch_id=weekly_batch_id,
            batch_size=batch_size,
        )
        project_ids = snapshot["project_ids"]
    report_root_ref = (
        (previous_payload.get("delivery_target") or {}).get("report_root_ref")
        if previous_finalize is not None
        else delivery_target.get("report_root_ref")
    )
    await finalize_weekly_batch(
        db,
        executor=executor,
        weekly_batch_id=weekly_batch_id,
        batch_size=batch_size,
        project_ids=project_ids,
        report_root_ref=report_root_ref,
        created_by=created_by,
        triggered_at=triggered_at,
        business_date=payload.get("business_date"),
        analysis_window=payload.get("analysis_window"),
    )


async def run_test_execution(
    db: AsyncSession,
    *,
    executor: ContentAnalysisExecutor,
    task_code: str,
    project_id: int | None,
    account_key: str | None,
    created_by: int,
    request_id: str,
    triggered_at: datetime,
    operation_log: OperationLog | None = None,
) -> TaskJob:
    request_id = request_id.strip()
    if not request_id:
        raise ValueError("request_id is required")
    if task_code == "daily" and isinstance(project_id, int):
        precheck, _ = await project_database_precheck(db, project_id)
        execution = {"object_type": "project", "project_id": project_id}
    elif task_code == "weekly" and isinstance(account_key, str) and account_key.strip():
        candidates = await list_weekly_account_candidates(db, project_ids=None)
        candidate = next((item for item in candidates if item["account_key"] == account_key.strip()), None)
        if candidate is None:
            raise ValueError("weekly account does not meet test requirements")
        execution = {
            "object_type": "account",
            "account_key": candidate["account_key"],
            "project_ids": candidate["project_ids"],
            "weekly_batch_id": f"weekly-test-{request_id}",
            "batch_size": 1,
            "batch_position": 1,
        }
        precheck = {
            "status": "ready",
            "reason_code": None,
            "input_limited": False,
            "input_limited_reasons": [],
        }
    else:
        raise ValueError("test execution object does not match task_code")
    business_date = str(calculate_business_window(task_code, triggered_at)["business_date"])
    keys = make_idempotency_keys(
        task_code=task_code,
        run_type="test",
        business_date=business_date,
        execution=execution,
        request_id=request_id,
    )
    task, _ = await _create_and_execute(
        db,
        executor=executor,
        task_code=task_code,
        run_type="test",
        execution=execution,
        database_precheck=precheck,
        report_root_ref=await load_report_root_ref(db),
        idempotency=keys,
        created_by=created_by,
        triggered_at=triggered_at,
        request_id=request_id,
        operation_log=operation_log,
    )
    return task


def _legacy_execution(payload: dict) -> dict:
    execution = payload.get("execution")
    if isinstance(execution, dict):
        return deepcopy(execution)
    if isinstance(payload.get("project_id"), int):
        return {"object_type": "project", "project_id": payload["project_id"]}
    raise ValueError("failed task is missing execution context")


def _window_from_payload(payload: dict) -> dict:
    window = payload.get("analysis_window")
    if isinstance(window, dict):
        return deepcopy(window)
    if isinstance(payload.get("window_start"), str) and isinstance(payload.get("window_end"), str):
        return {
            "start": payload["window_start"],
            "end": payload["window_end"],
            "timezone": "Asia/Shanghai",
            "end_exclusive": True,
        }
    raise ValueError("failed task is missing analysis window")


async def retry_failed_execution(
    db: AsyncSession,
    *,
    executor: ContentAnalysisExecutor,
    task_id: int,
    created_by: int,
    request_id: str,
    triggered_at: datetime,
    operation_log: OperationLog | None = None,
) -> TaskJob:
    request_id = request_id.strip()
    if not request_id:
        raise ValueError("request_id is required")
    original = await db.scalar(select(TaskJob).where(
        TaskJob.id == task_id,
    ).with_for_update())
    if original is None or original.tool_code not in _TOOL_CODES.values():
        raise ValueError("task is not a content-analysis task")
    payload = original.input_payload or {}
    if payload.get("agent_code") != AGENT_CODE or original.status != "failed":
        raise ValueError("only failed content-analysis tasks can be retried")
    existing = await db.scalar(select(TaskJob).where(
        TaskJob.tool_code.in_(tuple(_TOOL_CODES.values())),
        TaskJob.input_payload["retry"]["retry_of_task_id"].astext == str(task_id),
        TaskJob.input_payload["retry"]["request_id"].astext == request_id,
    ).order_by(TaskJob.id.asc()))
    if existing is not None:
        if operation_log is not None:
            operation_log.target_id = existing.id
            db.add(operation_log)
            await db.commit()
        return existing
    task_code = payload.get("task_code")
    if task_code not in _TOOL_CODES:
        raise ValueError("failed task is missing task_code")
    delivery_target = payload.get("delivery_target") or {}
    report_root_ref = normalize_report_root_ref(delivery_target.get("report_root_ref"))
    if report_root_ref is None:
        raise ValueError("原任务未配置报告根目录，请先配置后发起新任务")
    execution = _legacy_execution(payload)
    summary = original.result_summary or {}
    retry_mode = "delivery_only" if _is_delivery_only_retry(summary) else "full"
    if execution["object_type"] == "project":
        precheck, _ = await project_database_precheck(db, execution["project_id"])
    else:
        precheck = deepcopy(summary.get("database_precheck") or {"status": "ready", "reason_code": None})
    if precheck.get("status") != "ready":
        raise ValueError("required configuration is missing")
    idempotency = deepcopy(payload.get("idempotency") or {})
    business_date = payload.get("business_date")
    if not isinstance(business_date, str):
        raise ValueError("failed task is missing business_date")
    fallback = make_idempotency_keys(
        task_code=task_code,
        run_type="manual_retry",
        business_date=business_date,
        execution=execution,
        request_id=request_id,
    )
    idempotency = {
        "run_key": fallback["run_key"],
        "internal_result_key": idempotency.get("internal_result_key", fallback["internal_result_key"]),
        "document_key": idempotency.get("document_key", fallback["document_key"]),
    }
    redelivery_context = None
    if retry_mode == "delivery_only":
        internal_result_id = (summary.get("internal_result") or {}).get("internal_result_id")
        delivery_identity = (summary.get("delivery") or {}).get("delivery_identity")
        if not isinstance(internal_result_id, str) or not isinstance(delivery_identity, str):
            raise ValueError("delivery retry context is missing")
        redelivery_context = (
            internal_result_id,
            delivery_identity,
            (summary.get("internal_result") or {}).get("outcome", "content"),
        )
    delivery_scope = delivery_target.get("scope")
    if delivery_scope not in {"test", "formal"}:
        delivery_scope = "test" if payload.get("run_type") == "test" else "formal"
    task, _ = await _create_and_execute(
        db,
        executor=executor,
        task_code=task_code,
        run_type="manual_retry",
        execution=execution,
        database_precheck=precheck,
        report_root_ref=report_root_ref,
        idempotency=idempotency,
        created_by=created_by,
        triggered_at=triggered_at,
        retry_of_task_id=task_id,
        retry_mode=retry_mode,
        request_id=request_id,
        business_date=business_date,
        analysis_window=_window_from_payload(payload),
        delivery_scope=delivery_scope,
        redelivery_context=redelivery_context,
        operation_log=operation_log,
    )
    await _refinalize_after_weekly_account_attempt(
        db,
        executor=executor,
        task=task,
        created_by=created_by,
        triggered_at=triggered_at,
    )
    return task


async def run_internal_retry(
    db: AsyncSession,
    *,
    executor: ContentAnalysisExecutor,
    task_id: int,
    now: datetime,
) -> bool:
    task = await db.get(TaskJob, task_id)
    if task is None or task.status not in {"pending", "processing"}:
        return False
    envelope = deepcopy(task.input_payload or {})
    if envelope.get("agent_code") != AGENT_CODE:
        return False
    if normalize_report_root_ref((envelope.get("delivery_target") or {}).get("report_root_ref")) is None:
        return False
    envelope["task_identity"] = {
        "task_id": int(task.id),
        "task_no": str(task.task_no),
        "agent_code": AGENT_CODE,
    }
    envelope["run_type"] = "internal_retry"
    mode = "delivery_only" if _is_delivery_only_retry(task.result_summary) else "full"
    envelope["retry"] = {"retry_of_task_id": task.id, "mode": mode, "request_id": None}
    try:
        if mode == "delivery_only":
            internal_result = (task.result_summary or {}).get("internal_result") or {}
            delivery = (task.result_summary or {}).get("delivery") or {}
            executor_result = await executor.redeliver(
                envelope,
                internal_result["internal_result_id"],
                delivery["delivery_identity"],
            )
            executor_result = _normalize_redelivery_result(
                executor_result,
                (
                    internal_result["internal_result_id"],
                    delivery["delivery_identity"],
                    internal_result.get("outcome", "content"),
                ),
                execution_object_type=(envelope.get("execution") or {}).get("object_type"),
            )
        else:
            executor_result = await executor.execute(envelope)
    except Exception:
        if mode == "delivery_only":
            executor_result = _redelivery_failure_result(
                internal_result["internal_result_id"],
                delivery["delivery_identity"],
                internal_result.get("outcome", "content"),
                execution_object_type=(envelope.get("execution") or {}).get("object_type"),
            )
        else:
            executor_result = _execution_failure_result(
                (envelope.get("execution") or {}).get("object_type"),
            )
    applied = await apply_executor_result_if_active(
        db,
        task_id=task_id,
        database_precheck=envelope.get("database_precheck") or {"status": "ready"},
        executor_result=executor_result,
        finished_at=now,
        redelivery_context_confirmed=mode == "delivery_only",
    )
    if applied:
        await db.refresh(task)
        await _refinalize_after_weekly_account_attempt(
            db,
            executor=executor,
            task=task,
            created_by=int(task.created_by),
            triggered_at=now,
        )
    return applied


__all__ = [
    "apply_executor_result_if_active",
    "execute_persisted_task",
    "finalize_weekly_batch",
    "get_weekly_batch_terminal_snapshot",
    "list_weekly_account_candidates",
    "load_report_root_ref",
    "make_idempotency_keys",
    "normalize_report_root_ref",
    "prepare_execution_task",
    "project_database_precheck",
    "retry_failed_execution",
    "run_internal_retry",
    "run_test_execution",
    "_create_and_execute",
]
