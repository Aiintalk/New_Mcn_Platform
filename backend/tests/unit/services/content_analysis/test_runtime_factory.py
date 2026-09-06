"""部署配置注入与正式执行器装配合同。"""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import app.services.content_analysis as ca


SUCCESS_RESULT = {
    "failure_stage": None,
    "feishu_relation": {"status": "ready", "content_read_status": "ready"},
    "internal_result": {
        "status": "success",
        "outcome": "content",
        "internal_result_id": "result-1",
    },
    "delivery": {
        "status": "success",
        "delivery_identity": "identity-1",
    },
}


class FakeSession:
    def __init__(self, identity):
        self.identity = identity
        self.rolled_back = False
        self.closed = False

    async def rollback(self):
        self.rolled_back = True

    async def close(self):
        self.closed = True


class FakeHttp:
    def __init__(self, identity):
        self.identity = identity
        self.closed = False

    async def aclose(self):
        self.closed = True


def values():
    return {
        "CONTENT_ANALYSIS_FEISHU_APP_ID": "app-id",
        "CONTENT_ANALYSIS_FEISHU_APP_SECRET": "private-secret",
        "CONTENT_ANALYSIS_FEISHU_CONTENT_APP_TOKEN": "content-base",
        "CONTENT_ANALYSIS_FEISHU_CONTENT_TABLE_ID": "content-table",
        "CONTENT_ANALYSIS_FEISHU_RELATION_APP_TOKEN": "relation-base",
        "CONTENT_ANALYSIS_FEISHU_RELATION_TABLE_ID": "relation-table",
        "CONTENT_ANALYSIS_MODEL_ID": "model-id",
        "CONTENT_ANALYSIS_MODEL_PROVIDER": "yunwu",
        "CONTENT_ANALYSIS_SYSTEM_USER_ID": "100",
    }


def test_runtime_config_uses_only_injected_fixed_table_and_model_identifiers() -> None:
    config = ca.ContentAnalysisRuntimeConfig.from_mapping(values())

    assert config.content_table == ca.FeishuContentTableConfig("content-base", "content-table")
    assert config.relation_table == ca.FeishuRelationTableConfig("relation-base", "relation-table")
    assert config.model_id == "model-id"
    assert config.system_user_id == 100
    assert "private-secret" not in repr(config)


def test_runtime_config_fails_closed_when_secret_table_or_system_account_is_missing() -> None:
    for key in (
        "CONTENT_ANALYSIS_FEISHU_APP_SECRET",
        "CONTENT_ANALYSIS_FEISHU_CONTENT_TABLE_ID",
        "CONTENT_ANALYSIS_SYSTEM_USER_ID",
    ):
        broken = values()
        broken[key] = ""
        with pytest.raises(ValueError, match="运行配置"):
            ca.ContentAnalysisRuntimeConfig.from_mapping(broken)


@pytest.mark.asyncio
async def test_runtime_provider_uses_distinct_resources_for_concurrent_daily_calls(
    monkeypatch,
) -> None:
    sessions = []
    clients = []
    calls = []

    def session_factory():
        session = FakeSession(len(sessions) + 1)
        sessions.append(session)
        return session

    def http_factory():
        client = FakeHttp(len(clients) + 1)
        clients.append(client)
        return client

    def fake_build(session, http, config):
        class Adapter:
            async def execute(self, raw):
                calls.append((raw["task_identity"]["task_id"], session, http))
                await asyncio.sleep(0)
                return SUCCESS_RESULT

        return Adapter()

    monkeypatch.setattr(
        "app.services.content_analysis.runtime_factory.build_content_analysis_executor",
        fake_build,
    )
    provider = ca.ContentAnalysisRuntimeProvider(
        config_loader=lambda: object(),
        session_factory=session_factory,
        http_factory=http_factory,
    )
    first = {"task_code": "daily", "task_identity": {"task_id": 1}}
    second = {"task_code": "daily", "task_identity": {"task_id": 2}}

    results = await asyncio.gather(provider.execute(first), provider.execute(second))

    assert results == [SUCCESS_RESULT, SUCCESS_RESULT]
    assert len(sessions) == len(clients) == 2
    assert calls[0][1] is not calls[1][1]
    assert calls[0][2] is not calls[1][2]
    assert all(session.rolled_back and session.closed for session in sessions)
    assert all(client.closed for client in clients)


@pytest.mark.asyncio
async def test_runtime_provider_closes_resources_after_executor_exception(
    monkeypatch,
) -> None:
    session = FakeSession(1)
    client = FakeHttp(1)

    class Adapter:
        async def execute(self, raw):
            raise RuntimeError("private runtime detail")

    monkeypatch.setattr(
        "app.services.content_analysis.runtime_factory.build_content_analysis_executor",
        lambda *args: Adapter(),
    )
    provider = ca.ContentAnalysisRuntimeProvider(
        config_loader=lambda: object(),
        session_factory=lambda: session,
        http_factory=lambda: client,
    )

    result = await provider.execute({"task_code": "daily"})

    assert result == {
        "failure_stage": "internal_result",
        "feishu_relation": {"status": "skipped"},
        "internal_result": {
            "status": "failed",
            "reason_code": "EXECUTOR_RUNTIME_UNAVAILABLE",
        },
        "delivery": {"status": "skipped"},
    }
    assert "private runtime detail" not in str(result)
    assert session.rolled_back is True
    assert session.closed is True
    assert client.closed is True


@pytest.mark.asyncio
async def test_runtime_provider_redelivery_gets_an_independent_session(monkeypatch) -> None:
    sessions = []
    clients = []
    redelivery_sessions = []

    def session_factory():
        session = FakeSession(len(sessions) + 1)
        sessions.append(session)
        return session

    def http_factory():
        client = FakeHttp(len(clients) + 1)
        clients.append(client)
        return client

    def fake_build(session, http, config):
        class Adapter:
            async def execute(self, raw):
                return SUCCESS_RESULT

            async def redeliver(self, raw, result_id, identity):
                redelivery_sessions.append(session)
                return SUCCESS_RESULT

        return Adapter()

    monkeypatch.setattr(
        "app.services.content_analysis.runtime_factory.build_content_analysis_executor",
        fake_build,
    )
    provider = ca.ContentAnalysisRuntimeProvider(
        config_loader=lambda: object(),
        session_factory=session_factory,
        http_factory=http_factory,
    )

    await provider.execute({"task_code": "daily"})
    result = await provider.redeliver({}, "result-1", "identity-1")

    assert result == SUCCESS_RESULT
    assert len(sessions) == 2
    assert redelivery_sessions == [sessions[1]]
    assert all(session.closed for session in sessions)
    assert all(client.closed for client in clients)


@pytest.mark.asyncio
@pytest.mark.parametrize("failing_stage", ("config", "session", "http"))
async def test_runtime_provider_startup_failures_return_closed_four_layer_result(
    failing_stage,
) -> None:
    calls = []
    session = FakeSession(1)

    def config_loader():
        calls.append("config")
        if failing_stage == "config":
            raise RuntimeError("private config")
        return object()

    def session_factory():
        calls.append("session")
        if failing_stage == "session":
            raise RuntimeError("private session")
        return session

    def http_factory():
        calls.append("http")
        if failing_stage == "http":
            raise RuntimeError("private http")
        return FakeHttp(1)

    provider = ca.ContentAnalysisRuntimeProvider(
        config_loader=config_loader,
        session_factory=session_factory,
        http_factory=http_factory,
    )

    result = await provider.execute({"task_code": "daily"})

    assert set(result) == {
        "failure_stage",
        "feishu_relation",
        "internal_result",
        "delivery",
    }
    assert result["internal_result"] == {
        "status": "failed",
        "reason_code": "EXECUTOR_RUNTIME_UNAVAILABLE",
    }
    assert "private" not in str(result)
    if failing_stage == "http":
        assert session.rolled_back is True
        assert session.closed is True


@pytest.mark.asyncio
async def test_runtime_provider_failure_keeps_weekly_finalize_input_layer_skipped() -> None:
    provider = ca.ContentAnalysisRuntimeProvider(
        config_loader=lambda: (_ for _ in ()).throw(RuntimeError("private config")),
        session_factory=lambda: FakeSession(1),
        http_factory=lambda: FakeHttp(1),
    )

    result = await provider.execute(
        {"execution": {"object_type": "weekly_batch_finalize"}}
    )

    assert result == {
        "failure_stage": "internal_result",
        "feishu_relation": {"status": "skipped"},
        "internal_result": {
            "status": "failed",
            "reason_code": "EXECUTOR_RUNTIME_UNAVAILABLE",
        },
        "delivery": {"status": "skipped"},
    }


@pytest.mark.asyncio
async def test_runtime_provider_redelivery_startup_failure_stays_in_delivery_layer() -> None:
    provider = ca.ContentAnalysisRuntimeProvider(
        config_loader=lambda: (_ for _ in ()).throw(RuntimeError("private config")),
        session_factory=lambda: FakeSession(1),
        http_factory=lambda: FakeHttp(1),
    )

    result = await provider.redeliver({}, "77", "identity")

    assert result == {
        "failure_stage": "delivery",
        "feishu_relation": {"status": "skipped"},
        "internal_result": {"status": "skipped"},
        "delivery": {
            "status": "failed",
            "reason_code": "EXECUTOR_RUNTIME_UNAVAILABLE",
        },
    }
    assert "private" not in str(result)


def test_runtime_provider_construction_has_no_config_session_or_network_side_effects() -> None:
    calls = []

    ca.ContentAnalysisRuntimeProvider(
        config_loader=lambda: calls.append("config"),
        session_factory=lambda: calls.append("session"),
        http_factory=lambda: calls.append("http"),
    )

    assert calls == []


def test_runtime_provider_builder_defers_config_and_resource_creation_until_call() -> None:
    calls = []

    provider = ca.build_content_analysis_runtime_provider(
        {},
        session_factory=lambda: calls.append("session"),
        http_factory=lambda: calls.append("http"),
    )

    assert isinstance(provider, ca.ContentAnalysisRuntimeProvider)
    assert calls == []


@pytest.mark.parametrize(
    ("url", "expected"),
    (
        ("https://www.douyin.com/video/1", "douyin"),
        ("https://v.douyin.com/abc", "douyin"),
        ("https://douyin.com.evil.example/video/1", "unknown"),
        ("https://evil.example/?next=douyin.com", "unknown"),
        ("https://example.invalid/video/1", "unknown"),
        (None, "unknown"),
    ),
)
def test_source_platform_is_never_assumed_without_field_or_link_evidence(url, expected) -> None:
    platform, limitation = ca.infer_source_platform(url)
    assert platform == expected
    assert (limitation is None) == (expected == "douyin")
