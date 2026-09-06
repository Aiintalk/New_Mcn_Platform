"""内容分析智能体任务配置的领域规则与受控运行。"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kol import Kol
from app.models.kol_benchmark import KolBenchmark
from app.models.task import TaskJob, TaskLog


AGENT_CODE = "content-analysis"
TOOL_CODE_DAILY = "content-analysis-daily"
TOOL_CODE_WEEKLY = "content-analysis-weekly"
_TOOL_CODES = {"daily": TOOL_CODE_DAILY, "weekly": TOOL_CODE_WEEKLY}
_OPTIONAL_CONTEXT_FIELDS = (
    ("background", "BACKGROUND_MISSING"),
    ("experience", "EXPERIENCE_MISSING"),
    ("relationships", "RELATIONSHIPS_MISSING"),
    ("unique_story", "UNIQUE_STORY_MISSING"),
    ("extra_notes", "EXTRA_NOTES_MISSING"),
    ("style_notes", "STYLE_NOTES_MISSING"),
)
_SHANGHAI = timezone(timedelta(hours=8))
_DELIVERY_TARGET = "feishu_document"


def _has_text(value: str | None) -> bool:
    return bool(value and value.strip())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _content_tool_code(task_code: str) -> str:
    try:
        return _TOOL_CODES[task_code]
    except KeyError as exc:
        raise ValueError("task_code must be daily or weekly") from exc


def is_project_eligible(project: Kol) -> bool:
    """沿用既有入驻成功口径，不扩展全局规则。"""
    return (
        project.deleted_at is None
        and _has_text(project.persona)
        and _has_text(project.content_plan)
    )


def get_project_input_status(
    project: Kol,
    benchmarks: list[KolBenchmark],
) -> dict:
    """区分会阻断运行的内容对标账号与可缺失的上下文字段。"""
    has_content_sec_uid = any(
        benchmark.account_type == "content" and _has_text(benchmark.sec_uid)
        for benchmark in benchmarks
    )
    required_missing_reasons = [] if has_content_sec_uid else ["CONTENT_BENCHMARK_SEC_UID_MISSING"]
    input_limited_reasons = [
        reason
        for field, reason in _OPTIONAL_CONTEXT_FIELDS
        if not _has_text(getattr(project, field))
    ]
    return {
        "ready": not required_missing_reasons,
        "required_missing_reasons": required_missing_reasons,
        "input_limited": bool(input_limited_reasons),
        "input_limited_reasons": input_limited_reasons,
    }


def calculate_window(task_code: str, triggered_at: datetime) -> dict[str, str]:
    """返回右端排他的上海自然日窗口，保证窗口只含已完整结束的日期。"""
    _content_tool_code(task_code)
    if triggered_at.tzinfo is None:
        raise ValueError("triggered_at must be timezone-aware")
    local_now = triggered_at.astimezone(_SHANGHAI)
    end = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    days = 3 if task_code == "daily" else 30
    return {
        "business_date": (end - timedelta(days=1)).date().isoformat(),
        "window_start": _iso(end - timedelta(days=days)),
        "window_end": _iso(end),
    }


async def list_eligible_projects(db: AsyncSession) -> list[Kol]:
    projects = (await db.execute(select(Kol).where(Kol.deleted_at.is_(None)))).scalars().all()
    return [project for project in projects if is_project_eligible(project)]


async def validate_selected_project_ids(db: AsyncSession, project_ids: list[int]) -> list[int]:
    """去重并确认每个选择仍符合入驻成功口径。"""
    selected_project_ids = list(dict.fromkeys(project_ids))
    if not selected_project_ids:
        return []
    projects = (
        await db.execute(select(Kol).where(Kol.id.in_(selected_project_ids)))
    ).scalars().all()
    projects_by_id = {int(project.id): project for project in projects}
    invalid = [
        project_id
        for project_id in selected_project_ids
        if project_id not in projects_by_id or not is_project_eligible(projects_by_id[project_id])
    ]
    if invalid:
        raise ValueError(f"selected projects are not eligible: {invalid}")
    return selected_project_ids


async def _load_project_context(
    db: AsyncSession,
    project_id: int,
) -> tuple[Kol, list[KolBenchmark]]:
    project = (await db.execute(select(Kol).where(Kol.id == project_id))).scalar_one_or_none()
    if project is None or not is_project_eligible(project):
        raise ValueError("project is not eligible")
    benchmarks = (
        await db.execute(select(KolBenchmark).where(KolBenchmark.kol_id == project_id))
    ).scalars().all()
    return project, benchmarks


def _task_no() -> str:
    return f"CA-{uuid4().hex}"


def _base_payload(
    *,
    project_id: int,
    task_code: str,
    triggered_at: datetime,
) -> dict:
    _content_tool_code(task_code)
    window = calculate_window(task_code, triggered_at)
    return {
        "agent_code": AGENT_CODE,
        "task_code": task_code,
        "project_id": project_id,
        "run_type": "test",
        **window,
        "triggered_at": _iso(triggered_at),
        "deadline_at": _iso(triggered_at + timedelta(hours=12)),
    }


def _summary(input_status: dict) -> dict:
    return {
        "input_limited": input_status["input_limited"],
        "input_limited_reasons": input_status["input_limited_reasons"],
        "controlled_test": True,
        "delivery_target": _DELIVERY_TARGET,
    }


def _task_log(task_id: int, *, step_code: str, step_name: str, status: str, message: str) -> TaskLog:
    return TaskLog(
        task_id=task_id,
        step_code=step_code,
        step_name=step_name,
        status=status,
        message=message,
    )


async def run_controlled_task(
    db: AsyncSession,
    *,
    project_id: int,
    task_code: str,
    created_by: int,
    triggered_at: datetime | None = None,
) -> TaskJob:
    """只验证并记录受控状态，不调用真实智能体或写入 Output。"""
    triggered_at = triggered_at or _utc_now()
    if triggered_at.tzinfo is None:
        raise ValueError("triggered_at must be timezone-aware")
    tool_code = _content_tool_code(task_code)
    project, benchmarks = await _load_project_context(db, project_id)
    input_status = get_project_input_status(project, benchmarks)
    task = TaskJob(
        task_no=_task_no(),
        tool_code=tool_code,
        tool_name="内容分析",
        status="pending" if input_status["ready"] else "not_run",
        input_payload=_base_payload(
            project_id=project_id,
            task_code=task_code,
            triggered_at=triggered_at,
        ),
        result_summary=_summary(input_status),
        output_id=None,
        created_by=created_by,
    )
    if not input_status["ready"]:
        task.input_payload = {
            key: value
            for key, value in task.input_payload.items()
            if key != "deadline_at"
        }
        task.result_summary = {
            **task.result_summary,
            "reason_code": "CONFIG_MISSING",
            "required_missing_reasons": input_status["required_missing_reasons"],
        }
        db.add(task)
        await db.flush()
        db.add(_task_log(
            task.id,
            step_code="config_missing",
            step_name="配置校验",
            status="not_run",
            message="内容对标账号 sec_uid 缺失，任务未启动",
        ))
        return task

    db.add(task)
    await db.flush()
    db.add(_task_log(task.id, step_code="task_created", step_name="创建任务", status="pending", message="受控任务已创建"))
    task.status = "processing"
    task.started_at = triggered_at
    db.add(_task_log(task.id, step_code="controlled_run", step_name="受控运行", status="processing", message="隔离流程校验中"))
    task.status = "success"
    task.finished_at = triggered_at
    task.duration_ms = 0
    db.add(_task_log(task.id, step_code="controlled_complete", step_name="受控完成", status="success", message="隔离流程已完成，等待正式集成"))
    return task


def _parse_deadline(payload: dict | None) -> datetime | None:
    value = (payload or {}).get("deadline_at")
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


async def converge_overdue_tasks(
    db: AsyncSession,
    *,
    now: datetime | None = None,
) -> int:
    """仅收敛本 Agent 已过自身 deadline 的待处理任务，终态绝不回写。"""
    now = now or _utc_now()
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    candidates = (
        await db.execute(
            select(TaskJob).where(
                TaskJob.tool_code.in_(_TOOL_CODES.values()),
                TaskJob.input_payload["agent_code"].astext == AGENT_CODE,
                TaskJob.status.in_(("pending", "processing")),
            )
        )
    ).scalars().all()
    timed_out = 0
    for task in candidates:
        deadline = _parse_deadline(task.input_payload)
        if deadline is None or deadline >= now:
            continue
        if await _timeout_task_if_active(db, task=task, now=now):
            timed_out += 1
    return timed_out


async def _timeout_task_if_active(
    db: AsyncSession,
    *,
    task: TaskJob,
    now: datetime,
) -> bool:
    """仅在任务仍为可超时状态时原子地标记失败，防止覆盖晚到成功。"""
    summary = {
        "failure_stage": "timeout",
        "database_precheck": deepcopy((task.result_summary or {}).get("database_precheck") or {"status": "ready"}),
        "feishu_relation": {"status": "skipped"},
        "internal_result": {"status": "skipped"},
        "delivery": {"status": "skipped"},
    }
    execution = (task.result_summary or {}).get("execution")
    if isinstance(execution, dict):
        summary["execution"] = deepcopy(execution)
    values = {
        "status": "failed",
        "error_code": "TASK_TIMEOUT",
        "error_message": "任务超过自身截止时间",
        "finished_at": now,
        "result_summary": summary,
    }
    if task.started_at is not None:
        values["duration_ms"] = max(
            0,
            int((now - task.started_at).total_seconds() * 1000),
        )
    result = await db.execute(
        update(TaskJob)
        .where(
            TaskJob.id == task.id,
            TaskJob.status.in_(("pending", "processing")),
        )
        .values(**values)
    )
    if result.rowcount != 1:
        return False
    db.add(_task_log(
        task.id,
        step_code="timeout",
        step_name="超时收敛",
        status="failed",
        message="任务超过自身截止时间",
    ))
    return True


async def retry_failed_task(
    db: AsyncSession,
    *,
    task_id: int,
    created_by: int,
    triggered_at: datetime | None = None,
) -> TaskJob:
    """管理员手动重试创建新实例，绝不复用或改写原失败任务。"""
    original = (await db.execute(select(TaskJob).where(TaskJob.id == task_id))).scalar_one_or_none()
    if original is None or original.tool_code not in _TOOL_CODES.values():
        raise ValueError("task is not a content-analysis task")
    if original.status != "failed":
        raise ValueError("only failed tasks can be retried")
    original_payload = original.input_payload or {}
    project_id = original_payload.get("project_id")
    task_code = original_payload.get("task_code")
    business_date = original_payload.get("business_date")
    window_start = original_payload.get("window_start")
    window_end = original_payload.get("window_end")
    if (
        not isinstance(project_id, int)
        or task_code not in _TOOL_CODES
        or not all(isinstance(value, str) for value in (business_date, window_start, window_end))
    ):
        raise ValueError("failed task is missing retry context")
    triggered_at = triggered_at or _utc_now()
    if triggered_at.tzinfo is None:
        raise ValueError("triggered_at must be timezone-aware")
    project, benchmarks = await _load_project_context(db, project_id)
    input_status = get_project_input_status(project, benchmarks)
    if not input_status["ready"]:
        raise ValueError("project required configuration is missing")
    payload = {
        "agent_code": AGENT_CODE,
        "task_code": task_code,
        "project_id": project_id,
        "run_type": "retry",
        "business_date": business_date,
        "window_start": window_start,
        "window_end": window_end,
        "triggered_at": _iso(triggered_at),
        "deadline_at": _iso(triggered_at + timedelta(hours=12)),
        "retry_of_task_id": original.id,
    }
    task = TaskJob(
        task_no=_task_no(),
        tool_code=_content_tool_code(task_code),
        tool_name=original.tool_name,
        status="pending",
        input_payload=payload,
        result_summary=_summary(input_status),
        output_id=None,
        created_by=created_by,
    )
    db.add(task)
    await db.flush()
    db.add(_task_log(task.id, step_code="manual_retry", step_name="手动重试", status="pending", message="基于失败任务创建新的重试实例"))
    return task
