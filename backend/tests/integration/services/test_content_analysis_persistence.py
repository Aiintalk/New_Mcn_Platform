"""内容分析 Output 与五类表的事务、幂等及测试隔离。"""
import asyncio
import hashlib
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.requests import Request

import app.services.content_analysis as content_analysis
from tests.conftest import _cleanup_content_analysis_test_rows
from app.models.content_analysis import (
    ContentAnalysisAccountBaseline,
    ContentAnalysisCrossProjectOpportunity,
    ContentAnalysisDelivery,
    ContentAnalysisLibraryItem,
    ContentAnalysisResult,
)
from app.models.kol import Kol
from app.models.material_library import KolReference
from app.models.output import Output
from app.models.task import TaskJob
from app.routers.content_analysis_library import (
    LibraryAvailabilityUpdate,
    ManualOpeningUpdate,
    annotate_library_opening,
    set_library_availability,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
PERSISTENCE_NOW = datetime(2026, 9, 5, 5, tzinfo=SHANGHAI)


@pytest.fixture(autouse=True)
def fixed_persistence_module_clock(monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(
                PERSISTENCE_NOW.timestamp(),
                tz or PERSISTENCE_NOW.tzinfo,
            )

    monkeypatch.setattr(
        "app.services.content_analysis.persistence.datetime",
        FixedDateTime,
    )


@pytest.mark.asyncio
async def test_content_analysis_cleanup_is_limited_to_current_test_users(
    test_session,
    admin_user,
    operator_user,
) -> None:
    admin_task = TaskJob(
        task_no=f"ca_s28_cleanup_admin_{uuid4().hex[:8]}",
        tool_code="content-analysis-daily",
        tool_name="内容分析",
        status="failed",
        created_by=admin_user.id,
    )
    other_task = TaskJob(
        task_no=f"ca_s28_cleanup_other_{uuid4().hex[:8]}",
        tool_code="content-analysis-daily",
        tool_name="内容分析",
        status="failed",
        created_by=operator_user.id,
    )
    admin_project = Kol(
        name=f"cov_ca_cleanup_admin_{uuid4().hex[:8]}",
        status="signed",
        created_by=admin_user.id,
    )
    other_project = Kol(
        name=f"cov_ca_cleanup_other_{uuid4().hex[:8]}",
        status="signed",
        created_by=operator_user.id,
    )
    test_session.add_all((admin_task, other_task, admin_project, other_project))
    await test_session.commit()
    other_task_id = other_task.id
    other_project_id = other_project.id

    await _cleanup_content_analysis_test_rows(test_session, (admin_user.id,))

    assert await test_session.scalar(
        select(func.count()).select_from(TaskJob).where(TaskJob.id == admin_task.id)
    ) == 0
    assert await test_session.scalar(
        select(func.count()).select_from(Kol).where(Kol.id == admin_project.id)
    ) == 0
    assert await test_session.scalar(
        select(func.count()).select_from(TaskJob).where(TaskJob.id == other_task_id)
    ) == 1
    assert await test_session.scalar(
        select(func.count()).select_from(Kol).where(Kol.id == other_project_id)
    ) == 1


async def setup_envelope(test_session, admin_user, *, run_type=None, weekly=False):
    suffix = uuid4().hex[:10]
    project = Kol(
        name=f"cov_ca_project_{suffix}",
        persona="项目人设",
        content_plan="内容规划",
        status="signed",
        created_by=admin_user.id,
    )
    test_session.add(project)
    await test_session.flush()
    task = TaskJob(
        task_no=f"ca_s28_task_{suffix}",
        tool_code="content-analysis",
        tool_name="内容分析",
        status="processing",
        created_by=admin_user.id,
    )
    test_session.add(task)
    await test_session.commit()
    end = datetime(2026, 9, 5, tzinfo=SHANGHAI)
    kind = content_analysis.TaskCode.WEEKLY if weekly else content_analysis.TaskCode.DAILY
    execution = (
        content_analysis.AccountExecution(
            sec_uid=f"account-{suffix}",
            project_ids=(str(project.id),),
            weekly_batch_id="weekly-2026-09-05",
            batch_size=1,
            batch_position=1,
        )
        if weekly
        else content_analysis.ProjectExecution(project_id=str(project.id))
    )
    envelope = content_analysis.ContentAnalysisTaskEnvelope(
        task_id=task.id,
        task_no=task.task_no,
        task_code=kind,
        run_type=run_type or content_analysis.RunType.AUTO,
        business_date=date(2026, 9, 4),
        window_start=(
            datetime(2026, 8, 6, tzinfo=SHANGHAI)
            if weekly
            else datetime(2026, 9, 2, tzinfo=SHANGHAI)
        ),
        window_end=end,
        triggered_at=end,
        deadline_at=datetime(2026, 9, 5, 12, tzinfo=SHANGHAI),
        retry_of_task_id=None,
        trigger_source=content_analysis.TriggerSource.SYSTEM,
        precheck=content_analysis.DatabasePrecheck(
            content_analysis.DatabasePrecheckStatus.READY,
            input_limited=True,
            limitation_codes=("TARGET_USERS_MISSING",),
        ),
        delivery_target=content_analysis.DeliveryTarget(
            "root",
            (
                "测试/reports"
                if run_type is content_analysis.RunType.TEST
                else "reports"
            ),
            scope=(
                content_analysis.DeliveryScope.TEST
                if run_type is content_analysis.RunType.TEST
                else content_analysis.DeliveryScope.FORMAL
            ),
        ),
        idempotency=content_analysis.IdempotencyKeys(
            f"analysis-{suffix}",
            f"result-{suffix}",
            f"document-{suffix}",
        ),
        execution=execution,
    )
    return project, task, envelope


def stored_task_payload(
    envelope,
    *,
    run_type="auto",
    request_id: str | None = None,
) -> dict:
    execution = envelope.execution
    if isinstance(execution, content_analysis.ProjectExecution):
        execution_payload = {
            "object_type": "project",
            "project_id": int(execution.project_id),
        }
    elif isinstance(execution, content_analysis.AccountExecution):
        execution_payload = {
            "object_type": "account",
            "account_key": execution.sec_uid,
            "project_ids": [int(item) for item in execution.project_ids],
            "weekly_batch_id": execution.weekly_batch_id,
            "batch_size": execution.batch_size,
            "batch_position": execution.batch_position,
        }
    else:
        execution_payload = {
            "object_type": "weekly_batch_finalize",
            "project_ids": [int(item) for item in execution.project_ids],
            "weekly_batch_id": execution.weekly_batch_id,
            "batch_size": execution.batch_size,
            "finalize_version": execution.finalize_version,
        }
    return {
        "contract_version": "2.0",
        "task_identity": {
            "task_id": envelope.task_id,
            "task_no": envelope.task_no,
            "agent_code": "content-analysis",
        },
        "agent_code": "content-analysis",
        "task_code": "weekly" if envelope.task_code is content_analysis.TaskCode.WEEKLY else "daily",
        "run_type": run_type,
        "business_date": envelope.business_date.isoformat(),
        "analysis_window": {
            "start": envelope.window_start.isoformat(),
            "end": envelope.window_end.isoformat(),
            "timezone": "Asia/Shanghai",
            "end_exclusive": True,
        },
        "triggered_at": envelope.triggered_at.isoformat(),
        "deadline_at": envelope.deadline_at.isoformat(),
        "retry": {
            "retry_of_task_id": envelope.retry_of_task_id,
            "mode": (
                envelope.retry_mode.value
                if envelope.retry_mode is not None
                else None
            ),
            "request_id": request_id,
        },
        "database_precheck": {
            "status": envelope.precheck.status.value,
            "reason_code": None,
            "input_limited": envelope.precheck.input_limited,
            "input_limited_reasons": list(envelope.precheck.limitation_codes),
        },
        "delivery_target": {
            "report_root_ref": envelope.delivery_target.report_root_ref,
            "scope": envelope.delivery_target.scope.value,
            "test_subdirectory": (
                envelope.delivery_target.relative_directory
                if envelope.delivery_target.scope is content_analysis.DeliveryScope.TEST
                else None
            ),
        },
        "execution": execution_payload,
        "idempotency": {
            "run_key": envelope.idempotency.analysis_key,
            "internal_result_key": envelope.idempotency.result_key,
            "document_key": envelope.idempotency.document_key,
        },
    }


@pytest.mark.asyncio
async def test_daily_history_accepts_manual_library_content_without_external_identity(
    test_session,
    admin_user,
) -> None:
    project, _, envelope = await setup_envelope(test_session, admin_user)
    other_project = Kol(
        name=f"cov_ca_manual_history_{uuid4().hex[:8]}",
        persona="其他项目人设",
        content_plan="其他项目规划",
        status="signed",
        created_by=admin_user.id,
    )
    test_session.add(other_project)
    await test_session.flush()
    reference = KolReference(
        kol_id=other_project.id,
        title="人工千川正文",
        source="人工",
        type="千川爆款文案",
        content="只有人工正文，没有外部稳定身份",
        created_by=admin_user.id,
    )
    test_session.add(reference)
    await test_session.flush()
    manual = ContentAnalysisLibraryItem(
        kol_reference_id=reference.id,
        project_id=other_project.id,
        platform="unknown",
        account_id=None,
        platform_content_id=None,
        external_url=None,
        category="qianchuan",
        ingestion_source="manual",
        analysis={"opening": {"status": "unannotated"}},
        project_assessment={},
        latest_metrics={},
        confidence="unverified",
        opening_status="unannotated",
        availability="enabled",
        latest_result_id=None,
    )
    test_session.add(manual)
    await test_session.commit()

    history = await content_analysis.SqlContentAnalysisStore(
        test_session
    ).load_daily_history(
        envelope,
        str(project.id),
        ("account-in",),
    )

    saved = next(
        item
        for item in history.saved_library_records
        if item.project_id == str(other_project.id)
    )
    assert saved.content_key == f"library_item_id:{manual.id}"
    assert saved.identity_keys == ()


@pytest.mark.asyncio
async def test_internal_retry_origin_validation_binds_all_immutable_fields(
    test_session,
    admin_user,
) -> None:
    _, task, original = await setup_envelope(test_session, admin_user)
    task.tool_code = "content-analysis-daily"
    task.input_payload = stored_task_payload(original)
    await test_session.commit()
    retry = replace(
        original,
        run_type=content_analysis.RunType.RETRY,
        retry_of_task_id=task.id,
        retry_mode=content_analysis.RetryMode.FULL,
        trigger_source=content_analysis.TriggerSource.SYSTEM,
    )
    store = content_analysis.SqlContentAnalysisStore(test_session)

    assert await store.validate_internal_retry_origin(retry) is True
    assert await store.validate_internal_retry_origin(
        replace(
            retry,
            idempotency=replace(retry.idempotency, result_key="other-result"),
        )
    ) is False
    assert await store.validate_internal_retry_origin(
        replace(
            retry,
            business_date=retry.business_date - timedelta(days=1),
            window_start=retry.window_start - timedelta(days=1),
            window_end=retry.window_end - timedelta(days=1),
        )
    ) is False
    assert await store.validate_internal_retry_origin(
        replace(
            retry,
            delivery_target=replace(
                retry.delivery_target,
                report_root_ref="other-root",
            ),
        )
    ) is False
    assert await store.validate_internal_retry_origin(
        replace(retry, execution=content_analysis.ProjectExecution("999999"))
    ) is False


@pytest.mark.asyncio
async def test_internal_retry_binds_original_test_subdirectory(
    test_session,
    admin_user,
) -> None:
    _, task, original = await setup_envelope(
        test_session,
        admin_user,
        run_type=content_analysis.RunType.TEST,
    )
    task.tool_code = "content-analysis-daily"
    task.input_payload = stored_task_payload(original, run_type="test")
    await test_session.commit()
    retry = replace(
        original,
        run_type=content_analysis.RunType.RETRY,
        retry_of_task_id=task.id,
        retry_mode=content_analysis.RetryMode.FULL,
        trigger_source=content_analysis.TriggerSource.SYSTEM,
        delivery_target=replace(
            original.delivery_target,
            relative_directory="测试报告/其他",
        ),
    )

    assert await content_analysis.SqlContentAnalysisStore(
        test_session
    ).validate_internal_retry_origin(retry) is False


@pytest.mark.asyncio
async def test_weekly_finalize_internal_retry_binds_finalize_version(
    test_session,
    admin_user,
) -> None:
    project, task, account_envelope = await setup_envelope(
        test_session,
        admin_user,
        weekly=True,
    )
    original = replace(
        account_envelope,
        execution=content_analysis.WeeklyBatchFinalizeExecution(
            weekly_batch_id=account_envelope.execution.weekly_batch_id,
            batch_size=1,
            project_ids=(str(project.id),),
            finalize_version="state-v1",
        ),
    )
    task.tool_code = "content-analysis-weekly"
    task.input_payload = stored_task_payload(original)
    await test_session.commit()
    retry = replace(
        original,
        run_type=content_analysis.RunType.RETRY,
        retry_of_task_id=task.id,
        retry_mode=content_analysis.RetryMode.FULL,
        trigger_source=content_analysis.TriggerSource.SYSTEM,
    )
    store = content_analysis.SqlContentAnalysisStore(test_session)

    assert await store.validate_internal_retry_origin(retry) is True
    assert await store.validate_internal_retry_origin(
        replace(
            retry,
            execution=replace(retry.execution, finalize_version="state-v2"),
        )
    ) is False

    newer_task = TaskJob(
        task_no=f"ca_s28_finalize_newer_{uuid4().hex[:8]}",
        tool_code="content-analysis-weekly",
        tool_name="内容分析",
        status="success",
        created_by=admin_user.id,
    )
    test_session.add(newer_task)
    await test_session.flush()
    newer = replace(
        original,
        task_id=newer_task.id,
        task_no=newer_task.task_no,
        execution=replace(original.execution, finalize_version="state-v2"),
    )
    newer_task.input_payload = stored_task_payload(newer)
    await test_session.commit()

    assert await store.validate_internal_retry_origin(retry) is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("weekly", "stored_run_type"),
    ((False, "manual_retry"), (True, "retry")),
)
async def test_manual_full_retry_binds_daily_and_account_origins_and_scope(
    test_session,
    admin_user,
    weekly,
    stored_run_type,
) -> None:
    _, original_task, original = await setup_envelope(
        test_session,
        admin_user,
        weekly=weekly,
    )
    expected_tool = (
        "content-analysis-weekly" if weekly else "content-analysis-daily"
    )
    original_task.tool_code = expected_tool
    original_task.status = "failed"
    original_task.input_payload = stored_task_payload(original)
    original_task.result_summary = {
        "failure_stage": "internal_result",
        "internal_result": {"status": "failed"},
    }
    retry_task = TaskJob(
        task_no=f"ca_s28_manual_retry_{uuid4().hex[:8]}",
        tool_code=expected_tool,
        tool_name="内容分析",
        status="processing",
        created_by=admin_user.id,
    )
    test_session.add(retry_task)
    await test_session.commit()
    request_id = f"request-{uuid4().hex}"
    retry = replace(
        original,
        task_id=retry_task.id,
        task_no=retry_task.task_no,
        run_type=content_analysis.RunType.RETRY,
        retry_of_task_id=original_task.id,
        retry_mode=content_analysis.RetryMode.FULL,
        request_id=request_id,
        trigger_source=content_analysis.TriggerSource.USER,
        idempotency=content_analysis.IdempotencyKeys(
            f"manual-retry-analysis-{uuid4().hex}",
            original.idempotency.result_key,
            original.idempotency.document_key,
        ),
    )
    retry_task.input_payload = stored_task_payload(
        retry,
        run_type=stored_run_type,
        request_id=request_id,
    )
    await test_session.commit()
    store = content_analysis.SqlContentAnalysisStore(test_session)

    assert await store.validate_manual_retry_origin(retry) is True
    assert await store.validate_manual_retry_origin(
        replace(retry, request_id=f"different-{uuid4().hex}")
    ) is False

    mismatched_payload = stored_task_payload(original)
    mismatched_payload["delivery_target"] = {
        **mismatched_payload["delivery_target"],
        "scope": "test",
    }
    original_task.input_payload = mismatched_payload
    await test_session.commit()

    assert await store.validate_manual_retry_origin(retry) is False


@pytest.mark.asyncio
async def test_manual_full_retry_binds_original_test_subdirectory(
    test_session,
    admin_user,
) -> None:
    _, original_task, original = await setup_envelope(
        test_session,
        admin_user,
        run_type=content_analysis.RunType.TEST,
    )
    original_task.tool_code = "content-analysis-daily"
    original_task.status = "failed"
    original_task.input_payload = stored_task_payload(original, run_type="test")
    original_task.result_summary = {
        "failure_stage": "internal_result",
        "internal_result": {"status": "failed"},
    }
    retry_task = TaskJob(
        task_no=f"ca_s28_manual_test_retry_{uuid4().hex[:8]}",
        tool_code="content-analysis-daily",
        tool_name="内容分析",
        status="processing",
        created_by=admin_user.id,
    )
    test_session.add(retry_task)
    await test_session.flush()
    request_id = f"request-{uuid4().hex}"
    retry = replace(
        original,
        task_id=retry_task.id,
        task_no=retry_task.task_no,
        run_type=content_analysis.RunType.RETRY,
        retry_of_task_id=original_task.id,
        retry_mode=content_analysis.RetryMode.FULL,
        request_id=request_id,
        trigger_source=content_analysis.TriggerSource.USER,
        delivery_target=replace(
            original.delivery_target,
            relative_directory="测试报告/其他",
        ),
        idempotency=content_analysis.IdempotencyKeys(
            f"manual-test-retry-{uuid4().hex}",
            original.idempotency.result_key,
            original.idempotency.document_key,
        ),
    )
    retry_task.input_payload = stored_task_payload(
        retry,
        run_type="manual_retry",
        request_id=request_id,
    )
    await test_session.commit()

    assert await content_analysis.SqlContentAnalysisStore(
        test_session
    ).validate_manual_retry_origin(retry) is False


@pytest.mark.asyncio
async def test_manual_finalize_full_retry_binds_failed_origin_and_rejects_stale_version(
    test_session,
    admin_user,
) -> None:
    project, original_task, account_envelope = await setup_envelope(
        test_session,
        admin_user,
        weekly=True,
    )
    original = replace(
        account_envelope,
        execution=content_analysis.WeeklyBatchFinalizeExecution(
            weekly_batch_id=account_envelope.execution.weekly_batch_id,
            batch_size=0,
            project_ids=(str(project.id),),
            finalize_version="state-v1",
        ),
    )
    original_task.tool_code = "content-analysis-weekly"
    original_task.status = "failed"
    original_task.input_payload = stored_task_payload(original)
    original_task.result_summary = {
        "failure_stage": "internal_result",
        "internal_result": {
            "status": "failed",
            "reason_code": "INTERNAL_EXECUTION_FAILED",
        },
    }
    retry_task = TaskJob(
        task_no=f"ca_s28_manual_finalize_retry_{uuid4().hex[:8]}",
        tool_code="content-analysis-weekly",
        tool_name="内容分析",
        status="processing",
        created_by=admin_user.id,
    )
    test_session.add(retry_task)
    await test_session.commit()
    request_id = f"request-{uuid4().hex}"
    retry = replace(
        original,
        task_id=retry_task.id,
        task_no=retry_task.task_no,
        run_type=content_analysis.RunType.RETRY,
        retry_of_task_id=original_task.id,
        retry_mode=content_analysis.RetryMode.FULL,
        request_id=request_id,
        trigger_source=content_analysis.TriggerSource.USER,
        idempotency=content_analysis.IdempotencyKeys(
            f"manual-finalize-analysis-{uuid4().hex}",
            original.idempotency.result_key,
            original.idempotency.document_key,
        ),
    )
    retry_task.input_payload = stored_task_payload(
        retry,
        run_type="manual_retry",
        request_id=request_id,
    )
    await test_session.commit()
    store = content_analysis.SqlContentAnalysisStore(test_session)

    assert await store.validate_manual_finalize_retry_origin(retry) is True
    retry_task.input_payload = stored_task_payload(
        retry,
        run_type="retry",
        request_id=request_id,
    )
    await test_session.commit()
    assert await store.validate_manual_finalize_retry_origin(retry) is True
    assert await store.validate_manual_finalize_retry_origin(
        replace(
            retry,
            triggered_at=retry.triggered_at + timedelta(minutes=1),
            deadline_at=retry.deadline_at + timedelta(minutes=1),
        )
    ) is False

    original_task.result_summary = {"failure_stage": "delivery"}
    await test_session.commit()
    assert await store.validate_manual_finalize_retry_origin(retry) is False

    original_task.result_summary = {"failure_stage": "internal_result"}
    newer = replace(
        original,
        execution=replace(original.execution, finalize_version="state-v2"),
        idempotency=content_analysis.IdempotencyKeys(
            f"newer-finalize-analysis-{uuid4().hex}",
            f"newer-finalize-result-{uuid4().hex}",
            original.idempotency.document_key,
        ),
    )
    newer_task = TaskJob(
        task_no=f"ca_s28_newer_finalize_{uuid4().hex[:8]}",
        tool_code="content-analysis-weekly",
        tool_name="内容分析",
        status="success",
        input_payload=stored_task_payload(newer),
        result_summary={"failure_stage": None},
        created_by=admin_user.id,
    )
    test_session.add(newer_task)
    await test_session.commit()

    assert await store.validate_manual_finalize_retry_origin(retry) is False
    assert await store.validate_manual_finalize_retry_origin(
        replace(retry, execution=replace(retry.execution, finalize_version="state-v0"))
    ) is False
    assert await store.validate_manual_finalize_retry_origin(
        replace(
            retry,
            task_id=newer_task.id,
            task_no=newer_task.task_no,
        )
    ) is False

    rejected_retry_task = TaskJob(
        task_no=f"ca_s28_rejected_stale_retry_{uuid4().hex[:8]}",
        tool_code="content-analysis-weekly",
        tool_name="内容分析",
        status="failed",
        input_payload=stored_task_payload(retry, run_type="manual_retry"),
        result_summary={"failure_stage": "internal_result"},
        created_by=admin_user.id,
    )
    second_retry_task = TaskJob(
        task_no=f"ca_s28_second_stale_retry_{uuid4().hex[:8]}",
        tool_code="content-analysis-weekly",
        tool_name="内容分析",
        status="processing",
        created_by=admin_user.id,
    )
    test_session.add_all((rejected_retry_task, second_retry_task))
    await test_session.commit()
    chained_request_id = f"request-{uuid4().hex}"
    chained_retry = replace(
        retry,
        task_id=second_retry_task.id,
        task_no=second_retry_task.task_no,
        retry_of_task_id=rejected_retry_task.id,
        request_id=chained_request_id,
        idempotency=content_analysis.IdempotencyKeys(
            f"second-stale-analysis-{uuid4().hex}",
            retry.idempotency.result_key,
            retry.idempotency.document_key,
        ),
    )
    second_retry_task.input_payload = stored_task_payload(
        chained_retry,
        run_type="manual_retry",
        request_id=chained_request_id,
    )
    await test_session.commit()

    assert await store.validate_manual_finalize_retry_origin(chained_retry) is False

    delivery_only_origin = replace(
        retry,
        task_id=original_task.id,
        task_no=original_task.task_no,
        retry_mode=content_analysis.RetryMode.DELIVERY_ONLY,
    )
    original_task.input_payload = stored_task_payload(
        delivery_only_origin,
        run_type="manual_retry",
        request_id=f"request-{uuid4().hex}",
    )
    original_task.result_summary = {"failure_stage": "internal_result"}
    await test_session.commit()
    assert await store.validate_manual_finalize_retry_origin(retry) is False


@pytest.mark.asyncio
async def test_finalize_delivery_retry_binds_delivery_failure_and_rejects_stale_version(
    test_session,
    admin_user,
) -> None:
    project, original_task, account_envelope = await setup_envelope(
        test_session,
        admin_user,
        weekly=True,
    )
    original = replace(
        account_envelope,
        execution=content_analysis.WeeklyBatchFinalizeExecution(
            weekly_batch_id=account_envelope.execution.weekly_batch_id,
            batch_size=0,
            project_ids=(str(project.id),),
            finalize_version="state-v1",
        ),
    )
    original_task.tool_code = "content-analysis-weekly"
    original_task.status = "failed"
    original_task.input_payload = stored_task_payload(original)
    original_task.result_summary = {
        "failure_stage": "delivery",
        "internal_result": {
            "status": "success",
            "outcome": "content",
            "internal_result_id": "77",
        },
        "delivery": {
            "status": "failed",
            "reason_code": "DELIVERY_FAILED",
        },
    }
    retry_task = TaskJob(
        task_no=f"ca_s28_finalize_redelivery_{uuid4().hex[:8]}",
        tool_code="content-analysis-weekly",
        tool_name="内容分析",
        status="processing",
        created_by=admin_user.id,
    )
    test_session.add(retry_task)
    await test_session.commit()
    request_id = f"request-{uuid4().hex}"
    retry = replace(
        original,
        task_id=retry_task.id,
        task_no=retry_task.task_no,
        run_type=content_analysis.RunType.RETRY,
        retry_of_task_id=original_task.id,
        retry_mode=content_analysis.RetryMode.DELIVERY_ONLY,
        request_id=request_id,
        trigger_source=content_analysis.TriggerSource.USER,
        idempotency=content_analysis.IdempotencyKeys(
            f"finalize-redelivery-analysis-{uuid4().hex}",
            original.idempotency.result_key,
            original.idempotency.document_key,
        ),
    )
    retry_task.input_payload = stored_task_payload(
        retry,
        run_type="manual_retry",
        request_id=request_id,
    )
    await test_session.commit()
    store = content_analysis.SqlContentAnalysisStore(test_session)

    assert await store.validate_finalize_redelivery_origin(retry, 77) is True
    retry_task.input_payload = stored_task_payload(
        retry,
        run_type="retry",
        request_id=request_id,
    )
    await test_session.commit()
    assert await store.validate_finalize_redelivery_origin(retry, 77) is True
    assert await store.validate_finalize_redelivery_origin(retry, 78) is False

    original_task.status = "processing"
    await test_session.commit()
    internal_retry = replace(
        original,
        run_type=content_analysis.RunType.RETRY,
        retry_of_task_id=original_task.id,
        retry_mode=content_analysis.RetryMode.DELIVERY_ONLY,
        trigger_source=content_analysis.TriggerSource.SYSTEM,
    )
    assert await store.validate_finalize_redelivery_origin(internal_retry, 77) is True
    original_task.status = "failed"
    await test_session.commit()

    newer = replace(
        original,
        execution=replace(original.execution, finalize_version="state-v2"),
        idempotency=content_analysis.IdempotencyKeys(
            f"newer-finalize-analysis-{uuid4().hex}",
            f"newer-finalize-result-{uuid4().hex}",
            original.idempotency.document_key,
        ),
    )
    newer_task = TaskJob(
        task_no=f"ca_s28_newer_finalize_{uuid4().hex[:8]}",
        tool_code="content-analysis-weekly",
        tool_name="内容分析",
        status="success",
        input_payload=stored_task_payload(newer),
        result_summary={"failure_stage": None},
        created_by=admin_user.id,
    )
    test_session.add(newer_task)
    await test_session.commit()

    assert await store.validate_finalize_redelivery_origin(retry, 77) is False
    assert await store.validate_finalize_redelivery_origin(
        replace(
            retry,
            task_id=newer_task.id,
            task_no=newer_task.task_no,
        ),
        77,
    ) is False


@pytest.mark.asyncio
async def test_analysis_guard_serializes_same_key_across_database_sessions(
    test_engine,
    test_session,
    admin_user,
) -> None:
    _, _, envelope = await setup_envelope(test_session, admin_user)
    factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    first_entered = asyncio.Event()
    second_entered = asyncio.Event()
    release_first = asyncio.Event()

    async def first():
        async with factory() as session:
            async with content_analysis.SqlContentAnalysisStore(session).analysis_guard(
                envelope
            ):
                first_entered.set()
                await release_first.wait()

    async def second():
        await first_entered.wait()
        async with factory() as session:
            async with content_analysis.SqlContentAnalysisStore(session).analysis_guard(
                envelope
            ):
                second_entered.set()

    first_task = asyncio.create_task(first())
    second_task = asyncio.create_task(second())
    await asyncio.wait_for(first_entered.wait(), timeout=1)
    await asyncio.sleep(0.05)
    assert second_entered.is_set() is False
    release_first.set()
    await asyncio.wait_for(asyncio.gather(first_task, second_task), timeout=2)
    assert second_entered.is_set() is True


@pytest.mark.asyncio
async def test_weekly_batch_guard_survives_commit_between_finalize_versions(
    test_engine,
    test_session,
    admin_user,
) -> None:
    project, _, account_envelope = await setup_envelope(
        test_session,
        admin_user,
        weekly=True,
    )
    first_envelope = replace(
        account_envelope,
        execution=content_analysis.WeeklyBatchFinalizeExecution(
            weekly_batch_id=account_envelope.execution.weekly_batch_id,
            batch_size=1,
            project_ids=(str(project.id),),
            finalize_version="state-v1",
        ),
    )
    second_envelope = replace(
        first_envelope,
        execution=replace(first_envelope.execution, finalize_version="state-v2"),
        idempotency=content_analysis.IdempotencyKeys(
            f"second-analysis-{uuid4().hex}",
            f"second-result-{uuid4().hex}",
            first_envelope.idempotency.document_key,
        ),
    )
    factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    first_committed = asyncio.Event()
    second_entered = asyncio.Event()
    release_first = asyncio.Event()

    async def first():
        async with factory() as session:
            async with content_analysis.SqlContentAnalysisStore(session).analysis_guard(
                first_envelope
            ):
                await session.commit()
                first_committed.set()
                await release_first.wait()

    async def second():
        await first_committed.wait()
        async with factory() as session:
            async with content_analysis.SqlContentAnalysisStore(session).analysis_guard(
                second_envelope
            ):
                second_entered.set()

    first_task = asyncio.create_task(first())
    second_task = asyncio.create_task(second())
    await asyncio.wait_for(first_committed.wait(), timeout=1)
    await asyncio.sleep(0.05)
    assert second_entered.is_set() is False
    release_first.set()
    await asyncio.wait_for(asyncio.gather(first_task, second_task), timeout=2)
    assert second_entered.is_set() is True


@pytest.mark.asyncio
async def test_nested_guards_do_not_starve_a_small_business_connection_pool(
    test_engine,
    test_session,
    admin_user,
) -> None:
    _, _, base = await setup_envelope(test_session, admin_user, weekly=True)
    engine = create_async_engine(
        test_engine.url,
        pool_size=2,
        max_overflow=0,
        pool_timeout=0.5,
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def guarded(index: int) -> None:
        current = replace(
            base,
            idempotency=content_analysis.IdempotencyKeys(
                f"small-pool-analysis-{index}",
                f"small-pool-result-{index}",
                base.idempotency.document_key,
            ),
            execution=replace(
                base.execution,
                sec_uid=f"small-pool-account-{index}",
            ),
        )
        async with factory() as session:
            store = content_analysis.SqlContentAnalysisStore(session)
            async with store.analysis_guard(current):
                await session.execute(text("SELECT 1"))
                async with store.delivery_guard(current):
                    await session.execute(text("SELECT 1"))

    try:
        await asyncio.wait_for(
            asyncio.gather(*(guarded(index) for index in range(4))),
            timeout=3,
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_guard_wait_is_bounded_by_task_deadline(
    test_engine,
    test_session,
    admin_user,
) -> None:
    _, _, envelope = await setup_envelope(test_session, admin_user)
    factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as first_session, factory() as waiting_session:
        holder = content_analysis.SqlContentAnalysisStore(first_session)
        waiter = content_analysis.SqlContentAnalysisStore(waiting_session)
        now = waiter._clock().astimezone(SHANGHAI)
        waiting_envelope = replace(
            envelope,
            triggered_at=now - timedelta(hours=12) + timedelta(milliseconds=50),
            deadline_at=now + timedelta(milliseconds=50),
        )
        async with holder.analysis_guard(envelope):
            with pytest.raises(
                TimeoutError,
                match="等待数据库锁超过截止时间",
            ):
                async with waiter.analysis_guard(waiting_envelope):
                    raise AssertionError("锁等待超过截止时间后不应进入临界区")


@pytest.mark.asyncio
async def test_guard_releases_budget_and_resources_when_unlock_fails(
    test_engine,
    test_session,
    admin_user,
) -> None:
    _, _, envelope = await setup_envelope(test_session, admin_user)
    engine = create_async_engine(
        test_engine.url,
        pool_size=2,
        max_overflow=0,
        pool_timeout=0.5,
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as failed_session:
            failed_store = content_analysis.SqlContentAnalysisStore(failed_session)

            async def fail_unlock(connection, lock_names):
                await connection.invalidate()
                raise RuntimeError("模拟数据库解锁失败")

            failed_store._unlock_names = fail_unlock
            with pytest.raises(RuntimeError, match="解锁失败"):
                async with failed_store.analysis_guard(envelope):
                    pass
            assert failed_store._guard_connection is None
            assert failed_store._guard_lock_names == set()

        async with factory() as next_session:
            next_store = content_analysis.SqlContentAnalysisStore(next_session)

            async def enter_next_guard() -> None:
                async with next_store.analysis_guard(
                    replace(
                        envelope,
                        idempotency=replace(
                            envelope.idempotency,
                            analysis_key="after-unlock-failure",
                        ),
                    )
                ):
                    pass

            await asyncio.wait_for(enter_next_guard(), timeout=0.5)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cancelled_lock_acquisition_invalidates_uncertain_connection(
    test_session,
) -> None:
    class UncertainConnection:
        invalidated = False

        async def scalar(self, statement, parameters):
            raise asyncio.CancelledError

        async def invalidate(self):
            self.invalidated = True

    connection = UncertainConnection()
    store = content_analysis.SqlContentAnalysisStore(test_session)

    with pytest.raises(asyncio.CancelledError):
        await store._try_lock_names(connection, ("uncertain-lock",))

    assert connection.invalidated is True


@pytest.mark.asyncio
async def test_delivery_guard_serializes_shared_directory_prefix(
    test_engine,
    test_session,
    admin_user,
) -> None:
    _, _, envelope = await setup_envelope(test_session, admin_user)
    first_envelope = replace(
        envelope,
        delivery_target=replace(
            envelope.delivery_target,
            relative_directory="项目日报/1001-a",
        ),
    )
    second_envelope = replace(
        envelope,
        delivery_target=replace(
            envelope.delivery_target,
            relative_directory="项目日报/1002-b",
        ),
        idempotency=replace(envelope.idempotency, document_key="another-document"),
    )
    factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    first_entered = asyncio.Event()
    second_entered = asyncio.Event()
    release_first = asyncio.Event()

    async def first():
        async with factory() as session:
            async with content_analysis.SqlContentAnalysisStore(session).delivery_guard(
                first_envelope
            ):
                first_entered.set()
                await release_first.wait()

    async def second():
        await first_entered.wait()
        async with factory() as session:
            async with content_analysis.SqlContentAnalysisStore(session).delivery_guard(
                second_envelope
            ):
                second_entered.set()

    first_task = asyncio.create_task(first())
    second_task = asyncio.create_task(second())
    await asyncio.wait_for(first_entered.wait(), timeout=1)
    await asyncio.sleep(0.05)
    assert second_entered.is_set() is False
    release_first.set()
    await asyncio.wait_for(asyncio.gather(first_task, second_task), timeout=2)
    assert second_entered.is_set() is True


def weekly_account_task_payload(
    envelope,
    *,
    sec_uid: str,
    position: int,
    batch_id: str | None = None,
    scope: str | None = None,
    task_code: str = "weekly",
    object_type: str = "account",
    window_start: str | None = None,
) -> dict:
    return {
        "contract_version": "2.0",
        "agent_code": "content-analysis",
        "task_code": task_code,
        "business_date": envelope.business_date.isoformat(),
        "analysis_window": {
            "start": window_start or envelope.window_start.isoformat(),
            "end": envelope.window_end.isoformat(),
            "timezone": "Asia/Shanghai",
            "end_exclusive": True,
        },
        "delivery_target": {
            "report_root_ref": envelope.delivery_target.report_root_ref,
            "scope": scope or envelope.delivery_target.scope.value,
        },
        "execution": {
            "object_type": object_type,
            "account_key": sec_uid,
            "project_ids": [int(item) for item in envelope.execution.project_ids],
            "weekly_batch_id": batch_id or envelope.execution.weekly_batch_id,
            "batch_size": envelope.execution.batch_size,
            "batch_position": position,
        },
        "idempotency": {
            "document_key": envelope.idempotency.document_key,
        },
    }


def weekly_task_summary(status: str, *, outcome: str = "content") -> dict:
    if status == "success":
        return {
            "failure_stage": None,
            "feishu_relation": {
                "status": "ready",
                "content_read_status": "ready",
            },
            "internal_result": {
                "status": "success",
                "outcome": outcome,
                "internal_result_id": "1",
            },
            "delivery": {
                "status": "success",
                "delivery_identity": "identity",
            },
        }
    return {
        "failure_stage": "data_source",
        "feishu_relation": {
            "status": "ready",
            "content_read_status": "failed",
            "reason_code": "FEISHU_CONTENT_READ_FAILED",
        },
        "internal_result": {"status": "skipped"},
        "delivery": {"status": "skipped"},
    }


def weekly_baseline_payload(
    envelope,
    sec_uid: str,
    *,
    sample_count: int = 0,
    mean_likes: float = 12.0,
    median_likes: float = 10.0,
    maximum_likes: int = 20,
    minimum_likes: int = 6,
) -> dict:
    common = {
        "account_id": sec_uid,
        "window_start": envelope.window_start.isoformat(),
        "window_end": envelope.window_end.isoformat(),
        "updated_at": "2026-09-05T04:00:00+08:00",
    }
    if sample_count == 0:
        return {
            **common,
            "baseline": None,
            "status": "unavailable",
            "unavailable_reason": "窗口内没有可计算的人设点赞样本",
        }
    return {
        **common,
        "baseline": {
            "mean": mean_likes,
            "median": median_likes,
            "sample_size": sample_count,
            "maximum": maximum_likes,
            "minimum": minimum_likes,
        },
        "status": "available",
        "unavailable_reason": None,
    }


async def attach_weekly_account_result(
    session,
    job: TaskJob,
    finalize_envelope,
    *,
    sec_uid: str,
    outcome: str = "content",
    baseline: dict | None = None,
) -> ContentAnalysisResult:
    output = Output(
        title=f"账号 {sec_uid} 周报",
        tool_code="content_analysis_weekly",
        tool_name="内容分析智能体",
        task_id=job.id,
        content_json={
            "sec_uid": sec_uid,
            "project_ids": [
                str(item)
                for item in job.input_payload["execution"]["project_ids"]
            ],
            "weekly_batch_id": finalize_envelope.execution.weekly_batch_id,
            "baseline": baseline
            or weekly_baseline_payload(finalize_envelope, sec_uid),
        },
        created_by=job.created_by,
    )
    session.add(output)
    await session.flush()
    result = ContentAnalysisResult(
        result_key=f"account-result-{uuid4().hex}",
        analysis_key=f"account-analysis-{uuid4().hex}",
        task_id=job.id,
        task_code="content_analysis_weekly",
        run_type="auto",
        execution_kind="account",
        project_id=None,
        sec_uid=sec_uid,
        related_project_ids=[
            str(item) for item in job.input_payload["execution"]["project_ids"]
        ],
        business_date=finalize_envelope.business_date,
        window_start=finalize_envelope.window_start,
        window_end=finalize_envelope.window_end,
        context_versions={},
        source_receipts={},
        status=("no_content" if outcome == "no_content" else "success"),
        output_id=output.id,
        is_test=False,
    )
    session.add(result)
    await session.flush()
    job.result_summary = weekly_task_summary("success", outcome=outcome)
    job.result_summary["internal_result"]["internal_result_id"] = str(result.id)
    return result


def daily_write(
    project_id: int,
    suffix: str,
    *,
    platform_content_id: str | None = None,
    external_url: str | None = None,
):
    return content_analysis.ResultWrite(
        title="项目日报",
        status=content_analysis.InternalResultStatus.SUCCESS,
        payload={"report": {"summary": "完整结构化结果"}},
        context_versions={str(project_id): "context-v1"},
        source_receipts={"relation": "complete", "content": "complete"},
        library_items=(
            content_analysis.LibraryItemWrite(
                project_id=project_id,
                account_id="account-001",
                platform="unknown",
                platform_content_id=platform_content_id or f"work-{suffix}",
                external_url=external_url,
                category="persona",
                title="匿名标题",
                transcript="匿名转写",
                analysis={"topic": "选题"},
                project_assessment={"is_fit": True},
                latest_metrics={"like_count": 10},
                confidence="medium",
                priority=1,
                opening_status="available",
                opening_fragment="匿名开头",
                opening_unavailable_reason=None,
            ),
        ),
        cross_project_opportunities=(
            content_analysis.CrossProjectOpportunityWrite(
                method_key=f"method-{suffix}",
                method_payload={"name": "问题后置解法"},
                applicable_boundaries=["适用于知识表达"],
                sources=[{"project_id": str(project_id), "content_key": f"work-{suffix}"}],
            ),
        ),
    )


@pytest.mark.asyncio
async def test_formal_result_is_atomic_and_idempotent_across_output_and_business_tables(
    test_session,
    admin_user,
) -> None:
    project, task, envelope = await setup_envelope(test_session, admin_user)
    suffix = envelope.idempotency.result_key.rsplit("-", 1)[-1]
    store = content_analysis.SqlContentAnalysisStore(test_session)

    first = await store.persist(envelope, daily_write(project.id, suffix), admin_user.id)
    second = await store.persist(envelope, daily_write(project.id, suffix), admin_user.id)

    assert first.internal_result_id == second.internal_result_id
    assert first.output_id == second.output_id
    assert first.created is True
    assert second.created is False
    assert await test_session.scalar(
        select(func.count()).select_from(ContentAnalysisResult).where(
            ContentAnalysisResult.result_key == envelope.idempotency.result_key
        )
    ) == 1
    assert await test_session.scalar(
        select(func.count()).select_from(Output).where(Output.task_id == task.id)
    ) == 1
    assert await test_session.scalar(
        select(func.count()).select_from(ContentAnalysisLibraryItem).where(
            ContentAnalysisLibraryItem.project_id == project.id
        )
    ) == 1
    assert await test_session.scalar(
        select(func.count()).select_from(KolReference).where(
            KolReference.kol_id == project.id,
            KolReference.title == "匿名标题",
        )
    ) == 1
    assert await test_session.scalar(
        select(func.count()).select_from(ContentAnalysisCrossProjectOpportunity).where(
            ContentAnalysisCrossProjectOpportunity.method_key == f"method-{suffix}"
        )
    ) == 1


@pytest.mark.asyncio
async def test_cross_project_upsert_serializes_same_method_across_distinct_results(
    test_engine,
    test_session,
    admin_user,
    monkeypatch,
) -> None:
    first_project, _, first_envelope = await setup_envelope(
        test_session,
        admin_user,
    )
    second_project, _, second_envelope = await setup_envelope(
        test_session,
        admin_user,
    )
    method_key = f"shared-concurrent-{uuid4().hex}"
    factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    original_upsert = content_analysis.SqlContentAnalysisStore._upsert_cross_project
    both_upserts_ready = asyncio.Event()
    ready_count = 0

    async def synchronized_upsert(store, item, result_id):
        nonlocal ready_count
        await original_upsert(store, item, result_id)
        ready_count += 1
        if ready_count == 2:
            both_upserts_ready.set()
        try:
            await asyncio.wait_for(both_upserts_ready.wait(), timeout=0.15)
        except asyncio.TimeoutError:
            pass

    monkeypatch.setattr(
        content_analysis.SqlContentAnalysisStore,
        "_upsert_cross_project",
        synchronized_upsert,
    )

    def shared_write(project_id: int, suffix: str):
        base = daily_write(project_id, suffix)
        return replace(
            base,
            library_items=(),
            cross_project_opportunities=(
                replace(
                    base.cross_project_opportunities[0],
                    method_key=method_key,
                ),
            ),
        )

    async def persist_one(project, envelope):
        suffix = envelope.idempotency.result_key.rsplit("-", 1)[-1]
        async with factory() as session:
            return await content_analysis.SqlContentAnalysisStore(session).persist(
                envelope,
                shared_write(project.id, suffix),
                admin_user.id,
            )

    outcomes = await asyncio.gather(
        persist_one(first_project, first_envelope),
        persist_one(second_project, second_envelope),
        return_exceptions=True,
    )

    for item in outcomes:
        if isinstance(item, BaseException):
            raise item
        assert isinstance(item, content_analysis.PersistedResult)
    assert await test_session.scalar(
        select(func.count())
        .select_from(ContentAnalysisCrossProjectOpportunity)
        .where(ContentAnalysisCrossProjectOpportunity.method_key == method_key)
    ) == 1


@pytest.mark.asyncio
async def test_result_key_collision_with_different_analysis_identity_is_rejected(
    test_session,
    admin_user,
) -> None:
    project, _, envelope = await setup_envelope(test_session, admin_user)
    suffix = envelope.idempotency.result_key.rsplit("-", 1)[-1]
    store = content_analysis.SqlContentAnalysisStore(test_session)
    await store.persist(envelope, daily_write(project.id, suffix), admin_user.id)
    collision = replace(
        envelope,
        idempotency=content_analysis.IdempotencyKeys(
            f"different-analysis-{suffix}",
            envelope.idempotency.result_key,
            envelope.idempotency.document_key,
        ),
    )

    with pytest.raises(ValueError, match="结果幂等键"):
        await store.persist(
            collision,
            daily_write(project.id, suffix),
            admin_user.id,
        )


@pytest.mark.asyncio
async def test_test_run_persists_test_result_but_zero_writes_formal_business_tables(
    test_session,
    admin_user,
) -> None:
    project, task, envelope = await setup_envelope(
        test_session,
        admin_user,
        run_type=content_analysis.RunType.TEST,
    )
    suffix = envelope.idempotency.result_key.rsplit("-", 1)[-1]

    persisted = await content_analysis.SqlContentAnalysisStore(test_session).persist(
        envelope,
        daily_write(project.id, suffix),
        admin_user.id,
    )

    result = await test_session.get(ContentAnalysisResult, persisted.internal_result_id)
    output = await test_session.get(Output, persisted.output_id)
    assert result.is_test is True
    assert output.content_json == {"report": {"summary": "完整结构化结果"}}
    assert await test_session.scalar(
        select(func.count()).select_from(ContentAnalysisLibraryItem).where(
            ContentAnalysisLibraryItem.project_id == project.id
        )
    ) == 0
    assert await test_session.scalar(
        select(func.count()).select_from(ContentAnalysisCrossProjectOpportunity).where(
            ContentAnalysisCrossProjectOpportunity.method_key == f"method-{suffix}"
        )
    ) == 0


@pytest.mark.asyncio
async def test_weekly_baseline_persists_value_or_explicit_unavailable_reason(
    test_session,
    admin_user,
) -> None:
    project, task, envelope = await setup_envelope(
        test_session,
        admin_user,
        weekly=True,
    )
    write = content_analysis.ResultWrite(
        title="账号周报",
        status=content_analysis.InternalResultStatus.NO_CONTENT,
        payload={"baseline": None},
        context_versions={str(project.id): "context-v1"},
        source_receipts={"relation": "complete", "content": "complete"},
        account_baseline=content_analysis.AccountBaselineWrite(
            sec_uid=envelope.execution.sec_uid,
            window_start=envelope.window_start,
            window_end=envelope.window_end,
            related_project_ids=(str(project.id),),
            unavailable_reason="窗口内没有可计算的人设点赞样本",
        ),
    )

    persisted = await content_analysis.SqlContentAnalysisStore(test_session).persist(
        envelope,
        write,
        admin_user.id,
    )

    baseline = await test_session.scalar(
        select(ContentAnalysisAccountBaseline).where(
            ContentAnalysisAccountBaseline.latest_result_id == persisted.internal_result_id
        )
    )
    assert baseline.sample_count == 0
    assert baseline.unavailable_reason == "窗口内没有可计算的人设点赞样本"
    assert baseline.related_project_ids == [str(project.id)]


@pytest.mark.asyncio
async def test_delivery_state_is_separate_retryable_and_never_stores_raw_error(
    test_session,
    admin_user,
) -> None:
    project, task, envelope = await setup_envelope(test_session, admin_user)
    suffix = envelope.idempotency.result_key.rsplit("-", 1)[-1]
    store = content_analysis.SqlContentAnalysisStore(test_session)
    persisted = await store.persist(
        envelope,
        daily_write(project.id, suffix),
        admin_user.id,
    )

    assert await store.load_result_payload(persisted.internal_result_id) == {
        "report": {"summary": "完整结构化结果"}
    }
    await store.record_delivery(
        envelope,
        persisted.internal_result_id,
        status="failed",
        error="private token and user data",
    )
    await store.record_delivery(
        envelope,
        persisted.internal_result_id,
        status="success",
        identity=content_analysis.DeliveryIdentity(
            envelope.idempotency.document_key,
            "doc-1",
            "https://feishu.cn/docx/doc-1",
        ),
    )

    delivery = await test_session.scalar(
        select(ContentAnalysisDelivery).where(
            ContentAnalysisDelivery.document_key == envelope.idempotency.document_key
        )
    )
    assert delivery.status == "success"
    assert delivery.attempt_count == 2
    assert delivery.last_error is None
    assert delivery.internal_result_ids == [persisted.internal_result_id]
    assert await store.load_delivery_identity(envelope) == content_analysis.DeliveryIdentity(
        envelope.idempotency.document_key,
        "doc-1",
        "https://feishu.cn/docx/doc-1",
    )


@pytest.mark.asyncio
async def test_delivery_document_key_cannot_cross_formal_and_test_directories(
    test_session,
    admin_user,
) -> None:
    project, _, formal = await setup_envelope(test_session, admin_user)
    suffix = formal.idempotency.result_key.rsplit("-", 1)[-1]
    store = content_analysis.SqlContentAnalysisStore(test_session)
    persisted = await store.persist(
        formal,
        daily_write(project.id, suffix),
        admin_user.id,
    )
    identity = content_analysis.DeliveryIdentity(
        formal.idempotency.document_key,
        "formal-doc",
        "https://feishu.cn/docx/formal-doc",
    )
    await store.record_delivery(
        formal,
        persisted.internal_result_id,
        status="success",
        identity=identity,
    )
    test_envelope = replace(
        formal,
        run_type=content_analysis.RunType.TEST,
        delivery_target=content_analysis.DeliveryTarget(
            "root",
            "测试/reports",
            scope=content_analysis.DeliveryScope.TEST,
        ),
        idempotency=content_analysis.IdempotencyKeys(
            f"test-analysis-{suffix}",
            f"test-result-{suffix}",
            formal.idempotency.document_key,
        ),
    )

    with pytest.raises(ValueError, match="投递键"):
        await store.load_delivery_identity(test_envelope)
    with pytest.raises(ValueError, match="投递键|结果"):
        await store.record_delivery(
            test_envelope,
            persisted.internal_result_id,
            status="failed",
        )


@pytest.mark.asyncio
async def test_library_rejects_changed_url_for_an_existing_platform_identity(
    test_session,
    admin_user,
) -> None:
    project, _, envelope = await setup_envelope(test_session, admin_user)
    project_id = project.id
    suffix = envelope.idempotency.result_key.rsplit("-", 1)[-1]
    store = content_analysis.SqlContentAnalysisStore(test_session)
    await store.persist(
        envelope,
        daily_write(
            project_id,
            suffix,
            platform_content_id="stable-work",
            external_url="https://example.invalid/old",
        ),
        admin_user.id,
    )
    next_envelope = replace(
        envelope,
        idempotency=content_analysis.IdempotencyKeys(
            f"analysis-next-{suffix}",
            f"result-next-{suffix}",
            f"document-next-{suffix}",
        ),
    )

    with pytest.raises(ValueError, match="稳定身份别名发生冲突"):
        await store.persist(
            next_envelope,
            daily_write(
                project_id,
                f"next-{suffix}",
                platform_content_id="stable-work",
                external_url="https://example.invalid/new",
            ),
            admin_user.id,
        )

    items = list(
        (
            await test_session.scalars(
                select(ContentAnalysisLibraryItem).where(
                    ContentAnalysisLibraryItem.project_id == project_id
                )
            )
        ).all()
    )
    assert len(items) == 1
    assert items[0].platform_content_id == "stable-work"
    assert items[0].external_url == "https://example.invalid/old"


@pytest.mark.asyncio
async def test_library_rejects_two_stable_identities_that_point_to_different_records(
    test_session,
    admin_user,
) -> None:
    project, _, envelope = await setup_envelope(test_session, admin_user)
    suffix = envelope.idempotency.result_key.rsplit("-", 1)[-1]
    store = content_analysis.SqlContentAnalysisStore(test_session)
    await store.persist(
        envelope,
        replace(
            daily_write(project.id, suffix),
            library_items=(
                daily_write(
                    project.id,
                    suffix,
                    platform_content_id="stable-a",
                    external_url="https://example.invalid/a",
                ).library_items[0],
                daily_write(
                    project.id,
                    suffix,
                    platform_content_id="stable-b",
                    external_url="https://example.invalid/b",
                ).library_items[0],
            ),
        ),
        admin_user.id,
    )
    conflict_envelope = replace(
        envelope,
        idempotency=content_analysis.IdempotencyKeys(
            f"analysis-conflict-{suffix}",
            f"result-conflict-{suffix}",
            f"document-conflict-{suffix}",
        ),
    )

    with pytest.raises(ValueError, match="双稳定身份"):
        await store.persist(
            conflict_envelope,
            daily_write(
                project.id,
                f"conflict-{suffix}",
                platform_content_id="stable-a",
                external_url="https://example.invalid/b",
            ),
            admin_user.id,
        )

    assert await test_session.scalar(
        select(func.count()).select_from(ContentAnalysisResult).where(
            ContentAnalysisResult.result_key
            == conflict_envelope.idempotency.result_key
        )
    ) == 0


@pytest.mark.asyncio
async def test_library_keeps_stable_alias_and_manual_opening_across_partial_refreshes(
    test_session,
    admin_user,
) -> None:
    project, _, envelope = await setup_envelope(test_session, admin_user)
    suffix = envelope.idempotency.result_key.rsplit("-", 1)[-1]
    store = content_analysis.SqlContentAnalysisStore(test_session)
    stable_url = f"https://example.invalid/{suffix}"
    await store.persist(
        envelope,
        daily_write(
            project.id,
            suffix,
            platform_content_id="stable-work",
            external_url=stable_url,
        ),
        admin_user.id,
    )
    item = await test_session.scalar(
        select(ContentAnalysisLibraryItem).where(
            ContentAnalysisLibraryItem.project_id == project.id
        )
    )
    item.opening_status = "available"
    item.opening_fragment = "人工开头"
    item.opening_unavailable_reason = None
    item.analysis = {
        **dict(item.analysis),
        "opening": {
            "status": "available",
            "kind": "language",
            "fragment": "人工开头",
            "source": "manual",
        },
    }
    await test_session.commit()

    second_envelope = replace(
        envelope,
        idempotency=content_analysis.IdempotencyKeys(
            f"analysis-second-{suffix}",
            f"result-second-{suffix}",
            f"document-second-{suffix}",
        ),
    )
    second_item = replace(
        daily_write(project.id, f"second-{suffix}").library_items[0],
        platform_content_id="stable-work",
        external_url=None,
        title="刷新标题",
        transcript="刷新转写含人工开头",
        latest_metrics={"like_count": 99},
        analysis={"topic": "刷新选题", "opening": {"status": "unannotated"}},
    )
    await store.persist(
        second_envelope,
        replace(
            daily_write(project.id, f"second-{suffix}"),
            library_items=(second_item,),
        ),
        admin_user.id,
    )
    third_envelope = replace(
        envelope,
        idempotency=content_analysis.IdempotencyKeys(
            f"analysis-third-{suffix}",
            f"result-third-{suffix}",
            f"document-third-{suffix}",
        ),
    )
    third_item = replace(
        second_item,
        platform_content_id=None,
        external_url=stable_url,
    )
    await store.persist(
        third_envelope,
        replace(
            daily_write(project.id, f"third-{suffix}"),
            library_items=(third_item,),
        ),
        admin_user.id,
    )

    items = list(
        (
            await test_session.scalars(
                select(ContentAnalysisLibraryItem).where(
                    ContentAnalysisLibraryItem.project_id == project.id
                )
            )
        ).all()
    )
    assert len(items) == 1
    refreshed = items[0]
    reference = await test_session.get(KolReference, refreshed.kol_reference_id)
    assert refreshed.platform_content_id == "stable-work"
    assert refreshed.external_url == stable_url
    assert refreshed.opening_status == "available"
    assert refreshed.opening_fragment == "人工开头"
    assert refreshed.analysis["opening"]["source"] == "manual"
    assert refreshed.latest_metrics == {"like_count": 99}
    assert reference.title == "匿名标题"
    assert reference.content == "匿名转写"
    assert reference.likes == 99


@pytest.mark.asyncio
async def test_manual_opening_and_automatic_refresh_preserve_each_other_concurrently(
    test_engine,
    test_session,
    admin_user,
    monkeypatch,
) -> None:
    project, _, envelope = await setup_envelope(test_session, admin_user)
    suffix = envelope.idempotency.result_key.rsplit("-", 1)[-1]
    initial = daily_write(project.id, suffix)
    qianchuan_item = replace(
        initial.library_items[0],
        category="qianchuan",
    )
    await content_analysis.SqlContentAnalysisStore(test_session).persist(
        envelope,
        replace(initial, library_items=(qianchuan_item,)),
        admin_user.id,
    )
    item = await test_session.scalar(
        select(ContentAnalysisLibraryItem).where(
            ContentAnalysisLibraryItem.project_id == project.id
        )
    )
    item_id = item.id
    await test_session.commit()

    refresh_envelope = replace(
        envelope,
        idempotency=content_analysis.IdempotencyKeys(
            f"analysis-refresh-{suffix}",
            f"result-refresh-{suffix}",
            f"document-refresh-{suffix}",
        ),
    )
    refresh = content_analysis.LibraryRefreshWrite(
        project_id=project.id,
        platform_content_id=qianchuan_item.platform_content_id,
        external_url=None,
        analysis={
            "topic": "自动刷新新选题",
            "opening": {"status": "unannotated"},
        },
        project_assessment={"is_fit": True},
        latest_metrics={"like_count": 99},
        confidence="high",
        priority=1,
    )
    refresh_write = replace(
        initial,
        library_items=(),
        cross_project_opportunities=(),
        library_refreshes=(refresh,),
    )
    factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    refresh_loaded = asyncio.Event()
    manual_committed = asyncio.Event()
    original_refresh = content_analysis.SqlContentAnalysisStore._refresh_library

    async def delayed_refresh(store, refresh_item, result_id):
        await original_refresh(store, refresh_item, result_id)
        refresh_loaded.set()
        try:
            await asyncio.wait_for(manual_committed.wait(), timeout=0.15)
        except asyncio.TimeoutError:
            pass

    monkeypatch.setattr(
        content_analysis.SqlContentAnalysisStore,
        "_refresh_library",
        delayed_refresh,
    )

    async def automatic_refresh():
        async with factory() as session:
            await content_analysis.SqlContentAnalysisStore(session).persist(
                refresh_envelope,
                refresh_write,
                admin_user.id,
            )

    async def manual_annotation():
        await refresh_loaded.wait()
        async with factory() as session:
            response = await annotate_library_opening(
                item_id,
                ManualOpeningUpdate(
                    project_id=project.id,
                    status="available",
                    fragment="匿名转写",
                ),
                Request(
                    {
                        "type": "http",
                        "method": "PATCH",
                        "path": "/",
                        "headers": [],
                    }
                ),
                db=session,
                user=admin_user,
            )
            assert response.success is True
        manual_committed.set()

    await asyncio.gather(automatic_refresh(), manual_annotation())

    test_session.expire_all()
    refreshed = await test_session.get(ContentAnalysisLibraryItem, item_id)
    assert refreshed.analysis["topic"] == "自动刷新新选题"
    assert refreshed.analysis["opening"] == {
        "status": "available",
        "kind": "language",
        "fragment": "匿名转写",
        "source": "manual",
    }
    assert refreshed.opening_status == "available"
    assert refreshed.opening_fragment == "匿名转写"
    assert refreshed.latest_metrics == {"like_count": 99}


@pytest.mark.asyncio
async def test_restore_and_automatic_refresh_rebuild_from_the_latest_library_snapshot(
    test_engine,
    test_session,
    admin_user,
    monkeypatch,
) -> None:
    project, _, envelope = await setup_envelope(test_session, admin_user)
    suffix = envelope.idempotency.result_key.rsplit("-", 1)[-1]
    base_write = daily_write(project.id, suffix)

    def analysis(method_key: str, name: str) -> dict:
        return {
            "source_information": {
                "facts": [],
                "judgments": [],
                "assumptions": [],
                "limitations": [],
                "source_constraints": [],
            },
            "reusable_methods": [
                {
                    "name": name,
                    "description": f"{name}的匿名说明",
                    "method_key": method_key,
                    "evidence": [
                        {
                            "evidence_type": "transcript",
                            "locator": "transcript:0-4",
                            "detail": "匿名转写",
                        }
                    ],
                    "applicable_boundaries": [
                        {"statement": "只复用表达结构"}
                    ],
                }
            ],
        }

    assessment = {
        "is_fit": True,
        "cross_project_signals": [
            "novel_content_method",
            "shared_content_problem_solution",
        ],
        "cross_project_scenarios": [{"statement": "适合知识口播"}],
    }
    old_method_key = f"restore-old-{suffix}"
    new_method_key = f"restore-new-{suffix}"
    initial_item = replace(
        base_write.library_items[0],
        analysis=analysis(old_method_key, "旧方法"),
        project_assessment=assessment,
    )
    await content_analysis.SqlContentAnalysisStore(test_session).persist(
        envelope,
        replace(
            base_write,
            library_items=(initial_item,),
            cross_project_opportunities=(),
        ),
        admin_user.id,
    )
    item = await test_session.scalar(
        select(ContentAnalysisLibraryItem).where(
            ContentAnalysisLibraryItem.project_id == project.id
        )
    )
    item_id = item.id
    item.availability = "disabled"
    await test_session.commit()

    refresh_envelope = replace(
        envelope,
        idempotency=content_analysis.IdempotencyKeys(
            f"analysis-restore-refresh-{suffix}",
            f"result-restore-refresh-{suffix}",
            f"document-restore-refresh-{suffix}",
        ),
    )
    refresh = content_analysis.LibraryRefreshWrite(
        project_id=project.id,
        platform_content_id=initial_item.platform_content_id,
        external_url=initial_item.external_url,
        analysis=analysis(new_method_key, "新方法"),
        project_assessment=assessment,
        latest_metrics={"like_count": 99},
        confidence="high",
        priority=1,
    )
    refresh_write = replace(
        base_write,
        library_items=(),
        cross_project_opportunities=(),
        library_refreshes=(refresh,),
    )
    factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    restore_loaded = asyncio.Event()
    automatic_committed = asyncio.Event()
    original_rebuild = (
        content_analysis.SqlContentAnalysisStore.rebuild_cross_project_opportunities
    )

    async def delayed_restore_rebuild(store, result_id):
        restore_loaded.set()
        try:
            await asyncio.wait_for(automatic_committed.wait(), timeout=0.15)
        except asyncio.TimeoutError:
            pass
        await original_rebuild(store, result_id)

    monkeypatch.setattr(
        content_analysis.SqlContentAnalysisStore,
        "rebuild_cross_project_opportunities",
        delayed_restore_rebuild,
    )

    async def restore_item():
        async with factory() as session:
            response = await set_library_availability(
                item_id,
                LibraryAvailabilityUpdate(
                    project_id=project.id,
                    availability="enabled",
                ),
                Request(
                    {
                        "type": "http",
                        "method": "PATCH",
                        "path": "/",
                        "headers": [],
                    }
                ),
                db=session,
                user=admin_user,
            )
            assert response.success is True

    async def automatic_refresh():
        await restore_loaded.wait()
        async with factory() as session:
            await content_analysis.SqlContentAnalysisStore(session).persist(
                refresh_envelope,
                refresh_write,
                admin_user.id,
            )
        automatic_committed.set()

    await asyncio.gather(restore_item(), automatic_refresh())

    test_session.expire_all()
    refreshed = await test_session.get(ContentAnalysisLibraryItem, item_id)
    opportunities = list(
        (
            await test_session.scalars(
                select(ContentAnalysisCrossProjectOpportunity).where(
                    ContentAnalysisCrossProjectOpportunity.method_key.in_(
                        (old_method_key, new_method_key)
                    )
                )
            )
        ).all()
    )
    assert refreshed.analysis["reusable_methods"][0]["method_key"] == new_method_key
    assert {row.method_key for row in opportunities if row.is_active} == {
        new_method_key
    }


@pytest.mark.asyncio
async def test_library_refresh_fills_missing_stable_alias_and_future_id_only_refresh_matches(
    test_session,
    admin_user,
) -> None:
    project, _, envelope = await setup_envelope(test_session, admin_user)
    project_id = project.id
    suffix = envelope.idempotency.result_key.rsplit("-", 1)[-1]
    stable_url = f"https://example.invalid/alias-{suffix}"
    store = content_analysis.SqlContentAnalysisStore(test_session)
    initial = daily_write(project_id, suffix)
    await store.persist(
        envelope,
        replace(
            initial,
            library_items=(
                replace(
                    initial.library_items[0],
                    platform_content_id=None,
                    external_url=stable_url,
                ),
            ),
        ),
        admin_user.id,
    )
    refresh = content_analysis.LibraryRefreshWrite(
        project_id=project_id,
        platform_content_id="stable-alias-id",
        external_url=stable_url,
        analysis={"topic": "别名补齐"},
        project_assessment={"is_fit": True},
        latest_metrics={"like_count": 20},
        confidence="medium",
        priority=1,
    )
    second = replace(
        envelope,
        idempotency=content_analysis.IdempotencyKeys(
            f"analysis-alias-2-{suffix}",
            f"result-alias-2-{suffix}",
            f"document-alias-2-{suffix}",
        ),
    )
    await store.persist(
        second,
        replace(
            daily_write(project_id, f"alias-2-{suffix}"),
            library_items=(),
            cross_project_opportunities=(),
            library_refreshes=(refresh,),
        ),
        admin_user.id,
    )
    third = replace(
        envelope,
        idempotency=content_analysis.IdempotencyKeys(
            f"analysis-alias-3-{suffix}",
            f"result-alias-3-{suffix}",
            f"document-alias-3-{suffix}",
        ),
    )
    await store.persist(
        third,
        replace(
            daily_write(project_id, f"alias-3-{suffix}"),
            library_items=(),
            cross_project_opportunities=(),
            library_refreshes=(replace(refresh, external_url=None),),
        ),
        admin_user.id,
    )

    rows = list(
        (
            await test_session.scalars(
                select(ContentAnalysisLibraryItem).where(
                    ContentAnalysisLibraryItem.project_id == project_id
                )
            )
        ).all()
    )
    assert len(rows) == 1
    assert rows[0].platform_content_id == "stable-alias-id"
    assert rows[0].external_url == stable_url


@pytest.mark.asyncio
@pytest.mark.parametrize("remove_mode", ("disable", "soft_delete"))
async def test_cross_project_rebuild_deactivates_method_after_last_source_is_unavailable(
    test_session,
    admin_user,
    remove_mode,
) -> None:
    project, _, envelope = await setup_envelope(test_session, admin_user)
    suffix = envelope.idempotency.result_key.rsplit("-", 1)[-1]
    write = daily_write(project.id, suffix)
    method = {
        "name": "问题前置",
        "description": "先说共同问题，再说明解决步骤",
        "method_key": f"shared-{suffix}",
        "evidence": [
            {
                "evidence_type": "transcript",
                "locator": "transcript:0-4",
                "detail": "匿名转写",
            }
        ],
        "applicable_boundaries": [{"statement": "只复用表达结构"}],
    }
    library_item = replace(
        write.library_items[0],
        analysis={
            "source_information": {
                "facts": [],
                "judgments": [],
                "assumptions": [],
                "limitations": [],
                "source_constraints": [],
            },
            "reusable_methods": [method],
        },
        project_assessment={
            "cross_project_signals": [
                "novel_content_method",
                "shared_content_problem_solution",
            ],
            "cross_project_scenarios": [{"statement": "适合知识口播"}],
        },
    )
    store = content_analysis.SqlContentAnalysisStore(test_session)
    persisted = await store.persist(
        envelope,
        replace(
            write,
            library_items=(library_item,),
            cross_project_opportunities=(),
        ),
        admin_user.id,
    )
    cross = await test_session.scalar(
        select(ContentAnalysisCrossProjectOpportunity).where(
            ContentAnalysisCrossProjectOpportunity.method_key == f"shared-{suffix}"
        )
    )
    assert cross.is_active is True
    item = await test_session.scalar(
        select(ContentAnalysisLibraryItem).where(
            ContentAnalysisLibraryItem.project_id == project.id
        )
    )
    if remove_mode == "disable":
        item.availability = "disabled"
    else:
        reference = await test_session.get(KolReference, item.kol_reference_id)
        reference.deleted_at = datetime.now(timezone.utc)
    await store.rebuild_cross_project_opportunities(persisted.internal_result_id)
    await test_session.commit()
    await test_session.refresh(cross)
    assert cross.is_active is False


@pytest.mark.asyncio
async def test_system_service_user_validation_requires_enabled_admin(
    test_session,
    admin_user,
    operator_user,
) -> None:
    store = content_analysis.SqlContentAnalysisStore(test_session)

    assert await store.validate_system_user(admin_user.id) is True
    assert await store.validate_system_user(operator_user.id) is False
    admin_user.status = "disabled"
    await test_session.flush()
    assert await store.validate_system_user(admin_user.id) is False


@pytest.mark.asyncio
async def test_delivery_key_is_bound_to_daily_business_date(
    test_session,
    admin_user,
) -> None:
    project, _, envelope = await setup_envelope(test_session, admin_user)
    suffix = envelope.idempotency.result_key.rsplit("-", 1)[-1]
    store = content_analysis.SqlContentAnalysisStore(test_session)
    persisted = await store.persist(
        envelope,
        daily_write(project.id, suffix),
        admin_user.id,
    )
    await store.record_delivery(
        envelope,
        persisted.internal_result_id,
        status="success",
        identity=content_analysis.DeliveryIdentity(
            envelope.idempotency.document_key,
            "daily-doc",
            "https://feishu.cn/docx/daily-doc",
        ),
    )
    next_day = replace(
        envelope,
        business_date=date(2026, 9, 5),
        window_start=datetime(2026, 9, 3, tzinfo=SHANGHAI),
        window_end=datetime(2026, 9, 6, tzinfo=SHANGHAI),
    )

    with pytest.raises(ValueError, match="业务周期"):
        await store.load_delivery_identity(next_day)


@pytest.mark.asyncio
async def test_weekly_saved_result_requires_exact_related_project_snapshot(
    test_session,
    admin_user,
) -> None:
    project, _, envelope = await setup_envelope(
        test_session,
        admin_user,
        weekly=True,
    )
    other = Kol(
        name=f"cov_ca_weekly_other_{uuid4().hex[:8]}",
        persona="项目人设",
        content_plan="内容规划",
        status="signed",
        created_by=admin_user.id,
    )
    test_session.add(other)
    await test_session.flush()
    write = content_analysis.ResultWrite(
        title="账号周报",
        status=content_analysis.InternalResultStatus.NO_CONTENT,
        payload={"weekly_batch_id": envelope.execution.weekly_batch_id},
        context_versions={str(project.id): "context-v1"},
        source_receipts={"relation": "complete", "content": "complete"},
    )
    store = content_analysis.SqlContentAnalysisStore(test_session)
    persisted = await store.persist(envelope, write, admin_user.id)
    changed_projects = tuple(
        str(value) for value in sorted((project.id, other.id))
    )
    changed = replace(
        envelope,
        execution=replace(
            envelope.execution,
            project_ids=changed_projects,
        ),
    )

    with pytest.raises(ValueError, match="信封身份"):
        await store.load_persisted_result(
            changed,
            persisted.internal_result_id,
        )


@pytest.mark.asyncio
async def test_manual_redelivery_reuses_saved_result_with_a_new_run_key(
    test_session,
    admin_user,
) -> None:
    project, task, original = await setup_envelope(test_session, admin_user)
    store = content_analysis.SqlContentAnalysisStore(test_session)
    suffix = original.idempotency.result_key.rsplit("-", 1)[-1]
    persisted = await store.persist(
        original,
        daily_write(project.id, suffix),
        admin_user.id,
    )
    retry = replace(
        original,
        task_id=task.id + 100000,
        task_no=f"{task.task_no}-RETRY",
        run_type=content_analysis.RunType.RETRY,
        retry_of_task_id=task.id,
        retry_mode=content_analysis.RetryMode.DELIVERY_ONLY,
        trigger_source=content_analysis.TriggerSource.USER,
        idempotency=content_analysis.IdempotencyKeys(
            f"manual-redelivery-{uuid4().hex}",
            original.idempotency.result_key,
            original.idempotency.document_key,
        ),
    )

    loaded = await store.load_persisted_result(
        retry,
        persisted.internal_result_id,
    )

    assert loaded.internal_result_id == persisted.internal_result_id


@pytest.mark.asyncio
@pytest.mark.parametrize("weekly", (False, True))
async def test_manual_redelivery_origin_binds_failed_task_result_target_and_scope(
    test_session,
    admin_user,
    weekly,
) -> None:
    project, original_task, original = await setup_envelope(
        test_session,
        admin_user,
        weekly=weekly,
    )
    expected_tool = (
        "content-analysis-weekly" if weekly else "content-analysis-daily"
    )
    original_task.tool_code = expected_tool
    original_task.input_payload = stored_task_payload(original)
    store = content_analysis.SqlContentAnalysisStore(test_session)
    suffix = original.idempotency.result_key.rsplit("-", 1)[-1]
    write = (
        content_analysis.ResultWrite(
            title="账号周报",
            status=content_analysis.InternalResultStatus.NO_CONTENT,
            payload={"weekly_batch_id": original.execution.weekly_batch_id},
            context_versions={str(project.id): "context-v1"},
            source_receipts={"relation": "complete", "content": "complete"},
        )
        if weekly
        else daily_write(project.id, suffix)
    )
    persisted = await store.persist(original, write, admin_user.id)
    original_task.status = "failed"
    original_task.result_summary = {
        "failure_stage": "delivery",
        "internal_result": {
            "status": "success",
            "outcome": "no_content" if weekly else "content",
            "internal_result_id": str(persisted.internal_result_id),
        },
        "delivery": {"status": "failed", "reason_code": "DELIVERY_FAILED"},
    }
    retry_task = TaskJob(
        task_no=f"ca_s28_manual_redelivery_{uuid4().hex[:8]}",
        tool_code=expected_tool,
        tool_name="内容分析",
        status="processing",
        created_by=admin_user.id,
    )
    test_session.add(retry_task)
    await test_session.flush()
    request_id = f"request-{uuid4().hex}"
    retry = replace(
        original,
        task_id=retry_task.id,
        task_no=retry_task.task_no,
        run_type=content_analysis.RunType.RETRY,
        retry_of_task_id=original_task.id,
        retry_mode=content_analysis.RetryMode.DELIVERY_ONLY,
        request_id=request_id,
        trigger_source=content_analysis.TriggerSource.USER,
        idempotency=content_analysis.IdempotencyKeys(
            f"manual-redelivery-{uuid4().hex}",
            original.idempotency.result_key,
            original.idempotency.document_key,
        ),
    )
    retry_task.input_payload = stored_task_payload(
        retry,
        run_type="manual_retry",
        request_id=request_id,
    )
    await test_session.commit()

    assert await store.validate_manual_redelivery_origin(
        retry,
        persisted.internal_result_id,
    ) is True
    assert await store.validate_manual_redelivery_origin(
        replace(retry, request_id=f"different-{uuid4().hex}"),
        persisted.internal_result_id,
    ) is False
    assert await store.validate_manual_redelivery_origin(
        replace(
            retry,
            delivery_target=replace(retry.delivery_target, report_root_ref="other-root"),
        ),
        persisted.internal_result_id,
    ) is False
    assert await store.validate_manual_redelivery_origin(
        retry,
        persisted.internal_result_id + 1,
    ) is False


@pytest.mark.asyncio
async def test_manual_redelivery_binds_test_subdirectory_and_supports_failed_retry_chain(
    test_session,
    admin_user,
) -> None:
    project, original_task, original = await setup_envelope(
        test_session,
        admin_user,
        run_type=content_analysis.RunType.TEST,
    )
    original_task.tool_code = "content-analysis-daily"
    original_task.input_payload = stored_task_payload(original, run_type="test")
    store = content_analysis.SqlContentAnalysisStore(test_session)
    persisted = await store.persist(
        original,
        daily_write(
            project.id,
            original.idempotency.result_key.rsplit("-", 1)[-1],
        ),
        admin_user.id,
    )
    original_task.status = "failed"
    original_task.result_summary = {
        "failure_stage": "delivery",
        "internal_result": {
            "status": "success",
            "outcome": "content",
            "internal_result_id": str(persisted.internal_result_id),
        },
        "delivery": {"status": "failed", "reason_code": "DELIVERY_FAILED"},
    }

    first_task = TaskJob(
        task_no=f"ca_s28_first_test_redelivery_{uuid4().hex[:8]}",
        tool_code="content-analysis-daily",
        tool_name="内容分析",
        status="failed",
        created_by=admin_user.id,
    )
    test_session.add(first_task)
    await test_session.flush()
    first_request_id = f"request-{uuid4().hex}"
    first = replace(
        original,
        task_id=first_task.id,
        task_no=first_task.task_no,
        run_type=content_analysis.RunType.RETRY,
        retry_of_task_id=original_task.id,
        retry_mode=content_analysis.RetryMode.DELIVERY_ONLY,
        request_id=first_request_id,
        trigger_source=content_analysis.TriggerSource.USER,
        idempotency=content_analysis.IdempotencyKeys(
            f"first-test-redelivery-{uuid4().hex}",
            original.idempotency.result_key,
            original.idempotency.document_key,
        ),
    )
    first_task.input_payload = stored_task_payload(
        first,
        run_type="manual_retry",
        request_id=first_request_id,
    )
    first_task.result_summary = {
        "failure_stage": "delivery",
        "internal_result": {
            "status": "success",
            "outcome": "content",
            "internal_result_id": str(persisted.internal_result_id),
        },
        "delivery": {"status": "failed", "reason_code": "DELIVERY_FAILED"},
    }

    second_task = TaskJob(
        task_no=f"ca_s28_second_test_redelivery_{uuid4().hex[:8]}",
        tool_code="content-analysis-daily",
        tool_name="内容分析",
        status="processing",
        created_by=admin_user.id,
    )
    test_session.add(second_task)
    await test_session.flush()
    second_request_id = f"request-{uuid4().hex}"
    second = replace(
        first,
        task_id=second_task.id,
        task_no=second_task.task_no,
        retry_of_task_id=first_task.id,
        request_id=second_request_id,
        idempotency=content_analysis.IdempotencyKeys(
            f"second-test-redelivery-{uuid4().hex}",
            original.idempotency.result_key,
            original.idempotency.document_key,
        ),
    )
    second_task.input_payload = stored_task_payload(
        second,
        run_type="manual_retry",
        request_id=second_request_id,
    )
    await test_session.commit()

    assert await store.validate_manual_redelivery_origin(
        second,
        persisted.internal_result_id,
    ) is True
    assert await store.validate_manual_redelivery_origin(
        replace(
            second,
            delivery_target=replace(
                second.delivery_target,
                relative_directory="测试报告/其他",
            ),
        ),
        persisted.internal_result_id,
    ) is False


@pytest.mark.asyncio
async def test_weekly_document_key_cannot_cross_batch_identity(
    test_session,
    admin_user,
) -> None:
    project, _, envelope = await setup_envelope(
        test_session,
        admin_user,
        weekly=True,
    )
    store = content_analysis.SqlContentAnalysisStore(test_session)
    write = content_analysis.ResultWrite(
        title="账号周报",
        status=content_analysis.InternalResultStatus.NO_CONTENT,
        payload={"weekly_batch_id": envelope.execution.weekly_batch_id},
        context_versions={str(project.id): "context-v1"},
        source_receipts={"relation": "complete", "content": "complete"},
    )
    persisted = await store.persist(envelope, write, admin_user.id)
    await store.record_delivery(
        envelope,
        persisted.internal_result_id,
        status="success",
        identity=content_analysis.DeliveryIdentity(
            envelope.idempotency.document_key,
            "weekly-doc",
            "https://feishu.cn/docx/weekly-doc",
        ),
    )
    another_batch = replace(
        envelope,
        execution=replace(
            envelope.execution,
            weekly_batch_id="weekly-another-batch",
        ),
    )

    with pytest.raises(ValueError, match="周批次"):
        await store.load_delivery_identity(another_batch)


@pytest.mark.asyncio
async def test_weekly_finalize_uses_latest_terminal_attempt_and_three_final_states(
    test_session,
    admin_user,
) -> None:
    project, finalize_task, account_envelope = await setup_envelope(
        test_session,
        admin_user,
        weekly=True,
    )
    finalize_envelope = replace(
        account_envelope,
        execution=content_analysis.WeeklyBatchFinalizeExecution(
            weekly_batch_id=account_envelope.execution.weekly_batch_id,
            batch_size=3,
            project_ids=(str(project.id),),
            finalize_version="state-v1",
        ),
    )
    finalize_task.tool_code = "content-analysis-weekly"
    rows = (
        ("account-success", "failed", "content", 1, datetime(2026, 9, 5, 1, tzinfo=SHANGHAI)),
        ("account-success", "success", "content", 1, datetime(2026, 9, 5, 2, tzinfo=SHANGHAI)),
        ("account-empty", "success", "no_content", 2, datetime(2026, 9, 5, 3, tzinfo=SHANGHAI)),
        ("account-failed", "failed", "content", 3, datetime(2026, 9, 5, 4, tzinfo=SHANGHAI)),
    )
    successful_jobs = []
    for index, (sec_uid, status, outcome, position, finished_at) in enumerate(rows):
        job = TaskJob(
                task_no=f"ca_s28_finalize_{index}_{uuid4().hex[:6]}",
            tool_code="content-analysis-weekly",
            tool_name="内容分析",
            status=status,
            input_payload=weekly_account_task_payload(
                finalize_envelope,
                sec_uid=sec_uid,
                position=position,
            ),
            result_summary=weekly_task_summary(status, outcome=outcome),
            finished_at=finished_at,
            created_by=admin_user.id,
        )
        test_session.add(job)
        await test_session.flush()
        if status == "success":
            successful_jobs.append((job, sec_uid, outcome))
    for job, sec_uid, outcome in successful_jobs:
        await attach_weekly_account_result(
            test_session,
            job,
            finalize_envelope,
            sec_uid=sec_uid,
            outcome=outcome,
            baseline=(
                weekly_baseline_payload(
                    finalize_envelope,
                    sec_uid,
                    sample_count=3,
                )
                if sec_uid == "account-success"
                else weekly_baseline_payload(finalize_envelope, sec_uid)
            ),
        )
    await test_session.flush()

    summary = await content_analysis.SqlContentAnalysisStore(
        test_session
    ).load_weekly_batch_finalize_summary(finalize_envelope)

    assert summary["success_account_count"] == 1
    assert summary["no_content_account_count"] == 1
    assert summary["failed_account_count"] == 1
    assert summary["pending_account_count"] == 0
    assert summary["calculable_account_count"] == 1
    assert [item["status"] for item in summary["account_results"]] == [
        "no_content",
        "failed",
        "success",
    ]
    assert all(
        item["updated_at"].endswith("+08:00")
        for item in summary["account_results"]
    )
    assert summary["account_results"][0]["sample_count"] == 0
    assert summary["account_results"][0]["unavailable_reason"] == (
        "窗口内没有可计算的人设点赞样本"
    )
    assert summary["account_results"][2]["sample_count"] == 3
    assert summary["account_results"][2]["mean_likes"] == 12.0
    failed_hash = "sha256:" + hashlib.sha256(b"account-failed").hexdigest()
    assert summary["failures"] == [
        {
            "account_hash": failed_hash,
            "reason_code": "FEISHU_CONTENT_READ_FAILED",
            "public_message": "账号周任务执行失败",
        }
    ]
    assert summary["account_results"][1]["account_hash"] == failed_hash
    assert "sec_uid" not in summary["account_results"][1]
    assert "account-failed" not in str(summary)


@pytest.mark.asyncio
async def test_weekly_finalize_resolves_saved_result_owned_by_latest_delivery_retry_origin(
    test_session,
    admin_user,
) -> None:
    project, original_job, account_envelope = await setup_envelope(
        test_session,
        admin_user,
        weekly=True,
    )
    finalize_envelope = replace(
        account_envelope,
        execution=content_analysis.WeeklyBatchFinalizeExecution(
            weekly_batch_id=account_envelope.execution.weekly_batch_id,
            batch_size=1,
            project_ids=(str(project.id),),
            finalize_version="state-v1",
        ),
    )
    original_job.tool_code = "content-analysis-weekly"
    original_job.status = "failed"
    original_job.input_payload = stored_task_payload(account_envelope)
    original_job.finished_at = datetime(2026, 9, 5, 1, tzinfo=SHANGHAI)
    result = await attach_weekly_account_result(
        test_session,
        original_job,
        finalize_envelope,
        sec_uid=account_envelope.execution.sec_uid,
        baseline=weekly_baseline_payload(
            finalize_envelope,
            account_envelope.execution.sec_uid,
            sample_count=2,
        ),
    )
    original_job.status = "failed"
    original_job.result_summary["failure_stage"] = "delivery"
    original_job.result_summary["delivery"] = {
        "status": "failed",
        "reason_code": "DELIVERY_FAILED",
    }
    retry_job = TaskJob(
        task_no=f"ca_s28_account_redelivery_{uuid4().hex[:8]}",
        tool_code="content-analysis-weekly",
        tool_name="内容分析",
        status="failed",
        created_by=admin_user.id,
        finished_at=datetime(2026, 9, 5, 2, tzinfo=SHANGHAI),
    )
    test_session.add(retry_job)
    await test_session.flush()
    request_id = f"request-{uuid4().hex}"
    retry_envelope = replace(
        account_envelope,
        task_id=retry_job.id,
        task_no=retry_job.task_no,
        run_type=content_analysis.RunType.RETRY,
        retry_of_task_id=original_job.id,
        retry_mode=content_analysis.RetryMode.DELIVERY_ONLY,
        request_id=request_id,
        trigger_source=content_analysis.TriggerSource.USER,
        idempotency=content_analysis.IdempotencyKeys(
            f"account-redelivery-{uuid4().hex}",
            account_envelope.idempotency.result_key,
            account_envelope.idempotency.document_key,
        ),
    )
    retry_job.input_payload = stored_task_payload(
        retry_envelope,
        run_type="manual_retry",
        request_id=request_id,
    )
    retry_job.result_summary = {
        "failure_stage": "delivery",
        "internal_result": {
            "status": "success",
            "outcome": "content",
            "internal_result_id": str(result.id),
        },
        "delivery": {"status": "failed", "reason_code": "DELIVERY_FAILED"},
    }
    second_retry_job = TaskJob(
        task_no=f"ca_s28_account_second_redelivery_{uuid4().hex[:8]}",
        tool_code="content-analysis-weekly",
        tool_name="内容分析",
        status="success",
        created_by=admin_user.id,
        finished_at=datetime(2026, 9, 5, 3, tzinfo=SHANGHAI),
    )
    test_session.add(second_retry_job)
    await test_session.flush()
    second_request_id = f"request-{uuid4().hex}"
    second_retry_envelope = replace(
        retry_envelope,
        task_id=second_retry_job.id,
        task_no=second_retry_job.task_no,
        retry_of_task_id=retry_job.id,
        request_id=second_request_id,
        idempotency=content_analysis.IdempotencyKeys(
            f"account-second-redelivery-{uuid4().hex}",
            account_envelope.idempotency.result_key,
            account_envelope.idempotency.document_key,
        ),
    )
    second_retry_job.input_payload = stored_task_payload(
        second_retry_envelope,
        run_type="manual_retry",
        request_id=second_request_id,
    )
    second_retry_job.result_summary = {
        "failure_stage": None,
        "internal_result": {
            "status": "success",
            "outcome": "content",
            "internal_result_id": str(result.id),
        },
        "delivery": {"status": "success"},
    }
    await test_session.commit()

    summary = await content_analysis.SqlContentAnalysisStore(
        test_session
    ).load_weekly_batch_finalize_summary(finalize_envelope)

    assert summary["success_account_count"] == 1
    assert summary["calculable_account_count"] == 1
    assert summary["account_results"][0]["sample_count"] == 2


@pytest.mark.asyncio
async def test_weekly_finalize_all_failed_is_terminal_empty_summary(
    test_session,
    admin_user,
) -> None:
    project, _, account_envelope = await setup_envelope(
        test_session,
        admin_user,
        weekly=True,
    )
    finalize_envelope = replace(
        account_envelope,
        execution=content_analysis.WeeklyBatchFinalizeExecution(
            weekly_batch_id=account_envelope.execution.weekly_batch_id,
            batch_size=2,
            project_ids=(str(project.id),),
            finalize_version="state-v1",
        ),
    )
    for position in (1, 2):
        test_session.add(
            TaskJob(
                task_no=f"ca_s28_all_failed_{position}_{uuid4().hex[:6]}",
                tool_code="content-analysis-weekly",
                tool_name="内容分析",
                status="failed",
                input_payload=weekly_account_task_payload(
                    finalize_envelope,
                    sec_uid=f"account-failed-{position}",
                    position=position,
                ),
                result_summary=(
                    weekly_task_summary("failed")
                    if position == 1
                    else {
                        "failure_stage": "analysis",
                        "feishu_relation": {
                            "status": "ready",
                            "content_read_status": "ready",
                        },
                        "internal_result": {
                            "status": "failed",
                            "reason_code": "private-secret-must-not-leak",
                        },
                        "delivery": {"status": "skipped"},
                    }
                ),
                finished_at=datetime(2026, 9, 5, position, tzinfo=SHANGHAI),
                created_by=admin_user.id,
            )
        )
    await test_session.flush()

    summary = await content_analysis.SqlContentAnalysisStore(
        test_session
    ).load_weekly_batch_finalize_summary(finalize_envelope)

    assert summary["failed_account_count"] == 2
    assert summary["success_account_count"] == 0
    assert summary["no_content_account_count"] == 0
    assert summary["pending_account_count"] == 0
    assert summary["unavailable_reason"] == "本批次没有可计算账号"
    assert [item["reason_code"] for item in summary["failures"]] == [
        "FEISHU_CONTENT_READ_FAILED",
        "ACCOUNT_FAILED",
    ]


@pytest.mark.asyncio
async def test_weekly_finalize_success_without_persona_samples_is_not_calculable(
    test_session,
    admin_user,
) -> None:
    project, _, account_envelope = await setup_envelope(
        test_session,
        admin_user,
        weekly=True,
    )
    finalize_envelope = replace(
        account_envelope,
        execution=content_analysis.WeeklyBatchFinalizeExecution(
            weekly_batch_id=account_envelope.execution.weekly_batch_id,
            batch_size=1,
            project_ids=(str(project.id),),
            finalize_version="state-v1",
        ),
    )
    job = TaskJob(
        task_no=f"ca_s28_no_persona_{uuid4().hex[:6]}",
        tool_code="content-analysis-weekly",
        tool_name="内容分析",
        status="success",
        input_payload=weekly_account_task_payload(
            finalize_envelope,
            sec_uid="account-qianchuan-only",
            position=1,
        ),
        result_summary={},
        finished_at=datetime(2026, 9, 5, 4, tzinfo=SHANGHAI),
        created_by=admin_user.id,
    )
    test_session.add(job)
    await test_session.flush()
    await attach_weekly_account_result(
        test_session,
        job,
        finalize_envelope,
        sec_uid="account-qianchuan-only",
        baseline=weekly_baseline_payload(
            finalize_envelope,
            "account-qianchuan-only",
        ),
    )

    summary = await content_analysis.SqlContentAnalysisStore(
        test_session
    ).load_weekly_batch_finalize_summary(finalize_envelope)

    assert summary["success_account_count"] == 1
    assert summary["calculable_account_count"] == 0
    assert summary["unavailable_reason"] == "本批次没有可计算账号"
    assert summary["account_results"] == [
        {
            "sec_uid": "account-qianchuan-only",
            "status": "success",
            "reason_code": None,
            "project_ids": [str(project.id)],
            "sample_count": 0,
            "mean_likes": None,
            "median_likes": None,
            "maximum_likes": None,
            "minimum_likes": None,
            "baseline_updated_at": "2026-09-05T04:00:00+08:00",
            "unavailable_reason": "窗口内没有可计算的人设点赞样本",
            "updated_at": "2026-09-05T04:00:00+08:00",
        }
    ]


@pytest.mark.asyncio
async def test_weekly_finalize_zero_accounts_ignores_other_batch_rows(
    test_session,
    admin_user,
) -> None:
    project, _, account_envelope = await setup_envelope(
        test_session,
        admin_user,
        weekly=True,
    )
    finalize_envelope = replace(
        account_envelope,
        execution=content_analysis.WeeklyBatchFinalizeExecution(
            weekly_batch_id="weekly-empty-batch",
            batch_size=0,
            project_ids=(str(project.id),),
            finalize_version="empty-state-v1",
        ),
    )
    test_session.add(
        TaskJob(
            task_no=f"ca_s28_other_batch_{uuid4().hex[:6]}",
            tool_code="content-analysis-weekly",
            tool_name="内容分析",
            status="failed",
            input_payload=weekly_account_task_payload(
                replace(
                    finalize_envelope,
                    execution=content_analysis.WeeklyBatchFinalizeExecution(
                        weekly_batch_id="weekly-other-batch",
                        batch_size=1,
                        project_ids=(str(project.id),),
                        finalize_version="other-state-v1",
                    ),
                ),
                sec_uid="account-other-batch",
                position=1,
            ),
            result_summary=weekly_task_summary("failed"),
            finished_at=datetime(2026, 9, 5, 4, tzinfo=SHANGHAI),
            created_by=admin_user.id,
        )
    )
    await test_session.flush()

    summary = await content_analysis.SqlContentAnalysisStore(
        test_session
    ).load_weekly_batch_finalize_summary(finalize_envelope)

    assert summary == {
        "weekly_batch_id": "weekly-empty-batch",
        "finalize_version": "empty-state-v1",
        "selected_project_ids": [str(project.id)],
        "account_count": 0,
        "success_account_count": 0,
        "no_content_account_count": 0,
        "failed_account_count": 0,
        "pending_account_count": 0,
        "calculable_account_count": 0,
        "failures": [],
        "account_results": [],
        "unavailable_reason": "本批次没有账号实例",
    }


@pytest.mark.asyncio
async def test_weekly_finalize_query_isolated_by_tool_window_scope_and_object(
    test_session,
    admin_user,
) -> None:
    project, _, account_envelope = await setup_envelope(
        test_session,
        admin_user,
        weekly=True,
    )
    finalize_envelope = replace(
        account_envelope,
        execution=content_analysis.WeeklyBatchFinalizeExecution(
            weekly_batch_id=account_envelope.execution.weekly_batch_id,
            batch_size=1,
            project_ids=(str(project.id),),
            finalize_version="state-v1",
        ),
    )
    variants = (
        ("account-valid", "content-analysis-weekly", None, None, "weekly", "account"),
        ("account-other-tool", "other-agent", None, None, "weekly", "account"),
        ("account-test", "content-analysis-weekly", "test", None, "weekly", "account"),
        ("account-window", "content-analysis-weekly", None, "2026-08-05T00:00:00+08:00", "weekly", "account"),
        ("account-daily", "content-analysis-weekly", None, None, "daily", "account"),
        ("account-finalizer", "content-analysis-weekly", None, None, "weekly", "weekly_batch_finalize"),
    )
    valid_job = None
    for index, (sec_uid, tool_code, scope, start, task_code, object_type) in enumerate(variants):
        job = TaskJob(
            task_no=f"ca_s28_scope_{index}_{uuid4().hex[:6]}",
            tool_code=tool_code,
            tool_name="内容分析",
            status="success",
            input_payload=weekly_account_task_payload(
                finalize_envelope,
                sec_uid=sec_uid,
                position=1,
                scope=scope,
                task_code=task_code,
                object_type=object_type,
                window_start=start,
            ),
            result_summary=weekly_task_summary("success"),
            finished_at=datetime(2026, 9, 5, index + 1, tzinfo=SHANGHAI),
            created_by=admin_user.id,
        )
        test_session.add(job)
        await test_session.flush()
        if sec_uid == "account-valid":
            valid_job = job
    assert valid_job is not None
    await attach_weekly_account_result(
        test_session,
        valid_job,
        finalize_envelope,
        sec_uid="account-valid",
        baseline=weekly_baseline_payload(
            finalize_envelope,
            "account-valid",
            sample_count=3,
        ),
    )
    await test_session.flush()

    summary = await content_analysis.SqlContentAnalysisStore(
        test_session
    ).load_weekly_batch_finalize_summary(finalize_envelope)

    assert summary["account_count"] == 1
    assert summary["success_account_count"] == 1
    assert [item["sec_uid"] for item in summary["account_results"]] == [
        "account-valid"
    ]


@pytest.mark.asyncio
async def test_weekly_finalize_rejects_internal_result_bound_to_other_account_task(
    test_session,
    admin_user,
) -> None:
    project, _, account_envelope = await setup_envelope(
        test_session,
        admin_user,
        weekly=True,
    )
    finalize_envelope = replace(
        account_envelope,
        execution=content_analysis.WeeklyBatchFinalizeExecution(
            weekly_batch_id=account_envelope.execution.weekly_batch_id,
            batch_size=1,
            project_ids=(str(project.id),),
            finalize_version="state-v1",
        ),
    )
    source_job = TaskJob(
        task_no=f"ca_s28_result_source_{uuid4().hex[:6]}",
        tool_code="content-analysis-weekly",
        tool_name="内容分析",
        status="success",
        input_payload=weekly_account_task_payload(
            replace(
                finalize_envelope,
                execution=content_analysis.WeeklyBatchFinalizeExecution(
                    weekly_batch_id="weekly-other-batch",
                    batch_size=1,
                    project_ids=(str(project.id),),
                    finalize_version="other-state-v1",
                ),
            ),
            sec_uid="account-source",
            position=1,
        ),
        result_summary={},
        finished_at=datetime(2026, 9, 5, 3, tzinfo=SHANGHAI),
        created_by=admin_user.id,
    )
    target_job = TaskJob(
        task_no=f"ca_s28_result_target_{uuid4().hex[:6]}",
        tool_code="content-analysis-weekly",
        tool_name="内容分析",
        status="success",
        input_payload=weekly_account_task_payload(
            finalize_envelope,
            sec_uid="account-target",
            position=1,
        ),
        result_summary={},
        finished_at=datetime(2026, 9, 5, 4, tzinfo=SHANGHAI),
        created_by=admin_user.id,
    )
    test_session.add_all((source_job, target_job))
    await test_session.flush()
    source_result = await attach_weekly_account_result(
        test_session,
        source_job,
        replace(
            finalize_envelope,
            execution=content_analysis.WeeklyBatchFinalizeExecution(
                weekly_batch_id="weekly-other-batch",
                batch_size=1,
                project_ids=(str(project.id),),
                finalize_version="other-state-v1",
            ),
        ),
        sec_uid="account-source",
        baseline=weekly_baseline_payload(
            finalize_envelope,
            "account-source",
            sample_count=2,
        ),
    )
    target_job.result_summary = weekly_task_summary("success")
    target_job.result_summary["internal_result"]["internal_result_id"] = str(
        source_result.id
    )
    await test_session.flush()

    with pytest.raises(ValueError, match="内部结果.*不一致"):
        await content_analysis.SqlContentAnalysisStore(
            test_session
        ).load_weekly_batch_finalize_summary(finalize_envelope)


@pytest.mark.asyncio
async def test_weekly_finalize_rejects_malformed_saved_baseline_metrics(
    test_session,
    admin_user,
) -> None:
    project, _, account_envelope = await setup_envelope(
        test_session,
        admin_user,
        weekly=True,
    )
    finalize_envelope = replace(
        account_envelope,
        execution=content_analysis.WeeklyBatchFinalizeExecution(
            weekly_batch_id=account_envelope.execution.weekly_batch_id,
            batch_size=1,
            project_ids=(str(project.id),),
            finalize_version="state-v1",
        ),
    )
    job = TaskJob(
        task_no=f"ca_s28_bad_baseline_{uuid4().hex[:6]}",
        tool_code="content-analysis-weekly",
        tool_name="内容分析",
        status="success",
        input_payload=weekly_account_task_payload(
            finalize_envelope,
            sec_uid="account-invalid-baseline",
            position=1,
        ),
        result_summary={},
        finished_at=datetime(2026, 9, 5, 4, tzinfo=SHANGHAI),
        created_by=admin_user.id,
    )
    test_session.add(job)
    await test_session.flush()
    result = await attach_weekly_account_result(
        test_session,
        job,
        finalize_envelope,
        sec_uid="account-invalid-baseline",
        baseline=weekly_baseline_payload(
            finalize_envelope,
            "account-invalid-baseline",
            sample_count=2,
        ),
    )
    output = await test_session.get(Output, result.output_id)
    malformed = dict(output.content_json)
    malformed_baseline = dict(malformed["baseline"])
    malformed_values = dict(malformed_baseline["baseline"])
    malformed_values["sample_size"] = "2"
    malformed_baseline["baseline"] = malformed_values
    malformed["baseline"] = malformed_baseline
    output.content_json = malformed
    await test_session.flush()

    with pytest.raises(ValueError, match="五项统计"):
        await content_analysis.SqlContentAnalysisStore(
            test_session
        ).load_weekly_batch_finalize_summary(finalize_envelope)


@pytest.mark.asyncio
async def test_weekly_finalize_rejects_batch_with_pending_latest_attempt(
    test_session,
    admin_user,
) -> None:
    project, _, account_envelope = await setup_envelope(
        test_session,
        admin_user,
        weekly=True,
    )
    finalize_envelope = replace(
        account_envelope,
        execution=content_analysis.WeeklyBatchFinalizeExecution(
            weekly_batch_id=account_envelope.execution.weekly_batch_id,
            batch_size=1,
            project_ids=(str(project.id),),
            finalize_version="state-v1",
        ),
    )
    test_session.add(
        TaskJob(
            task_no=f"ca_s28_pending_finalize_{uuid4().hex[:6]}",
            tool_code="content-analysis-weekly",
            tool_name="内容分析",
            status="pending",
            input_payload=weekly_account_task_payload(
                finalize_envelope,
                sec_uid="account-pending",
                position=1,
            ),
            result_summary={},
            created_by=admin_user.id,
        )
    )
    await test_session.flush()

    with pytest.raises(ValueError, match="终态"):
        await content_analysis.SqlContentAnalysisStore(
            test_session
        ).load_weekly_batch_finalize_summary(finalize_envelope)


@pytest.mark.asyncio
async def test_weekly_finalize_persists_only_immutable_summary_and_is_idempotent(
    test_session,
    admin_user,
) -> None:
    project, finalize_task, account_envelope = await setup_envelope(
        test_session,
        admin_user,
        weekly=True,
    )
    finalize_task.tool_code = "content-analysis-weekly"
    finalize_envelope = replace(
        account_envelope,
        execution=content_analysis.WeeklyBatchFinalizeExecution(
            weekly_batch_id=account_envelope.execution.weekly_batch_id,
            batch_size=1,
            project_ids=(str(project.id),),
            finalize_version="state-v1",
        ),
        idempotency=content_analysis.IdempotencyKeys(
            f"finalize-analysis-{uuid4().hex}",
            f"finalize-result-{uuid4().hex}",
            account_envelope.idempotency.document_key,
        ),
    )
    summary = {
        "weekly_batch_id": finalize_envelope.execution.weekly_batch_id,
        "finalize_version": finalize_envelope.execution.finalize_version,
        "account_count": 1,
        "success_account_count": 0,
        "no_content_account_count": 0,
        "failed_account_count": 1,
        "pending_account_count": 0,
        "failures": [],
        "account_results": [],
        "selected_project_ids": [str(project.id)],
        "unavailable_reason": "本批次没有可计算账号",
    }
    write = content_analysis.ResultWrite(
        title="周批次收尾",
        status=content_analysis.InternalResultStatus.SUCCESS,
        payload={"batch_summary": summary},
        context_versions={},
        source_receipts={
            "task_jobs": {
                "status": "complete",
                "finalize_version": finalize_envelope.execution.finalize_version,
            }
        },
    )
    before = {
        "library": await test_session.scalar(
            select(func.count()).select_from(ContentAnalysisLibraryItem)
        ),
        "cross": await test_session.scalar(
            select(func.count()).select_from(ContentAnalysisCrossProjectOpportunity)
        ),
        "baseline": await test_session.scalar(
            select(func.count()).select_from(ContentAnalysisAccountBaseline)
        ),
    }
    store = content_analysis.SqlContentAnalysisStore(test_session)

    first = await store.persist(finalize_envelope, write, admin_user.id)
    second = await store.persist(finalize_envelope, write, admin_user.id)

    result = await test_session.get(ContentAnalysisResult, first.internal_result_id)
    assert first.created is True
    assert second.created is False
    assert second.internal_result_id == first.internal_result_id
    assert result.execution_kind == "weekly_batch_finalize"
    assert result.project_id is None
    assert result.sec_uid is None
    assert result.related_project_ids == [str(project.id)]
    assert result.source_receipts["task_jobs"]["finalize_version"] == "state-v1"
    assert await test_session.scalar(
        select(func.count()).select_from(Output).where(
            Output.task_id == finalize_task.id
        )
    ) == 1
    assert before == {
        "library": await test_session.scalar(
            select(func.count()).select_from(ContentAnalysisLibraryItem)
        ),
        "cross": await test_session.scalar(
            select(func.count()).select_from(ContentAnalysisCrossProjectOpportunity)
        ),
        "baseline": await test_session.scalar(
            select(func.count()).select_from(ContentAnalysisAccountBaseline)
        ),
    }
    with pytest.raises(ValueError, match="身份不一致"):
        await store.find_persisted_result(
            replace(
                finalize_envelope,
                execution=replace(
                    finalize_envelope.execution,
                    finalize_version="state-v2",
                ),
            )
        )
    with pytest.raises(ValueError, match="finalize_version"):
        await store.persist(
            replace(
                finalize_envelope,
                idempotency=content_analysis.IdempotencyKeys(
                    f"finalize-analysis-missing-version-{uuid4().hex}",
                    f"finalize-result-missing-version-{uuid4().hex}",
                    finalize_envelope.idempotency.document_key,
                ),
            ),
            replace(
                write,
                source_receipts={"task_jobs": {"status": "complete"}},
            ),
            admin_user.id,
        )


@pytest.mark.asyncio
async def test_weekly_document_identity_is_shared_by_finalizer_and_account_results(
    test_session,
    admin_user,
) -> None:
    project, _, account_envelope = await setup_envelope(
        test_session,
        admin_user,
        weekly=True,
    )
    finalize_envelope = replace(
        account_envelope,
        execution=content_analysis.WeeklyBatchFinalizeExecution(
            weekly_batch_id=account_envelope.execution.weekly_batch_id,
            batch_size=1,
            project_ids=(str(project.id),),
            finalize_version="state-v1",
        ),
        idempotency=content_analysis.IdempotencyKeys(
            f"finalize-analysis-{uuid4().hex}",
            f"finalize-result-{uuid4().hex}",
            account_envelope.idempotency.document_key,
        ),
    )
    store = content_analysis.SqlContentAnalysisStore(test_session)
    finalize = await store.persist(
        finalize_envelope,
        content_analysis.ResultWrite(
            title="周批次收尾",
            status=content_analysis.InternalResultStatus.SUCCESS,
            payload={
                "weekly_batch_id": finalize_envelope.execution.weekly_batch_id,
                "batch_summary": {"pending_account_count": 0},
            },
            context_versions={},
            source_receipts={
                "task_jobs": {
                    "status": "complete",
                    "finalize_version": finalize_envelope.execution.finalize_version,
                }
            },
        ),
        admin_user.id,
    )
    identity = content_analysis.DeliveryIdentity(
        account_envelope.idempotency.document_key,
        "weekly-doc",
        "https://feishu.cn/docx/weekly-doc",
    )
    await store.record_delivery(
        finalize_envelope,
        finalize.internal_result_id,
        status="success",
        identity=identity,
    )
    account = await store.persist(
        account_envelope,
        content_analysis.ResultWrite(
            title="账号周报",
            status=content_analysis.InternalResultStatus.NO_CONTENT,
            payload={"weekly_batch_id": account_envelope.execution.weekly_batch_id},
            context_versions={str(project.id): "context-v1"},
            source_receipts={"relation": "complete", "content": "complete"},
        ),
        admin_user.id,
    )

    assert await store.load_delivery_identity(account_envelope) == identity
    await store.record_delivery(
        account_envelope,
        account.internal_result_id,
        status="success",
        identity=identity,
    )


@pytest.mark.asyncio
async def test_account_retry_creates_new_finalize_result_version_with_same_document_key(
    test_session,
    admin_user,
) -> None:
    project, _, account_envelope = await setup_envelope(
        test_session,
        admin_user,
        weekly=True,
    )
    base_finalize = replace(
        account_envelope,
        execution=content_analysis.WeeklyBatchFinalizeExecution(
            weekly_batch_id=account_envelope.execution.weekly_batch_id,
            batch_size=1,
            project_ids=(str(project.id),),
            finalize_version="state-v1",
        ),
        idempotency=content_analysis.IdempotencyKeys(
            f"finalize-analysis-v1-{uuid4().hex}",
            f"finalize-result-v1-{uuid4().hex}",
            account_envelope.idempotency.document_key,
        ),
    )
    test_session.add(
        TaskJob(
            task_no=f"ca_s28_retry_before_{uuid4().hex[:6]}",
            tool_code="content-analysis-weekly",
            tool_name="内容分析",
            status="failed",
            input_payload=weekly_account_task_payload(
                base_finalize,
                sec_uid="account-retried",
                position=1,
            ),
            result_summary=weekly_task_summary("failed"),
            finished_at=datetime(2026, 9, 5, 1, tzinfo=SHANGHAI),
            created_by=admin_user.id,
        )
    )
    await test_session.commit()
    store = content_analysis.SqlContentAnalysisStore(test_session)
    first_summary = await store.load_weekly_batch_finalize_summary(base_finalize)
    first = await store.persist(
        base_finalize,
        content_analysis.ResultWrite(
            title="周批次收尾 v1",
            status=content_analysis.InternalResultStatus.SUCCESS,
            payload={
                "weekly_batch_id": base_finalize.execution.weekly_batch_id,
                "batch_summary": first_summary,
            },
            context_versions={},
            source_receipts={
                "task_jobs": {
                    "status": "complete",
                    "finalize_version": base_finalize.execution.finalize_version,
                }
            },
        ),
        admin_user.id,
    )
    retry_job = TaskJob(
        task_no=f"ca_s28_retry_after_{uuid4().hex[:6]}",
        tool_code="content-analysis-weekly",
        tool_name="内容分析",
        status="success",
        input_payload=weekly_account_task_payload(
            base_finalize,
            sec_uid="account-retried",
            position=1,
        ),
        result_summary={},
        finished_at=datetime(2026, 9, 5, 2, tzinfo=SHANGHAI),
        created_by=admin_user.id,
    )
    test_session.add(retry_job)
    await test_session.flush()
    await attach_weekly_account_result(
        test_session,
        retry_job,
        base_finalize,
        sec_uid="account-retried",
        baseline=weekly_baseline_payload(
            base_finalize,
            "account-retried",
            sample_count=2,
        ),
    )
    await test_session.commit()
    second_envelope = replace(
        base_finalize,
        task_no=f"{base_finalize.task_no}-v2",
        execution=replace(
            base_finalize.execution,
            finalize_version="state-v2",
        ),
        idempotency=content_analysis.IdempotencyKeys(
            f"finalize-analysis-v2-{uuid4().hex}",
            f"finalize-result-v2-{uuid4().hex}",
            base_finalize.idempotency.document_key,
        ),
    )
    second_summary = await store.load_weekly_batch_finalize_summary(second_envelope)
    second = await store.persist(
        second_envelope,
        content_analysis.ResultWrite(
            title="周批次收尾 v2",
            status=content_analysis.InternalResultStatus.SUCCESS,
            payload={
                "weekly_batch_id": second_envelope.execution.weekly_batch_id,
                "batch_summary": second_summary,
            },
            context_versions={},
            source_receipts={
                "task_jobs": {
                    "status": "complete",
                    "finalize_version": second_envelope.execution.finalize_version,
                }
            },
        ),
        admin_user.id,
    )

    assert first.internal_result_id != second.internal_result_id
    assert first_summary["finalize_version"] == "state-v1"
    assert second_summary["finalize_version"] == "state-v2"
    assert first_summary["failed_account_count"] == 1
    assert second_summary["success_account_count"] == 1
    assert second_summary["failed_account_count"] == 0
    assert base_finalize.idempotency.document_key == second_envelope.idempotency.document_key


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("run_type", "expected_status"),
    (
        (None, "available"),
        (content_analysis.RunType.TEST, "unannotated"),
    ),
)
async def test_manual_opening_update_is_atomic_for_formal_and_zero_write_for_test(
    test_session,
    admin_user,
    run_type,
    expected_status,
) -> None:
    project, _, envelope = await setup_envelope(
        test_session,
        admin_user,
        run_type=run_type,
    )
    reference = KolReference(
        kol_id=project.id,
        title="人工标题",
        source="人工",
        type="千川爆款文案",
        content="先说匿名问题，再给方法",
        created_by=admin_user.id,
    )
    test_session.add(reference)
    await test_session.flush()
    manual = ContentAnalysisLibraryItem(
        kol_reference_id=reference.id,
        project_id=project.id,
        platform="unknown",
        account_id=None,
        category="qianchuan",
        ingestion_source="manual",
        analysis={"opening": {"status": "unannotated"}},
        project_assessment={},
        latest_metrics={},
        confidence="unverified",
        opening_status="unannotated",
        availability="enabled",
        latest_result_id=None,
    )
    test_session.add(manual)
    await test_session.commit()
    suffix = envelope.idempotency.result_key.rsplit("-", 1)[-1]
    write = replace(
        daily_write(project.id, suffix),
        library_items=(),
        cross_project_opportunities=(),
        manual_opening_updates=(
            content_analysis.ManualOpeningWrite(
                item_id=manual.id,
                project_id=project.id,
                status="available",
                fragment="先说匿名问题",
                unavailable_reason=None,
                opening_payload={
                    "status": "available",
                    "kind": "language",
                    "fragment": "先说匿名问题",
                },
            ),
        ),
    )

    persisted = await content_analysis.SqlContentAnalysisStore(test_session).persist(
        envelope,
        write,
        admin_user.id,
    )

    await test_session.refresh(manual)
    assert manual.opening_status == expected_status
    assert manual.ingestion_source == "manual"
    if run_type is None:
        assert manual.opening_fragment == "先说匿名问题"
        assert manual.analysis["opening"]["source"] == "content_analysis"
        assert manual.latest_result_id == persisted.internal_result_id
    else:
        assert manual.opening_fragment is None
        assert manual.latest_result_id is None


@pytest.mark.asyncio
async def test_automatic_manual_opening_update_cannot_overwrite_operator_annotation(
    test_engine,
    test_session,
    admin_user,
    monkeypatch,
) -> None:
    project, _, envelope = await setup_envelope(test_session, admin_user)
    reference = KolReference(
        kol_id=project.id,
        title="人工标题",
        source="人工",
        type="千川爆款文案",
        content="先说匿名问题，再给方法",
        created_by=admin_user.id,
    )
    test_session.add(reference)
    await test_session.flush()
    manual = ContentAnalysisLibraryItem(
        kol_reference_id=reference.id,
        project_id=project.id,
        platform="unknown",
        account_id=None,
        category="qianchuan",
        ingestion_source="manual",
        analysis={"opening": {"status": "unannotated"}},
        project_assessment={},
        latest_metrics={},
        confidence="unverified",
        opening_status="unannotated",
        availability="enabled",
        latest_result_id=None,
    )
    test_session.add(manual)
    await test_session.commit()
    item_id = manual.id
    suffix = envelope.idempotency.result_key.rsplit("-", 1)[-1]
    automatic_write = replace(
        daily_write(project.id, suffix),
        library_items=(),
        cross_project_opportunities=(),
        manual_opening_updates=(
            content_analysis.ManualOpeningWrite(
                item_id=item_id,
                project_id=project.id,
                status="available",
                fragment="先说匿名问题",
                unavailable_reason=None,
                opening_payload={
                    "status": "available",
                    "kind": "language",
                    "fragment": "先说匿名问题",
                },
            ),
        ),
    )
    factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    automatic_loaded = asyncio.Event()
    manual_committed = asyncio.Event()
    original_apply = content_analysis.SqlContentAnalysisStore._apply_manual_opening

    async def delayed_apply(store, opening, result_id):
        await original_apply(store, opening, result_id)
        automatic_loaded.set()
        try:
            await asyncio.wait_for(manual_committed.wait(), timeout=0.15)
        except asyncio.TimeoutError:
            pass

    monkeypatch.setattr(
        content_analysis.SqlContentAnalysisStore,
        "_apply_manual_opening",
        delayed_apply,
    )

    async def automatic_annotation():
        async with factory() as session:
            await content_analysis.SqlContentAnalysisStore(session).persist(
                envelope,
                automatic_write,
                admin_user.id,
            )

    async def operator_annotation():
        await automatic_loaded.wait()
        async with factory() as session:
            response = await annotate_library_opening(
                item_id,
                ManualOpeningUpdate(
                    project_id=project.id,
                    status="available",
                    fragment="再给方法",
                ),
                Request(
                    {
                        "type": "http",
                        "method": "PATCH",
                        "path": "/",
                        "headers": [],
                    }
                ),
                db=session,
                user=admin_user,
            )
            assert response.success is True
        manual_committed.set()

    await asyncio.gather(automatic_annotation(), operator_annotation())

    test_session.expire_all()
    refreshed = await test_session.get(ContentAnalysisLibraryItem, item_id)
    assert refreshed.ingestion_source == "manual"
    assert refreshed.opening_fragment == "再给方法"
    assert refreshed.analysis["opening"]["source"] == "manual"
