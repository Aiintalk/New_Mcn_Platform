"""任务配置 2.0 字典合同到内容分析内部合同的同进程适配。"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import app.services.content_analysis as ca


SHANGHAI = ZoneInfo("Asia/Shanghai")
_UNSET = object()


def raw_envelope(
    *,
    weekly=False,
    finalize=False,
    retry=False,
    test=False,
    run_type=None,
    retry_mode=_UNSET,
):
    run_type = run_type or (
        "manual_retry" if retry else ("test" if test else "auto")
    )
    is_retry = run_type in {"internal_retry", "manual_retry", "retry"}
    return {
        "contract_version": "2.0",
        "task_identity": {
            "task_id": 101,
            "task_no": "CA-S28-101",
            "agent_code": "content-analysis",
        },
        "task_code": "weekly" if weekly else "daily",
        "run_type": run_type,
        "business_date": "2026-09-04",
        "analysis_window": {
            "start": (
                "2026-08-06T00:00:00+08:00"
                if weekly
                else "2026-09-02T00:00:00+08:00"
            ),
            "end": "2026-09-05T00:00:00+08:00",
            "timezone": "Asia/Shanghai",
            "end_exclusive": True,
        },
        "triggered_at": "2026-09-05T00:00:00+08:00",
        "deadline_at": "2026-09-05T12:00:00+08:00",
        "retry": {
            "retry_of_task_id": (
                101 if run_type == "internal_retry" else (99 if is_retry else None)
            ),
            "mode": (
                "delivery_only" if is_retry else None
            ) if retry_mode is _UNSET else retry_mode,
            "request_id": (
                "test-1"
                if run_type == "test"
                else "retry-1"
                if run_type in {"manual_retry", "retry"}
                else None
            ),
        },
        "database_precheck": {
            "status": "ready",
            "reason_code": None,
            "input_limited": True,
            "input_limited_reasons": ["TARGET_USERS_MISSING"],
        },
        "delivery_target": {
            "report_root_ref": "folder-token",
            "scope": "test" if test else "formal",
            "test_subdirectory": "测试报告" if test else None,
        },
        "execution": (
            {
                "object_type": "weekly_batch_finalize",
                "project_ids": [1001, 1002],
                "weekly_batch_id": "weekly-2026-09-04",
                "batch_size": 2,
                "finalize_version": "state-v1",
            }
            if finalize
            else
            {
                "object_type": "account",
                "account_key": "account-001",
                "project_ids": [1001, 1002],
                "weekly_batch_id": "weekly-2026-09-04",
                "batch_size": 2,
                "batch_position": 1,
            }
            if weekly
            else {"object_type": "project", "project_id": 1001}
        ),
        "idempotency": {
            "run_key": "run-key",
            "internal_result_key": "result-key",
            "document_key": "document-key",
        },
    }


class Core:
    def __init__(self, outcome):
        self.outcome = outcome
        self.execute_calls = []
        self.redeliver_calls = []

    async def execute(self, envelope):
        self.execute_calls.append(envelope)
        return self.outcome

    async def redeliver(self, envelope, result_id, identity):
        self.redeliver_calls.append((envelope, result_id, identity))
        return self.outcome


def outcome(
    *,
    status=ca.ExecutionOverallStatus.SUCCESS,
    internal="success",
    stage=None,
    reason_code=None,
    internal_result_id=77,
    relation="complete",
):
    identity = ca.DeliveryIdentity(
        "document-key",
        "doc-1",
        "https://feishu.cn/docx/doc-1",
    )
    return ca.ExecutionOutcome(
        status,
        ca.ExecutionLayerSummary(
            precheck="ready",
            relation=relation,
            internal_result=internal,
            delivery="success" if status is ca.ExecutionOverallStatus.SUCCESS else "failed",
            failure_stage=stage,
            reason_code=(
                reason_code
                if reason_code is not None
                else "DELIVERY_FAILED" if stage == "delivery" else None
            ),
            public_message="飞书报告投递失败" if stage == "delivery" else None,
        ),
        internal_result_id=internal_result_id,
        output_id=88,
        delivery_identity=identity,
    )


@pytest.mark.asyncio
async def test_adapter_converts_daily_dictionary_and_success_result_without_http_callback() -> None:
    core = Core(outcome())
    adapter = ca.ContentAnalysisTaskConfigAdapter(core)

    result = await adapter.execute(raw_envelope())

    parsed = core.execute_calls[0]
    assert parsed.execution == ca.ProjectExecution("1001")
    assert parsed.delivery_target.relative_directory == "项目日报"
    assert parsed.precheck.limitation_codes == ("TARGET_USERS_MISSING",)
    assert result == {
        "failure_stage": None,
        "feishu_relation": {"status": "ready", "content_read_status": "ready"},
        "internal_result": {
            "status": "success",
            "outcome": "content",
            "internal_result_id": "77",
        },
        "delivery": {
            "status": "success",
            "delivery_identity": json.dumps(
                {
                    "document_key": "document-key",
                    "document_id": "doc-1",
                    "document_url": "https://feishu.cn/docx/doc-1",
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "document_url": "https://feishu.cn/docx/doc-1",
        },
    }


def test_adapter_converts_weekly_batch_finalize_dictionary() -> None:
    parsed = ca.parse_task_config_envelope(
        raw_envelope(weekly=True, finalize=True)
    )

    assert parsed.execution == ca.WeeklyBatchFinalizeExecution(
        weekly_batch_id="weekly-2026-09-04",
        batch_size=2,
        project_ids=("1001", "1002"),
        finalize_version="state-v1",
    )
    assert parsed.delivery_target.relative_directory == "账号基准周报"


def test_adapter_accepts_weekly_batch_finalize_with_selected_projects_and_zero_accounts() -> None:
    raw = raw_envelope(weekly=True, finalize=True)
    raw["execution"]["batch_size"] = 0

    parsed = ca.parse_task_config_envelope(raw)

    assert parsed.execution == ca.WeeklyBatchFinalizeExecution(
        weekly_batch_id="weekly-2026-09-04",
        batch_size=0,
        project_ids=("1001", "1002"),
        finalize_version="state-v1",
    )


@pytest.mark.parametrize(
    "path",
    (
        (),
        ("task_identity",),
        ("analysis_window",),
        ("database_precheck",),
        ("delivery_target",),
        ("retry",),
        ("idempotency",),
    ),
)
def test_adapter_rejects_unknown_fields_in_every_envelope_layer(path) -> None:
    raw = raw_envelope()
    target = raw
    for field_name in path:
        target = target[field_name]
    target["unexpected_private_payload"] = "must-not-enter"

    with pytest.raises(ValueError, match="未知字段"):
        ca.parse_task_config_envelope(raw)


@pytest.mark.parametrize(
    ("run_type", "field_name", "invalid_value"),
    (
        ("auto", "retry_of_task_id", 99),
        ("auto", "request_id", "unexpected-retry"),
        ("test", "retry_of_task_id", 99),
        ("test", "mode", "full"),
        ("internal_retry", "request_id", "unexpected-user-request"),
        ("manual_retry", "request_id", None),
        ("manual_retry", "request_id", {"opaque": "object"}),
    ),
)
def test_retry_fields_are_closed_by_run_type(
    run_type,
    field_name,
    invalid_value,
) -> None:
    raw = raw_envelope(
        run_type=run_type,
        retry_mode="full",
        test=run_type == "test",
    )
    if run_type in {"auto", "test"}:
        raw["retry"]["mode"] = None
    raw["retry"][field_name] = invalid_value

    with pytest.raises(ValueError, match="重试|request_id|retry"):
        ca.parse_task_config_envelope(raw)


def test_manual_retry_preserves_request_id_for_saved_task_binding() -> None:
    raw = raw_envelope(run_type="manual_retry", retry_mode="delivery_only")

    parsed = ca.parse_task_config_envelope(raw)

    assert parsed.request_id == "retry-1"


@pytest.mark.parametrize(
    ("raw", "extra_field"),
    (
        (raw_envelope(), "account_key"),
        (raw_envelope(weekly=True), "project_id"),
        (raw_envelope(weekly=True, finalize=True), "content_records"),
        (raw_envelope(weekly=True, finalize=True), "relation_records"),
        (raw_envelope(weekly=True, finalize=True), "project_context"),
    ),
)
def test_each_execution_branch_rejects_fields_from_other_scopes(
    raw,
    extra_field,
) -> None:
    raw["execution"][extra_field] = []

    with pytest.raises(ValueError, match="execution.*未知字段"):
        ca.parse_task_config_envelope(raw)


def test_weekly_batch_finalize_requires_nonempty_snapshot_version() -> None:
    raw = raw_envelope(weekly=True, finalize=True)
    raw["execution"]["finalize_version"] = " "

    with pytest.raises(ValueError, match="finalize_version"):
        ca.parse_task_config_envelope(raw)


def test_weekly_batch_finalize_rejects_test_scope() -> None:
    raw = raw_envelope(weekly=True, finalize=True, test=True)

    with pytest.raises(ValueError, match="正式"):
        ca.parse_task_config_envelope(raw)


@pytest.mark.asyncio
async def test_failed_weekly_finalize_allows_full_manual_retry() -> None:
    core = Core(outcome())
    adapter = ca.ContentAnalysisTaskConfigAdapter(core)
    raw = raw_envelope(
        weekly=True,
        finalize=True,
        run_type="manual_retry",
        retry_mode="full",
    )

    result = await adapter.execute(raw)

    assert result["failure_stage"] is None
    assert len(core.execute_calls) == 1
    assert core.execute_calls[0].retry_mode is ca.RetryMode.FULL


@pytest.mark.asyncio
async def test_weekly_finalize_manual_retry_requires_origin_and_full_mode() -> None:
    core = Core(outcome())
    adapter = ca.ContentAnalysisTaskConfigAdapter(core)
    missing_origin = raw_envelope(
        weekly=True,
        finalize=True,
        run_type="manual_retry",
        retry_mode="full",
    )
    missing_origin["retry"]["retry_of_task_id"] = None
    delivery_only = raw_envelope(
        weekly=True,
        finalize=True,
        run_type="manual_retry",
        retry_mode="delivery_only",
    )
    unknown_mode = raw_envelope(
        weekly=True,
        finalize=True,
        run_type="manual_retry",
        retry_mode="rerun_everything",
    )
    identity = json.dumps(
        {
            "document_key": "document-key",
            "document_id": "doc-1",
            "document_url": "https://feishu.cn/docx/doc-1",
        }
    )

    missing_result = await adapter.execute(missing_origin)
    execute_result = await adapter.execute(delivery_only)
    unknown_result = await adapter.execute(unknown_mode)
    redeliver_result = await adapter.redeliver(delivery_only, "77", identity)

    assert missing_result["internal_result"]["reason_code"] == (
        "EXECUTOR_CONTRACT_INVALID"
    )
    assert execute_result["internal_result"]["reason_code"] == (
        "EXECUTOR_CONTRACT_INVALID"
    )
    assert unknown_result["internal_result"]["reason_code"] == (
        "EXECUTOR_CONTRACT_INVALID"
    )
    assert core.execute_calls == []
    assert redeliver_result["failure_stage"] is None
    assert len(core.redeliver_calls) == 1


@pytest.mark.asyncio
async def test_weekly_batch_finalize_result_strictly_skips_feishu_input_layer() -> None:
    core = Core(outcome())

    result = await ca.ContentAnalysisTaskConfigAdapter(core).execute(
        raw_envelope(weekly=True, finalize=True)
    )

    assert result["failure_stage"] is None
    assert result["feishu_relation"] == {"status": "skipped"}
    assert result["internal_result"] == {
        "status": "success",
        "outcome": "content",
        "internal_result_id": "77",
    }
    assert result["delivery"]["status"] == "success"


def test_adapter_converts_weekly_scope_and_test_directory() -> None:
    parsed = ca.parse_task_config_envelope(raw_envelope(weekly=True, test=True))

    assert parsed.execution == ca.AccountExecution(
        "account-001",
        ("1001", "1002"),
        "weekly-2026-09-04",
        2,
        1,
    )
    assert parsed.delivery_target.scope is ca.DeliveryScope.TEST
    assert parsed.delivery_target.relative_directory == "测试报告"


@pytest.mark.parametrize(
    ("run_type", "expected_source"),
    (
        ("auto", ca.TriggerSource.SYSTEM),
        ("internal_retry", ca.TriggerSource.SYSTEM),
        ("test", ca.TriggerSource.USER),
        ("manual_retry", ca.TriggerSource.USER),
        ("retry", ca.TriggerSource.USER),
    ),
)
def test_adapter_maps_task_config_trigger_source(run_type, expected_source) -> None:
    parsed = ca.parse_task_config_envelope(
        raw_envelope(
            run_type=run_type,
            test=run_type == "test",
        )
    )

    assert parsed.trigger_source is expected_source


@pytest.mark.parametrize(
    ("input_limited", "reasons"),
    (
        (False, ["TARGET_USERS_MISSING"]),
        (True, []),
        ("false", []),
    ),
)
def test_adapter_rejects_inconsistent_or_non_boolean_input_limitation(
    input_limited,
    reasons,
) -> None:
    raw = raw_envelope()
    raw["database_precheck"]["input_limited"] = input_limited
    raw["database_precheck"]["input_limited_reasons"] = reasons

    with pytest.raises(ValueError, match="输入受限"):
        ca.parse_task_config_envelope(raw)


def test_adapter_rejects_non_positive_project_ids() -> None:
    daily = raw_envelope()
    daily["execution"]["project_id"] = 0
    weekly = raw_envelope(weekly=True)
    weekly["execution"]["project_ids"] = [0, 1001]

    with pytest.raises(ValueError, match="项目编号"):
        ca.parse_task_config_envelope(daily)
    with pytest.raises(ValueError, match="项目"):
        ca.parse_task_config_envelope(weekly)


@pytest.mark.asyncio
async def test_delivery_failure_round_trips_identity_into_delivery_only_retry() -> None:
    core = Core(
        outcome(
            status=ca.ExecutionOverallStatus.FAILED,
            stage="delivery",
        )
    )
    adapter = ca.ContentAnalysisTaskConfigAdapter(core)
    failed = await adapter.execute(raw_envelope())

    retried = await adapter.redeliver(
        raw_envelope(retry=True),
        failed["internal_result"]["internal_result_id"],
        failed["delivery"]["delivery_identity"],
    )

    assert retried["failure_stage"] == "delivery"
    _, result_id, identity = core.redeliver_calls[0]
    assert result_id == 77
    assert identity == ca.DeliveryIdentity(
        "document-key",
        "doc-1",
        "https://feishu.cn/docx/doc-1",
    )


@pytest.mark.asyncio
async def test_invalid_finalize_redelivery_remains_a_delivery_layer_failure() -> None:
    core = Core(
        outcome(
            status=ca.ExecutionOverallStatus.FAILED,
            internal="not_started",
            stage="delivery",
            reason_code="EXECUTOR_CONTRACT_INVALID",
            internal_result_id=None,
        )
    )
    adapter = ca.ContentAnalysisTaskConfigAdapter(core)
    raw = raw_envelope(
        weekly=True,
        finalize=True,
        run_type="manual_retry",
    )
    identity = json.dumps(
        {
            "document_key": "document-key",
            "document_id": "doc-1",
            "document_url": "https://feishu.cn/docx/doc-1",
        }
    )

    result = await adapter.redeliver(raw, "77", identity)

    assert result == {
        "failure_stage": "delivery",
        "feishu_relation": {"status": "skipped"},
        "internal_result": {"status": "skipped"},
        "delivery": {
            "status": "failed",
            "reason_code": "EXECUTOR_CONTRACT_INVALID",
        },
    }


@pytest.mark.asyncio
async def test_invalid_redelivery_arguments_fail_in_delivery_layer() -> None:
    core = Core(outcome())
    raw = raw_envelope(retry=True)

    result = await ca.ContentAnalysisTaskConfigAdapter(core).redeliver(
        raw,
        "not-an-integer",
        "not-a-delivery-identity",
    )

    assert result == {
        "failure_stage": "delivery",
        "feishu_relation": {"status": "skipped"},
        "internal_result": {"status": "skipped"},
        "delivery": {
            "status": "failed",
            "reason_code": "EXECUTOR_CONTRACT_INVALID",
        },
    }
    assert core.redeliver_calls == []


@pytest.mark.asyncio
async def test_redelivery_identity_rejects_unknown_fields() -> None:
    core = Core(outcome())
    raw = raw_envelope(retry=True)

    result = await ca.ContentAnalysisTaskConfigAdapter(core).redeliver(
        raw,
        "77",
        json.dumps(
            {
                "document_key": "document-key",
                "document_id": "doc-1",
                "document_url": "https://feishu.cn/docx/doc-1",
                "unexpected_private_payload": "must-not-pass",
            }
        ),
    )

    assert result["delivery"]["reason_code"] == "EXECUTOR_CONTRACT_INVALID"
    assert core.redeliver_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("delivery_only", (False, True))
async def test_pre_input_executor_failure_marks_feishu_layer_skipped(
    delivery_only,
) -> None:
    core = Core(
        outcome(
            status=ca.ExecutionOverallStatus.FAILED,
            internal="not_started",
            stage="delivery" if delivery_only else "system_config",
            reason_code="EXECUTOR_CONTRACT_INVALID",
            internal_result_id=None,
            relation="not_started",
        )
    )
    adapter = ca.ContentAnalysisTaskConfigAdapter(core)
    raw = raw_envelope(retry=delivery_only)

    result = (
        await adapter.redeliver(
            raw,
            "77",
            json.dumps(
                {
                    "document_key": "document-key",
                    "document_id": "doc-1",
                    "document_url": "https://feishu.cn/docx/doc-1",
                }
            ),
        )
        if delivery_only
        else await adapter.execute(raw)
    )

    assert result["feishu_relation"] == {"status": "skipped"}


@pytest.mark.asyncio
async def test_deadline_failure_before_input_maps_to_timeout_without_fake_ready_layer() -> None:
    core = Core(
        ca.ExecutionOutcome(
            ca.ExecutionOverallStatus.FAILED,
            ca.ExecutionLayerSummary(
                precheck="ready",
                relation="not_started",
                internal_result="not_started",
                delivery="not_started",
                failure_stage="deadline",
                reason_code="DEADLINE_EXCEEDED",
                public_message="内容分析任务已超过截止时间",
            ),
        )
    )

    result = await ca.ContentAnalysisTaskConfigAdapter(core).execute(raw_envelope())

    assert result == {
        "failure_stage": "timeout",
        "feishu_relation": {"status": "skipped"},
        "internal_result": {
            "status": "failed",
            "reason_code": "DEADLINE_EXCEEDED",
        },
        "delivery": {"status": "skipped"},
    }


@pytest.mark.asyncio
async def test_delivery_retry_deadline_keeps_original_result_and_timeout_stage() -> None:
    core = Core(
        ca.ExecutionOutcome(
            ca.ExecutionOverallStatus.FAILED,
            ca.ExecutionLayerSummary(
                precheck="ready",
                relation="not_started",
                internal_result="success",
                delivery="failed",
                failure_stage="deadline",
                reason_code="DEADLINE_EXCEEDED",
                public_message="内容分析任务已超过截止时间",
            ),
            internal_result_id=77,
            delivery_identity=ca.DeliveryIdentity(
                "document-key",
                "doc-1",
                "https://feishu.cn/docx/doc-1",
            ),
        )
    )
    raw = raw_envelope(retry=True)

    result = await ca.ContentAnalysisTaskConfigAdapter(core).redeliver(
        raw,
        "77",
        json.dumps(
            {
                "document_key": "document-key",
                "document_id": "doc-1",
                "document_url": "https://feishu.cn/docx/doc-1",
            }
        ),
    )

    assert result["failure_stage"] == "timeout"
    assert result["feishu_relation"] == {"status": "skipped"}
    assert result["internal_result"]["internal_result_id"] == "77"
    assert result["delivery"]["reason_code"] == "DEADLINE_EXCEEDED"


@pytest.mark.asyncio
async def test_internal_retry_full_execution_uses_system_trigger_and_original_deadline(
) -> None:
    core = Core(outcome())
    adapter = ca.ContentAnalysisTaskConfigAdapter(core)
    raw = raw_envelope(run_type="internal_retry", retry_mode="full")

    result = await adapter.execute(raw)

    assert result["failure_stage"] is None
    assert set(result) == {
        "failure_stage",
        "feishu_relation",
        "internal_result",
        "delivery",
    }
    parsed = core.execute_calls[0]
    assert parsed.run_type is ca.RunType.RETRY
    assert parsed.trigger_source is ca.TriggerSource.SYSTEM
    assert parsed.retry_of_task_id == raw["task_identity"]["task_id"]
    assert parsed.deadline_at.isoformat() == raw["deadline_at"]


@pytest.mark.asyncio
async def test_internal_retry_delivery_only_accepts_real_task_dictionary() -> None:
    core = Core(outcome())
    adapter = ca.ContentAnalysisTaskConfigAdapter(core)
    raw = raw_envelope(run_type="internal_retry")
    identity = json.dumps(
        {
            "document_key": "document-key",
            "document_id": "doc-1",
            "document_url": "https://feishu.cn/docx/doc-1",
        }
    )

    result = await adapter.redeliver(raw, "77", identity)

    assert result["failure_stage"] is None
    parsed, result_id, parsed_identity = core.redeliver_calls[0]
    assert parsed.run_type is ca.RunType.RETRY
    assert parsed.trigger_source is ca.TriggerSource.SYSTEM
    assert parsed.retry_of_task_id == raw["task_identity"]["task_id"]
    assert result_id == 77
    assert parsed_identity.document_key == "document-key"


def test_unknown_run_type_remains_rejected() -> None:
    raw = raw_envelope(run_type="unexpected_retry")

    with pytest.raises(ValueError, match="运行类型不受支持"):
        ca.parse_task_config_envelope(raw)


def test_internal_retry_must_reference_the_same_persisted_task() -> None:
    raw = raw_envelope(run_type="internal_retry")
    raw["retry"]["retry_of_task_id"] = 999

    with pytest.raises(ValueError, match="原任务"):
        ca.parse_task_config_envelope(raw)


@pytest.mark.asyncio
async def test_invalid_envelope_fails_closed_without_echoing_private_input() -> None:
    core = Core(outcome())
    raw = raw_envelope()
    raw["delivery_target"]["report_root_ref"] = ""
    raw["private_secret"] = "must-not-leak"

    result = await ca.ContentAnalysisTaskConfigAdapter(core).execute(raw)

    assert result["internal_result"]["reason_code"] == "EXECUTOR_CONTRACT_INVALID"
    assert result["feishu_relation"] == {"status": "skipped"}
    assert "must-not-leak" not in json.dumps(result)
    assert core.execute_calls == []


@pytest.mark.asyncio
async def test_invalid_finalize_envelope_still_uses_closed_skipped_input_layer() -> None:
    core = Core(outcome())
    raw = raw_envelope(weekly=True, finalize=True)
    raw["delivery_target"]["report_root_ref"] = ""

    result = await ca.ContentAnalysisTaskConfigAdapter(core).execute(raw)

    assert result == {
        "failure_stage": "internal_result",
        "feishu_relation": {"status": "skipped"},
        "internal_result": {
            "status": "failed",
            "reason_code": "EXECUTOR_CONTRACT_INVALID",
        },
        "delivery": {"status": "skipped"},
    }
    assert core.execute_calls == []
