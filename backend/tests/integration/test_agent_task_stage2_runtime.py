"""内容分析任务配置阶段二：自动批次、执行回传与重试。"""
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.agent_task_config import AgentTaskConfig
from app.models.kol import Kol
from app.models.kol_benchmark import KolBenchmark
from app.models.output import Output
from app.models.task import TaskJob, TaskLog
from app.models.user import User
from app.services.agent_task_config_service import converge_overdue_tasks
from app.services.agent_task_execution_service import (
    _executor_envelope,
    _preferred_account_name,
    apply_executor_result_if_active,
    finalize_weekly_batch,
    get_weekly_batch_terminal_snapshot,
    make_idempotency_keys,
    prepare_execution_task,
    retry_failed_execution,
    run_internal_retry,
    run_test_execution,
)
import app.services.content_analysis as content_analysis
from app.services.agent_task_scheduler import (
    _resume_pending_automatic_tasks,
    run_automatic_tick,
    shutdown_content_analysis_scheduler,
    wait_for_automatic_executions,
)


SHANGHAI = timezone(timedelta(hours=8))


@pytest_asyncio.fixture(autouse=True)
async def _isolate_stage2_runtime_rows(test_session):
    await test_session.execute(delete(AgentTaskConfig).where(
        AgentTaskConfig.agent_code == "content-analysis",
    ))
    await test_session.commit()
    yield
    await shutdown_content_analysis_scheduler(None)
    task_ids = (await test_session.execute(select(TaskJob.id).where(
        TaskJob.task_no.like("CA-S28-%"),
    ))).scalars().all()
    if task_ids:
        await test_session.execute(delete(TaskLog).where(TaskLog.task_id.in_(task_ids)))
        await test_session.execute(delete(TaskJob).where(TaskJob.id.in_(task_ids)))
    await test_session.execute(delete(AgentTaskConfig).where(
        AgentTaskConfig.agent_code == "content-analysis",
    ))
    project_ids = (await test_session.execute(select(Kol.id).where(
        Kol.name.like("cov_ca_s28_%"),
    ))).scalars().all()
    if project_ids:
        await test_session.execute(delete(KolBenchmark).where(KolBenchmark.kol_id.in_(project_ids)))
        await test_session.execute(delete(Kol).where(Kol.id.in_(project_ids)))
    await test_session.commit()


def _successful_result(*, suffix: str = "1", outcome: str = "content") -> dict:
    return {
        "feishu_relation": {"status": "ready", "content_read_status": "ready"},
        "internal_result": {
            "status": "success",
            "outcome": outcome,
            "internal_result_id": f"internal-{suffix}",
        },
        "delivery": {
            "status": "success",
            "delivery_identity": f"document-{suffix}",
            "document_url": f"https://example.invalid/{suffix}",
        },
    }


def _failed_result(*, reason_code: str = "ANALYSIS_FAILED") -> dict:
    return {
        "failure_stage": "analysis",
        "feishu_relation": {"status": "ready", "content_read_status": "ready"},
        "internal_result": {"status": "failed", "reason_code": reason_code},
        "delivery": {"status": "skipped"},
    }


def _successful_finalize_result(*, suffix: str = "1") -> dict:
    return {
        "feishu_relation": {"status": "skipped"},
        "internal_result": {
            "status": "success",
            "outcome": "content",
            "internal_result_id": f"weekly-summary-{suffix}",
        },
        "delivery": {
            "status": "success",
            "delivery_identity": "weekly-document",
            "document_url": "https://example.invalid/weekly-document",
        },
    }


class FakeExecutor:
    """只保存测试目录结果的执行器；正式业务集合用于证明测试隔离。"""

    def __init__(self, results: dict[str, dict] | None = None):
        self.results = results or {}
        self.execute_calls: list[dict] = []
        self.redeliver_calls: list[tuple[dict, str, str]] = []
        self.formal_daily_reports: list[dict] = []
        self.content_library: list[dict] = []
        self.cross_project_opportunities: list[dict] = []
        self.account_baselines: list[dict] = []
        self.test_documents: list[dict] = []
        self.input_table_reads = 0
        self.model_calls = 0
        self.professional_business_writes = 0

    async def execute(self, envelope: dict) -> dict:
        self.execute_calls.append(envelope)
        if envelope["execution"]["object_type"] == "weekly_batch_finalize":
            version = envelope["execution"]["finalize_version"]
            return self.results.get("__finalize__", _successful_finalize_result(suffix=version))
        if envelope["delivery_target"]["scope"] == "test":
            self.test_documents.append({"task_id": envelope["task_identity"]["task_id"]})
        account_key = envelope["execution"].get("account_key", "default")
        return self.results.get(account_key, _successful_result(suffix=account_key))

    async def redeliver(
        self,
        envelope: dict,
        internal_result_id: str,
        delivery_identity: str,
    ) -> dict:
        self.redeliver_calls.append((envelope, internal_result_id, delivery_identity))
        relation = (
            {"status": "skipped"}
            if envelope["execution"]["object_type"] == "weekly_batch_finalize"
            else {"status": "ready", "content_read_status": "ready"}
        )
        return {
            "feishu_relation": relation,
            "internal_result": {
                "status": "success",
                "outcome": "content",
                "internal_result_id": internal_result_id,
            },
            "delivery": {
                "status": "success",
                "delivery_identity": delivery_identity,
                "document_url": "https://example.invalid/redelivered",
            },
        }


def _weekly_account_job(
    *,
    admin_id: int,
    weekly_batch_id: str,
    account_key: str,
    status: str,
    batch_size: int,
    batch_position: int,
    run_type: str = "auto",
    scope: str = "formal",
    outcome: str = "content",
    reason_code: str = "ANALYSIS_FAILED",
) -> TaskJob:
    execution = {
        "object_type": "account",
        "account_key": account_key,
        "project_ids": [71],
        "weekly_batch_id": weekly_batch_id,
        "batch_size": batch_size,
        "batch_position": batch_position,
    }
    if status == "success":
        summary = {
            "execution": execution,
            "failure_stage": None,
            "database_precheck": {"status": "ready"},
            "feishu_relation": {"status": "ready", "content_read_status": "ready"},
            "internal_result": {
                "status": "success",
                "outcome": outcome,
                "internal_result_id": f"internal-{uuid4().hex}",
            },
            "delivery": {
                "status": "success",
                "delivery_identity": "weekly-document",
            },
        }
        error_code = None
    elif status in {"pending", "processing"}:
        summary = {"execution": execution}
        error_code = None
    else:
        summary = {
            "execution": execution,
            "failure_stage": "analysis",
            "database_precheck": {"status": "ready"},
            "feishu_relation": {"status": "ready", "content_read_status": "ready"},
            "internal_result": {"status": "failed", "reason_code": reason_code},
            "delivery": {"status": "skipped"},
        }
        error_code = reason_code
    return TaskJob(
        task_no=f"CA-S28-{uuid4().hex}",
        tool_code="content-analysis-weekly",
        tool_name="内容分析",
        status=status,
        input_payload={
            "agent_code": "content-analysis",
            "task_code": "weekly",
            "run_type": run_type,
            "business_date": "2026-09-06",
            "analysis_window": {
                "start": "2026-08-08T00:00:00+08:00",
                "end": "2026-09-07T00:00:00+08:00",
                "timezone": "Asia/Shanghai",
                "end_exclusive": True,
            },
            "triggered_at": "2026-09-07T01:00:00+08:00",
            "delivery_target": {
                "report_root_ref": "weekly-root",
                "scope": scope,
                "test_subdirectory": "测试报告" if scope == "test" else None,
            },
            "execution": execution,
            "idempotency": {
                "run_key": f"run-{uuid4().hex}",
                "internal_result_key": f"internal-key-{uuid4().hex}",
                "document_key": weekly_batch_id,
            },
        },
        result_summary=summary,
        error_code=error_code,
        created_by=admin_id,
    )


def test_nullable_weekly_account_name_is_compared_safely():
    assert _preferred_account_name(None, "展示名") == "展示名"
    assert _preferred_account_name("展示名", None) == "展示名"


class BlockingExecutor(FakeExecutor):
    def __init__(self, *, fail_redelivery: bool = False):
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.fail_redelivery = fail_redelivery

    async def execute(self, envelope: dict) -> dict:
        self.execute_calls.append(envelope)
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        if envelope["execution"]["object_type"] == "weekly_batch_finalize":
            return _successful_finalize_result(suffix="blocking")
        return _successful_result(suffix="blocking")

    async def redeliver(self, envelope, internal_result_id, delivery_identity):
        self.redeliver_calls.append((envelope, internal_result_id, delivery_identity))
        self.started.set()
        if self.fail_redelivery:
            raise RuntimeError("delivery unavailable")
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return _successful_result(suffix="redelivery")


class FirstCallBlockingExecutor(FakeExecutor):
    def __init__(self):
        super().__init__()
        self.first_started = asyncio.Event()
        self.release_first = asyncio.Event()

    async def execute(self, envelope: dict) -> dict:
        self.execute_calls.append(envelope)
        if len(self.execute_calls) == 1:
            self.first_started.set()
            await self.release_first.wait()
            return {
                "feishu_relation": {"status": "ready", "content_read_status": "ready"},
                "internal_result": {
                    "status": "success", "outcome": "content", "internal_result_id": "internal-first",
                },
                "delivery": {
                    "status": "failed", "reason_code": "DELIVERY_FAILED",
                    "delivery_identity": "document-first",
                },
            }
        if envelope["execution"]["object_type"] == "weekly_batch_finalize":
            return _successful_finalize_result(suffix="queue")
        return _successful_result(suffix=envelope["execution"]["account_key"])


class InvalidRedeliveryExecutor(FakeExecutor):
    async def redeliver(self, envelope, internal_result_id, delivery_identity):
        self.redeliver_calls.append((envelope, internal_result_id, delivery_identity))
        return {"delivery": {"status": "failed"}}


class RuntimeUnavailableRedeliveryExecutor(FakeExecutor):
    async def redeliver(self, envelope, internal_result_id, delivery_identity):
        self.redeliver_calls.append((envelope, internal_result_id, delivery_identity))
        return {
            "failure_stage": "delivery",
            "feishu_relation": {"status": "skipped"},
            "internal_result": {"status": "skipped"},
            "delivery": {
                "status": "failed",
                "reason_code": "EXECUTOR_RUNTIME_UNAVAILABLE",
            },
        }


class TimeoutRedeliveryExecutor(FakeExecutor):
    async def redeliver(self, envelope, internal_result_id, delivery_identity):
        self.redeliver_calls.append((envelope, internal_result_id, delivery_identity))
        return {
            "failure_stage": "timeout",
            "feishu_relation": {"status": "skipped"},
            "internal_result": {
                "status": "success",
                "outcome": "content",
                "internal_result_id": internal_result_id,
            },
            "delivery": {
                "status": "failed",
                "reason_code": "DEADLINE_EXCEEDED",
                "delivery_identity": delivery_identity,
            },
        }


async def _project(
    db,
    *,
    name: str,
    admin_id: int,
    sec_uids: list[str | None],
) -> Kol:
    project = Kol(
        name=name,
        persona="人设",
        content_plan="内容规划",
        created_by=admin_id,
    )
    db.add(project)
    await db.flush()
    for index, sec_uid in enumerate(sec_uids):
        db.add(KolBenchmark(
            kol_id=project.id,
            account_name=f"账号-{index}",
            account_type="content",
            sec_uid=sec_uid,
            created_by=admin_id,
        ))
    return project


@pytest.mark.asyncio
async def test_weekly_auto_deduplicates_orders_and_continues_after_failed_account(
    test_session,
    admin_user,
):
    suffix = uuid4().hex[:8]
    first = await _project(
        test_session,
        name=f"cov_ca_s28_first_{suffix}",
        admin_id=admin_user.id,
        sec_uids=[" sec-b ", "sec-a"],
    )
    second = await _project(
        test_session,
        name=f"cov_ca_s28_second_{suffix}",
        admin_id=admin_user.id,
        sec_uids=["sec-b", "sec-c"],
    )
    missing = await _project(
        test_session,
        name=f"cov_ca_s28_missing_{suffix}",
        admin_id=admin_user.id,
        sec_uids=["   "],
    )
    unselected = await _project(
        test_session,
        name=f"cov_ca_s28_unselected_auto_{suffix}",
        admin_id=admin_user.id,
        sec_uids=["sec-unselected-auto"],
    )
    config = AgentTaskConfig(
        agent_code="content-analysis",
        selected_project_ids=[second.id, missing.id, first.id],
        report_root_ref="folder-secret-ref",
        updated_by=admin_user.id,
    )
    test_session.add(config)
    await test_session.commit()
    executor = FakeExecutor(results={
        "sec-a": {
            "feishu_relation": {"status": "ready", "content_read_status": "ready"},
            "internal_result": {
                "status": "success",
                "outcome": "content",
                "internal_result_id": "internal-a",
            },
            "delivery": {
                "status": "failed",
                "reason_code": "DELIVERY_FAILED",
                "delivery_identity": "document-a",
            },
        },
    })

    result = await run_automatic_tick(
        test_session,
        executor=executor,
        now=datetime(2026, 9, 7, 1, 0, tzinfo=SHANGHAI),
        enabled=True,
        system_user_id=admin_user.id,
    )
    await wait_for_automatic_executions()
    await test_session.commit()

    assert result == {"status": "success", "task_code": "weekly", "created": 3, "existing": 0}
    account_calls = [
        call for call in executor.execute_calls
        if call["execution"]["object_type"] == "account"
    ]
    assert [call["execution"]["account_key"] for call in account_calls] == [
        "sec-a", "sec-b", "sec-c",
    ]
    assert all(unselected.id not in call["execution"]["project_ids"] for call in account_calls)
    assert [call["execution"]["batch_position"] for call in account_calls] == [1, 2, 3]
    assert all(call["execution"]["batch_size"] == 3 for call in account_calls)
    assert account_calls[1]["execution"]["project_ids"] == sorted([first.id, second.id])
    assert len({call["execution"]["weekly_batch_id"] for call in account_calls}) == 1
    assert len({call["idempotency"]["document_key"] for call in executor.execute_calls}) == 1
    assert executor.execute_calls[-1]["execution"]["object_type"] == "weekly_batch_finalize"
    assert executor.execute_calls[-1]["delivery_target"]["report_root_ref"] == "folder-secret-ref"

    tasks = (await test_session.execute(select(TaskJob).where(
        TaskJob.created_by == admin_user.id,
        TaskJob.input_payload["business_date"].astext == "2026-09-06",
        TaskJob.input_payload["execution"]["object_type"].astext == "account",
    ).order_by(TaskJob.id))).scalars().all()
    assert [task.status for task in tasks] == ["failed", "success", "success"]
    assert all(task.created_by == admin_user.id for task in tasks)
    assert tasks[0].result_summary["failure_stage"] == "delivery"

    repeated = await run_automatic_tick(
        test_session,
        executor=executor,
        now=datetime(2026, 9, 7, 1, 0, tzinfo=SHANGHAI),
        enabled=True,
        system_user_id=admin_user.id,
    )
    await wait_for_automatic_executions()
    assert repeated == {"status": "success", "task_code": "weekly", "created": 0, "existing": 3}
    assert len(executor.execute_calls) == 4


@pytest.mark.asyncio
async def test_daily_auto_persists_full_batch_and_next_weekly_batch_before_blocked_work_finishes(
    test_engine, test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    first = await _project(
        test_session, name=f"cov_ca_s28_queue_daily_first_{suffix}",
        admin_id=admin_user.id, sec_uids=["queue-shared"],
    )
    second = await _project(
        test_session, name=f"cov_ca_s28_queue_daily_second_{suffix}",
        admin_id=admin_user.id, sec_uids=["queue-shared"],
    )
    missing = await _project(
        test_session, name=f"cov_ca_s28_queue_daily_missing_{suffix}",
        admin_id=admin_user.id, sec_uids=[],
    )
    test_session.add(AgentTaskConfig(
        agent_code="content-analysis",
        selected_project_ids=[first.id, second.id, missing.id],
        report_root_ref="queue-daily-root",
        updated_by=admin_user.id,
    ))
    await test_session.commit()
    executor = BlockingExecutor()
    daily_tick = asyncio.create_task(run_automatic_tick(
        test_session,
        executor=executor,
        now=datetime(2026, 9, 7, 0, 0, tzinfo=SHANGHAI),
        enabled=True,
        system_user_id=admin_user.id,
    ))
    await asyncio.wait_for(executor.started.wait(), timeout=2)
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as observer:
            daily_tasks = (await observer.execute(select(TaskJob).where(
                TaskJob.tool_code == "content-analysis-daily",
                TaskJob.input_payload["business_date"].astext == "2026-09-06",
            ).order_by(TaskJob.id))).scalars().all()
            assert [task.input_payload["execution"]["project_id"] for task in daily_tasks] == [
                first.id, second.id, missing.id,
            ]
            assert daily_tasks[-1].status == "not_run"
            await converge_overdue_tasks(
                observer,
                now=datetime(2026, 9, 7, 13, 0, tzinfo=SHANGHAI),
            )
            await observer.commit()

        daily_result = await asyncio.wait_for(asyncio.shield(daily_tick), timeout=1)
        assert daily_result == {"status": "success", "task_code": "daily", "created": 3, "existing": 0}

        async with factory() as weekly_session:
            weekly_result = await asyncio.wait_for(run_automatic_tick(
                weekly_session,
                executor=executor,
                now=datetime(2026, 9, 7, 1, 0, tzinfo=SHANGHAI),
                enabled=True,
                system_user_id=admin_user.id,
            ), timeout=1)
            assert weekly_result == {
                "status": "success", "task_code": "weekly", "created": 1, "existing": 0,
            }

        async with factory() as observer:
            weekly_tasks = (await observer.execute(select(TaskJob).where(
                TaskJob.tool_code == "content-analysis-weekly",
                TaskJob.input_payload["business_date"].astext == "2026-09-06",
            ))).scalars().all()
            assert len(weekly_tasks) == 1
    finally:
        executor.release.set()
        if not daily_tick.done():
            await daily_tick
        await wait_for_automatic_executions()

    async with factory() as observer:
        first_task = await observer.scalar(select(TaskJob).where(
            TaskJob.tool_code == "content-analysis-daily",
            TaskJob.input_payload["execution"]["project_id"].astext == str(first.id),
        ))
        assert first_task.status == "failed"
        assert first_task.result_summary["failure_stage"] == "timeout"


@pytest.mark.asyncio
async def test_weekly_auto_persists_whole_batch_then_executes_in_order_after_failure(
    test_engine, test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    project = await _project(
        test_session, name=f"cov_ca_s28_queue_weekly_{suffix}", admin_id=admin_user.id,
        sec_uids=["queue-c", "queue-a", "queue-b"],
    )
    test_session.add(AgentTaskConfig(
        agent_code="content-analysis",
        selected_project_ids=[project.id],
        report_root_ref="queue-weekly-root",
        updated_by=admin_user.id,
    ))
    await test_session.commit()
    executor = FirstCallBlockingExecutor()
    tick = asyncio.create_task(run_automatic_tick(
        test_session,
        executor=executor,
        now=datetime(2026, 9, 7, 1, 0, tzinfo=SHANGHAI),
        enabled=True,
        system_user_id=admin_user.id,
    ))
    await asyncio.wait_for(executor.first_started.wait(), timeout=2)
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as observer:
            tasks = (await observer.execute(select(TaskJob).where(
                TaskJob.tool_code == "content-analysis-weekly",
                TaskJob.input_payload["business_date"].astext == "2026-09-06",
            ).order_by(TaskJob.input_payload["execution"]["batch_position"].astext))).scalars().all()
            assert len(tasks) == 3
        assert await asyncio.wait_for(asyncio.shield(tick), timeout=1) == {
            "status": "success", "task_code": "weekly", "created": 3, "existing": 0,
        }
        assert [call["execution"]["account_key"] for call in executor.execute_calls] == ["queue-a"]
    finally:
        executor.release_first.set()
        if not tick.done():
            await tick
        await wait_for_automatic_executions()

    account_calls = [
        call for call in executor.execute_calls
        if call["execution"]["object_type"] == "account"
    ]
    assert [call["execution"]["account_key"] for call in account_calls] == [
        "queue-a", "queue-b", "queue-c",
    ]
    assert executor.execute_calls[-1]["execution"]["object_type"] == "weekly_batch_finalize"
    async with factory() as observer:
        statuses = (await observer.execute(select(TaskJob.status).where(
            TaskJob.tool_code == "content-analysis-weekly",
            TaskJob.input_payload["business_date"].astext == "2026-09-06",
            TaskJob.input_payload["execution"]["object_type"].astext == "account",
        ).order_by(TaskJob.input_payload["execution"]["batch_position"].astext))).scalars().all()
        assert statuses == ["failed", "success", "success"]


@pytest.mark.asyncio
async def test_scheduler_shutdown_cancels_and_waits_for_tracked_automatic_work(
    test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    project = await _project(
        test_session, name=f"cov_ca_s28_shutdown_{suffix}", admin_id=admin_user.id,
        sec_uids=["shutdown-sec"],
    )
    test_session.add(AgentTaskConfig(
        agent_code="content-analysis",
        selected_project_ids=[project.id],
        report_root_ref="shutdown-root",
        updated_by=admin_user.id,
    ))
    await test_session.commit()
    executor = BlockingExecutor()

    result = await run_automatic_tick(
        test_session,
        executor=executor,
        now=datetime(2026, 9, 8, 0, 0, tzinfo=SHANGHAI),
        enabled=True,
        system_user_id=admin_user.id,
    )
    await asyncio.wait_for(executor.started.wait(), timeout=2)
    await shutdown_content_analysis_scheduler(None)

    assert result == {"status": "success", "task_code": "daily", "created": 1, "existing": 0}
    assert executor.cancelled.is_set()


@pytest.mark.asyncio
async def test_automatic_tick_fails_closed_for_missing_or_invalid_system_account(
    test_session,
    admin_user,
    caplog,
):
    executor = FakeExecutor()
    before = await test_session.scalar(select(func.count()).select_from(TaskJob))

    missing = await run_automatic_tick(
        test_session,
        executor=executor,
        now=datetime(2026, 9, 8, 0, 0, tzinfo=SHANGHAI),
        enabled=True,
        system_user_id=None,
    )
    admin_user.status = "disabled"
    await test_session.commit()
    invalid = await run_automatic_tick(
        test_session,
        executor=executor,
        now=datetime(2026, 9, 8, 0, 0, tzinfo=SHANGHAI),
        enabled=True,
        system_user_id=admin_user.id,
    )

    assert missing == {"status": "failed", "error_code": "SYSTEM_ACCOUNT_INVALID", "created": 0}
    assert invalid == missing
    assert await test_session.scalar(select(func.count()).select_from(TaskJob)) == before
    assert executor.execute_calls == []
    assert "SYSTEM_ACCOUNT_INVALID" in caplog.text


@pytest.mark.asyncio
async def test_automatic_tick_rejects_enabled_operator_before_creating_tasks(
    test_session,
    admin_user,
    operator_user,
):
    suffix = uuid4().hex[:8]
    project = await _project(
        test_session,
        name=f"cov_ca_s28_operator_system_{suffix}",
        admin_id=admin_user.id,
        sec_uids=["operator-system-sec"],
    )
    test_session.add(AgentTaskConfig(
        agent_code="content-analysis",
        selected_project_ids=[project.id],
        report_root_ref="operator-system-root",
        updated_by=admin_user.id,
    ))
    await test_session.commit()
    executor = FakeExecutor()
    before = await test_session.scalar(select(func.count()).select_from(TaskJob))

    result = await run_automatic_tick(
        test_session,
        executor=executor,
        now=datetime(2026, 9, 8, 0, 0, tzinfo=SHANGHAI),
        enabled=True,
        system_user_id=operator_user.id,
    )

    assert result == {
        "status": "failed",
        "error_code": "SYSTEM_ACCOUNT_INVALID",
        "created": 0,
    }
    assert await test_session.scalar(select(func.count()).select_from(TaskJob)) == before
    assert executor.execute_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("task_code", "scheduled_for", "recovered_at", "business_date"),
    [
        (
            "daily",
            datetime(2026, 9, 8, 0, 0, tzinfo=SHANGHAI),
            datetime(2026, 9, 8, 13, 0, tzinfo=SHANGHAI),
            "2026-09-07",
        ),
        (
            "weekly",
            datetime(2026, 9, 7, 1, 0, tzinfo=SHANGHAI),
            datetime(2026, 9, 7, 14, 0, tzinfo=SHANGHAI),
            "2026-09-06",
        ),
    ],
)
async def test_recovery_uses_fixed_business_window_but_a_fresh_execution_deadline(
    task_code, scheduled_for, recovered_at, business_date, test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    project = await _project(
        test_session,
        name=f"cov_ca_s28_recovery_deadline_{task_code}_{suffix}",
        admin_id=admin_user.id,
        sec_uids=[f"recovery-deadline-{suffix}"],
    )
    test_session.add(AgentTaskConfig(
        agent_code="content-analysis",
        selected_project_ids=[project.id],
        report_root_ref="recovery-root",
        updated_by=admin_user.id,
    ))
    await test_session.commit()
    executor = FakeExecutor()

    result = await run_automatic_tick(
        test_session,
        executor=executor,
        now=recovered_at,
        scheduled_for=scheduled_for,
        enabled=True,
        system_user_id=admin_user.id,
    )
    await wait_for_automatic_executions()

    assert result["task_code"] == task_code
    assert executor.execute_calls
    for envelope in executor.execute_calls:
        assert envelope["business_date"] == business_date
        assert envelope["triggered_at"] == recovered_at.isoformat()
        assert datetime.fromisoformat(envelope["deadline_at"]) > recovered_at


@pytest.mark.asyncio
async def test_recovery_executes_persisted_daily_task_after_project_scope_changes(
    test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    project = await _project(
        test_session,
        name=f"cov_ca_s28_resume_daily_{suffix}",
        admin_id=admin_user.id,
        sec_uids=[f"resume-daily-{suffix}"],
    )
    config = AgentTaskConfig(
        agent_code="content-analysis",
        selected_project_ids=[project.id],
        report_root_ref="resume-daily-root",
        updated_by=admin_user.id,
    )
    test_session.add(config)
    await test_session.commit()
    execution = {"object_type": "project", "project_id": project.id}
    keys = make_idempotency_keys(
        task_code="daily",
        run_type="auto",
        business_date="2026-09-07",
        execution=execution,
    )
    task, created, should_execute = await prepare_execution_task(
        test_session,
        task_code="daily",
        run_type="auto",
        execution=execution,
        database_precheck={"status": "ready"},
        report_root_ref="resume-daily-root",
        idempotency=keys,
        created_by=admin_user.id,
        triggered_at=datetime(2026, 9, 8, 0, 0, tzinfo=SHANGHAI),
    )
    await test_session.commit()
    config.selected_project_ids = []
    await test_session.commit()
    executor = FakeExecutor()

    resumed = await _resume_pending_automatic_tasks(
        test_session,
        executor=executor,
        now=datetime(2026, 9, 8, 0, 5, tzinfo=SHANGHAI),
        system_user_id=admin_user.id,
    )
    await wait_for_automatic_executions()
    await test_session.refresh(task)

    assert (created, should_execute, resumed) == (True, True, 1)
    assert task.status == "success"
    assert len(executor.execute_calls) == 1


@pytest.mark.asyncio
async def test_recovery_executes_persisted_weekly_batch_after_account_scope_changes(
    test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    project = await _project(
        test_session,
        name=f"cov_ca_s28_resume_weekly_{suffix}",
        admin_id=admin_user.id,
        sec_uids=[f"resume-weekly-b-{suffix}", f"resume-weekly-a-{suffix}"],
    )
    config = AgentTaskConfig(
        agent_code="content-analysis",
        selected_project_ids=[project.id],
        report_root_ref="resume-weekly-root",
        updated_by=admin_user.id,
    )
    test_session.add(config)
    await test_session.commit()
    batch_id = "content-analysis:weekly:2026-09-06"
    pending_tasks = []
    for position, account_key in enumerate(
        [f"resume-weekly-a-{suffix}", f"resume-weekly-b-{suffix}"],
        start=1,
    ):
        execution = {
            "object_type": "account",
            "account_key": account_key,
            "project_ids": [project.id],
            "weekly_batch_id": batch_id,
            "batch_size": 2,
            "batch_position": position,
        }
        task, created, should_execute = await prepare_execution_task(
            test_session,
            task_code="weekly",
            run_type="auto",
            execution=execution,
            database_precheck={"status": "ready"},
            report_root_ref="resume-weekly-root",
            idempotency=make_idempotency_keys(
                task_code="weekly",
                run_type="auto",
                business_date="2026-09-06",
                execution=execution,
                document_key=batch_id,
            ),
            created_by=admin_user.id,
            triggered_at=datetime(2026, 9, 7, 1, 0, tzinfo=SHANGHAI),
        )
        assert created and should_execute
        pending_tasks.append(task)
    await test_session.commit()
    config.selected_project_ids = []
    await test_session.commit()
    executor = FakeExecutor()

    resumed = await _resume_pending_automatic_tasks(
        test_session,
        executor=executor,
        now=datetime(2026, 9, 7, 1, 5, tzinfo=SHANGHAI),
        system_user_id=admin_user.id,
    )
    await wait_for_automatic_executions()
    for task in pending_tasks:
        await test_session.refresh(task)

    account_calls = [
        call for call in executor.execute_calls
        if call["execution"]["object_type"] == "account"
    ]
    assert resumed == 2
    assert [call["execution"]["batch_position"] for call in account_calls] == [1, 2]
    assert all(task.status == "success" for task in pending_tasks)
    assert executor.execute_calls[-1]["execution"]["object_type"] == "weekly_batch_finalize"


@pytest.mark.asyncio
async def test_daily_auto_precheck_missing_is_not_run_without_calling_executor(
    test_session,
    admin_user,
):
    suffix = uuid4().hex[:8]
    ready = await _project(
        test_session,
        name=f"cov_ca_s28_daily_ready_{suffix}",
        admin_id=admin_user.id,
        sec_uids=["daily-sec"],
    )
    missing = await _project(
        test_session,
        name=f"cov_ca_s28_daily_missing_{suffix}",
        admin_id=admin_user.id,
        sec_uids=[],
    )
    test_session.add(AgentTaskConfig(
        agent_code="content-analysis",
        selected_project_ids=[ready.id, missing.id],
        report_root_ref="daily-folder",
        updated_by=admin_user.id,
    ))
    await test_session.commit()
    executor = FakeExecutor()

    result = await run_automatic_tick(
        test_session,
        executor=executor,
        now=datetime(2026, 9, 8, 0, 0, tzinfo=SHANGHAI),
        enabled=True,
        system_user_id=admin_user.id,
    )
    await wait_for_automatic_executions()
    await test_session.commit()

    assert result == {"status": "success", "task_code": "daily", "created": 2, "existing": 0}
    assert len(executor.execute_calls) == 1
    assert executor.execute_calls[0]["business_date"] == "2026-09-07"
    tasks = (await test_session.execute(select(TaskJob).where(
        TaskJob.created_by == admin_user.id,
        TaskJob.input_payload["business_date"].astext == "2026-09-07",
    ).order_by(TaskJob.id))).scalars().all()
    assert [task.status for task in tasks] == ["success", "not_run"]
    assert tasks[1].result_summary == {
        "failure_stage": None,
        "database_precheck": {
            "status": "missing",
            "reason_code": "CONTENT_BENCHMARK_SEC_UID_MISSING",
            "input_limited": True,
            "input_limited_reasons": [
                "BACKGROUND_MISSING", "EXPERIENCE_MISSING", "RELATIONSHIPS_MISSING",
                "UNIQUE_STORY_MISSING", "EXTRA_NOTES_MISSING", "STYLE_NOTES_MISSING",
            ],
        },
        "feishu_relation": {"status": "skipped"},
        "internal_result": {"status": "skipped"},
        "delivery": {"status": "skipped"},
        "execution": {"object_type": "project", "project_id": missing.id},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("task_code", "triggered_at"),
    [
        ("daily", datetime(2026, 9, 8, 0, 0, tzinfo=SHANGHAI)),
        ("weekly", datetime(2026, 9, 7, 1, 0, tzinfo=SHANGHAI)),
    ],
)
async def test_automatic_run_without_report_root_persists_not_run_and_never_calls_executor(
    task_code, triggered_at, test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    project = await _project(
        test_session,
        name=f"cov_ca_s28_root_missing_auto_{task_code}_{suffix}",
        admin_id=admin_user.id,
        sec_uids=[f"root-missing-{task_code}-{suffix}"],
    )
    test_session.add(AgentTaskConfig(
        agent_code="content-analysis",
        selected_project_ids=[project.id],
        report_root_ref=None,
        updated_by=admin_user.id,
    ))
    await test_session.commit()
    executor = FakeExecutor()

    result = await run_automatic_tick(
        test_session,
        executor=executor,
        now=triggered_at,
        enabled=True,
        system_user_id=admin_user.id,
    )
    await wait_for_automatic_executions()
    task = await test_session.scalar(select(TaskJob).where(
        TaskJob.tool_code == f"content-analysis-{task_code}",
        TaskJob.created_by == admin_user.id,
    ).order_by(TaskJob.id.desc()))

    assert result["created"] == 1
    assert task.status == "not_run"
    assert task.result_summary["database_precheck"]["reason_code"] == "REPORT_ROOT_REF_MISSING"
    assert task.result_summary["feishu_relation"] == {"status": "skipped"}
    assert task.result_summary["internal_result"] == {"status": "skipped"}
    assert task.result_summary["delivery"] == {"status": "skipped"}
    assert "deadline_at" not in task.input_payload
    assert executor.execute_calls == []


@pytest.mark.asyncio
async def test_test_mode_uses_test_scope_and_does_not_write_formal_business_outputs(
    test_session,
    admin_user,
):
    suffix = uuid4().hex[:8]
    project = await _project(
        test_session,
        name=f"cov_ca_s28_test_{suffix}",
        admin_id=admin_user.id,
        sec_uids=["test-sec"],
    )
    test_session.add(AgentTaskConfig(
        agent_code="content-analysis",
        selected_project_ids=[],
        report_root_ref="test-root",
        updated_by=admin_user.id,
    ))
    await test_session.commit()
    executor = FakeExecutor()
    output_count = await test_session.scalar(select(func.count()).select_from(Output))

    task = await run_test_execution(
        test_session,
        executor=executor,
        task_code="daily",
        project_id=project.id,
        account_key=None,
        created_by=admin_user.id,
        request_id=f"test-{suffix}",
        triggered_at=datetime(2026, 9, 5, 10, 0, tzinfo=SHANGHAI),
    )
    await test_session.commit()

    assert task.status == "success"
    assert task.output_id is None
    assert executor.execute_calls[0]["delivery_target"] == {
        "report_root_ref": "test-root",
        "scope": "test",
        "test_subdirectory": "测试报告",
    }
    assert executor.test_documents == [{"task_id": task.id}]
    assert executor.formal_daily_reports == []
    assert executor.content_library == []
    assert executor.cross_project_opportunities == []
    assert executor.account_baselines == []
    assert await test_session.scalar(select(func.count()).select_from(Output)) == output_count


@pytest.mark.asyncio
@pytest.mark.parametrize("report_root_ref", ["test-root", None])
async def test_weekly_result_summary_never_persists_raw_account_key(
    report_root_ref, test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    account_key = f"sensitive-account-{suffix}"
    project = await _project(
        test_session,
        name=f"cov_ca_s28_summary_privacy_{suffix}",
        admin_id=admin_user.id,
        sec_uids=[account_key],
    )
    test_session.add(AgentTaskConfig(
        agent_code="content-analysis",
        selected_project_ids=[],
        report_root_ref=report_root_ref,
        updated_by=admin_user.id,
    ))
    await test_session.commit()

    task = await run_test_execution(
        test_session,
        executor=FakeExecutor(),
        task_code="weekly",
        project_id=None,
        account_key=account_key,
        created_by=admin_user.id,
        request_id=f"summary-privacy-{suffix}",
        triggered_at=datetime(2026, 9, 5, 10, 0, tzinfo=SHANGHAI),
    )
    await test_session.refresh(task)

    assert task.input_payload["execution"]["account_key"] == account_key
    assert account_key not in str(task.result_summary["execution"])
    assert task.result_summary["execution"] == {
        "object_type": "account",
        "account_key_hash": hashlib.sha256(account_key.encode("utf-8")).hexdigest()[:16],
        "project_ids": [project.id],
        "weekly_batch_id": f"weekly-test-summary-privacy-{suffix}",
        "batch_size": 1,
        "batch_position": 1,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("task_code", ["daily", "weekly"])
async def test_test_run_without_report_root_is_not_run_without_executor_call(
    task_code, test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    account_key = f"test-root-missing-{task_code}-{suffix}"
    project = await _project(
        test_session,
        name=f"cov_ca_s28_root_missing_test_{task_code}_{suffix}",
        admin_id=admin_user.id,
        sec_uids=[account_key],
    )
    test_session.add(AgentTaskConfig(
        agent_code="content-analysis",
        selected_project_ids=[],
        report_root_ref=None,
        updated_by=admin_user.id,
    ))
    await test_session.commit()
    executor = FakeExecutor()

    task = await run_test_execution(
        test_session,
        executor=executor,
        task_code=task_code,
        project_id=project.id if task_code == "daily" else None,
        account_key=account_key if task_code == "weekly" else None,
        created_by=admin_user.id,
        request_id=f"root-missing-{task_code}-{suffix}",
        triggered_at=datetime(2026, 9, 5, 10, 0, tzinfo=SHANGHAI),
    )

    assert task.status == "not_run"
    assert task.result_summary["database_precheck"]["reason_code"] == "REPORT_ROOT_REF_MISSING"
    assert task.result_summary["feishu_relation"] == {"status": "skipped"}
    assert executor.execute_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("task_code", ["daily", "weekly"])
async def test_same_normalized_test_request_is_idempotent_but_different_request_is_new(
    task_code, test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    project = await _project(
        test_session,
        name=f"cov_ca_s28_test_idempotent_{task_code}_{suffix}",
        admin_id=admin_user.id,
        sec_uids=[f"test-idempotent-{task_code}-{suffix}"],
    )
    test_session.add(AgentTaskConfig(
        agent_code="content-analysis",
        selected_project_ids=[],
        report_root_ref="idempotent-test-root",
        updated_by=admin_user.id,
    ))
    await test_session.commit()
    executor = FakeExecutor()
    common = {
        "db": test_session,
        "executor": executor,
        "task_code": task_code,
        "project_id": project.id if task_code == "daily" else None,
        "account_key": None if task_code == "daily" else f"test-idempotent-{task_code}-{suffix}",
        "created_by": admin_user.id,
        "triggered_at": datetime(2026, 9, 5, 10, 0, tzinfo=SHANGHAI),
    }

    first = await run_test_execution(
        **common,
        request_id=f"  same-test-{task_code}-{suffix}  ",
    )
    repeated = await run_test_execution(
        **common,
        request_id=f"same-test-{task_code}-{suffix}",
    )
    different = await run_test_execution(
        **common,
        request_id=f"different-test-{task_code}-{suffix}",
    )

    assert first.id == repeated.id
    assert different.id != first.id
    assert len(executor.execute_calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("task_code", ["daily", "weekly"])
async def test_concurrent_same_test_request_creates_and_executes_once(
    task_code, test_engine, test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    account_key = f"test-concurrent-{task_code}-{suffix}"
    project = await _project(
        test_session,
        name=f"cov_ca_s28_test_concurrent_{task_code}_{suffix}",
        admin_id=admin_user.id,
        sec_uids=[account_key],
    )
    test_session.add(AgentTaskConfig(
        agent_code="content-analysis",
        selected_project_ids=[],
        report_root_ref="concurrent-test-root",
        updated_by=admin_user.id,
    ))
    await test_session.commit()
    executor = BlockingExecutor()
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    request_id = f"same-concurrent-test-{task_code}-{suffix}"

    async with factory() as first_session, factory() as second_session:
        first_call = asyncio.create_task(run_test_execution(
            first_session,
            executor=executor,
            task_code=task_code,
            project_id=project.id if task_code == "daily" else None,
            account_key=None if task_code == "daily" else account_key,
            created_by=admin_user.id,
            request_id=request_id,
            triggered_at=datetime(2026, 9, 5, 10, 0, tzinfo=SHANGHAI),
        ))
        await asyncio.wait_for(executor.started.wait(), timeout=2)
        second_call = asyncio.create_task(run_test_execution(
            second_session,
            executor=executor,
            task_code=task_code,
            project_id=project.id if task_code == "daily" else None,
            account_key=None if task_code == "daily" else account_key,
            created_by=admin_user.id,
            request_id=request_id,
            triggered_at=datetime(2026, 9, 5, 10, 1, tzinfo=SHANGHAI),
        ))
        await asyncio.sleep(0.2)
        assert len(executor.execute_calls) == 1
        executor.release.set()
        first, second = await asyncio.gather(first_call, second_call)

    assert first.id == second.id
    assert len(executor.execute_calls) == 1


@pytest.mark.asyncio
async def test_delivery_failure_manual_retry_redelivers_once_for_same_request_id(
    test_session,
    admin_user,
):
    suffix = uuid4().hex[:8]
    project = await _project(
        test_session,
        name=f"cov_ca_s28_retry_{suffix}",
        admin_id=admin_user.id,
        sec_uids=["retry-sec"],
    )
    test_session.add(AgentTaskConfig(
        agent_code="content-analysis",
        selected_project_ids=[project.id],
        report_root_ref="retry-root",
        updated_by=admin_user.id,
    ))
    original = TaskJob(
        task_no=f"CA-S28-{suffix}-original",
        tool_code="content-analysis-daily",
        tool_name="内容分析",
        status="failed",
        input_payload={
            "contract_version": "2.0",
            "agent_code": "content-analysis",
            "task_code": "daily",
            "run_type": "auto",
            "business_date": "2026-09-04",
            "analysis_window": {
                "start": "2026-09-02T00:00:00+08:00",
                "end": "2026-09-05T00:00:00+08:00",
                "timezone": "Asia/Shanghai",
                "end_exclusive": True,
            },
            "triggered_at": "2026-09-05T00:00:00+08:00",
                "deadline_at": "2026-09-05T12:00:00+08:00",
                "execution": {"object_type": "project", "project_id": project.id},
                "delivery_target": {"report_root_ref": "retry-root", "scope": "formal"},
                "idempotency": {
                "run_key": "original-run",
                "internal_result_key": "original-internal",
                "document_key": "original-document",
            },
        },
        result_summary={
            "failure_stage": "delivery",
            "database_precheck": {"status": "ready", "reason_code": None},
            "feishu_relation": {"status": "ready", "content_read_status": "ready"},
            "internal_result": {
                "status": "success", "internal_result_id": "internal-original",
            },
            "delivery": {
                "status": "failed", "delivery_identity": "document-original",
            },
            "execution": {"object_type": "project", "project_id": project.id},
        },
        created_by=admin_user.id,
    )
    test_session.add(original)
    await test_session.commit()
    executor = FakeExecutor()
    triggered_at = datetime(2026, 9, 6, 9, 0, tzinfo=SHANGHAI)

    first = await retry_failed_execution(
        test_session,
        executor=executor,
        task_id=original.id,
        created_by=admin_user.id,
        request_id=f"retry-request-{suffix}",
        triggered_at=triggered_at,
    )
    await test_session.commit()
    second = await retry_failed_execution(
        test_session,
        executor=executor,
        task_id=original.id,
        created_by=admin_user.id,
        request_id=f"retry-request-{suffix}",
        triggered_at=triggered_at + timedelta(minutes=1),
    )

    assert first.id == second.id
    assert first.status == "success"
    assert len(executor.redeliver_calls) == 1
    assert executor.execute_calls == []
    envelope, internal_result_id, delivery_identity = executor.redeliver_calls[0]
    assert (internal_result_id, delivery_identity) == ("internal-original", "document-original")
    assert envelope["run_type"] == "manual_retry"
    assert envelope["retry"] == {
        "retry_of_task_id": original.id,
        "mode": "delivery_only",
        "request_id": f"retry-request-{suffix}",
    }
    assert envelope["business_date"] == "2026-09-04"
    assert envelope["analysis_window"] == original.input_payload["analysis_window"]
    assert envelope["deadline_at"] == "2026-09-06T21:00:00+08:00"
    assert envelope["idempotency"]["internal_result_key"] == "original-internal"
    assert envelope["idempotency"]["document_key"] == "original-document"


@pytest.mark.asyncio
async def test_internal_retry_reuses_task_window_and_deadline(
    test_session,
    admin_user,
):
    suffix = uuid4().hex[:8]
    project = await _project(
        test_session,
        name=f"cov_ca_s28_internal_{suffix}",
        admin_id=admin_user.id,
        sec_uids=["internal-sec"],
    )
    task = TaskJob(
        task_no=f"CA-S28-{suffix}-internal",
        tool_code="content-analysis-daily",
        tool_name="内容分析",
        status="processing",
        input_payload={
            "contract_version": "2.0",
            "agent_code": "content-analysis",
            "task_code": "daily",
            "run_type": "auto",
            "business_date": "2026-09-04",
            "analysis_window": {
                "start": "2026-09-02T00:00:00+08:00",
                "end": "2026-09-05T00:00:00+08:00",
                "timezone": "Asia/Shanghai",
                "end_exclusive": True,
            },
            "triggered_at": "2026-09-05T00:00:00+08:00",
            "deadline_at": "2026-09-05T12:00:00+08:00",
            "execution": {"object_type": "project", "project_id": project.id},
            "database_precheck": {"status": "ready", "reason_code": None},
            "delivery_target": {"report_root_ref": "root", "scope": "formal", "test_subdirectory": None},
            "idempotency": {
                "run_key": "internal-run",
                "internal_result_key": "internal-result-key",
                "document_key": "internal-document",
            },
        },
        result_summary={},
        created_by=admin_user.id,
    )
    test_session.add(task)
    await test_session.commit()
    executor = FakeExecutor()

    await run_internal_retry(
        test_session,
        executor=executor,
        task_id=task.id,
        now=datetime(2026, 9, 5, 1, 0, tzinfo=SHANGHAI),
    )

    assert len(executor.execute_calls) == 1
    envelope = executor.execute_calls[0]
    assert envelope["task_identity"]["task_id"] == task.id
    assert envelope["run_type"] == "internal_retry"
    assert envelope["business_date"] == "2026-09-04"
    assert envelope["analysis_window"] == task.input_payload["analysis_window"]
    assert envelope["triggered_at"] == "2026-09-05T00:00:00+08:00"
    assert envelope["deadline_at"] == "2026-09-05T12:00:00+08:00"
    assert envelope["idempotency"] == task.input_payload["idempotency"]


@pytest.mark.asyncio
async def test_late_executor_result_cannot_overwrite_timeout_terminal_state(
    test_engine,
    test_session,
    admin_user,
):
    task = TaskJob(
        task_no=f"CA-S28-late-{uuid4().hex}",
        tool_code="content-analysis-daily",
        tool_name="内容分析",
        status="processing",
        input_payload={"agent_code": "content-analysis"},
        result_summary={},
        created_by=admin_user.id,
    )
    test_session.add(task)
    await test_session.commit()
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as timeout_session, factory() as late_session:
        timed_out = await timeout_session.get(TaskJob, task.id)
        timed_out.status = "failed"
        timed_out.error_code = "TASK_TIMEOUT"
        timed_out.result_summary = {
            "failure_stage": "timeout",
            "database_precheck": {"status": "ready"},
            "feishu_relation": {"status": "skipped"},
            "internal_result": {"status": "skipped"},
            "delivery": {"status": "skipped"},
        }
        await timeout_session.commit()

        updated = await apply_executor_result_if_active(
            late_session,
            task_id=task.id,
            database_precheck={"status": "ready"},
            executor_result=_successful_result(suffix="late"),
            finished_at=datetime(2026, 9, 5, 2, 0, tzinfo=SHANGHAI),
        )
        await late_session.commit()

        assert updated is False
        persisted = await late_session.get(TaskJob, task.id)
        assert persisted.status == "failed"
        assert persisted.result_summary["failure_stage"] == "timeout"
        assert await late_session.scalar(select(TaskLog.id).where(
            TaskLog.task_id == task.id,
            TaskLog.step_code == "executor_result",
        )) is None


@pytest.mark.asyncio
async def test_executor_deadline_failure_persists_timeout_stage_and_reason(
    test_session,
    admin_user,
):
    task = TaskJob(
        task_no=f"CA-S28-deadline-{uuid4().hex}",
        tool_code="content-analysis-daily",
        tool_name="内容分析",
        status="processing",
        input_payload={
            "agent_code": "content-analysis",
            "execution": {"object_type": "project", "project_id": 7},
        },
        result_summary={},
        created_by=admin_user.id,
        started_at=datetime(2026, 9, 5, 0, 0, tzinfo=SHANGHAI),
    )
    test_session.add(task)
    await test_session.commit()

    updated = await apply_executor_result_if_active(
        test_session,
        task_id=task.id,
        database_precheck={"status": "ready"},
        executor_result={
            "failure_stage": "timeout",
            "feishu_relation": {"status": "skipped"},
            "internal_result": {
                "status": "failed",
                "reason_code": "DEADLINE_EXCEEDED",
            },
            "delivery": {"status": "skipped"},
        },
        finished_at=datetime(2026, 9, 5, 12, 0, tzinfo=SHANGHAI),
    )
    await test_session.commit()
    await test_session.refresh(task)

    assert updated is True
    assert task.status == "failed"
    assert task.result_summary["failure_stage"] == "timeout"
    assert task.error_code == "DEADLINE_EXCEEDED"


@pytest.mark.asyncio
async def test_created_task_is_committed_and_timeout_visible_while_executor_is_blocked(
    test_engine, test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    project = await _project(
        test_session,
        name=f"cov_ca_s28_visible_{suffix}",
        admin_id=admin_user.id,
        sec_uids=["visible-sec"],
    )
    test_session.add(AgentTaskConfig(
        agent_code="content-analysis",
        selected_project_ids=[project.id],
        report_root_ref="visible-root",
        updated_by=admin_user.id,
    ))
    await test_session.commit()
    executor = BlockingExecutor()
    triggered_at = datetime(2026, 9, 1, 0, 0, tzinfo=SHANGHAI)
    running = asyncio.create_task(run_test_execution(
        test_session,
        executor=executor,
        task_code="daily",
        project_id=project.id,
        account_key=None,
        created_by=admin_user.id,
        request_id=f"visible-{suffix}",
        triggered_at=triggered_at,
    ))
    await asyncio.wait_for(executor.started.wait(), timeout=2)
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as observer:
            task = await observer.scalar(select(TaskJob).where(
                TaskJob.input_payload["retry"]["request_id"].astext == f"visible-{suffix}",
            ))
            assert task is not None
            assert task.status == "processing"
            converged_count = await converge_overdue_tasks(
                observer,
                now=triggered_at + timedelta(hours=13),
            )
            assert converged_count >= 1
            await observer.refresh(task)
            assert task.status == "failed"
            assert task.result_summary["failure_stage"] == "timeout"
            await observer.commit()
    finally:
        executor.release.set()
        task = await running

    assert task.status == "failed"
    assert task.result_summary["failure_stage"] == "timeout"


@pytest.mark.asyncio
async def test_redelivery_exception_preserves_delivery_retry_context(
    test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    project = await _project(
        test_session,
        name=f"cov_ca_s28_redelivery_error_{suffix}",
        admin_id=admin_user.id,
        sec_uids=["delivery-sec"],
    )
    await test_session.commit()
    original = TaskJob(
        task_no=f"CA-S28-{suffix}-delivery",
        tool_code="content-analysis-daily",
        tool_name="内容分析",
        status="failed",
        input_payload={
            "agent_code": "content-analysis", "task_code": "daily", "run_type": "auto",
            "business_date": "2026-09-04",
            "analysis_window": {
                "start": "2026-09-02T00:00:00+08:00", "end": "2026-09-05T00:00:00+08:00",
                "timezone": "Asia/Shanghai", "end_exclusive": True,
            },
            "execution": {"object_type": "project", "project_id": project.id},
            "delivery_target": {"report_root_ref": "root", "scope": "formal"},
            "idempotency": {
                "run_key": "old", "internal_result_key": "internal-key", "document_key": "doc-key",
            },
        },
        result_summary={
            "failure_stage": "delivery", "database_precheck": {"status": "ready"},
            "feishu_relation": {"status": "ready", "content_read_status": "ready"},
            "internal_result": {"status": "success", "outcome": "content", "internal_result_id": "internal-id"},
            "delivery": {"status": "failed", "reason_code": "DELIVERY_FAILED", "delivery_identity": "delivery-id"},
        },
        created_by=admin_user.id,
    )
    test_session.add(original)
    await test_session.commit()
    executor = BlockingExecutor(fail_redelivery=True)

    first = await retry_failed_execution(
        test_session, executor=executor, task_id=original.id, created_by=admin_user.id,
        request_id=f"redelivery-1-{suffix}", triggered_at=datetime(2026, 9, 6, tzinfo=SHANGHAI),
    )
    executor.release.set()
    second = await retry_failed_execution(
        test_session, executor=executor, task_id=first.id, created_by=admin_user.id,
        request_id=f"redelivery-2-{suffix}", triggered_at=datetime(2026, 9, 7, tzinfo=SHANGHAI),
    )

    assert first.result_summary["failure_stage"] == "delivery"
    assert first.result_summary["internal_result"]["internal_result_id"] == "internal-id"
    assert first.result_summary["delivery"]["delivery_identity"] == "delivery-id"
    assert second.result_summary["failure_stage"] == "delivery"
    assert len(executor.redeliver_calls) == 2
    assert executor.execute_calls == []


@pytest.mark.asyncio
async def test_redelivery_runtime_setup_failure_preserves_context_for_next_retry(
    test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    project = await _project(
        test_session,
        name=f"cov_ca_s28_redelivery_runtime_{suffix}",
        admin_id=admin_user.id,
        sec_uids=["delivery-runtime-sec"],
    )
    await test_session.commit()
    original = TaskJob(
        task_no=f"CA-S28-{suffix}-delivery-runtime",
        tool_code="content-analysis-daily",
        tool_name="内容分析",
        status="failed",
        input_payload={
            "agent_code": "content-analysis", "task_code": "daily", "run_type": "auto",
            "business_date": "2026-09-04",
            "analysis_window": {
                "start": "2026-09-02T00:00:00+08:00", "end": "2026-09-05T00:00:00+08:00",
                "timezone": "Asia/Shanghai", "end_exclusive": True,
            },
            "execution": {"object_type": "project", "project_id": project.id},
            "delivery_target": {"report_root_ref": "root", "scope": "formal"},
            "idempotency": {
                "run_key": "old", "internal_result_key": "internal-key", "document_key": "doc-key",
            },
        },
        result_summary={
            "failure_stage": "delivery", "database_precheck": {"status": "ready"},
            "feishu_relation": {"status": "ready", "content_read_status": "ready"},
            "internal_result": {
                "status": "success", "outcome": "content", "internal_result_id": "internal-id",
            },
            "delivery": {
                "status": "failed", "reason_code": "DELIVERY_FAILED",
                "delivery_identity": "delivery-id",
            },
        },
        created_by=admin_user.id,
    )
    test_session.add(original)
    await test_session.commit()
    executor = RuntimeUnavailableRedeliveryExecutor()

    first = await retry_failed_execution(
        test_session, executor=executor, task_id=original.id, created_by=admin_user.id,
        request_id=f"runtime-redelivery-1-{suffix}",
        triggered_at=datetime(2026, 9, 6, tzinfo=SHANGHAI),
    )
    second = await retry_failed_execution(
        test_session, executor=executor, task_id=first.id, created_by=admin_user.id,
        request_id=f"runtime-redelivery-2-{suffix}",
        triggered_at=datetime(2026, 9, 7, tzinfo=SHANGHAI),
    )

    assert first.result_summary["feishu_relation"] == {"status": "skipped"}
    assert first.result_summary["internal_result"] == {
        "status": "skipped",
        "outcome": "content",
        "internal_result_id": "internal-id",
    }
    assert first.result_summary["delivery"] == {
        "status": "failed",
        "reason_code": "EXECUTOR_RUNTIME_UNAVAILABLE",
        "delivery_identity": "delivery-id",
    }
    assert second.result_summary["failure_stage"] == "delivery"
    assert len(executor.redeliver_calls) == 2
    assert executor.execute_calls == []


@pytest.mark.asyncio
async def test_redelivery_timeout_persists_stage_and_context_for_next_retry(
    test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    project = await _project(
        test_session,
        name=f"cov_ca_s28_redelivery_timeout_{suffix}",
        admin_id=admin_user.id,
        sec_uids=["redelivery-timeout-sec"],
    )
    await test_session.commit()
    original = TaskJob(
        task_no=f"CA-S28-{suffix}-redelivery-timeout",
        tool_code="content-analysis-daily",
        tool_name="内容分析",
        status="failed",
        input_payload={
            "agent_code": "content-analysis", "task_code": "daily", "run_type": "auto",
            "business_date": "2026-09-04",
            "analysis_window": {
                "start": "2026-09-02T00:00:00+08:00", "end": "2026-09-05T00:00:00+08:00",
                "timezone": "Asia/Shanghai", "end_exclusive": True,
            },
            "execution": {"object_type": "project", "project_id": project.id},
            "delivery_target": {"report_root_ref": "root", "scope": "formal"},
            "idempotency": {
                "run_key": "old", "internal_result_key": "internal-key", "document_key": "doc-key",
            },
        },
        result_summary={
            "failure_stage": "delivery", "database_precheck": {"status": "ready"},
            "feishu_relation": {"status": "ready", "content_read_status": "ready"},
            "internal_result": {
                "status": "success", "outcome": "content", "internal_result_id": "internal-id",
            },
            "delivery": {
                "status": "failed", "reason_code": "DELIVERY_FAILED",
                "delivery_identity": "delivery-id",
            },
        },
        created_by=admin_user.id,
    )
    test_session.add(original)
    await test_session.commit()
    executor = TimeoutRedeliveryExecutor()

    first = await retry_failed_execution(
        test_session, executor=executor, task_id=original.id, created_by=admin_user.id,
        request_id=f"timeout-redelivery-1-{suffix}",
        triggered_at=datetime(2026, 9, 6, tzinfo=SHANGHAI),
    )
    second = await retry_failed_execution(
        test_session, executor=executor, task_id=first.id, created_by=admin_user.id,
        request_id=f"timeout-redelivery-2-{suffix}",
        triggered_at=datetime(2026, 9, 7, tzinfo=SHANGHAI),
    )

    assert first.result_summary["failure_stage"] == "timeout"
    assert first.result_summary["internal_result"] == {
        "status": "skipped",
        "outcome": "content",
        "internal_result_id": "internal-id",
    }
    assert first.result_summary["delivery"] == {
        "status": "failed",
        "reason_code": "DEADLINE_EXCEEDED",
        "delivery_identity": "delivery-id",
    }
    assert second.result_summary["failure_stage"] == "timeout"
    assert len(executor.redeliver_calls) == 2
    assert executor.execute_calls == []


@pytest.mark.asyncio
async def test_delivery_timeout_retries_delivery_without_repeating_analysis(
    test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    project = await _project(
        test_session,
        name=f"cov_ca_s28_delivery_timeout_{suffix}",
        admin_id=admin_user.id,
        sec_uids=["delivery-timeout-sec"],
    )
    await test_session.commit()
    original = TaskJob(
        task_no=f"CA-S28-{suffix}-delivery-timeout",
        tool_code="content-analysis-daily",
        tool_name="内容分析",
        status="failed",
        input_payload={
            "agent_code": "content-analysis", "task_code": "daily", "run_type": "auto",
            "business_date": "2026-09-04",
            "analysis_window": {
                "start": "2026-09-02T00:00:00+08:00", "end": "2026-09-05T00:00:00+08:00",
                "timezone": "Asia/Shanghai", "end_exclusive": True,
            },
            "execution": {"object_type": "project", "project_id": project.id},
            "delivery_target": {"report_root_ref": "root", "scope": "formal"},
            "idempotency": {
                "run_key": "old", "internal_result_key": "internal-key", "document_key": "doc-key",
            },
        },
        result_summary={
            "failure_stage": "timeout", "database_precheck": {"status": "ready"},
            "feishu_relation": {"status": "ready", "content_read_status": "ready"},
            "internal_result": {
                "status": "success", "outcome": "content", "internal_result_id": "internal-id",
            },
            "delivery": {
                "status": "failed", "reason_code": "DEADLINE_EXCEEDED",
                "delivery_identity": "delivery-id",
            },
        },
        created_by=admin_user.id,
    )
    test_session.add(original)
    await test_session.commit()
    executor = FakeExecutor()

    retried = await retry_failed_execution(
        test_session, executor=executor, task_id=original.id, created_by=admin_user.id,
        request_id=f"delivery-timeout-retry-{suffix}",
        triggered_at=datetime(2026, 9, 6, tzinfo=SHANGHAI),
    )

    assert retried.input_payload["retry"]["mode"] == "delivery_only"
    assert len(executor.redeliver_calls) == 1
    assert executor.execute_calls == []


@pytest.mark.asyncio
async def test_invalid_redelivery_result_preserves_context_and_next_retry_stays_delivery_only(
    test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    project = await _project(
        test_session,
        name=f"cov_ca_s28_invalid_redelivery_{suffix}",
        admin_id=admin_user.id,
        sec_uids=["invalid-delivery-sec"],
    )
    await test_session.commit()
    original = TaskJob(
        task_no=f"CA-S28-{suffix}-invalid-delivery",
        tool_code="content-analysis-daily",
        tool_name="内容分析",
        status="failed",
        input_payload={
            "agent_code": "content-analysis", "task_code": "daily", "run_type": "auto",
            "business_date": "2026-09-04",
            "analysis_window": {
                "start": "2026-09-02T00:00:00+08:00", "end": "2026-09-05T00:00:00+08:00",
                "timezone": "Asia/Shanghai", "end_exclusive": True,
            },
            "execution": {"object_type": "project", "project_id": project.id},
            "delivery_target": {"report_root_ref": "root", "scope": "formal"},
            "idempotency": {
                "run_key": "old", "internal_result_key": "internal-key", "document_key": "doc-key",
            },
        },
        result_summary={
            "failure_stage": "delivery", "database_precheck": {"status": "ready"},
            "feishu_relation": {"status": "ready", "content_read_status": "ready"},
            "internal_result": {
                "status": "success", "outcome": "content", "internal_result_id": "internal-id",
            },
            "delivery": {
                "status": "failed", "reason_code": "DELIVERY_FAILED",
                "delivery_identity": "delivery-id",
            },
        },
        created_by=admin_user.id,
    )
    test_session.add(original)
    await test_session.commit()
    executor = InvalidRedeliveryExecutor()

    first = await retry_failed_execution(
        test_session, executor=executor, task_id=original.id, created_by=admin_user.id,
        request_id=f"invalid-redelivery-1-{suffix}",
        triggered_at=datetime(2026, 9, 6, tzinfo=SHANGHAI),
    )
    second = await retry_failed_execution(
        test_session, executor=executor, task_id=first.id, created_by=admin_user.id,
        request_id=f"invalid-redelivery-2-{suffix}",
        triggered_at=datetime(2026, 9, 7, tzinfo=SHANGHAI),
    )

    assert first.result_summary["failure_stage"] == "delivery"
    assert first.result_summary["internal_result"]["internal_result_id"] == "internal-id"
    assert first.result_summary["delivery"]["delivery_identity"] == "delivery-id"
    assert second.result_summary["failure_stage"] == "delivery"
    assert len(executor.redeliver_calls) == 2
    assert executor.execute_calls == []


@pytest.mark.asyncio
async def test_internal_redelivery_retry_normalizes_invalid_result_to_delivery_failure(
    test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    task = TaskJob(
        task_no=f"CA-S28-{suffix}-internal-invalid-delivery",
        tool_code="content-analysis-daily",
        tool_name="内容分析",
        status="processing",
        input_payload={
            "agent_code": "content-analysis", "task_code": "daily", "run_type": "auto",
            "database_precheck": {"status": "ready"},
            "execution": {"object_type": "project", "project_id": 999999},
            "delivery_target": {"report_root_ref": "root", "scope": "formal"},
        },
        result_summary={
            "failure_stage": "delivery",
            "internal_result": {
                "status": "success", "outcome": "content", "internal_result_id": "internal-id",
            },
            "delivery": {"status": "failed", "delivery_identity": "delivery-id"},
        },
        created_by=admin_user.id,
    )
    test_session.add(task)
    await test_session.commit()
    executor = InvalidRedeliveryExecutor()

    updated = await run_internal_retry(
        test_session,
        executor=executor,
        task_id=task.id,
        now=datetime(2026, 9, 6, tzinfo=SHANGHAI),
    )
    await test_session.commit()
    await test_session.refresh(task)

    assert updated is True
    assert task.result_summary["failure_stage"] == "delivery"
    assert task.result_summary["internal_result"]["internal_result_id"] == "internal-id"
    assert task.result_summary["delivery"]["delivery_identity"] == "delivery-id"
    assert len(executor.redeliver_calls) == 1
    assert executor.execute_calls == []


@pytest.mark.asyncio
async def test_concurrent_same_request_retry_creates_and_executes_once(
    test_engine, test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    project = await _project(
        test_session,
        name=f"cov_ca_s28_concurrent_retry_{suffix}",
        admin_id=admin_user.id,
        sec_uids=["retry-sec"],
    )
    await test_session.flush()
    original = TaskJob(
        task_no=f"CA-S28-{suffix}-concurrent", tool_code="content-analysis-daily",
        tool_name="内容分析", status="failed",
        input_payload={
            "agent_code": "content-analysis", "task_code": "daily", "run_type": "auto",
            "business_date": "2026-09-04",
            "analysis_window": {
                "start": "2026-09-02T00:00:00+08:00", "end": "2026-09-05T00:00:00+08:00",
                "timezone": "Asia/Shanghai", "end_exclusive": True,
            },
            "execution": {"object_type": "project", "project_id": project.id},
            "delivery_target": {"scope": "formal", "report_root_ref": "concurrent-retry-root"},
            "idempotency": {"run_key": "old", "internal_result_key": "ik", "document_key": "dk"},
        },
        result_summary={
            "failure_stage": "delivery", "database_precheck": {"status": "ready"},
            "feishu_relation": {"status": "ready", "content_read_status": "ready"},
            "internal_result": {"status": "success", "outcome": "content", "internal_result_id": "iid"},
            "delivery": {"status": "failed", "reason_code": "DELIVERY_FAILED", "delivery_identity": "did"},
        },
        created_by=admin_user.id,
    )
    test_session.add(original)
    await test_session.commit()
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    executor = BlockingExecutor()
    request_id = f"same-{suffix}"
    async with factory() as first_session, factory() as second_session:
        first_call = asyncio.create_task(retry_failed_execution(
            first_session, executor=executor, task_id=original.id, created_by=admin_user.id,
            request_id=request_id, triggered_at=datetime(2026, 9, 6, tzinfo=SHANGHAI),
        ))
        await asyncio.wait_for(executor.started.wait(), timeout=2)
        second_call = asyncio.create_task(retry_failed_execution(
            second_session, executor=executor, task_id=original.id, created_by=admin_user.id,
            request_id=request_id, triggered_at=datetime(2026, 9, 6, 0, 1, tzinfo=SHANGHAI),
        ))
        await asyncio.sleep(0.2)
        assert len(executor.redeliver_calls) == 1
        executor.release.set()
        first, second = await asyncio.gather(first_call, second_call)

    assert first.id == second.id
    assert len(executor.redeliver_calls) == 1


@pytest.mark.asyncio
async def test_legacy_test_failure_retry_stays_in_test_delivery_scope(
    test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    project = await _project(
        test_session,
        name=f"cov_ca_s28_legacy_test_{suffix}",
        admin_id=admin_user.id,
        sec_uids=["legacy-sec"],
    )
    await test_session.flush()
    original = TaskJob(
        task_no=f"CA-S28-{suffix}-legacy", tool_code="content-analysis-daily",
        tool_name="内容分析", status="failed",
        input_payload={
            "agent_code": "content-analysis", "task_code": "daily", "run_type": "test",
            "project_id": project.id, "business_date": "2026-09-04",
            "window_start": "2026-09-02T00:00:00+08:00", "window_end": "2026-09-05T00:00:00+08:00",
            "delivery_target": {"scope": "test", "report_root_ref": "legacy-test-root"},
            "idempotency": {
                "run_key": "legacy-test-run",
                "internal_result_key": "legacy-test-internal",
                "document_key": "legacy-test-document",
            },
        },
        result_summary={"failure_stage": "analysis"}, created_by=admin_user.id,
    )
    test_session.add(original)
    await test_session.commit()
    executor = FakeExecutor()

    await retry_failed_execution(
        test_session, executor=executor, task_id=original.id, created_by=admin_user.id,
        request_id=f"legacy-{suffix}", triggered_at=datetime(2026, 9, 6, tzinfo=SHANGHAI),
    )

    assert executor.execute_calls[0]["delivery_target"] == {
        "report_root_ref": "legacy-test-root",
        "scope": "test",
        "test_subdirectory": "测试报告",
    }
    assert executor.execute_calls[0]["idempotency"]["internal_result_key"] == "legacy-test-internal"
    assert executor.execute_calls[0]["idempotency"]["document_key"] == "legacy-test-document"


@pytest.mark.asyncio
async def test_manual_retry_with_missing_original_report_root_is_rejected_without_executor_call(
    test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    project = await _project(
        test_session,
        name=f"cov_ca_s28_retry_root_missing_{suffix}",
        admin_id=admin_user.id,
        sec_uids=["retry-root-missing"],
    )
    original = TaskJob(
        task_no=f"CA-S28-{suffix}-missing-root",
        tool_code="content-analysis-daily",
        tool_name="内容分析",
        status="failed",
        input_payload={
            "agent_code": "content-analysis",
            "task_code": "daily",
            "run_type": "auto",
            "business_date": "2026-09-04",
            "analysis_window": {
                "start": "2026-09-02T00:00:00+08:00",
                "end": "2026-09-05T00:00:00+08:00",
                "timezone": "Asia/Shanghai",
                "end_exclusive": True,
            },
            "execution": {"object_type": "project", "project_id": project.id},
            "delivery_target": {"scope": "formal", "report_root_ref": "   "},
            "idempotency": {
                "run_key": "missing-root-run",
                "internal_result_key": "missing-root-internal",
                "document_key": "missing-root-document",
            },
        },
        result_summary={"failure_stage": "delivery", "database_precheck": {"status": "ready"}},
        created_by=admin_user.id,
    )
    test_session.add(original)
    await test_session.commit()
    executor = FakeExecutor()

    with pytest.raises(ValueError, match="报告根目录"):
        await retry_failed_execution(
            test_session,
            executor=executor,
            task_id=original.id,
            created_by=admin_user.id,
            request_id=f"missing-root-{suffix}",
            triggered_at=datetime(2026, 9, 6, tzinfo=SHANGHAI),
        )

    assert executor.execute_calls == []
    assert executor.redeliver_calls == []


@pytest.mark.asyncio
async def test_weekly_test_uses_all_ready_projects_without_changing_automatic_selection(
    test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    first = await _project(
        test_session, name=f"cov_ca_s28_scope_first_{suffix}", admin_id=admin_user.id,
        sec_uids=["shared-sec"],
    )
    second = await _project(
        test_session, name=f"cov_ca_s28_scope_second_{suffix}", admin_id=admin_user.id,
        sec_uids=["shared-sec"],
    )
    unselected = await _project(
        test_session, name=f"cov_ca_s28_scope_unselected_{suffix}", admin_id=admin_user.id,
        sec_uids=["shared-sec", "unselected-sec"],
    )
    ineligible = await _project(
        test_session, name=f"cov_ca_s28_scope_ineligible_{suffix}", admin_id=admin_user.id,
        sec_uids=["shared-sec"],
    )
    ineligible.content_plan = None
    livestream_only = Kol(
        name=f"cov_ca_s28_scope_livestream_{suffix}",
        persona="人设",
        content_plan="内容规划",
        created_by=admin_user.id,
    )
    test_session.add(livestream_only)
    await test_session.flush()
    test_session.add(KolBenchmark(
        kol_id=livestream_only.id,
        account_name="直播账号",
        account_type="livestream",
        sec_uid="shared-sec",
        created_by=admin_user.id,
    ))
    blank_content = await _project(
        test_session, name=f"cov_ca_s28_scope_blank_{suffix}", admin_id=admin_user.id,
        sec_uids=["   "],
    )
    test_session.add(AgentTaskConfig(
        agent_code="content-analysis",
        selected_project_ids=[second.id, first.id],
        report_root_ref="weekly-test-scope-root",
        updated_by=admin_user.id,
    ))
    await test_session.commit()
    executor = FakeExecutor()

    task = await run_test_execution(
        test_session, executor=executor, task_code="weekly", project_id=None,
        account_key="shared-sec", created_by=admin_user.id, request_id=f"shared-{suffix}",
        triggered_at=datetime(2026, 9, 6, tzinfo=SHANGHAI),
    )

    assert task.input_payload["execution"]["project_ids"] == sorted([first.id, second.id, unselected.id])
    assert ineligible.id not in task.input_payload["execution"]["project_ids"]
    assert livestream_only.id not in task.input_payload["execution"]["project_ids"]
    assert blank_content.id not in task.input_payload["execution"]["project_ids"]

    unselected_task = await run_test_execution(
        test_session, executor=executor, task_code="weekly", project_id=None,
        account_key="unselected-sec", created_by=admin_user.id,
        request_id=f"unselected-{suffix}", triggered_at=datetime(2026, 9, 6, tzinfo=SHANGHAI),
    )

    assert unselected_task.input_payload["execution"]["project_ids"] == [unselected.id]
    config = await test_session.scalar(select(AgentTaskConfig).where(
        AgentTaskConfig.agent_code == "content-analysis",
    ))
    assert config.selected_project_ids == [second.id, first.id]
    assert all(
        call["execution"]["object_type"] == "account"
        for call in executor.execute_calls
    )


@pytest.mark.asyncio
async def test_weekly_batch_snapshot_uses_latest_formal_account_attempt_and_is_domain_isolated(
    test_session, admin_user,
):
    batch_id = f"content-analysis:weekly:snapshot-{uuid4().hex[:8]}"
    original = _weekly_account_job(
        admin_id=admin_user.id, weekly_batch_id=batch_id, account_key="private-account-a",
        status="success", batch_size=2, batch_position=1,
    )
    no_content = _weekly_account_job(
        admin_id=admin_user.id, weekly_batch_id=batch_id, account_key="private-account-b",
        status="success", outcome="no_content", batch_size=2, batch_position=2,
    )
    test_domain = _weekly_account_job(
        admin_id=admin_user.id, weekly_batch_id=batch_id, account_key="test-only",
        status="failed", batch_size=2, batch_position=1, run_type="test", scope="test",
    )
    other_batch = _weekly_account_job(
        admin_id=admin_user.id, weekly_batch_id=f"{batch_id}:other", account_key="other",
        status="failed", batch_size=1, batch_position=1,
    )
    wrong_task_type = _weekly_account_job(
        admin_id=admin_user.id, weekly_batch_id=batch_id, account_key="wrong-tool",
        status="failed", batch_size=2, batch_position=1,
    )
    wrong_task_type.tool_code = "content-analysis-daily"
    test_session.add_all([original, no_content, test_domain, other_batch, wrong_task_type])
    await test_session.flush()
    retry = _weekly_account_job(
        admin_id=admin_user.id, weekly_batch_id=batch_id, account_key="private-account-a",
        status="pending", batch_size=2, batch_position=1, run_type="manual_retry",
    )
    test_session.add(retry)
    await test_session.commit()

    waiting = await get_weekly_batch_terminal_snapshot(
        test_session, weekly_batch_id=batch_id, batch_size=2,
    )
    assert waiting["ready"] is False
    assert waiting["pending"] == 1
    assert waiting["status_counts"] == {"success": 0, "no_content": 1, "failed": 0}

    retry.status = "failed"
    retry.error_code = "ANALYSIS_FAILED"
    retry.result_summary = {
        "execution": retry.input_payload["execution"],
        "failure_stage": "analysis",
        "database_precheck": {"status": "ready"},
        "feishu_relation": {"status": "ready", "content_read_status": "ready"},
        "internal_result": {"status": "failed", "reason_code": "ANALYSIS_FAILED"},
        "delivery": {"status": "skipped"},
    }
    await test_session.commit()

    complete = await get_weekly_batch_terminal_snapshot(
        test_session, weekly_batch_id=batch_id, batch_size=2,
    )
    assert complete["ready"] is True
    assert complete["pending"] == 0
    assert complete["status_counts"] == {"success": 0, "no_content": 1, "failed": 1}
    assert len(complete["accounts"]) == 2
    assert all("account_key" not in account for account in complete["accounts"])
    assert "private-account-a" not in str(complete)
    assert complete["accounts"][0]["reason_code"] == "ANALYSIS_FAILED"


@pytest.mark.asyncio
async def test_weekly_auto_runs_finalize_after_last_account_failure_with_terminal_counts(
    test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    project = await _project(
        test_session, name=f"cov_ca_s28_finalize_mixed_{suffix}", admin_id=admin_user.id,
        sec_uids=["final-a", "final-b", "final-c"],
    )
    test_session.add(AgentTaskConfig(
        agent_code="content-analysis", selected_project_ids=[project.id],
        report_root_ref="finalize-root", updated_by=admin_user.id,
    ))
    await test_session.commit()
    executor = FakeExecutor(results={
        "final-a": _successful_result(suffix="a"),
        "final-b": _successful_result(suffix="b", outcome="no_content"),
        "final-c": _failed_result(reason_code="LAST_ACCOUNT_FAILED"),
    })

    await run_automatic_tick(
        test_session, executor=executor,
        now=datetime(2026, 9, 7, 1, 0, tzinfo=SHANGHAI),
        enabled=True, system_user_id=admin_user.id,
    )
    await wait_for_automatic_executions()

    object_types = [call["execution"]["object_type"] for call in executor.execute_calls]
    assert object_types == ["account", "account", "account", "weekly_batch_finalize"]
    finalize_envelope = executor.execute_calls[-1]
    assert finalize_envelope["execution"]["project_ids"] == [project.id]
    assert finalize_envelope["execution"]["batch_size"] == 3
    assert "account_key" not in str(finalize_envelope["execution"])
    snapshot = await get_weekly_batch_terminal_snapshot(
        test_session,
        weekly_batch_id=finalize_envelope["execution"]["weekly_batch_id"],
        batch_size=3,
    )
    assert snapshot["ready"] is True
    assert snapshot["pending"] == 0
    assert snapshot["status_counts"] == {"success": 1, "no_content": 1, "failed": 1}
    assert executor.input_table_reads == 0
    assert executor.model_calls == 0
    assert executor.professional_business_writes == 0


@pytest.mark.asyncio
async def test_weekly_finalize_runs_for_all_failed_and_empty_batches(
    test_session, admin_user,
):
    failed_batch = f"content-analysis:weekly:failed-{uuid4().hex[:8]}"
    test_session.add_all([
        _weekly_account_job(
            admin_id=admin_user.id, weekly_batch_id=failed_batch, account_key="failed-a",
            status="failed", batch_size=2, batch_position=1,
        ),
        _weekly_account_job(
            admin_id=admin_user.id, weekly_batch_id=failed_batch, account_key="failed-b",
            status="not_run", batch_size=2, batch_position=2,
            reason_code="CONFIG_MISSING",
        ),
    ])
    await test_session.commit()
    executor = FakeExecutor()
    triggered_at = datetime(2026, 9, 7, 1, 5, tzinfo=SHANGHAI)

    failed_finalize = await finalize_weekly_batch(
        test_session, executor=executor, weekly_batch_id=failed_batch,
        batch_size=2, project_ids=[71], report_root_ref="finalize-root",
        created_by=admin_user.id, triggered_at=triggered_at,
    )
    empty_batch = f"content-analysis:weekly:empty-{uuid4().hex[:8]}"
    test_session.add_all([
        _weekly_account_job(
            admin_id=admin_user.id, weekly_batch_id=empty_batch, account_key="test-only",
            status="failed", batch_size=1, batch_position=1, run_type="test", scope="test",
        ),
        _weekly_account_job(
            admin_id=admin_user.id, weekly_batch_id=f"{empty_batch}:other",
            account_key="other-batch", status="failed", batch_size=1, batch_position=1,
        ),
    ])
    await test_session.commit()
    empty_finalize = await finalize_weekly_batch(
        test_session, executor=executor, weekly_batch_id=empty_batch,
        batch_size=0, project_ids=[72], report_root_ref="finalize-root",
        created_by=admin_user.id, triggered_at=triggered_at,
    )

    assert failed_finalize.status == "success"
    assert empty_finalize.status == "success"
    failed_snapshot = await get_weekly_batch_terminal_snapshot(
        test_session, weekly_batch_id=failed_batch, batch_size=2,
    )
    empty_snapshot = await get_weekly_batch_terminal_snapshot(
        test_session, weekly_batch_id=empty_batch, batch_size=0,
    )
    assert failed_snapshot["status_counts"] == {"success": 0, "no_content": 0, "failed": 2}
    assert empty_snapshot["status_counts"] == {"success": 0, "no_content": 0, "failed": 0}
    assert failed_snapshot["pending"] == empty_snapshot["pending"] == 0
    assert empty_snapshot["accounts"] == []
    assert [call["execution"]["object_type"] for call in executor.execute_calls] == [
        "weekly_batch_finalize", "weekly_batch_finalize",
    ]


@pytest.mark.asyncio
async def test_weekly_auto_without_selected_projects_creates_no_tasks_or_finalize(
    test_session, admin_user,
):
    test_session.add(AgentTaskConfig(
        agent_code="content-analysis", selected_project_ids=[],
        report_root_ref="empty-auto-root", updated_by=admin_user.id,
    ))
    await test_session.commit()
    executor = FakeExecutor()

    result = await run_automatic_tick(
        test_session, executor=executor,
        now=datetime(2026, 9, 7, 1, 0, tzinfo=SHANGHAI),
        enabled=True, system_user_id=admin_user.id,
    )
    await wait_for_automatic_executions()

    assert result == {"status": "success", "task_code": "weekly", "created": 0, "existing": 0}
    assert executor.execute_calls == []
    task_count = await test_session.scalar(select(func.count(TaskJob.id)).where(
        TaskJob.tool_code == "content-analysis-weekly",
        TaskJob.input_payload["execution"]["weekly_batch_id"].astext
        == "content-analysis:weekly:2026-09-06",
    ))
    assert task_count == 0


@pytest.mark.asyncio
async def test_weekly_auto_with_selected_project_and_zero_accounts_runs_empty_finalize(
    test_session, admin_user,
):
    suffix = uuid4().hex[:8]
    project = await _project(
        test_session,
        name=f"cov_ca_s28_empty_selected_{suffix}",
        admin_id=admin_user.id,
        sec_uids=[],
    )
    test_session.add(AgentTaskConfig(
        agent_code="content-analysis", selected_project_ids=[project.id],
        report_root_ref="empty-auto-root", updated_by=admin_user.id,
    ))
    await test_session.commit()
    executor = FakeExecutor()

    result = await run_automatic_tick(
        test_session, executor=executor,
        now=datetime(2026, 9, 7, 1, 0, tzinfo=SHANGHAI),
        enabled=True, system_user_id=admin_user.id,
    )
    await wait_for_automatic_executions()

    assert result == {"status": "success", "task_code": "weekly", "created": 0, "existing": 0}
    assert len(executor.execute_calls) == 1
    finalize_envelope = executor.execute_calls[0]
    assert finalize_envelope["execution"]["object_type"] == "weekly_batch_finalize"
    assert finalize_envelope["execution"]["batch_size"] == 0
    assert finalize_envelope["execution"]["project_ids"] == [project.id]
    snapshot = await get_weekly_batch_terminal_snapshot(
        test_session,
        weekly_batch_id=finalize_envelope["execution"]["weekly_batch_id"],
        batch_size=0,
    )
    assert snapshot["ready"] is True
    assert snapshot["pending"] == 0
    assert snapshot["status_counts"] == {"success": 0, "no_content": 0, "failed": 0}
    assert snapshot["accounts"] == []
    assert executor.input_table_reads == 0
    assert executor.model_calls == 0
    assert executor.professional_business_writes == 0


@pytest.mark.asyncio
async def test_weekly_finalize_delivery_failure_retry_only_redelivers_same_result_and_document(
    test_session, admin_user,
):
    batch_id = f"content-analysis:weekly:delivery-{uuid4().hex[:8]}"
    test_session.add(_weekly_account_job(
        admin_id=admin_user.id, weekly_batch_id=batch_id, account_key="delivery-a",
        status="success", batch_size=1, batch_position=1,
    ))
    await test_session.commit()
    failed_result = _successful_finalize_result(suffix="delivery")
    failed_result["failure_stage"] = "delivery"
    failed_result["delivery"] = {
        "status": "failed", "reason_code": "DELIVERY_FAILED",
        "delivery_identity": "weekly-document",
    }
    executor = FakeExecutor(results={"__finalize__": failed_result})
    triggered_at = datetime(2026, 9, 7, 1, 5, tzinfo=SHANGHAI)

    original = await finalize_weekly_batch(
        test_session, executor=executor, weekly_batch_id=batch_id,
        batch_size=1, project_ids=[71], report_root_ref="finalize-root",
        created_by=admin_user.id, triggered_at=triggered_at,
    )
    retry = await retry_failed_execution(
        test_session, executor=executor, task_id=original.id,
        created_by=admin_user.id, request_id=f"finalize-retry-{uuid4().hex[:8]}",
        triggered_at=triggered_at + timedelta(minutes=1),
    )

    assert original.status == "failed"
    assert retry.status == "success"
    assert len(executor.execute_calls) == 1
    assert len(executor.redeliver_calls) == 1
    assert retry.input_payload["idempotency"]["internal_result_key"] == original.input_payload["idempotency"]["internal_result_key"]
    assert retry.input_payload["idempotency"]["document_key"] == original.input_payload["idempotency"]["document_key"]
    assert retry.result_summary["feishu_relation"] == {"status": "skipped"}


@pytest.mark.asyncio
async def test_weekly_account_manual_retry_creates_new_finalize_version_without_rerunning_peers(
    test_session, admin_user,
):
    batch_id = f"content-analysis:weekly:refinalize-{uuid4().hex[:8]}"
    failed = _weekly_account_job(
        admin_id=admin_user.id, weekly_batch_id=batch_id, account_key="retry-a",
        status="failed", batch_size=2, batch_position=1,
    )
    peer = _weekly_account_job(
        admin_id=admin_user.id, weekly_batch_id=batch_id, account_key="retry-b",
        status="success", outcome="no_content", batch_size=2, batch_position=2,
    )
    test_session.add_all([failed, peer])
    await test_session.commit()
    executor = FakeExecutor()
    triggered_at = datetime(2026, 9, 7, 1, 5, tzinfo=SHANGHAI)

    initial_finalize = await finalize_weekly_batch(
        test_session, executor=executor, weekly_batch_id=batch_id,
        batch_size=2, project_ids=[71], report_root_ref="finalize-root",
        created_by=admin_user.id, triggered_at=triggered_at,
    )
    retried_account = await retry_failed_execution(
        test_session, executor=executor, task_id=failed.id,
        created_by=admin_user.id, request_id=f"account-retry-{uuid4().hex[:8]}",
        triggered_at=triggered_at + timedelta(minutes=1),
    )

    assert retried_account.status == "success"
    assert [call["execution"]["object_type"] for call in executor.execute_calls] == [
        "weekly_batch_finalize", "account", "weekly_batch_finalize",
    ]
    finalizers = (await test_session.execute(select(TaskJob).where(
        TaskJob.tool_code == "content-analysis-weekly",
        TaskJob.input_payload["execution"]["object_type"].astext == "weekly_batch_finalize",
        TaskJob.input_payload["execution"]["weekly_batch_id"].astext == batch_id,
    ).order_by(TaskJob.id))).scalars().all()
    assert len(finalizers) == 2
    assert finalizers[0].input_payload["idempotency"]["internal_result_key"] != finalizers[1].input_payload["idempotency"]["internal_result_key"]
    assert finalizers[0].input_payload["idempotency"]["document_key"] == finalizers[1].input_payload["idempotency"]["document_key"] == batch_id
    assert all(call["execution"].get("account_key") != "retry-b" for call in executor.execute_calls)
    assert initial_finalize.id != finalizers[-1].id


@pytest.mark.asyncio
async def test_concurrent_duplicate_weekly_finalize_is_idempotent(
    test_engine, test_session, admin_user,
):
    batch_id = f"content-analysis:weekly:concurrent-{uuid4().hex[:8]}"
    test_session.add(_weekly_account_job(
        admin_id=admin_user.id, weekly_batch_id=batch_id, account_key="concurrent-a",
        status="success", batch_size=1, batch_position=1,
    ))
    await test_session.commit()
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    executor = FakeExecutor()
    common = {
        "executor": executor,
        "weekly_batch_id": batch_id,
        "batch_size": 1,
        "project_ids": [71],
        "report_root_ref": "finalize-root",
        "created_by": admin_user.id,
        "triggered_at": datetime(2026, 9, 7, 1, 5, tzinfo=SHANGHAI),
    }

    async def invoke():
        async with factory() as session:
            return await finalize_weekly_batch(session, **common)

    first, second = await asyncio.gather(invoke(), invoke())

    assert first.id == second.id
    assert len(executor.execute_calls) == 1
    async with factory() as observer:
        count = await observer.scalar(select(func.count()).select_from(TaskJob).where(
            TaskJob.tool_code == "content-analysis-weekly",
            TaskJob.input_payload["execution"]["object_type"].astext == "weekly_batch_finalize",
            TaskJob.input_payload["execution"]["weekly_batch_id"].astext == batch_id,
        ))
    assert count == 1


@pytest.mark.asyncio
async def test_new_weekly_finalize_waits_for_shared_content_lock_then_creates_v2(
    test_engine, test_session, admin_user,
):
    batch_id = f"content-analysis:weekly:shared-lock-{uuid4().hex[:8]}"
    test_session.add(_weekly_account_job(
        admin_id=admin_user.id, weekly_batch_id=batch_id, account_key="shared-lock-a",
        status="failed", batch_size=1, batch_position=1,
    ))
    await test_session.commit()
    executor = FakeExecutor()
    triggered_at = datetime(2026, 9, 7, 1, 5, tzinfo=SHANGHAI)
    first_finalize = await finalize_weekly_batch(
        test_session, executor=executor, weekly_batch_id=batch_id,
        batch_size=1, project_ids=[71], report_root_ref="finalize-root",
        created_by=admin_user.id, triggered_at=triggered_at,
    )
    first_version = first_finalize.input_payload["execution"]["finalize_version"]

    test_session.add(_weekly_account_job(
        admin_id=admin_user.id, weekly_batch_id=batch_id, account_key="shared-lock-a",
        status="success", batch_size=1, batch_position=1, run_type="manual_retry",
    ))
    await test_session.commit()

    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    first_envelope = content_analysis.parse_task_config_envelope(
        _executor_envelope(first_finalize.input_payload)
    )
    async with factory() as content_session:
        content_store = content_analysis.SqlContentAnalysisStore(content_session)
        async def create_v2():
            async with factory() as session:
                return await finalize_weekly_batch(
                    session, executor=executor, weekly_batch_id=batch_id,
                    batch_size=1, project_ids=[71], report_root_ref="finalize-root",
                    created_by=admin_user.id,
                    triggered_at=triggered_at + timedelta(minutes=1),
                )

        async with content_store.analysis_guard(first_envelope):
            pending_creation = asyncio.create_task(create_v2())
            await asyncio.sleep(0.1)
            waited_for_content_lock = not pending_creation.done()
            async with factory() as observer:
                finalize_count_while_locked = await observer.scalar(
                    select(func.count()).select_from(TaskJob).where(
                        TaskJob.tool_code == "content-analysis-weekly",
                        TaskJob.input_payload["execution"]["object_type"].astext
                        == "weekly_batch_finalize",
                        TaskJob.input_payload["execution"]["weekly_batch_id"].astext
                        == batch_id,
                    )
                )
        second_finalize = await asyncio.wait_for(pending_creation, timeout=2)

    assert waited_for_content_lock is True
    assert finalize_count_while_locked == 1
    assert second_finalize.id != first_finalize.id
    assert second_finalize.input_payload["execution"]["finalize_version"] != first_version
    assert len(executor.execute_calls) == 2


@pytest.mark.asyncio
async def test_committed_v2_makes_old_v1_fail_before_summary_read_or_delivery(
    test_engine, test_session, admin_user,
):
    batch_id = f"content-analysis:weekly:stale-v1-{uuid4().hex[:8]}"
    test_session.add(_weekly_account_job(
        admin_id=admin_user.id, weekly_batch_id=batch_id, account_key="stale-v1-a",
        status="failed", batch_size=1, batch_position=1,
    ))
    await test_session.commit()
    executor = FakeExecutor()
    triggered_at = datetime(2026, 9, 7, 1, 5, tzinfo=SHANGHAI)
    first_finalize = await finalize_weekly_batch(
        test_session, executor=executor, weekly_batch_id=batch_id,
        batch_size=1, project_ids=[71], report_root_ref="finalize-root",
        created_by=admin_user.id, triggered_at=triggered_at,
    )
    test_session.add(_weekly_account_job(
        admin_id=admin_user.id, weekly_batch_id=batch_id, account_key="stale-v1-a",
        status="success", batch_size=1, batch_position=1, run_type="manual_retry",
    ))
    await test_session.commit()
    second_finalize = await finalize_weekly_batch(
        test_session, executor=executor, weekly_batch_id=batch_id,
        batch_size=1, project_ids=[71], report_root_ref="finalize-root",
        created_by=admin_user.id, triggered_at=triggered_at + timedelta(minutes=1),
    )
    first_envelope = content_analysis.parse_task_config_envelope(
        _executor_envelope(first_finalize.input_payload)
    )

    class ForbiddenDependency:
        async def read(self, *args, **kwargs):
            raise AssertionError("旧收尾不得读取飞书关系")

        async def read_accounts(self, *args, **kwargs):
            raise AssertionError("旧收尾不得读取飞书内容")

        async def load(self, *args, **kwargs):
            raise AssertionError("旧收尾不得读取项目上下文")

        async def analyze_content(self, *args, **kwargs):
            raise AssertionError("旧收尾不得调用模型")

        async def assess_project(self, *args, **kwargs):
            raise AssertionError("旧收尾不得执行项目适配")

        async def deliver(self, *args, **kwargs):
            raise AssertionError("旧收尾不得覆盖新周报")

    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as content_session:
        forbidden = ForbiddenDependency()
        service = content_analysis.ContentAnalysisExecutor(
            relation_reader=forbidden,
            content_reader=forbidden,
            context_reader=forbidden,
            analyzer=forbidden,
            store=content_analysis.SqlContentAnalysisStore(content_session),
            delivery=forbidden,
            system_user_id=admin_user.id,
            clock=lambda: triggered_at + timedelta(minutes=2),
        )

        outcome = await service.execute(first_envelope)

    assert second_finalize.id > first_finalize.id
    assert outcome.overall_status is content_analysis.ExecutionOverallStatus.FAILED
    assert outcome.summary.failure_stage == "system_config"
    assert outcome.summary.reason_code == "EXECUTOR_CONTRACT_INVALID"


@pytest.mark.asyncio
async def test_weekly_finalize_creation_error_rolls_back_and_releases_shared_lock(
    test_engine, test_session, admin_user,
):
    batch_id = f"content-analysis:weekly:lock-rollback-{uuid4().hex[:8]}"
    test_session.add(_weekly_account_job(
        admin_id=admin_user.id, weekly_batch_id=batch_id, account_key="lock-rollback-a",
        status="success", batch_size=1, batch_position=1,
    ))
    await test_session.commit()
    lock_name = f"content-analysis:weekly-batch:{batch_id}"

    with pytest.raises(ValueError, match="project_ids"):
        await finalize_weekly_batch(
            test_session, executor=FakeExecutor(), weekly_batch_id=batch_id,
            batch_size=1, project_ids=[], report_root_ref="finalize-root",
            created_by=admin_user.id,
            triggered_at=datetime(2026, 9, 7, 1, 5, tzinfo=SHANGHAI),
        )

    assert test_session.in_transaction() is False
    async with test_engine.connect() as observer:
        acquired = await observer.scalar(text(
            "SELECT pg_try_advisory_lock(hashtextextended(:lock_name, 0))"
        ), {"lock_name": lock_name})
        try:
            assert acquired is True
        finally:
            if acquired:
                await observer.execute(text(
                    "SELECT pg_advisory_unlock(hashtextextended(:lock_name, 0))"
                ), {"lock_name": lock_name})
