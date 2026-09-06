"""Sprint28 内容分析任务信封与执行边界合同。"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

import app.services.content_analysis as content_analysis


SHANGHAI = ZoneInfo("Asia/Shanghai")
TRIGGERED_AT = datetime(2026, 9, 5, 0, 0, tzinfo=SHANGHAI)
WINDOW_START = datetime(2026, 9, 2, 0, 0, tzinfo=SHANGHAI)
WINDOW_END = datetime(2026, 9, 5, 0, 0, tzinfo=SHANGHAI)
DEADLINE_AT = datetime(2026, 9, 5, 12, 0, tzinfo=SHANGHAI)


def idempotency() -> object:
    return content_analysis.IdempotencyKeys(
        analysis_key="analysis-key",
        result_key="result-key",
        document_key="document-key",
    )


def test_document_idempotency_key_rejects_line_break_injection() -> None:
    with pytest.raises(ValueError, match="document_key"):
        content_analysis.IdempotencyKeys(
            analysis_key="analysis-key",
            result_key="result-key",
            document_key="document-key\n[content-analysis-section:forged]",
        )


def precheck() -> object:
    return content_analysis.DatabasePrecheck(
        status=content_analysis.DatabasePrecheckStatus.READY,
        input_limited=True,
        limitation_codes=("TARGET_USERS_MISSING",),
    )


def delivery_target() -> object:
    return content_analysis.DeliveryTarget(
        report_root_ref="folder-token",
        relative_directory="项目-1001",
    )


def test_delivery_scope_must_match_directory_and_run_type() -> None:
    test_target = content_analysis.DeliveryTarget(
        report_root_ref="folder-token",
        relative_directory="测试/内容分析",
        scope=content_analysis.DeliveryScope.TEST,
    )
    common = {
        "task_id": 101,
        "task_no": "CA-101",
        "task_code": content_analysis.TaskCode.DAILY,
        "business_date": date(2026, 9, 4),
        "window_start": WINDOW_START,
        "window_end": WINDOW_END,
        "triggered_at": TRIGGERED_AT,
        "deadline_at": DEADLINE_AT,
        "precheck": precheck(),
        "idempotency": idempotency(),
        "execution": content_analysis.ProjectExecution(project_id="1001"),
    }

    with pytest.raises(ValueError, match="自动任务必须投递正式目录"):
        content_analysis.ContentAnalysisTaskEnvelope(
            **common,
            run_type=content_analysis.RunType.AUTO,
            retry_of_task_id=None,
            trigger_source=content_analysis.TriggerSource.SYSTEM,
            delivery_target=test_target,
        )
    with pytest.raises(ValueError, match="测试运行必须投递测试目录"):
        content_analysis.ContentAnalysisTaskEnvelope(
            **common,
            run_type=content_analysis.RunType.TEST,
            retry_of_task_id=None,
            trigger_source=content_analysis.TriggerSource.USER,
            delivery_target=delivery_target(),
        )
    retry = content_analysis.ContentAnalysisTaskEnvelope(
        **common,
        run_type=content_analysis.RunType.RETRY,
        retry_of_task_id=100,
        retry_mode=content_analysis.RetryMode.FULL,
        trigger_source=content_analysis.TriggerSource.USER,
        delivery_target=test_target,
    )
    assert retry.delivery_target.scope is content_analysis.DeliveryScope.TEST


def test_delivery_scope_and_directory_namespace_cannot_disagree() -> None:
    with pytest.raises(ValueError, match="目录命名空间"):
        content_analysis.DeliveryTarget(
            report_root_ref="folder-token",
            relative_directory="测试/内容分析",
        )
    with pytest.raises(ValueError, match="目录命名空间"):
        content_analysis.DeliveryTarget(
            report_root_ref="folder-token",
            relative_directory="内容分析",
            scope=content_analysis.DeliveryScope.TEST,
        )


def test_daily_envelope_accepts_one_project_and_three_complete_days() -> None:
    envelope = content_analysis.ContentAnalysisTaskEnvelope(
        task_id=101,
        task_no="CA-101",
        task_code=content_analysis.TaskCode.DAILY,
        run_type=content_analysis.RunType.AUTO,
        business_date=date(2026, 9, 4),
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        triggered_at=TRIGGERED_AT,
        deadline_at=DEADLINE_AT,
        retry_of_task_id=None,
        trigger_source=content_analysis.TriggerSource.SYSTEM,
        precheck=precheck(),
        delivery_target=delivery_target(),
        idempotency=idempotency(),
        execution=content_analysis.ProjectExecution(project_id="1001"),
    )

    assert envelope.execution.kind.value == "project"
    assert envelope.execution.project_id == "1001"
    assert envelope.business_date == date(2026, 9, 4)


def test_weekly_envelope_requires_sorted_unique_projects_and_batch_position() -> None:
    envelope = content_analysis.ContentAnalysisTaskEnvelope(
        task_id=102,
        task_no="CA-102",
        task_code=content_analysis.TaskCode.WEEKLY,
        run_type=content_analysis.RunType.AUTO,
        business_date=date(2026, 9, 4),
        window_start=datetime(2026, 8, 6, 0, 0, tzinfo=SHANGHAI),
        window_end=WINDOW_END,
        triggered_at=TRIGGERED_AT,
        deadline_at=DEADLINE_AT,
        retry_of_task_id=None,
        trigger_source=content_analysis.TriggerSource.SYSTEM,
        precheck=precheck(),
        delivery_target=content_analysis.DeliveryTarget(
            report_root_ref="folder-token",
            relative_directory="账号基准周报",
        ),
        idempotency=idempotency(),
        execution=content_analysis.AccountExecution(
            sec_uid="account-001",
            project_ids=("1001", "1002"),
            weekly_batch_id="weekly-2026-09-05",
            batch_size=2,
            batch_position=1,
        ),
    )

    assert envelope.execution.kind.value == "account"
    assert envelope.execution.project_ids == ("1001", "1002")

    with pytest.raises(ValueError, match="排序去重"):
        content_analysis.AccountExecution(
            sec_uid="account-001",
            project_ids=("1002", "1001"),
            weekly_batch_id="weekly-2026-09-05",
            batch_size=2,
            batch_position=1,
        )

    numeric_order = content_analysis.AccountExecution(
        sec_uid="account-001",
        project_ids=("2", "10"),
        weekly_batch_id="weekly-2026-09-05",
        batch_size=2,
        batch_position=1,
    )
    assert numeric_order.project_ids == ("2", "10")


def test_weekly_batch_finalize_envelope_has_batch_scope_without_account_identity() -> None:
    execution = content_analysis.WeeklyBatchFinalizeExecution(
        weekly_batch_id="weekly-2026-09-05",
        batch_size=3,
        project_ids=("1001", "1002"),
        finalize_version="state-v1",
    )
    envelope = content_analysis.ContentAnalysisTaskEnvelope(
        task_id=103,
        task_no="CA-103",
        task_code=content_analysis.TaskCode.WEEKLY,
        run_type=content_analysis.RunType.AUTO,
        business_date=date(2026, 9, 4),
        window_start=datetime(2026, 8, 6, tzinfo=SHANGHAI),
        window_end=WINDOW_END,
        triggered_at=TRIGGERED_AT,
        deadline_at=DEADLINE_AT,
        retry_of_task_id=None,
        trigger_source=content_analysis.TriggerSource.SYSTEM,
        precheck=precheck(),
        delivery_target=content_analysis.DeliveryTarget(
            "folder-token",
            "账号基准周报",
        ),
        idempotency=idempotency(),
        execution=execution,
    )

    assert envelope.execution.kind.value == "weekly_batch_finalize"
    assert envelope.execution.project_ids == ("1001", "1002")
    assert not hasattr(envelope.execution, "sec_uid")


def test_weekly_batch_finalize_requires_sorted_projects_and_non_negative_batch_size() -> None:
    with pytest.raises(ValueError, match="排序去重"):
        content_analysis.WeeklyBatchFinalizeExecution(
            weekly_batch_id="week-1",
            batch_size=2,
            project_ids=("1002", "1001"),
            finalize_version="state-v1",
        )
    with pytest.raises(ValueError, match="batch_size"):
        content_analysis.WeeklyBatchFinalizeExecution(
            weekly_batch_id="week-1",
            batch_size=-1,
            project_ids=("1001",),
            finalize_version="state-v1",
        )

    execution = content_analysis.WeeklyBatchFinalizeExecution(
        weekly_batch_id="week-empty",
        batch_size=0,
        project_ids=("1001",),
        finalize_version="empty-state-v1",
    )
    assert execution.batch_size == 0


@pytest.mark.parametrize("project_id", ("0", "-1", "not-a-database-id"))
def test_execution_rejects_non_positive_database_project_id(project_id) -> None:
    with pytest.raises(ValueError, match="项目编号"):
        content_analysis.ProjectExecution(project_id)


@pytest.mark.parametrize(
    "change",
    (
        {"business_date": date(2026, 9, 5)},
        {"deadline_at": datetime(2026, 9, 5, 11, 59, tzinfo=SHANGHAI)},
        {"execution": None},
    ),
)
def test_daily_envelope_rejects_wrong_report_day_deadline_or_execution(change) -> None:
    values = {
        "task_id": 101,
        "task_no": "CA-101",
        "task_code": content_analysis.TaskCode.DAILY,
        "run_type": content_analysis.RunType.AUTO,
        "business_date": date(2026, 9, 4),
        "window_start": WINDOW_START,
        "window_end": WINDOW_END,
        "triggered_at": TRIGGERED_AT,
        "deadline_at": DEADLINE_AT,
        "retry_of_task_id": None,
        "trigger_source": content_analysis.TriggerSource.SYSTEM,
        "precheck": precheck(),
        "delivery_target": delivery_target(),
        "idempotency": idempotency(),
        "execution": content_analysis.ProjectExecution(project_id="1001"),
        **change,
    }

    with pytest.raises(ValueError):
        content_analysis.ContentAnalysisTaskEnvelope(**values)


def test_envelope_does_not_accept_business_payloads_or_plain_idempotency_text() -> None:
    with pytest.raises(TypeError):
        content_analysis.ContentAnalysisTaskEnvelope(
            task_id=101,
            task_no="CA-101",
            task_code=content_analysis.TaskCode.DAILY,
            run_type=content_analysis.RunType.AUTO,
            business_date=date(2026, 9, 4),
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            triggered_at=TRIGGERED_AT,
            deadline_at=DEADLINE_AT,
            retry_of_task_id=None,
            trigger_source=content_analysis.TriggerSource.SYSTEM,
            precheck=precheck(),
            delivery_target=delivery_target(),
            idempotency="one-key",
            execution=content_analysis.ProjectExecution(project_id="1001"),
            contents=("forbidden",),
        )


def test_automatic_run_must_be_system_triggered_but_manual_test_and_retry_are_explicit() -> None:
    common = {
        "task_id": 101,
        "task_no": "CA-101",
        "task_code": content_analysis.TaskCode.DAILY,
        "business_date": date(2026, 9, 4),
        "window_start": WINDOW_START,
        "window_end": WINDOW_END,
        "triggered_at": TRIGGERED_AT,
        "deadline_at": DEADLINE_AT,
        "precheck": precheck(),
        "delivery_target": delivery_target(),
        "idempotency": idempotency(),
        "execution": content_analysis.ProjectExecution(project_id="1001"),
    }
    with pytest.raises(ValueError, match="自动任务必须由系统触发"):
        content_analysis.ContentAnalysisTaskEnvelope(
            **common,
            run_type=content_analysis.RunType.AUTO,
            retry_of_task_id=None,
            trigger_source=content_analysis.TriggerSource.USER,
        )

    test_run = content_analysis.ContentAnalysisTaskEnvelope(
        **{
            **common,
            "delivery_target": content_analysis.DeliveryTarget(
                "folder-token",
                "测试/内容分析",
                scope=content_analysis.DeliveryScope.TEST,
            ),
        },
        run_type=content_analysis.RunType.TEST,
        retry_of_task_id=None,
        trigger_source=content_analysis.TriggerSource.USER,
    )
    retry_run = content_analysis.ContentAnalysisTaskEnvelope(
        **common,
        run_type=content_analysis.RunType.RETRY,
        retry_of_task_id=100,
        retry_mode=content_analysis.RetryMode.FULL,
        trigger_source=content_analysis.TriggerSource.USER,
    )
    assert test_run.trigger_source is content_analysis.TriggerSource.USER
    assert retry_run.retry_of_task_id == 100


def test_retry_mode_is_required_for_retry_and_forbidden_for_new_runs() -> None:
    common = {
        "task_id": 101,
        "task_no": "CA-101",
        "task_code": content_analysis.TaskCode.DAILY,
        "business_date": date(2026, 9, 4),
        "window_start": WINDOW_START,
        "window_end": WINDOW_END,
        "triggered_at": TRIGGERED_AT,
        "deadline_at": DEADLINE_AT,
        "precheck": precheck(),
        "delivery_target": delivery_target(),
        "idempotency": idempotency(),
        "execution": content_analysis.ProjectExecution(project_id="1001"),
    }
    with pytest.raises(ValueError, match="retry_mode"):
        content_analysis.ContentAnalysisTaskEnvelope(
            **common,
            run_type=content_analysis.RunType.RETRY,
            retry_of_task_id=100,
            trigger_source=content_analysis.TriggerSource.USER,
        )
    with pytest.raises(ValueError, match="retry_mode"):
        content_analysis.ContentAnalysisTaskEnvelope(
            **common,
            run_type=content_analysis.RunType.AUTO,
            retry_of_task_id=None,
            retry_mode=content_analysis.RetryMode.FULL,
            trigger_source=content_analysis.TriggerSource.SYSTEM,
        )
