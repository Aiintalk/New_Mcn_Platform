"""内容分析智能体任务配置管理员接口的真实数据库集成测试。"""
import asyncio
import hashlib
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.requests import Request

from app.models.agent_task_config import AgentTaskConfig
from app.models.kol import Kol
from app.models.kol_benchmark import KolBenchmark
from app.models.log import OperationLog
from app.models.task import TaskJob, TaskLog


BASE = "/api/admin/agent-tasks/content-analysis"


def _endpoint(app, suffix: str):
    from app.routers.admin_agent_tasks import router

    path = f"/admin/agent-tasks/content-analysis{suffix}"
    route = next((route for route in router.routes if getattr(route, "path", None) == path), None)
    assert route is not None, f"missing content-analysis endpoint: {path}"
    return route.endpoint


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": BASE, "headers": []})


@pytest_asyncio.fixture
async def content_projects(test_session, admin_user):
    """三个人格和内容规划都已填写的测试项目：一个可运行、一个缺必要配置。"""
    ready = Kol(
        name="cov_ca_ready",
        account_name="ready-account",
        persona="可信人设",
        content_plan="内容规划",
        style_notes="风格备注",
        created_by=admin_user.id,
    )
    missing = Kol(
        name="cov_ca_missing",
        account_name="missing-account",
        persona="可信人设",
        content_plan="内容规划",
        created_by=admin_user.id,
    )
    unselected = Kol(
        name="cov_ca_unselected",
        account_name="unselected-account",
        persona="可信人设",
        content_plan="内容规划",
        created_by=admin_user.id,
    )
    test_session.add_all([ready, missing, unselected])
    await test_session.flush()
    test_session.add(KolBenchmark(
        kol_id=ready.id,
        account_name="content-benchmark",
        account_type="content",
        sec_uid="sec-ready",
        created_by=admin_user.id,
    ))
    test_session.add_all([
        KolBenchmark(
            kol_id=ready.id, account_name="content-missing-sec", account_type="content",
            sec_uid=None, created_by=admin_user.id,
        ),
        KolBenchmark(
            kol_id=ready.id, account_name="livestream-benchmark", account_type="livestream",
            sec_uid=None, created_by=admin_user.id,
        ),
    ])
    test_session.add(AgentTaskConfig(
        agent_code="content-analysis",
        selected_project_ids=[ready.id, missing.id],
        report_root_ref="fixture-report-root",
        updated_by=admin_user.id,
    ))
    await test_session.commit()
    yield {"ready": ready, "missing": missing, "unselected": unselected}
    ids = [ready.id, missing.id, unselected.id]
    task_ids = (await test_session.execute(
        select(TaskJob.id).where(TaskJob.input_payload["project_id"].astext.in_([str(item) for item in ids]))
    )).scalars().all()
    if task_ids:
        await test_session.execute(delete(TaskLog).where(TaskLog.task_id.in_(task_ids)))
        await test_session.execute(delete(TaskJob).where(TaskJob.id.in_(task_ids)))
    await test_session.execute(delete(OperationLog).where(OperationLog.detail["agent_code"].astext == "content-analysis"))
    await test_session.execute(delete(AgentTaskConfig).where(AgentTaskConfig.agent_code == "content-analysis"))
    await test_session.execute(delete(KolBenchmark).where(KolBenchmark.kol_id.in_(ids)))
    await test_session.execute(delete(Kol).where(Kol.name.like("cov_ca_%")))
    await test_session.commit()


@pytest.mark.asyncio
async def test_http_admin_overview_uses_standard_envelope_and_operator_is_denied(
    test_client, admin_headers, operator_headers, content_projects
):
    response = await test_client.get(f"{BASE}/overview", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["code"] == "OK"
    assert body["data"]["agent_code"] == "content-analysis"
    assert body["data"]["delivery_target"] == "feishu_document"
    assert all(item["latest_formal_run"] is None for item in body["data"]["tasks"])
    assert [item["name"] for item in body["data"]["tasks"]] == ["每日项目对标内容分析", "账号人设内容基准更新"]
    assert body["data"]["config_updated_by"] is not None
    assert body["data"]["config_updated_by_name"] == "test_admin" or body["data"]["config_updated_by_name"].startswith("test_admin_")
    assert all(item["next_fixed_run"] is not None for item in body["data"]["tasks"])
    assert set(body["data"]["status_summary"]) == {"today_completed", "current_running", "failed_last_7_days"}

    denied = await test_client.get(f"{BASE}/overview", headers=operator_headers)
    assert denied.status_code == 403
    assert denied.json() == {
        "success": False,
        "code": "PERMISSION_DENIED",
        "message": "无权限访问",
        "data": None,
    }


@pytest.mark.asyncio
async def test_projects_direct_call_reports_only_eligible_projects_and_three_scope_statuses(
    test_session, admin_user, content_projects
):
    from app.main import app

    endpoint = _endpoint(app, "/projects")
    response = await endpoint(
        page=1, page_size=100, keyword="cov_ca_", scope_status="", db=test_session, current_user=admin_user
    )
    items = {item["project_name"]: item for item in response.data["items"]}

    assert items["cov_ca_ready"]["scope_status"] == "selected_ready"
    assert items["cov_ca_missing"]["scope_status"] == "selected_missing"
    assert items["cov_ca_unselected"]["scope_status"] == "unselected"
    assert response.data["pagination"] == {"page": 1, "page_size": 100, "total": 3, "total_pages": 1}
    ready = items["cov_ca_ready"]
    assert ready["project"] == {
        "id": content_projects["ready"].id, "name": "cov_ca_ready",
        "kol_name": "cov_ca_ready", "account_name": "ready-account",
    }
    assert ready["content_benchmark_total"] == 2
    assert ready["content_benchmark_valid_count"] == 1
    assert ready["content_benchmark_relation_status"] == "partial_missing"
    assert ready["content_data_status"] == "ready"
    assert ready["project_context_status"] == "partial_missing"


@pytest.mark.asyncio
async def test_projects_direct_call_caps_page_size_at_100(test_session, admin_user, content_projects):
    from app.main import app

    endpoint = _endpoint(app, "/projects")
    response = await endpoint(
        page=1, page_size=101, keyword="", scope_status="", db=test_session, current_user=admin_user
    )

    assert response.data["pagination"]["page_size"] == 100


@pytest.mark.asyncio
async def test_input_direct_call_exposes_integrated_runtime_sources_without_business_data(
    test_session, admin_user, content_projects
):
    from app.main import app

    endpoint = _endpoint(app, "/projects/{project_id}/input")
    response = await endpoint(content_projects["ready"].id, db=test_session, current_user=admin_user)
    modules = {item["key"]: item for item in response.data["modules"]}

    assert modules["content_benchmarks"]["status"] == "ready"
    assert modules["content_data"]["status"] == "ready"
    assert modules["content_data"]["source"] == "feishu_bitable_runtime"
    assert modules["content_data"]["missing_reason"] is None
    assert modules["historical_analysis"]["status"] == "ready"
    assert modules["historical_analysis"]["source"] == "content_analysis_results/outputs"
    assert modules["formal_result_target"]["status"] == "ready"
    assert modules["formal_result_target"]["source"] == "feishu_document"
    assert {"source", "updated_at", "value", "missing_reason"} <= modules["persona"].keys()


@pytest.mark.asyncio
async def test_optional_context_missing_is_visible_but_does_not_block_selected_ready(
    test_session, admin_user, content_projects
):
    from app.main import app

    projects = await _endpoint(app, "/projects")(
        page=1, page_size=20, keyword="cov_ca_", scope_status="", db=test_session, current_user=admin_user,
    )
    item = next(row for row in projects.data["items"] if row["project_id"] == content_projects["ready"].id)
    modules = (await _endpoint(app, "/projects/{project_id}/input")(
        content_projects["ready"].id, db=test_session, current_user=admin_user,
    )).data["modules"]
    optional = next(row for row in modules if row["key"] == "optional_context")

    assert item["scope_status"] == "selected_ready"
    assert item["project_context_status"] == "partial_missing"
    assert optional["required"] is False
    assert optional["status"] == "missing"
    assert optional["missing_reason"] == "optional_context_missing"
    assert optional["missing_reasons"] == ["BACKGROUND_MISSING", "EXPERIENCE_MISSING", "RELATIONSHIPS_MISSING", "UNIQUE_STORY_MISSING", "EXTRA_NOTES_MISSING"]


@pytest.mark.asyncio
async def test_config_direct_call_deduplicates_and_replaces_scope_with_audit_log(
    test_session, admin_user, content_projects
):
    from app.main import app
    from app.routers.admin_agent_tasks import ConfigRequest

    endpoint = _endpoint(app, "/config")
    response = await endpoint(
        ConfigRequest(selected_project_ids=[content_projects["ready"].id, content_projects["ready"].id]),
        _request(), db=test_session, current_user=admin_user,
    )
    config = (await test_session.execute(
        select(AgentTaskConfig).where(AgentTaskConfig.agent_code == "content-analysis")
    )).scalar_one()
    audit = (await test_session.execute(
        select(OperationLog).where(OperationLog.action == "update_agent_task_config")
    )).scalar_one()

    assert response.data["selected_project_ids"] == [content_projects["ready"].id]
    assert response.data["updated_by"] == admin_user.id
    assert response.data["updated_by_name"] == admin_user.username
    assert response.data["updated_at"] is not None
    assert config.selected_project_ids == [content_projects["ready"].id]
    assert audit.detail == {
        "agent_code": "content-analysis",
        "project_ids": [content_projects["ready"].id],
        "report_root_ref_configured": True,
    }


@pytest.mark.asyncio
async def test_invalid_config_keeps_existing_selection_unchanged(test_session, admin_user, content_projects):
    from app.main import app
    from app.routers.admin_agent_tasks import ConfigRequest

    response = await _endpoint(app, "/config")(
        ConfigRequest(selected_project_ids=[99999999]), _request(), db=test_session, current_user=admin_user,
    )
    config = (await test_session.execute(select(AgentTaskConfig).where(
        AgentTaskConfig.agent_code == "content-analysis"
    ))).scalar_one()

    assert response.code == "VALIDATION_ERROR"
    assert config.selected_project_ids == [content_projects["ready"].id, content_projects["missing"].id]


@pytest.mark.asyncio
async def test_runs_direct_call_converges_overdue_filters_content_tasks_and_hides_other_tools(
    test_session, admin_user, content_projects
):
    from app.main import app

    overdue = TaskJob(
        task_no="cov-ca-overdue", tool_code="content-analysis-daily", tool_name="内容分析", status="pending",
        input_payload={"agent_code": "content-analysis", "task_code": "daily", "project_id": content_projects["ready"].id,
                       "run_type": "test", "deadline_at": "2020-01-01T00:00:00+00:00"},
        result_summary={"controlled_test": True}, created_by=admin_user.id,
    )
    other = TaskJob(
        task_no="cov-ca-other", tool_code="content-analysis-daily", tool_name="内容分析", status="pending",
        input_payload={"agent_code": "other-agent", "project_id": content_projects["ready"].id,
                       "deadline_at": "2020-01-01T00:00:00+00:00"}, created_by=admin_user.id,
    )
    test_session.add_all([overdue, other])
    await test_session.commit()

    endpoint = _endpoint(app, "/runs")
    response = await endpoint(
        page=1, page_size=20, task_code="daily", status="failed", project_id=content_projects["ready"].id,
        run_type="test", started_from=None, started_to=None, db=test_session, current_user=admin_user,
    )

    assert [item["id"] for item in response.data["items"]] == [overdue.id]
    assert response.data["items"][0]["status"] == "failed"
    assert response.data["items"][0]["delivery_target"] == "feishu_document"
    assert response.data["items"][0]["delivery_status"] == "skipped"
    assert response.data["items"][0]["result_status"] == "skipped"
    assert response.data["items"][0]["agent_code"] == "content-analysis"
    assert response.data["items"][0]["task"]["name"] == "每日项目对标内容分析"
    assert response.data["items"][0]["project"] == {
        "id": content_projects["ready"].id,
        "name": "cov_ca_ready",
        "kol_name": "cov_ca_ready",
        "account_name": "ready-account",
    }
    assert response.data["items"][0]["reason_code"] == "TASK_TIMEOUT"
    await test_session.refresh(other)
    assert other.status == "pending"


@pytest.mark.asyncio
async def test_run_detail_direct_call_isolates_non_content_analysis_task(
    test_session, admin_user, content_projects
):
    from app.main import app

    other = TaskJob(
        task_no="cov-ca-hidden", tool_code="other-tool", tool_name="其他", status="success",
        input_payload={"project_id": content_projects["ready"].id}, created_by=admin_user.id,
    )
    test_session.add(other)
    await test_session.commit()
    endpoint = _endpoint(app, "/runs/{run_id}")
    response = await endpoint(other.id, db=test_session, current_user=admin_user)

    assert response.success is False
    assert response.code == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_run_detail_rejects_matching_tool_code_with_wrong_agent_payload(test_session, admin_user, content_projects):
    from app.main import app

    wrong_agent = TaskJob(
        task_no="cov-ca-detail-wrong-agent", tool_code="content-analysis-daily", tool_name="内容分析", status="success",
        input_payload={"agent_code": "other-agent", "project_id": content_projects["ready"].id},
        created_by=admin_user.id,
    )
    test_session.add(wrong_agent)
    await test_session.commit()

    response = await _endpoint(app, "/runs/{run_id}")(
        wrong_agent.id, db=test_session, current_user=admin_user,
    )

    assert response.code == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_runs_rejects_matching_tool_code_with_wrong_agent_payload(test_session, admin_user, content_projects):
    from app.main import app

    wrong_agent = TaskJob(
        task_no="cov-ca-wrong-agent", tool_code="content-analysis-daily", tool_name="内容分析", status="success",
        input_payload={"agent_code": "other-agent", "task_code": "daily", "project_id": content_projects["ready"].id,
                       "run_type": "auto", "triggered_at": "2026-09-02T00:00:00+00:00"},
        result_summary={}, created_by=admin_user.id,
    )
    test_session.add(wrong_agent)
    await test_session.commit()
    response = await _endpoint(app, "/runs")(
        page=1, page_size=20, task_code="daily", status="success", project_id=content_projects["ready"].id,
        run_type="auto", started_from=None, started_to=None, db=test_session, current_user=admin_user,
    )

    assert response.data["items"] == []


@pytest.mark.asyncio
async def test_runs_filter_in_database_by_all_dimensions_with_boundary_and_pagination(
    test_session, admin_user, content_projects
):
    from app.main import app

    ready_id = content_projects["ready"].id
    missing_id = content_projects["missing"].id
    test_session.add_all([
        TaskJob(
            task_no="cov-ca-filter-daily", tool_code="content-analysis-daily", tool_name="内容分析", status="success",
            input_payload={"agent_code": "content-analysis", "task_code": "daily", "project_id": ready_id,
                           "run_type": "auto", "triggered_at": "2026-09-01T00:00:00+00:00"},
            result_summary={}, created_by=admin_user.id,
        ),
        TaskJob(
            task_no="cov-ca-filter-weekly", tool_code="content-analysis-weekly", tool_name="内容分析", status="failed",
            input_payload={"agent_code": "content-analysis", "task_code": "weekly", "project_id": missing_id,
                           "run_type": "manual", "triggered_at": "2026-09-02T00:00:00+00:00"},
            result_summary={}, created_by=admin_user.id,
        ),
        TaskJob(
            task_no="cov-ca-filter-queued", tool_code="content-analysis-daily", tool_name="内容分析", status="pending",
            input_payload={"agent_code": "content-analysis", "task_code": "daily", "project_id": ready_id,
                           "run_type": "test", "triggered_at": "2026-09-03T00:00:00+00:00", "deadline_at": "2030-01-01T00:00:00+00:00"},
            result_summary={}, created_by=admin_user.id,
        ),
    ])
    await test_session.commit()
    endpoint = _endpoint(app, "/runs")
    daily = await endpoint(
        page=1, page_size=1, task_code="daily", status="", project_id=ready_id, run_type="auto",
        started_from=datetime(2026, 9, 1, tzinfo=timezone.utc), started_to=datetime(2026, 9, 1, tzinfo=timezone.utc),
        db=test_session, current_user=admin_user,
    )
    queued = await endpoint(
        page=1, page_size=20, task_code="daily", status="queued", project_id=ready_id, run_type="test",
        started_from=None, started_to=None, db=test_session, current_user=admin_user,
    )
    weekly = await endpoint(
        page=1, page_size=20, task_code="weekly", status="failed", project_id=missing_id, run_type="manual",
        started_from=None, started_to=None, db=test_session, current_user=admin_user,
    )

    assert daily.data["pagination"] == {"page": 1, "page_size": 1, "total": 1, "total_pages": 1}
    assert daily.data["items"][0]["task_no"] == "cov-ca-filter-daily"
    assert queued.data["items"][0]["task_no"] == "cov-ca-filter-queued"
    assert weekly.data["items"][0]["task_no"] == "cov-ca-filter-weekly"
    overview = await _endpoint(app, "/overview")(db=test_session, current_user=admin_user)
    daily_task = next(item for item in overview.data["tasks"] if item["task_code"] == "daily")
    assert daily_task["latest_formal_run"]["task_no"] == "cov-ca-filter-daily"


@pytest.mark.asyncio
async def test_controlled_test_and_retry_direct_calls_write_audits_without_outputs(
    test_session, admin_user, content_projects
):
    from app.main import app
    from app.routers.admin_agent_tasks import RetryRunRequest, TestRunRequest

    test_endpoint = _endpoint(app, "/test-runs")
    executor = _Stage2Executor()
    tested = await test_endpoint(
        TestRunRequest(
            task_code="daily",
            project_id=content_projects["ready"].id,
            request_id="stage1-compat-test",
        ),
        _request(), db=test_session, current_user=admin_user, executor=executor,
    )
    tested_id = tested.data["id"]
    task = (await test_session.execute(select(TaskJob).where(TaskJob.id == tested_id))).scalar_one()
    assert task.status == "success"
    assert task.output_id is None
    assert tested.data["project"] == {
        "id": content_projects["ready"].id,
        "name": "cov_ca_ready",
        "kol_name": "cov_ca_ready",
        "account_name": "ready-account",
    }

    failed = TaskJob(
        task_no="cov-ca-failed", tool_code="content-analysis-daily", tool_name="内容分析", status="failed",
        input_payload={"agent_code": "content-analysis", "task_code": "daily", "project_id": content_projects["ready"].id,
                       "business_date": "2026-09-01", "window_start": "2026-08-29T00:00:00+08:00",
                       "window_end": "2026-09-01T00:00:00+08:00",
                       "delivery_target": {"scope": "formal", "report_root_ref": "fixture-report-root"}},
        result_summary={}, created_by=admin_user.id,
    )
    test_session.add(failed)
    await test_session.flush()
    test_session.add(TaskLog(
        task_id=failed.id, step_code="failed", step_name="失败", status="failed", message="受控失败记录",
    ))
    await test_session.commit()
    retry_endpoint = _endpoint(app, "/runs/{run_id}/retry")
    retried = await retry_endpoint(
        failed.id,
        _request(),
        body=RetryRunRequest(request_id="stage1-compat-retry"),
        db=test_session,
        current_user=admin_user,
        executor=executor,
    )
    original_detail = await _endpoint(app, "/runs/{run_id}")(
        failed.id, db=test_session, current_user=admin_user,
    )

    assert retried.data["status"] == "success"
    assert retried.data["retry_of_task_id"] == failed.id
    assert retried.data["project"] == {
        "id": content_projects["ready"].id,
        "name": "cov_ca_ready",
        "kol_name": "cov_ca_ready",
        "account_name": "ready-account",
    }
    assert original_detail.data["retried_by_task_ids"] == [retried.data["id"]]
    assert original_detail.data["agent_code"] == "content-analysis"
    assert original_detail.data["project"] == {
        "id": content_projects["ready"].id,
        "name": "cov_ca_ready",
        "kol_name": "cov_ca_ready",
        "account_name": "ready-account",
    }
    assert original_detail.data["logs"]
    assert (await test_session.execute(select(OperationLog).where(
        OperationLog.action.in_(("create_agent_task_test_run", "retry_agent_task_run"))
    ))).scalars().all()


@pytest.mark.asyncio
async def test_controlled_test_direct_call_returns_not_run_when_required_benchmark_is_missing(
    test_session, admin_user, content_projects
):
    from app.main import app
    from app.routers.admin_agent_tasks import TestRunRequest

    endpoint = _endpoint(app, "/test-runs")
    response = await endpoint(
        TestRunRequest(
            task_code="daily",
            project_id=content_projects["missing"].id,
            request_id="missing-config-test",
        ),
        _request(), db=test_session, current_user=admin_user, executor=_Stage2Executor(),
    )

    assert response.data["status"] == "not_run"
    assert response.data["database_precheck"]["reason_code"] == "CONTENT_BENCHMARK_SEC_UID_MISSING"
    assert response.data["feishu_relation"] == {"status": "skipped"}
    task = (await test_session.execute(select(TaskJob).where(TaskJob.id == response.data["id"]))).scalar_one()
    assert "deadline_at" not in task.input_payload


@pytest.mark.asyncio
async def test_non_failed_retry_leaves_task_count_unchanged(test_session, admin_user, content_projects):
    from app.main import app
    from app.routers.admin_agent_tasks import RetryRunRequest

    pending = TaskJob(
        task_no="cov-ca-pending", tool_code="content-analysis-daily", tool_name="内容分析", status="pending",
        input_payload={"agent_code": "content-analysis", "task_code": "daily", "project_id": content_projects["ready"].id},
        result_summary={}, created_by=admin_user.id,
    )
    test_session.add(pending)
    await test_session.commit()
    before = (await test_session.execute(select(TaskJob).where(TaskJob.tool_code == "content-analysis-daily"))).scalars().all()
    response = await _endpoint(app, "/runs/{run_id}/retry")(
        pending.id,
        _request(),
        body=RetryRunRequest(request_id="non-failed-retry"),
        db=test_session,
        current_user=admin_user,
        executor=_Stage2Executor(),
    )
    after = (await test_session.execute(select(TaskJob).where(TaskJob.tool_code == "content-analysis-daily"))).scalars().all()

    assert response.code == "VALIDATION_ERROR"
    assert len(after) == len(before)


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,json_body", [
    ("get", "/overview", None),
    ("get", "/projects", None),
    ("get", "/projects/1/input", None),
    ("get", "/weekly-accounts", None),
    ("put", "/config", {"selected_project_ids": []}),
    ("get", "/runs", None),
    ("get", "/runs/1", None),
    ("post", "/test-runs", {"task_code": "daily", "project_id": 1}),
    ("post", "/runs/1/retry", {"request_id": "permission-check"}),
])
async def test_all_agent_task_endpoints_reject_operator(test_client, operator_headers, method, path, json_body):
    response = await test_client.request(method, f"{BASE}{path}", headers=operator_headers, json=json_body)

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_http_validation_error_uses_standard_envelope(test_client, admin_headers):
    response = await test_client.post(f"{BASE}/test-runs", headers=admin_headers, json={"task_code": "daily"})

    assert response.status_code == 422
    assert response.json() == {
        "success": False, "code": "VALIDATION_ERROR", "message": "请求参数校验失败", "data": None,
    }


@pytest.mark.asyncio
async def test_first_config_save_is_atomic_under_two_sessions(test_engine, admin_user):
    from app.main import app
    from app.routers.admin_agent_tasks import ConfigRequest

    project = Kol(name="cov_ca_concurrent", persona="人设", content_plan="规划", created_by=admin_user.id)
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as seed:
        seed.add(project)
        await seed.commit()
        await seed.refresh(project)
    async def save_once():
        async with session_factory() as session:
            return await _endpoint(app, "/config")(
                ConfigRequest(selected_project_ids=[project.id]), _request(), db=session, current_user=admin_user,
            )
    outcomes = await asyncio.gather(save_once(), save_once())
    async with session_factory() as verify:
        configs = (await verify.execute(select(AgentTaskConfig).where(
            AgentTaskConfig.agent_code == "content-analysis"
        ))).scalars().all()
        await verify.execute(delete(OperationLog).where(OperationLog.detail["agent_code"].astext == "content-analysis"))
        await verify.execute(delete(AgentTaskConfig).where(AgentTaskConfig.agent_code == "content-analysis"))
        await verify.execute(delete(Kol).where(Kol.name == "cov_ca_concurrent"))
        await verify.commit()

    assert [item.success for item in outcomes] == [True, True]
    assert len(configs) == 1


class _Stage2Executor:
    def __init__(self):
        self.execute_calls = []
        self.redeliver_calls = []

    async def execute(self, envelope):
        self.execute_calls.append(envelope)
        return {
            "feishu_relation": {"status": "ready", "content_read_status": "ready"},
            "internal_result": {
                "status": "success", "outcome": "content", "internal_result_id": "internal-test",
            },
            "delivery": {
                "status": "success", "delivery_identity": "document-test",
            },
        }

    async def redeliver(self, envelope, internal_result_id, delivery_identity):
        self.redeliver_calls.append((envelope, internal_result_id, delivery_identity))
        return await self.execute(envelope)


@pytest.mark.asyncio
async def test_weekly_test_accounts_include_all_ready_projects_and_remain_filtered_paginated_admin_only(
    test_client, admin_headers, operator_headers, test_session, content_projects,
):
    ready_id = content_projects["ready"].id
    missing_id = content_projects["missing"].id
    unselected_id = content_projects["unselected"].id
    test_session.add_all([
        KolBenchmark(
            kol_id=ready_id, account_name="共享账号 Z", account_type="content",
            sec_uid=" shared-sec ", created_by=content_projects["ready"].created_by,
        ),
        KolBenchmark(
            kol_id=missing_id, account_name="共享账号 A", account_type="content",
            sec_uid="shared-sec", created_by=content_projects["ready"].created_by,
        ),
        KolBenchmark(
            kol_id=unselected_id, account_name="共享账号 B", account_type="content",
            sec_uid="shared-sec", created_by=content_projects["ready"].created_by,
        ),
        KolBenchmark(
            kol_id=unselected_id, account_name="未选择账号", account_type="content",
            sec_uid="unselected-only", created_by=content_projects["ready"].created_by,
        ),
    ])
    await test_session.commit()

    response = await test_client.get(
        f"{BASE}/weekly-accounts?page=1&page_size=1&keyword=shared",
        headers=admin_headers,
    )
    unselected_scope = await test_client.get(
        f"{BASE}/weekly-accounts?project_id={unselected_id}",
        headers=admin_headers,
    )
    denied = await test_client.get(f"{BASE}/weekly-accounts", headers=operator_headers)

    assert response.status_code == 200
    assert response.json()["data"] == {
        "items": [{
            "account_key": "shared-sec",
            "account_name": "共享账号 A",
            "project_ids": sorted([ready_id, missing_id, unselected_id]),
        }],
        "pagination": {"page": 1, "page_size": 1, "total": 1, "total_pages": 1},
    }
    assert denied.status_code == 403
    assert denied.json()["code"] == "PERMISSION_DENIED"
    assert unselected_scope.json()["data"] == {
        "items": [
            {
                "account_key": "shared-sec",
                "account_name": "共享账号 B",
                "project_ids": [unselected_id],
            },
            {
                "account_key": "unselected-only",
                "account_name": "未选择账号",
                "project_ids": [unselected_id],
            },
        ],
        "pagination": {"page": 1, "page_size": 20, "total": 2, "total_pages": 1},
    }


@pytest.mark.asyncio
async def test_config_saves_report_root_without_writing_reference_to_audit(
    test_session, admin_user, content_projects,
):
    from app.main import app
    from app.routers.admin_agent_tasks import ConfigRequest

    secret_reference = "folder-reference-must-not-enter-log"
    response = await _endpoint(app, "/config")(
        ConfigRequest(
            selected_project_ids=[content_projects["ready"].id],
            report_root_ref=secret_reference,
        ),
        _request(), db=test_session, current_user=admin_user,
    )
    config = await test_session.scalar(select(AgentTaskConfig).where(
        AgentTaskConfig.agent_code == "content-analysis",
    ))
    audit = await test_session.scalar(select(OperationLog).where(
        OperationLog.action == "update_agent_task_config",
    ).order_by(OperationLog.id.desc()))

    assert response.data["report_root_ref"] == secret_reference
    assert config.report_root_ref == secret_reference
    assert audit.detail == {
        "agent_code": "content-analysis",
        "project_ids": [content_projects["ready"].id],
        "report_root_ref_configured": True,
    }
    assert secret_reference not in str(audit.detail)
    overview = await _endpoint(app, "/overview")(db=test_session, current_user=admin_user)
    assert overview.data["report_root_ref"] == secret_reference


@pytest.mark.asyncio
async def test_config_normalizes_blank_report_root_to_null_and_unconfigured(
    test_session, admin_user, content_projects,
):
    from app.main import app
    from app.routers.admin_agent_tasks import ConfigRequest

    response = await _endpoint(app, "/config")(
        ConfigRequest(
            selected_project_ids=[content_projects["ready"].id],
            report_root_ref="  \n  ",
        ),
        _request(), db=test_session, current_user=admin_user,
    )
    config = await test_session.scalar(select(AgentTaskConfig).where(
        AgentTaskConfig.agent_code == "content-analysis",
    ))
    audit = await test_session.scalar(select(OperationLog).where(
        OperationLog.action == "update_agent_task_config",
    ).order_by(OperationLog.id.desc()))
    overview = await _endpoint(app, "/overview")(db=test_session, current_user=admin_user)

    assert response.data["report_root_ref"] is None
    assert config.report_root_ref is None
    assert audit.detail["report_root_ref_configured"] is False
    assert overview.data["report_root_ref_configured"] is False


@pytest.mark.asyncio
async def test_weekly_candidates_remain_browsable_but_test_is_not_run_without_report_root(
    test_session, admin_user, content_projects,
):
    from app.main import app
    from app.routers.admin_agent_tasks import TestRunRequest

    config = await test_session.scalar(select(AgentTaskConfig).where(
        AgentTaskConfig.agent_code == "content-analysis",
    ))
    config.report_root_ref = None
    await test_session.commit()
    candidates = await _endpoint(app, "/weekly-accounts")(
        page=1, page_size=20, keyword="sec-ready", project_id=None,
        db=test_session, current_user=admin_user,
    )
    executor = _Stage2Executor()
    tested = await _endpoint(app, "/test-runs")(
        TestRunRequest(
            task_code="weekly", account_key="sec-ready", request_id="missing-root-weekly",
        ),
        _request(), db=test_session, current_user=admin_user, executor=executor,
    )

    assert candidates.data["pagination"]["total"] == 1
    assert tested.data["status"] == "not_run"
    assert tested.data["database_precheck"]["reason_code"] == "REPORT_ROOT_REF_MISSING"
    assert executor.execute_calls == []


@pytest.mark.asyncio
async def test_weekly_test_run_derives_projects_and_writes_redacted_audit(
    test_session, admin_user, content_projects,
):
    from app.main import app
    from app.routers.admin_agent_tasks import TestRunRequest

    account_key = "sec-ready"
    executor = _Stage2Executor()
    response = await _endpoint(app, "/test-runs")(
        TestRunRequest(task_code="weekly", account_key=account_key, request_id="weekly-request-1"),
        _request(), db=test_session, current_user=admin_user, executor=executor,
    )
    audit = await test_session.scalar(select(OperationLog).where(
        OperationLog.action == "create_agent_task_test_run",
    ).order_by(OperationLog.id.desc()))

    assert response.data["status"] == "success"
    assert executor.execute_calls[0]["execution"] == {
        "object_type": "account",
        "account_key": account_key,
        "project_ids": [content_projects["ready"].id],
        "weekly_batch_id": "weekly-test-weekly-request-1",
        "batch_size": 1,
        "batch_position": 1,
    }
    assert audit.detail["execution_type"] == "account"
    assert account_key not in str(audit.detail)


@pytest.mark.asyncio
async def test_repeated_weekly_test_request_returns_same_task_and_redacted_audits(
    test_session, admin_user, content_projects,
):
    from app.main import app
    from app.routers.admin_agent_tasks import TestRunRequest

    account_key = "sec-ready"
    body = TestRunRequest(
        task_code="weekly",
        account_key=account_key,
        request_id="weekly-repeat-request",
    )
    executor = _Stage2Executor()
    endpoint = _endpoint(app, "/test-runs")

    first = await endpoint(
        body, _request(), db=test_session, current_user=admin_user, executor=executor,
    )
    second = await endpoint(
        body, _request(), db=test_session, current_user=admin_user, executor=executor,
    )
    audits = (await test_session.execute(select(OperationLog).where(
        OperationLog.action == "create_agent_task_test_run",
    ).order_by(OperationLog.id))).scalars().all()

    assert first.data["id"] == second.data["id"]
    assert len(executor.execute_calls) == 1
    assert len(audits) == 2
    assert all(account_key not in str(audit.detail) for audit in audits)
    assert all("report_root_ref" not in str(audit.detail) for audit in audits)


@pytest.mark.asyncio
async def test_runs_expose_four_layers_and_filter_nested_execution(
    test_session, admin_user, content_projects,
):
    from app.main import app

    ready_id = content_projects["ready"].id
    account_key = "nested-account-key"
    summary = {
        "failure_stage": None,
        "execution": {
            "object_type": "account", "account_key": account_key, "project_ids": [ready_id],
        },
        "database_precheck": {"status": "ready"},
        "feishu_relation": {"status": "ready"},
        "internal_result": {"status": "success"},
        "delivery": {"status": "success"},
    }
    task = TaskJob(
        task_no="cov-ca-stage2-nested", tool_code="content-analysis-weekly",
        tool_name="内容分析", status="success",
        input_payload={
            "agent_code": "content-analysis", "task_code": "weekly", "run_type": "auto",
            "execution": {
                "object_type": "account", "account_key": account_key, "project_ids": [ready_id],
            },
            "business_date": "2026-09-04", "triggered_at": "2026-09-05T01:00:00+08:00",
        },
        result_summary=summary, created_by=admin_user.id,
    )
    test_session.add(task)
    await test_session.commit()

    response = await _endpoint(app, "/runs")(
        page=1, page_size=20, task_code="weekly", status="success", project_id=ready_id,
        account_key=account_key, run_type="auto", started_from=None, started_to=None,
        db=test_session, current_user=admin_user,
    )
    item = response.data["items"][0]

    assert item["id"] == task.id
    assert item["execution"] == {
        "object_type": "account",
        "account_key_hash": hashlib.sha256(account_key.encode("utf-8")).hexdigest()[:16],
        "project_ids": [ready_id],
    }
    assert item["failure_stage"] is None
    assert item["database_precheck"] == {"status": "ready"}
    assert item["feishu_relation"] == {"status": "ready"}
    assert item["internal_result"] == {"status": "success"}
    assert item["delivery"] == {"status": "success"}
    detail = await _endpoint(app, "/runs/{run_id}")(
        task.id, db=test_session, current_user=admin_user,
    )
    assert account_key not in str(detail.data)
    assert detail.data["controlled_result_summary"]["execution"]["account_key_hash"] == item["execution"]["account_key_hash"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["delivery", "timeout"])
async def test_retry_endpoint_uses_request_id_idempotently_and_redacts_audit(
    failure_stage, test_session, admin_user, content_projects,
):
    from app.main import app
    from app.routers.admin_agent_tasks import RetryRunRequest

    ready_id = content_projects["ready"].id
    original = TaskJob(
        task_no=f"cov-ca-stage2-retry-{failure_stage}", tool_code="content-analysis-daily",
        tool_name="内容分析", status="failed",
        input_payload={
            "agent_code": "content-analysis", "task_code": "daily", "run_type": "auto",
            "business_date": "2026-09-04",
            "analysis_window": {
                "start": "2026-09-02T00:00:00+08:00", "end": "2026-09-05T00:00:00+08:00",
                "timezone": "Asia/Shanghai", "end_exclusive": True,
            },
            "execution": {"object_type": "project", "project_id": ready_id},
            "idempotency": {
                "run_key": "old-run", "internal_result_key": "old-internal",
                "document_key": "old-document",
            },
            "delivery_target": {"report_root_ref": "secret-root", "scope": "formal"},
        },
        result_summary={
            "failure_stage": failure_stage, "database_precheck": {"status": "ready"},
            "feishu_relation": {"status": "ready"},
            "internal_result": {"status": "success", "internal_result_id": "internal-1"},
            "delivery": {"status": "failed", "delivery_identity": "delivery-1"},
        },
        created_by=admin_user.id,
    )
    test_session.add(original)
    await test_session.commit()
    executor = _Stage2Executor()
    endpoint = _endpoint(app, "/runs/{run_id}/retry")
    body = RetryRunRequest(request_id="retry-request-1")

    first = await endpoint(
        original.id, _request(), body=body, db=test_session,
        current_user=admin_user, executor=executor,
    )
    second = await endpoint(
        original.id, _request(), body=body, db=test_session,
        current_user=admin_user, executor=executor,
    )
    audits = (await test_session.execute(select(OperationLog).where(
        OperationLog.action == "retry_agent_task_run",
    ))).scalars().all()

    assert first.data["id"] == second.data["id"]
    assert len(executor.redeliver_calls) == 1
    assert len(audits) == 2
    assert all("secret-root" not in str(audit.detail) for audit in audits)
    assert all(audit.detail["retry_mode"] == "delivery_only" for audit in audits)


@pytest.mark.asyncio
async def test_retry_endpoint_rejects_legacy_blank_report_root_without_execution(
    test_session, admin_user, content_projects,
):
    from app.main import app
    from app.routers.admin_agent_tasks import RetryRunRequest

    original = TaskJob(
        task_no="cov-ca-stage2-blank-root-retry",
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
            "execution": {
                "object_type": "project",
                "project_id": content_projects["ready"].id,
            },
            "idempotency": {
                "run_key": "legacy-blank-root-run",
                "internal_result_key": "legacy-blank-root-internal",
                "document_key": "legacy-blank-root-document",
            },
            "delivery_target": {"report_root_ref": "   ", "scope": "formal"},
        },
        result_summary={
            "failure_stage": "analysis",
            "database_precheck": {"status": "ready"},
            "feishu_relation": {"status": "ready"},
            "internal_result": {"status": "failed", "reason_code": "ANALYSIS_FAILED"},
            "delivery": {"status": "skipped"},
        },
        created_by=admin_user.id,
    )
    test_session.add(original)
    await test_session.commit()
    executor = _Stage2Executor()

    response = await _endpoint(app, "/runs/{run_id}/retry")(
        original.id,
        _request(),
        body=RetryRunRequest(request_id="blank-root-retry-request"),
        db=test_session,
        current_user=admin_user,
        executor=executor,
    )
    retries = (await test_session.execute(select(TaskJob).where(
        TaskJob.input_payload["retry"]["retry_of_task_id"].astext == str(original.id),
    ))).scalars().all()

    assert response.success is False
    assert response.code == "VALIDATION_ERROR"
    assert response.message == "原任务未配置报告根目录，请先配置后发起新任务"
    assert executor.execute_calls == []
    assert executor.redeliver_calls == []
    assert retries == []


def test_test_and_retry_request_ids_reject_blank_values():
    from app.routers.admin_agent_tasks import RetryRunRequest, TestRunRequest

    with pytest.raises(ValidationError):
        TestRunRequest(task_code="weekly", account_key="sec-1", request_id="  ")
    with pytest.raises(ValidationError):
        RetryRunRequest(request_id="")


@pytest.mark.asyncio
async def test_invalid_or_unregistered_executor_returns_standard_503(
    test_client, admin_headers, content_projects,
):
    from app.services.agent_task_execution_contract import register_content_analysis_executor

    class ExecuteOnly:
        async def execute(self, envelope):
            return {}

    expected = {
        "success": False,
        "code": "SERVICE_UNAVAILABLE",
        "message": "内容分析执行器尚未注册或不符合合同",
        "data": None,
    }
    try:
        register_content_analysis_executor(ExecuteOnly())
        invalid = await test_client.post(
            f"{BASE}/test-runs",
            headers=admin_headers,
            json={
                "task_code": "daily",
                "project_id": content_projects["ready"].id,
                "request_id": "invalid-executor",
            },
        )
        register_content_analysis_executor(None)
        missing = await test_client.post(
            f"{BASE}/test-runs",
            headers=admin_headers,
            json={
                "task_code": "daily",
                "project_id": content_projects["ready"].id,
                "request_id": "missing-executor",
            },
        )
    finally:
        register_content_analysis_executor(None)

    assert invalid.status_code == 503
    assert invalid.json() == expected
    assert missing.status_code == 503
    assert missing.json() == expected


class _BlockingRouteExecutor(_Stage2Executor):
    def __init__(self):
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(self, envelope):
        self.execute_calls.append(envelope)
        self.started.set()
        await self.release.wait()
        return {
            "feishu_relation": {"status": "ready", "content_read_status": "ready"},
            "internal_result": {
                "status": "success", "outcome": "content", "internal_result_id": "route-internal",
            },
            "delivery": {"status": "success", "delivery_identity": "route-document"},
        }


@pytest.mark.asyncio
async def test_test_run_persists_task_and_operation_log_before_executor_finishes(
    test_engine, test_session, admin_user, content_projects,
):
    from app.main import app
    from app.routers.admin_agent_tasks import TestRunRequest

    request_id = f"visible-route-{content_projects['ready'].id}"
    executor = _BlockingRouteExecutor()
    call = asyncio.create_task(_endpoint(app, "/test-runs")(
        TestRunRequest(
            task_code="daily",
            project_id=content_projects["ready"].id,
            request_id=request_id,
        ),
        _request(), db=test_session, current_user=admin_user, executor=executor,
    ))
    await asyncio.wait_for(executor.started.wait(), timeout=2)
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as observer:
            task = await observer.scalar(select(TaskJob).where(
                TaskJob.input_payload["retry"]["request_id"].astext == request_id,
            ))
            audit = await observer.scalar(select(OperationLog).where(
                OperationLog.action == "create_agent_task_test_run",
            ).order_by(OperationLog.id.desc()))
            assert task is not None
            assert task.status == "processing"
            assert audit is not None
            assert audit.target_id == task.id
    finally:
        executor.release.set()
        await call


@pytest.mark.asyncio
async def test_runs_identify_weekly_batch_finalize_as_internal_batch_object(
    test_session, admin_user,
):
    from app.main import app

    batch_id = "content-analysis:weekly:monitor-finalize"
    execution = {
        "object_type": "weekly_batch_finalize",
        "weekly_batch_id": batch_id,
        "batch_size": 3,
        "project_ids": [7, 9],
        "finalize_version": "state-v1",
    }
    task = TaskJob(
        task_no="cov-ca-weekly-finalize-monitor",
        tool_code="content-analysis-weekly",
        tool_name="内容分析",
        status="success",
        input_payload={
            "agent_code": "content-analysis",
            "task_code": "weekly",
            "run_type": "auto",
            "business_date": "2026-09-06",
            "triggered_at": "2026-09-07T01:05:00+08:00",
            "execution": execution,
            "delivery_target": {"scope": "formal", "report_root_ref": "private-root"},
        },
        result_summary={
            "execution": execution,
            "failure_stage": None,
            "database_precheck": {"status": "ready"},
            "feishu_relation": {"status": "skipped"},
            "internal_result": {
                "status": "success", "outcome": "content",
                "internal_result_id": "weekly-summary-v1",
            },
            "delivery": {"status": "success", "delivery_identity": "weekly-document"},
        },
        created_by=admin_user.id,
    )
    test_session.add(task)
    await test_session.commit()

    response = await _endpoint(app, "/runs")(
        page=1, page_size=20, task_code="weekly", status="success",
        project_id=None, account_key="", run_type="auto",
        started_from=None, started_to=None, db=test_session, current_user=admin_user,
    )
    item = next(row for row in response.data["items"] if row["id"] == task.id)

    assert item["task"]["name"] == "周批次收尾"
    assert item["execution"] == execution
    assert "account_key_hash" not in item["execution"]
    detail = await _endpoint(app, "/runs/{run_id}")(
        task.id, db=test_session, current_user=admin_user,
    )
    assert "private-root" not in str(detail.data)
