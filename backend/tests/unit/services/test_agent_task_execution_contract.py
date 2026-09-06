"""内容分析任务信封 2.0 与四层结果映射合同测试。"""
import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from app.services.agent_task_execution_contract import (
    build_task_envelope,
    get_registered_content_analysis_executor,
    map_execution_result,
    register_content_analysis_executor,
)
from app.services.agent_task_execution_service import make_idempotency_keys
from app.services.agent_task_execution_service import (
    _execution_failure_result,
    _is_delivery_only_retry,
    _normalize_redelivery_result,
)
from app.services.content_analysis.runtime_factory import _runtime_unavailable_result


SHANGHAI = timezone(timedelta(hours=8))


@pytest.mark.parametrize(
    ("task_code", "execution"),
    [
        ("daily", {"object_type": "project", "project_id": 17}),
        ("weekly", {"object_type": "account", "account_key": "sec-17", "project_ids": [17]}),
    ],
)
def test_test_idempotency_keys_are_stable_and_isolated_from_formal_runs(task_code, execution):
    common = {
        "task_code": task_code,
        "business_date": "2026-09-04",
        "execution": execution,
    }

    formal = make_idempotency_keys(**common, run_type="auto")
    first_test = make_idempotency_keys(
        **common, run_type="test", request_id="  test-request-1  ",
    )
    repeated_test = make_idempotency_keys(
        **common, run_type="test", request_id="test-request-1",
    )
    other_test = make_idempotency_keys(
        **common, run_type="test", request_id="test-request-2",
    )

    segment = (
        f"project:{execution['project_id']}"
        if execution["object_type"] == "project"
        else f"account:{hashlib.sha256(execution['account_key'].encode('utf-8')).hexdigest()[:16]}"
    )
    logical_key = f"content-analysis:{task_code}:2026-09-04:{segment}"
    assert formal == {
        "run_key": f"content-analysis:{task_code}:auto:2026-09-04:{segment}",
        "internal_result_key": logical_key,
        "document_key": logical_key,
    }
    assert first_test == repeated_test
    assert "test-request-1" in first_test["internal_result_key"]
    assert "test-request-1" in first_test["document_key"]
    assert all(first_test[key] != formal[key] for key in first_test)
    assert all(first_test[key] != other_test[key] for key in first_test)


def test_daily_envelope_uses_just_ended_day_and_right_exclusive_three_day_window():
    triggered_at = datetime(2026, 9, 5, 0, 0, tzinfo=SHANGHAI)

    envelope = build_task_envelope(
        task_id=41,
        task_no="CA-daily-41",
        task_code="daily",
        run_type="auto",
        triggered_at=triggered_at,
        execution={"object_type": "project", "project_id": 17},
        database_precheck={
            "status": "ready",
            "reason_code": None,
            "input_limited": False,
            "input_limited_reasons": [],
        },
        report_root_ref="folder-ref",
        run_key="content-analysis:daily:auto:2026-09-04:project:17",
        internal_result_key="content-analysis:daily:2026-09-04:project:17",
        document_key="content-analysis:daily:2026-09-04:project:17",
    )

    assert envelope == {
        "contract_version": "2.0",
        "task_identity": {
            "task_id": 41,
            "task_no": "CA-daily-41",
            "agent_code": "content-analysis",
        },
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
        "retry": {
            "retry_of_task_id": None,
            "mode": None,
            "request_id": None,
        },
        "database_precheck": {
            "status": "ready",
            "reason_code": None,
            "input_limited": False,
            "input_limited_reasons": [],
        },
        "delivery_target": {
            "report_root_ref": "folder-ref",
            "scope": "formal",
            "test_subdirectory": None,
        },
        "execution": {"object_type": "project", "project_id": 17},
        "idempotency": {
            "run_key": "content-analysis:daily:auto:2026-09-04:project:17",
            "internal_result_key": "content-analysis:daily:2026-09-04:project:17",
            "document_key": "content-analysis:daily:2026-09-04:project:17",
        },
    }


def test_daily_test_envelope_normalizes_utc_trigger_and_derived_deadline_to_shanghai():
    envelope = build_task_envelope(
        task_id=42,
        task_no="CA-daily-test-42",
        task_code="daily",
        run_type="test",
        triggered_at=datetime(2026, 9, 5, 2, 30, tzinfo=timezone.utc),
        execution={"object_type": "project", "project_id": 17},
        database_precheck={
            "status": "ready",
            "reason_code": None,
            "input_limited": False,
            "input_limited_reasons": [],
        },
        report_root_ref="folder-ref",
        run_key="daily-test-request",
        internal_result_key="daily-test-request:internal",
        document_key="daily-test-request:document",
        request_id="daily-test-request",
    )

    assert envelope["triggered_at"] == "2026-09-05T10:30:00+08:00"
    assert envelope["deadline_at"] == "2026-09-05T22:30:00+08:00"
    assert envelope["business_date"] == "2026-09-04"
    assert envelope["analysis_window"] == {
        "start": "2026-09-02T00:00:00+08:00",
        "end": "2026-09-05T00:00:00+08:00",
        "timezone": "Asia/Shanghai",
        "end_exclusive": True,
    }


def test_weekly_manual_retry_envelope_normalizes_utc_trigger_and_deadline_to_shanghai():
    envelope = build_task_envelope(
        task_id=53,
        task_no="CA-weekly-retry-53",
        task_code="weekly",
        run_type="manual_retry",
        triggered_at=datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc),
        execution={
            "object_type": "account",
            "account_key": "sec-17",
            "project_ids": [17, 9],
            "weekly_batch_id": "weekly-2026-09-06",
            "batch_size": 1,
            "batch_position": 1,
        },
        database_precheck={
            "status": "ready",
            "reason_code": None,
            "input_limited": False,
            "input_limited_reasons": [],
        },
        report_root_ref="folder-ref",
        run_key="weekly-retry-request",
        internal_result_key="weekly-original:internal",
        document_key="weekly-original:document",
        retry_of_task_id=52,
        retry_mode="full",
        request_id="weekly-retry-request",
        business_date="2026-09-06",
        analysis_window={
            "start": "2026-08-08T00:00:00+08:00",
            "end": "2026-09-07T00:00:00+08:00",
            "timezone": "Asia/Shanghai",
            "end_exclusive": True,
        },
    )

    assert envelope["triggered_at"] == "2026-09-08T09:00:00+08:00"
    assert envelope["deadline_at"] == "2026-09-08T21:00:00+08:00"
    assert envelope["business_date"] == "2026-09-06"
    assert envelope["retry"] == {
        "retry_of_task_id": 52,
        "mode": "full",
        "request_id": "weekly-retry-request",
    }


def test_envelope_normalizes_explicit_utc_deadline_to_shanghai():
    envelope = build_task_envelope(
        task_id=54,
        task_no="CA-daily-explicit-deadline-54",
        task_code="daily",
        run_type="auto",
        triggered_at=datetime(2026, 9, 5, 16, 0, tzinfo=timezone.utc),
        deadline_at=datetime(2026, 9, 6, 4, 0, tzinfo=timezone.utc),
        execution={"object_type": "project", "project_id": 17},
        database_precheck={
            "status": "ready",
            "reason_code": None,
            "input_limited": False,
            "input_limited_reasons": [],
        },
        report_root_ref="folder-ref",
        run_key="daily-explicit-deadline",
        internal_result_key="daily-explicit-deadline:internal",
        document_key="daily-explicit-deadline:document",
    )

    assert envelope["triggered_at"] == "2026-09-06T00:00:00+08:00"
    assert envelope["deadline_at"] == "2026-09-06T12:00:00+08:00"


def test_weekly_envelope_has_shared_batch_document_and_sorted_unique_projects():
    envelope = build_task_envelope(
        task_id=52,
        task_no="CA-weekly-52",
        task_code="weekly",
        run_type="test",
        triggered_at=datetime(2026, 9, 7, 1, 0, tzinfo=SHANGHAI),
        execution={
            "object_type": "account",
            "account_key": " sec-B ",
            "project_ids": [9, 3, 9],
            "weekly_batch_id": "weekly-2026-09-06",
            "batch_size": 3,
            "batch_position": 2,
        },
        database_precheck={
            "status": "ready",
            "reason_code": None,
            "input_limited": True,
            "input_limited_reasons": ["STYLE_NOTES_MISSING"],
        },
        report_root_ref=None,
        run_key="test-request-52",
        internal_result_key="test-request-52:internal",
        document_key="content-analysis:weekly:2026-09-06",
        request_id="request-52",
    )

    assert envelope["business_date"] == "2026-09-06"
    assert envelope["analysis_window"] == {
        "start": "2026-08-08T00:00:00+08:00",
        "end": "2026-09-07T00:00:00+08:00",
        "timezone": "Asia/Shanghai",
        "end_exclusive": True,
    }
    assert envelope["execution"] == {
        "object_type": "account",
        "account_key": "sec-B",
        "project_ids": [3, 9],
        "weekly_batch_id": "weekly-2026-09-06",
        "batch_size": 3,
        "batch_position": 2,
    }
    assert envelope["delivery_target"] == {
        "report_root_ref": None,
        "scope": "test",
        "test_subdirectory": "测试报告",
    }
    assert envelope["idempotency"]["document_key"] == "content-analysis:weekly:2026-09-06"


def test_weekly_batch_finalize_envelope_contains_only_batch_scope_and_control_fields():
    envelope = build_task_envelope(
        task_id=53,
        task_no="CA-weekly-finalize-53",
        task_code="weekly",
        run_type="auto",
        triggered_at=datetime(2026, 9, 7, 2, 0, tzinfo=SHANGHAI),
        execution={
            "object_type": "weekly_batch_finalize",
            "weekly_batch_id": "content-analysis:weekly:2026-09-06",
            "batch_size": 3,
            "project_ids": [9, 3, 9],
            "finalize_version": "state-abc",
        },
        database_precheck={"status": "ready", "reason_code": None},
        report_root_ref="folder-ref",
        run_key="finalize-run-state-abc",
        internal_result_key="finalize-internal-state-abc",
        document_key="content-analysis:weekly:2026-09-06",
        business_date="2026-09-06",
        analysis_window={
            "start": "2026-08-08T00:00:00+08:00",
            "end": "2026-09-07T00:00:00+08:00",
            "timezone": "Asia/Shanghai",
            "end_exclusive": True,
        },
    )

    assert envelope["execution"] == {
        "object_type": "weekly_batch_finalize",
        "weekly_batch_id": "content-analysis:weekly:2026-09-06",
        "batch_size": 3,
        "project_ids": [3, 9],
        "finalize_version": "state-abc",
    }
    assert "account_key" not in str(envelope["execution"])
    assert "content" not in envelope["execution"]
    assert envelope["idempotency"] == {
        "run_key": "finalize-run-state-abc",
        "internal_result_key": "finalize-internal-state-abc",
        "document_key": "content-analysis:weekly:2026-09-06",
    }


def test_weekly_batch_finalize_allows_zero_accounts_for_nonempty_selected_project_scope():
    envelope = build_task_envelope(
        task_id=54,
        task_no="CA-weekly-finalize-empty-54",
        task_code="weekly",
        run_type="auto",
        triggered_at=datetime(2026, 9, 7, 1, 0, tzinfo=SHANGHAI),
        execution={
            "object_type": "weekly_batch_finalize",
            "weekly_batch_id": "content-analysis:weekly:2026-09-06",
            "batch_size": 0,
            "project_ids": [9, 3, 9],
            "finalize_version": "empty-state-abc",
        },
        database_precheck={"status": "ready", "reason_code": None},
        report_root_ref="folder-ref",
        run_key="finalize-run-empty-state-abc",
        internal_result_key="finalize-internal-empty-state-abc",
        document_key="content-analysis:weekly:2026-09-06",
        business_date="2026-09-06",
    )

    assert envelope["execution"]["batch_size"] == 0
    assert envelope["execution"]["project_ids"] == [3, 9]


def test_weekly_batch_finalize_rejects_empty_selected_project_scope():
    with pytest.raises(ValueError, match="project_ids must be a nonempty integer list"):
        build_task_envelope(
            task_id=55,
            task_no="CA-weekly-finalize-no-project-55",
            task_code="weekly",
            run_type="auto",
            triggered_at=datetime(2026, 9, 7, 1, 0, tzinfo=SHANGHAI),
            execution={
                "object_type": "weekly_batch_finalize",
                "weekly_batch_id": "content-analysis:weekly:2026-09-06",
                "batch_size": 0,
                "project_ids": [],
                "finalize_version": "empty-state-no-project",
            },
            database_precheck={"status": "ready", "reason_code": None},
            report_root_ref="folder-ref",
            run_key="finalize-run-empty-state-no-project",
            internal_result_key="finalize-internal-empty-state-no-project",
            document_key="content-analysis:weekly:2026-09-06",
            business_date="2026-09-06",
        )


def test_weekly_batch_finalize_result_skips_input_relation_but_can_complete_delivery():
    status, summary = map_execution_result(
        database_precheck={"status": "ready", "reason_code": None},
        executor_result={
            "feishu_relation": {"status": "skipped"},
            "internal_result": {
                "status": "success",
                "outcome": "content",
                "internal_result_id": "weekly-summary-v1",
            },
            "delivery": {
                "status": "success",
                "delivery_identity": "weekly-document",
                "document_url": "https://example.invalid/weekly-document",
            },
        },
        execution_object_type="weekly_batch_finalize",
    )

    assert status == "success"
    assert summary["feishu_relation"] == {"status": "skipped"}


@pytest.mark.parametrize(
    ("executor_result", "expected_status", "expected_stage", "expected_layers"),
    [
        (
            {
                "feishu_relation": {"status": "missing", "reason_code": "FEISHU_RELATION_MISSING"},
                "internal_result": {"status": "skipped"},
                "delivery": {"status": "skipped"},
            },
            "not_run",
            None,
            ("ready", "missing", "skipped", "skipped"),
        ),
        (
            {
                "feishu_relation": {"status": "failed", "reason_code": "FEISHU_RELATION_READ_FAILED"},
                "internal_result": {"status": "skipped"},
                "delivery": {"status": "skipped"},
            },
            "failed",
            "data_source",
            ("ready", "failed", "skipped", "skipped"),
        ),
        (
            {
                "feishu_relation": {"status": "ready", "content_read_status": "ready"},
                "internal_result": {
                    "status": "success",
                    "outcome": "no_content",
                    "internal_result_id": "result-empty-1",
                },
                "delivery": {
                    "status": "success",
                    "delivery_identity": "doc-empty-1",
                    "document_url": "https://example.invalid/doc-empty-1",
                },
            },
            "success",
            None,
            ("ready", "ready", "success", "success"),
        ),
        (
            {
                "feishu_relation": {"status": "ready", "content_read_status": "ready"},
                "internal_result": {
                    "status": "success",
                    "outcome": "content",
                    "internal_result_id": "result-1",
                },
                "delivery": {
                    "status": "failed",
                    "reason_code": "DELIVERY_FAILED",
                    "delivery_identity": "doc-1",
                },
            },
            "failed",
            "delivery",
            ("ready", "ready", "success", "failed"),
        ),
        (
            {
                "feishu_relation": {"status": "ready", "content_read_status": "ready"},
                "internal_result": {"status": "failed", "reason_code": "ANALYSIS_FAILED"},
                "delivery": {"status": "skipped"},
            },
            "failed",
            "analysis",
            ("ready", "ready", "failed", "skipped"),
        ),
    ],
)
def test_four_layer_mapping_is_exact(executor_result, expected_status, expected_stage, expected_layers):
    status, summary = map_execution_result(
        database_precheck={"status": "ready", "reason_code": None},
        executor_result=executor_result,
    )

    assert status == expected_status
    assert summary["failure_stage"] == expected_stage
    assert (
        summary["database_precheck"]["status"],
        summary["feishu_relation"]["status"],
        summary["internal_result"]["status"],
        summary["delivery"]["status"],
    ) == expected_layers


def test_database_precheck_missing_skips_remaining_layers_without_executor_result():
    status, summary = map_execution_result(
        database_precheck={
            "status": "missing",
            "reason_code": "CONTENT_BENCHMARK_SEC_UID_MISSING",
        },
        executor_result=None,
    )

    assert status == "not_run"
    assert summary == {
        "failure_stage": None,
        "database_precheck": {
            "status": "missing",
            "reason_code": "CONTENT_BENCHMARK_SEC_UID_MISSING",
        },
        "feishu_relation": {"status": "skipped"},
        "internal_result": {"status": "skipped"},
        "delivery": {"status": "skipped"},
    }


def test_runtime_unavailable_before_input_preserves_skipped_relation_and_reason():
    executor_result = _runtime_unavailable_result({"private_secret": "must-not-leak"})

    status, summary = map_execution_result(
        database_precheck={"status": "ready", "reason_code": None},
        executor_result=executor_result,
    )

    assert status == "failed"
    assert summary["failure_stage"] == "internal_result"
    assert summary["feishu_relation"] == {"status": "skipped"}
    assert summary["internal_result"] == {
        "status": "failed",
        "reason_code": "EXECUTOR_RUNTIME_UNAVAILABLE",
    }
    assert summary["delivery"] == {"status": "skipped"}
    assert "private_secret" not in str(summary)


def test_unhandled_executor_failure_does_not_fabricate_completed_input_read():
    result = _execution_failure_result("project")

    assert result["feishu_relation"] == {"status": "skipped"}
    assert result["internal_result"] == {
        "status": "failed",
        "reason_code": "EXECUTOR_ERROR",
    }
    assert result["delivery"] == {"status": "skipped"}


def test_redelivery_runtime_failure_is_not_rewritten_as_ready_or_internal_success():
    executor_result = _runtime_unavailable_result({}, delivery_only=True)

    normalized = _normalize_redelivery_result(
        executor_result,
        ("immutable-result-1", "immutable-delivery-1", "content"),
    )
    status, summary = map_execution_result(
        database_precheck={"status": "ready", "reason_code": None},
        executor_result=normalized,
        redelivery_context_confirmed=True,
    )

    assert normalized["feishu_relation"] == {"status": "skipped"}
    assert status == "failed"
    assert summary["failure_stage"] == "delivery"
    assert summary["feishu_relation"] == {"status": "skipped"}
    assert summary["internal_result"] == {
        "status": "skipped",
        "outcome": "content",
        "internal_result_id": "immutable-result-1",
    }
    assert summary["delivery"] == {
        "status": "failed",
        "reason_code": "EXECUTOR_RUNTIME_UNAVAILABLE",
        "delivery_identity": "immutable-delivery-1",
    }


def test_redelivery_timeout_preserves_stage_and_immutable_context():
    normalized = _normalize_redelivery_result(
        {
            "failure_stage": "timeout",
            "feishu_relation": {"status": "skipped"},
            "internal_result": {
                "status": "success",
                "outcome": "content",
                "internal_result_id": "immutable-result-1",
            },
            "delivery": {
                "status": "failed",
                "reason_code": "DEADLINE_EXCEEDED",
                "delivery_identity": "adapter-delivery",
            },
        },
        ("immutable-result-1", "immutable-delivery-1", "content"),
    )

    status, summary = map_execution_result(
        database_precheck={"status": "ready", "reason_code": None},
        executor_result=normalized,
        redelivery_context_confirmed=True,
    )

    assert status == "failed"
    assert summary["failure_stage"] == "timeout"
    assert summary["internal_result"] == {
        "status": "skipped",
        "outcome": "content",
        "internal_result_id": "immutable-result-1",
    }
    assert summary["delivery"] == {
        "status": "failed",
        "reason_code": "DEADLINE_EXCEEDED",
        "delivery_identity": "immutable-delivery-1",
    }


def test_redelivery_failure_discards_unknown_executor_fields_without_losing_context():
    normalized = _normalize_redelivery_result(
        {
            "failure_stage": "delivery",
            "feishu_relation": {"status": "skipped"},
            "internal_result": {"status": "skipped"},
            "delivery": {
                "status": "failed",
                "reason_code": "DELIVERY_FAILED",
                "debug_detail": "must-not-cross-contract",
            },
        },
        ("immutable-result-1", "immutable-delivery-1", "content"),
    )

    status, summary = map_execution_result(
        database_precheck={"status": "ready", "reason_code": None},
        executor_result=normalized,
        redelivery_context_confirmed=True,
    )

    assert status == "failed"
    assert summary["failure_stage"] == "delivery"
    assert summary["internal_result"]["internal_result_id"] == "immutable-result-1"
    assert summary["delivery"] == {
        "status": "failed",
        "reason_code": "DELIVERY_FAILED",
        "delivery_identity": "immutable-delivery-1",
    }


@pytest.mark.parametrize("execution_object_type", ["project", "account"])
def test_non_finalize_execution_cannot_succeed_when_input_was_skipped(
    execution_object_type,
):
    status, summary = map_execution_result(
        database_precheck={"status": "ready"},
        executor_result={
            "feishu_relation": {"status": "skipped"},
            "internal_result": {
                "status": "success",
                "outcome": "content",
                "internal_result_id": "unverified-result",
            },
            "delivery": {
                "status": "success",
                "delivery_identity": "unverified-delivery",
            },
        },
        execution_object_type=execution_object_type,
    )

    assert status == "failed"
    assert summary["failure_stage"] == "analysis"
    assert summary["internal_result"] == {
        "status": "failed",
        "reason_code": "EXECUTOR_CONTRACT_INVALID",
    }


def test_full_execution_cannot_inject_a_redelivery_context_after_skipping_input():
    status, summary = map_execution_result(
        database_precheck={"status": "ready"},
        executor_result={
            "failure_stage": "delivery",
            "feishu_relation": {"status": "skipped"},
            "internal_result": {
                "status": "skipped",
                "outcome": "content",
                "internal_result_id": "unverified-result",
            },
            "delivery": {
                "status": "failed",
                "reason_code": "DELIVERY_FAILED",
                "delivery_identity": "unverified-delivery",
            },
        },
        execution_object_type="project",
    )

    assert status == "failed"
    assert summary["internal_result"]["reason_code"] == "EXECUTOR_CONTRACT_INVALID"


@pytest.mark.parametrize(
    "executor_result",
    [
        {
            "feishu_relation": {
                "status": "missing",
                "reason_code": "RELATION_MISSING",
                "content_read_status": "ready",
            },
            "internal_result": {"status": "skipped"},
            "delivery": {"status": "skipped"},
        },
        {
            "feishu_relation": {
                "status": "missing",
                "reason_code": "RELATION_MISSING",
            },
            "internal_result": {
                "status": "skipped",
                "outcome": "content",
                "internal_result_id": "NOT_ALLOWED",
            },
            "delivery": {"status": "skipped"},
        },
        {
            "feishu_relation": {"status": "skipped"},
            "internal_result": {"status": "skipped", "reason_code": "NOT_ALLOWED"},
            "delivery": {
                "status": "failed",
                "reason_code": "DELIVERY_FAILED",
            },
            "failure_stage": "delivery",
        },
        {
            "feishu_relation": {"status": "ready", "content_read_status": "ready"},
            "internal_result": {
                "status": "success",
                "outcome": "content",
                "internal_result_id": "result-1",
                "reason_code": "NOT_ALLOWED",
            },
            "delivery": {
                "status": "success",
                "delivery_identity": "delivery-1",
                "reason_code": "NOT_ALLOWED",
            },
        },
    ],
)
def test_result_layers_reject_fields_that_do_not_belong_to_their_state(
    executor_result,
):
    status, summary = map_execution_result(
        database_precheck={"status": "ready"},
        executor_result=executor_result,
    )

    assert status == "failed"
    assert summary["internal_result"] == {
        "status": "failed",
        "reason_code": "EXECUTOR_CONTRACT_INVALID",
    }


@pytest.mark.parametrize(
    "executor_result",
    [
        {
            "failure_stage": "timeout",
            "feishu_relation": {"status": "skipped"},
            "internal_result": {
                "status": "failed",
                "reason_code": "DEADLINE_EXCEEDED",
            },
            "delivery": {"status": "skipped"},
        },
        {
            "failure_stage": "timeout",
            "feishu_relation": {"status": "ready", "content_read_status": "ready"},
            "internal_result": {
                "status": "success",
                "outcome": "content",
                "internal_result_id": "immutable-result-1",
            },
            "delivery": {
                "status": "failed",
                "reason_code": "DEADLINE_EXCEEDED",
                "delivery_identity": "immutable-delivery-1",
            },
        },
    ],
)
def test_deadline_exceeded_preserves_timeout_with_or_without_internal_result(executor_result):
    status, summary = map_execution_result(
        database_precheck={"status": "ready", "reason_code": None},
        executor_result=executor_result,
    )

    assert status == "failed"
    assert summary["failure_stage"] == "timeout"
    assert (
        summary["internal_result"].get("reason_code")
        or summary["delivery"].get("reason_code")
    ) == "DEADLINE_EXCEEDED"


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        (
            {
                "failure_stage": "timeout",
                "internal_result": {
                    "status": "success",
                    "internal_result_id": "result-1",
                },
                "delivery": {
                    "status": "failed",
                    "delivery_identity": "delivery-1",
                },
            },
            True,
        ),
        (
            {
                "failure_stage": "timeout",
                "internal_result": {"status": "failed"},
                "delivery": {"status": "skipped"},
            },
            False,
        ),
    ],
)
def test_timeout_retry_mode_depends_on_a_saved_delivery_context(summary, expected):
    assert _is_delivery_only_retry(summary) is expected


@pytest.mark.parametrize("executor_result", [
    {
        "feishu_relation": {"status": "unexpected"},
        "internal_result": {"status": "success", "outcome": "content", "internal_result_id": "id-1"},
        "delivery": {"status": "success", "delivery_identity": "doc-1"},
    },
    {
        "feishu_relation": {"status": "missing"},
        "internal_result": {"status": "success", "outcome": "content", "internal_result_id": "id-1"},
        "delivery": {"status": "success", "delivery_identity": "doc-1"},
    },
    {
        "feishu_relation": {"status": "ready", "content_read_status": "ready", "unexpected": "secret"},
        "internal_result": {"status": "success", "outcome": "content", "internal_result_id": "id-1"},
        "delivery": {"status": "success", "delivery_identity": "doc-1"},
    },
    {
        "feishu_relation": {"status": "ready", "content_read_status": "ready"},
        "internal_result": {"status": "success", "outcome": "content"},
        "delivery": {"status": "success", "delivery_identity": "doc-1"},
    },
])
def test_invalid_executor_result_safely_becomes_contract_failure(executor_result):
    status, summary = map_execution_result(
        database_precheck={"status": "ready", "reason_code": None},
        executor_result=executor_result,
    )

    assert status == "failed"
    assert summary["failure_stage"] == "analysis"
    assert summary["internal_result"] == {
        "status": "failed",
        "reason_code": "EXECUTOR_CONTRACT_INVALID",
    }
    assert summary["delivery"] == {"status": "skipped"}
    assert "secret" not in str(summary)


def test_executor_registry_rejects_object_missing_either_async_method():
    class ExecuteOnly:
        async def execute(self, envelope):
            return {}

    register_content_analysis_executor(ExecuteOnly())
    try:
        assert get_registered_content_analysis_executor() is None
    finally:
        register_content_analysis_executor(None)
