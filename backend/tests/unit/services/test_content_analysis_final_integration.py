"""任务配置与内容分析组合后的应用级合同。"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.agent_task_execution_contract import (
    build_task_envelope,
    get_registered_content_analysis_executor,
    map_execution_result,
    register_content_analysis_executor,
)
from app.services.agent_task_execution_service import _normalize_redelivery_result
from app.services.content_analysis.executor import (
    DeliveryIdentity,
    ExecutionLayerSummary,
    ExecutionOutcome,
    ExecutionOverallStatus,
)
from app.services.content_analysis.runtime_factory import ContentAnalysisRuntimeProvider
from app.services.content_analysis.task_config_adapter import ContentAnalysisTaskConfigAdapter


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _missing_runtime_config():
    raise ValueError("配置缺失")


class _Session:
    def __init__(self) -> None:
        self.closed = False

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        self.closed = True


class _Http:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_real_builder_parser_and_registered_provider_share_one_contract(
    monkeypatch,
) -> None:
    """真实构造器字段漂移时，真实解析器与注册入口必须共同暴露失败。"""
    parsed = []

    class CoreExecutor:
        async def execute(self, envelope):
            parsed.append(envelope)
            return ExecutionOutcome(
                overall_status=ExecutionOverallStatus.SUCCESS,
                summary=ExecutionLayerSummary(
                    precheck="ready",
                    relation="complete",
                    internal_result="success",
                    delivery="success",
                ),
                internal_result_id=9,
                delivery_identity=DeliveryIdentity(
                    envelope.idempotency.document_key,
                    "doc-9",
                    "https://feishu.cn/docx/doc-9",
                ),
            )

    session = _Session()
    http = _Http()
    monkeypatch.setattr(
        "app.services.content_analysis.runtime_factory.build_content_analysis_executor",
        lambda *_args: ContentAnalysisTaskConfigAdapter(CoreExecutor()),
    )
    provider = ContentAnalysisRuntimeProvider(
        config_loader=lambda: object(),
        session_factory=lambda: session,
        http_factory=lambda: http,
    )
    raw = build_task_envelope(
        task_id=81,
        task_no="CA-S28-JOINT-81",
        task_code="daily",
        run_type="auto",
        triggered_at=datetime(2026, 9, 5, 0, 0, tzinfo=SHANGHAI),
        execution={"object_type": "project", "project_id": 7},
        database_precheck={
            "status": "ready",
            "reason_code": None,
            "input_limited": False,
            "input_limited_reasons": [],
        },
        report_root_ref="report-root",
        run_key="joint-run-81",
        internal_result_key="joint-result-81",
        document_key="joint-document-81",
    )

    register_content_analysis_executor(provider)
    try:
        result = await get_registered_content_analysis_executor().execute(raw)
    finally:
        register_content_analysis_executor(None)

    assert result["internal_result"] == {
        "status": "success",
        "outcome": "content",
        "internal_result_id": "9",
    }
    assert result["delivery"]["document_url"] == "https://feishu.cn/docx/doc-9"
    assert parsed[0].execution.project_id == "7"
    assert session.closed is True
    assert http.closed is True


@pytest.mark.asyncio
async def test_app_lifespan_registers_runtime_before_scheduler_and_closes_in_order(
    monkeypatch,
) -> None:
    """调度先于执行器注册或关闭顺序颠倒时，本测试必须失败。"""
    import app.main as main

    events = []

    class Provider:
        async def execute(self, _envelope):
            return {}

        async def redeliver(self, _envelope, _result_id, _identity):
            return {}

        async def aclose(self):
            events.append("provider_closed")

    provider = Provider()
    runtime_values = {"CONTENT_ANALYSIS_FEISHU_APP_ID": "app-from-dotenv"}

    async def seed():
        events.append("seeded")

    async def tikhub():
        return None

    def register(value):
        events.append("registered" if value is provider else "unregistered")

    def start():
        events.append("scheduler_started")
        return object()

    async def shutdown(_task):
        events.append("scheduler_stopped")

    monkeypatch.setattr(main, "seed_initial_data", seed)
    monkeypatch.setattr(main, "tikhub_refresh_scheduler", tikhub)
    monkeypatch.setattr(
        type(main.settings),
        "content_analysis_runtime_values",
        lambda _self: runtime_values,
    )

    def build_provider(values):
        assert values == runtime_values
        events.append("runtime_config_loaded")
        return provider

    monkeypatch.setattr(main, "build_content_analysis_runtime_provider", build_provider)
    monkeypatch.setattr(main, "register_content_analysis_executor", register)
    monkeypatch.setattr(main, "start_content_analysis_scheduler", start)
    monkeypatch.setattr(main, "shutdown_content_analysis_scheduler", shutdown)

    async with main.startup_lifespan(main.app):
        events.append("serving")

    assert events == [
        "seeded",
        "runtime_config_loaded",
        "registered",
        "scheduler_started",
        "serving",
        "scheduler_stopped",
        "unregistered",
        "provider_closed",
    ]


def _runtime_failure_envelope() -> dict:
    return build_task_envelope(
        task_id=82,
        task_no="CA-S28-JOINT-82",
        task_code="daily",
        run_type="auto",
        triggered_at=datetime(2026, 9, 5, 0, 0, tzinfo=SHANGHAI),
        execution={"object_type": "project", "project_id": 7},
        database_precheck={
            "status": "ready",
            "reason_code": None,
            "input_limited": False,
            "input_limited_reasons": [],
        },
        report_root_ref="report-root",
        run_key="joint-run-82",
        internal_result_key="joint-result-82",
        document_key="joint-document-82",
    )


@pytest.mark.asyncio
async def test_runtime_setup_failure_crosses_full_execution_contract_without_fake_input() -> None:
    provider = ContentAnalysisRuntimeProvider(
        config_loader=_missing_runtime_config,
        session_factory=lambda: (_ for _ in ()).throw(AssertionError("不应建会话")),
        http_factory=lambda: (_ for _ in ()).throw(AssertionError("不应联网")),
    )

    raw_result = await provider.execute(_runtime_failure_envelope())
    status, summary = map_execution_result(
        database_precheck={"status": "ready"},
        executor_result=raw_result,
    )

    assert status == "failed"
    assert summary["failure_stage"] == "internal_result"
    assert summary["feishu_relation"] == {"status": "skipped"}
    assert summary["internal_result"]["reason_code"] == "EXECUTOR_RUNTIME_UNAVAILABLE"


@pytest.mark.asyncio
async def test_runtime_setup_failure_crosses_redelivery_contract_without_fake_result() -> None:
    provider = ContentAnalysisRuntimeProvider(
        config_loader=_missing_runtime_config,
        session_factory=lambda: (_ for _ in ()).throw(AssertionError("不应建会话")),
        http_factory=lambda: (_ for _ in ()).throw(AssertionError("不应联网")),
    )

    raw_result = await provider.redeliver(
        _runtime_failure_envelope(),
        "immutable-result-82",
        "immutable-delivery-82",
    )
    normalized = _normalize_redelivery_result(
        raw_result,
        ("immutable-result-82", "immutable-delivery-82", "content"),
    )
    status, summary = map_execution_result(
        database_precheck={"status": "ready"},
        executor_result=normalized,
        redelivery_context_confirmed=True,
    )

    assert status == "failed"
    assert summary["failure_stage"] == "delivery"
    assert summary["feishu_relation"] == {"status": "skipped"}
    assert summary["internal_result"] == {
        "status": "skipped",
        "outcome": "content",
        "internal_result_id": "immutable-result-82",
    }
    assert summary["delivery"] == {
        "status": "failed",
        "reason_code": "EXECUTOR_RUNTIME_UNAVAILABLE",
        "delivery_identity": "immutable-delivery-82",
    }
