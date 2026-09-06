"""内容分析任务的受控自动调度入口。"""
from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.agent_task_config import AgentTaskConfig
from app.models.task import TaskJob
from app.models.user import User
from app.services.agent_task_execution_contract import (
    SHANGHAI,
    ContentAnalysisExecutor,
    calculate_business_window,
    get_registered_content_analysis_executor,
    is_valid_content_analysis_executor,
    is_valid_content_analysis_system_user,
)
from app.services.agent_task_config_service import (
    TOOL_CODE_DAILY,
    TOOL_CODE_WEEKLY,
    converge_overdue_tasks,
)
from app.services.agent_task_execution_service import (
    execute_persisted_task,
    finalize_weekly_batch,
    list_weekly_account_candidates,
    load_report_root_ref,
    make_idempotency_keys,
    prepare_execution_task,
    project_database_precheck,
)


logger = logging.getLogger(__name__)
_automatic_execution_tasks: set[asyncio.Task] = set()


def _track_automatic_execution(coroutine) -> asyncio.Task:
    task = asyncio.create_task(coroutine)
    _automatic_execution_tasks.add(task)
    task.add_done_callback(_automatic_execution_tasks.discard)
    return task


async def _execute_automatic_task(
    *,
    executor: ContentAnalysisExecutor,
    task_id: int,
) -> None:
    async with AsyncSessionLocal() as execution_db:
        try:
            await execute_persisted_task(
                execution_db,
                executor=executor,
                task_id=task_id,
            )
        except asyncio.CancelledError:
            await execution_db.rollback()
            raise
        except Exception:
            await execution_db.rollback()
            logger.exception("内容分析自动任务执行失败 task_id=%s", task_id)


async def _execute_weekly_batch(
    *,
    executor: ContentAnalysisExecutor,
    task_ids: list[int],
    weekly_batch_id: str,
    batch_size: int,
    project_ids: list[int],
    report_root_ref: str | None,
    created_by: int,
    triggered_at: datetime,
    business_date: str,
    analysis_window: dict,
) -> None:
    for task_id in task_ids:
        await _execute_automatic_task(executor=executor, task_id=task_id)
    async with AsyncSessionLocal() as finalize_db:
        try:
            await finalize_weekly_batch(
                finalize_db,
                executor=executor,
                weekly_batch_id=weekly_batch_id,
                batch_size=batch_size,
                project_ids=project_ids,
                report_root_ref=report_root_ref,
                created_by=created_by,
                triggered_at=triggered_at,
                business_date=business_date,
                analysis_window=analysis_window,
            )
        except asyncio.CancelledError:
            await finalize_db.rollback()
            raise
        except Exception:
            await finalize_db.rollback()
            logger.exception("内容分析周批次收尾失败 weekly_batch_id=%s", weekly_batch_id)


async def wait_for_automatic_executions() -> None:
    """等待当前已登记的自动执行完成，主要用于测试与受控进程排空。"""
    while _automatic_execution_tasks:
        await asyncio.gather(*list(_automatic_execution_tasks), return_exceptions=True)


async def shutdown_content_analysis_scheduler(scheduler_task: asyncio.Task | None) -> None:
    """先停止调度扫描，再取消并等待本模块自动执行，避免泄漏协程。"""
    if scheduler_task is not None and not scheduler_task.done():
        scheduler_task.cancel()
        await asyncio.gather(scheduler_task, return_exceptions=True)
    while _automatic_execution_tasks:
        tasks = list(_automatic_execution_tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def _scheduled_task_code(now: datetime) -> str | None:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local_now = now.astimezone(SHANGHAI)
    if local_now.hour == 0 and local_now.minute == 0:
        return "daily"
    if local_now.weekday() == 0 and local_now.hour == 1 and local_now.minute == 0:
        return "weekly"
    return None


def _due_task_times(now: datetime) -> tuple[datetime, datetime]:
    """返回当前时刻以前最近一次日任务和周任务的固定触发时点。"""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local_now = now.astimezone(SHANGHAI)
    daily_due = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    weekly_due = (
        local_now - timedelta(days=local_now.weekday())
    ).replace(hour=1, minute=0, second=0, microsecond=0)
    if weekly_due > local_now:
        weekly_due -= timedelta(days=7)
    return daily_due, weekly_due


async def _valid_system_user(db: AsyncSession, system_user_id: int | None) -> User | None:
    if not isinstance(system_user_id, int):
        return None
    user = await db.get(User, system_user_id)
    if not is_valid_content_analysis_system_user(user):
        return None
    return user


async def _run_daily(
    db: AsyncSession,
    *,
    executor: ContentAnalysisExecutor,
    project_ids: list[int],
    report_root_ref: str | None,
    created_by: int,
    now: datetime,
    scheduled_for: datetime | None = None,
) -> tuple[int, int]:
    window = calculate_business_window("daily", scheduled_for or now)
    business_date = str(window["business_date"])
    created_count = 0
    existing_count = 0
    executable_task_ids: list[int] = []
    for project_id in project_ids:
        precheck, _ = await project_database_precheck(db, project_id)
        execution = {"object_type": "project", "project_id": project_id}
        keys = make_idempotency_keys(
            task_code="daily",
            run_type="auto",
            business_date=business_date,
            execution=execution,
        )
        task, created, should_execute = await prepare_execution_task(
            db,
            task_code="daily",
            run_type="auto",
            execution=execution,
            database_precheck=precheck,
            report_root_ref=report_root_ref,
            idempotency=keys,
            created_by=created_by,
            triggered_at=now,
            business_date=business_date,
            analysis_window={
                "start": window["start"],
                "end": window["end"],
                "timezone": window["timezone"],
                "end_exclusive": window["end_exclusive"],
            },
        )
        created_count += int(created)
        existing_count += int(not created)
        if should_execute or (not created and task.status == "pending"):
            executable_task_ids.append(int(task.id))
    await db.commit()
    for task_id in executable_task_ids:
        _track_automatic_execution(_execute_automatic_task(
            executor=executor,
            task_id=task_id,
        ))
    return created_count, existing_count


async def _run_weekly(
    db: AsyncSession,
    *,
    executor: ContentAnalysisExecutor,
    project_ids: list[int],
    report_root_ref: str | None,
    created_by: int,
    now: datetime,
    scheduled_for: datetime | None = None,
) -> tuple[int, int]:
    if not project_ids:
        return 0, 0
    candidates = await list_weekly_account_candidates(db, project_ids=project_ids)
    window = calculate_business_window("weekly", scheduled_for or now)
    business_date = str(window["business_date"])
    weekly_batch_id = f"content-analysis:weekly:{business_date}"
    document_key = weekly_batch_id
    precheck = {
        "status": "ready",
        "reason_code": None,
        "input_limited": False,
        "input_limited_reasons": [],
    }
    created_count = 0
    existing_count = 0
    executable_task_ids: list[int] = []
    for position, candidate in enumerate(candidates, start=1):
        execution = {
            "object_type": "account",
            "account_key": candidate["account_key"],
            "project_ids": deepcopy(candidate["project_ids"]),
            "weekly_batch_id": weekly_batch_id,
            "batch_size": len(candidates),
            "batch_position": position,
        }
        keys = make_idempotency_keys(
            task_code="weekly",
            run_type="auto",
            business_date=business_date,
            execution=execution,
            document_key=document_key,
        )
        task, created, should_execute = await prepare_execution_task(
            db,
            task_code="weekly",
            run_type="auto",
            execution=execution,
            database_precheck=precheck,
            report_root_ref=report_root_ref,
            idempotency=keys,
            created_by=created_by,
            triggered_at=now,
            business_date=business_date,
            analysis_window={
                "start": window["start"],
                "end": window["end"],
                "timezone": window["timezone"],
                "end_exclusive": window["end_exclusive"],
            },
        )
        created_count += int(created)
        existing_count += int(not created)
        if should_execute or (not created and task.status == "pending"):
            executable_task_ids.append(int(task.id))
    await db.commit()
    _track_automatic_execution(_execute_weekly_batch(
        executor=executor,
        task_ids=executable_task_ids,
        weekly_batch_id=weekly_batch_id,
        batch_size=len(candidates),
        project_ids=sorted(set(project_ids)),
        report_root_ref=report_root_ref,
        created_by=created_by,
        triggered_at=now,
        business_date=business_date,
        analysis_window={
            "start": window["start"],
            "end": window["end"],
            "timezone": window["timezone"],
            "end_exclusive": window["end_exclusive"],
        },
    ))
    return created_count, existing_count


async def _resume_pending_automatic_tasks(
    db: AsyncSession,
    *,
    executor: ContentAnalysisExecutor,
    now: datetime,
    system_user_id: int | None,
) -> int:
    """恢复已持久化但尚未领取的正式自动任务，不重新读取当前项目范围。"""
    if await _valid_system_user(db, system_user_id) is None:
        return 0
    payload = TaskJob.input_payload
    pending = list((await db.execute(select(TaskJob).where(
        TaskJob.status == "pending",
        TaskJob.tool_code.in_((TOOL_CODE_DAILY, TOOL_CODE_WEEKLY)),
        payload["agent_code"].astext == "content-analysis",
        payload["run_type"].astext == "auto",
        payload["delivery_target"]["scope"].astext == "formal",
    ).order_by(TaskJob.id.asc()))).scalars().all())
    weekly_groups: dict[str, list[TaskJob]] = {}
    resumed = 0
    for task in pending:
        execution = (task.input_payload or {}).get("execution") or {}
        if execution.get("object_type") == "account":
            batch_id = execution.get("weekly_batch_id")
            if isinstance(batch_id, str) and batch_id:
                weekly_groups.setdefault(batch_id, []).append(task)
                resumed += 1
                continue
        _track_automatic_execution(_execute_automatic_task(
            executor=executor,
            task_id=int(task.id),
        ))
        resumed += 1

    for batch_id, batch_pending in weekly_groups.items():
        all_accounts = list((await db.execute(select(TaskJob).where(
            TaskJob.tool_code == TOOL_CODE_WEEKLY,
            payload["agent_code"].astext == "content-analysis",
            payload["run_type"].astext == "auto",
            payload["delivery_target"]["scope"].astext == "formal",
            payload["execution"]["object_type"].astext == "account",
            payload["execution"]["weekly_batch_id"].astext == batch_id,
        ).order_by(TaskJob.id.asc()))).scalars().all())
        project_ids: set[int] = set()
        batch_size = 0
        for task in all_accounts:
            execution = (task.input_payload or {}).get("execution") or {}
            batch_size = max(batch_size, execution.get("batch_size", 0))
            project_ids.update(
                project_id
                for project_id in execution.get("project_ids") or []
                if isinstance(project_id, int)
            )
        representative = batch_pending[0]
        representative_payload = representative.input_payload or {}
        window = deepcopy(representative_payload.get("analysis_window") or {})
        root_ref = (representative_payload.get("delivery_target") or {}).get(
            "report_root_ref"
        )
        ordered_pending = sorted(
            batch_pending,
            key=lambda task: (
                ((task.input_payload or {}).get("execution") or {}).get(
                    "batch_position", 0
                ),
                int(task.id),
            ),
        )
        _track_automatic_execution(_execute_weekly_batch(
            executor=executor,
            task_ids=[int(task.id) for task in ordered_pending],
            weekly_batch_id=batch_id,
            batch_size=batch_size,
            project_ids=sorted(project_ids),
            report_root_ref=root_ref,
            created_by=int(representative.created_by),
            triggered_at=now,
            business_date=str(representative_payload.get("business_date")),
            analysis_window=window,
        ))
    return resumed


async def run_automatic_tick(
    db: AsyncSession,
    *,
    executor: ContentAnalysisExecutor,
    now: datetime,
    scheduled_for: datetime | None = None,
    enabled: bool,
    system_user_id: int | None,
) -> dict:
    """运行一个确定的调度时点；关闭或空档时不建任务。"""
    if not enabled:
        return {"status": "disabled", "created": 0}
    fixed_time = scheduled_for or now
    task_code = _scheduled_task_code(fixed_time)
    if task_code is None:
        return {"status": "idle", "created": 0}
    system_user = await _valid_system_user(db, system_user_id)
    if system_user is None:
        logger.error("SYSTEM_ACCOUNT_INVALID")
        return {"status": "failed", "error_code": "SYSTEM_ACCOUNT_INVALID", "created": 0}
    config = await db.scalar(select(AgentTaskConfig).where(
        AgentTaskConfig.agent_code == "content-analysis",
    ))
    project_ids = list(dict.fromkeys(config.selected_project_ids if config else []))
    report_root_ref = await load_report_root_ref(db)
    if task_code == "daily":
        created, existing = await _run_daily(
            db,
            executor=executor,
            project_ids=project_ids,
            report_root_ref=report_root_ref,
            created_by=int(system_user.id),
            now=now,
            scheduled_for=fixed_time,
        )
    else:
        created, existing = await _run_weekly(
            db,
            executor=executor,
            project_ids=project_ids,
            report_root_ref=report_root_ref,
            created_by=int(system_user.id),
            now=now,
            scheduled_for=fixed_time,
        )
    return {
        "status": "success",
        "task_code": task_code,
        "created": created,
        "existing": existing,
    }


async def content_analysis_scheduler_loop(executor: ContentAnalysisExecutor) -> None:
    """每分钟补扫最近日/周固定时点；数据库幂等约束承接重复扫描。"""
    while True:
        async with AsyncSessionLocal() as db:
            try:
                now = datetime.now(SHANGHAI)
                await _resume_pending_automatic_tasks(
                    db,
                    executor=executor,
                    now=now,
                    system_user_id=settings.content_analysis_system_user_id,
                )
                await converge_overdue_tasks(db, now=now)
                for due_at in _due_task_times(now):
                    await run_automatic_tick(
                        db,
                        executor=executor,
                        now=now,
                        scheduled_for=due_at,
                        enabled=True,
                        system_user_id=settings.content_analysis_system_user_id,
                    )
                await db.commit()
            except Exception:
                await db.rollback()
                logger.exception("内容分析自动调度失败")
        current = datetime.now(SHANGHAI)
        delay = max(0.05, 60 - current.second - current.microsecond / 1_000_000)
        await asyncio.sleep(delay)


def start_content_analysis_scheduler(
    *,
    enabled: bool | None = None,
    executor: ContentAnalysisExecutor | None = None,
):
    resolved_enabled = settings.content_analysis_scheduler_enabled if enabled is None else enabled
    if not resolved_enabled:
        return None
    resolved_executor = executor or get_registered_content_analysis_executor()
    if not is_valid_content_analysis_executor(resolved_executor):
        logger.error("CONTENT_ANALYSIS_EXECUTOR_NOT_REGISTERED")
        return None
    return asyncio.create_task(content_analysis_scheduler_loop(resolved_executor))


__all__ = [
    "run_automatic_tick",
    "shutdown_content_analysis_scheduler",
    "start_content_analysis_scheduler",
    "wait_for_automatic_executions",
]
