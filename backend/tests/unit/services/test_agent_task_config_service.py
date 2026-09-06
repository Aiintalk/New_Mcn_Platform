"""内容分析任务配置领域服务的行为测试。"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.kol import Kol
from app.models.kol_benchmark import KolBenchmark
from app.models.task import TaskJob, TaskLog
from app.services.agent_task_config_service import (
    AGENT_CODE,
    TOOL_CODE_DAILY,
    calculate_window,
    converge_overdue_tasks,
    get_project_input_status,
    is_project_eligible,
    retry_failed_task,
    run_controlled_task,
    _timeout_task_if_active,
)


SHANGHAI = timezone(timedelta(hours=8))


def test_project_eligibility_requires_active_kol_and_nonblank_enrollment_fields():
    assert is_project_eligible(Kol(name="合格", persona="定位", content_plan="计划"))
    assert not is_project_eligible(Kol(name="缺人格", persona=" \n", content_plan="计划"))
    assert not is_project_eligible(Kol(name="已删除", persona="定位", content_plan="计划", deleted_at=datetime.now(timezone.utc)))


def test_input_status_requires_content_benchmark_sec_uid_but_marks_optional_context_limited():
    project = Kol(
        name="项目",
        persona="定位",
        content_plan="计划",
        background=" ",
        experience="经历",
        relationships="关系",
        unique_story="故事",
        extra_notes="补充",
        style_notes=None,
    )
    missing = get_project_input_status(project, [KolBenchmark(account_name="内容对标", account_type="content", sec_uid=" ")])
    assert missing["ready"] is False
    assert missing["required_missing_reasons"] == ["CONTENT_BENCHMARK_SEC_UID_MISSING"]
    assert missing["input_limited"] is True
    assert missing["input_limited_reasons"] == ["BACKGROUND_MISSING", "STYLE_NOTES_MISSING"]

    ready = get_project_input_status(project, [KolBenchmark(account_name="内容对标", account_type="content", sec_uid="sec-1")])
    assert ready["ready"] is True


def test_windows_are_complete_previous_shanghai_natural_days():
    triggered_at = datetime(2026, 9, 3, 15, 30, tzinfo=timezone.utc)
    daily = calculate_window("daily", triggered_at)
    weekly = calculate_window("weekly", triggered_at)
    assert daily == {
        "business_date": "2026-09-02",
        "window_start": "2026-08-31T00:00:00+08:00",
        "window_end": "2026-09-03T00:00:00+08:00",
    }
    assert weekly == {
        "business_date": "2026-09-02",
        "window_start": "2026-08-04T00:00:00+08:00",
        "window_end": "2026-09-03T00:00:00+08:00",
    }


@pytest.mark.asyncio
async def test_controlled_run_records_three_state_logs_and_never_creates_output(test_session, admin_user):
    project = Kol(name="合格项目", persona="定位", content_plan="计划", background="")
    test_session.add(project)
    await test_session.flush()
    test_session.add(KolBenchmark(kol_id=project.id, account_name="对标", account_type="content", sec_uid="sec-1"))
    await test_session.commit()

    triggered_at = datetime(2026, 9, 3, 1, 0, tzinfo=timezone.utc)
    task = await run_controlled_task(test_session, project_id=project.id, task_code="daily", created_by=admin_user.id, triggered_at=triggered_at)
    await test_session.commit()

    assert task.status == "success"
    assert task.tool_code == TOOL_CODE_DAILY
    assert task.output_id is None
    assert task.input_payload == {
        "agent_code": AGENT_CODE,
        "task_code": "daily",
        "project_id": project.id,
        "run_type": "test",
        "business_date": "2026-09-02",
        "window_start": "2026-08-31T00:00:00+08:00",
        "window_end": "2026-09-03T00:00:00+08:00",
        "triggered_at": "2026-09-03T01:00:00+00:00",
        "deadline_at": "2026-09-03T13:00:00+00:00",
    }
    assert task.result_summary == {
        "input_limited": True,
        "input_limited_reasons": ["BACKGROUND_MISSING", "EXPERIENCE_MISSING", "RELATIONSHIPS_MISSING", "UNIQUE_STORY_MISSING", "EXTRA_NOTES_MISSING", "STYLE_NOTES_MISSING"],
        "controlled_test": True,
        "delivery_target": "feishu_document",
    }
    logs = (await test_session.execute(select(TaskLog).where(TaskLog.task_id == task.id).order_by(TaskLog.id))).scalars().all()
    assert [(log.status, log.step_code) for log in logs] == [
        ("pending", "task_created"),
        ("processing", "controlled_run"),
        ("success", "controlled_complete"),
    ]


@pytest.mark.asyncio
async def test_missing_required_config_creates_not_run_without_starting(test_session, admin_user):
    project = Kol(name="缺配置项目", persona="定位", content_plan="计划")
    test_session.add(project)
    await test_session.commit()

    task = await run_controlled_task(test_session, project_id=project.id, task_code="weekly", created_by=admin_user.id, triggered_at=datetime(2026, 9, 3, tzinfo=timezone.utc))
    assert task.status == "not_run"
    assert task.started_at is None
    assert task.output_id is None
    assert task.result_summary["reason_code"] == "CONFIG_MISSING"
    assert task.result_summary["required_missing_reasons"] == ["CONTENT_BENCHMARK_SEC_UID_MISSING"]
    assert task.result_summary["controlled_test"] is True
    assert "deadline_at" not in task.input_payload


@pytest.mark.asyncio
async def test_timeout_only_fails_overdue_content_analysis_pending_or_processing_tasks(test_session, admin_user):
    overdue = TaskJob(task_no="CA-overdue", tool_code=TOOL_CODE_DAILY, tool_name="内容分析", status="processing", input_payload={"agent_code": AGENT_CODE, "deadline_at": "2026-09-01T00:00:00+00:00"}, created_by=admin_user.id)
    other_tool = TaskJob(task_no="other-overdue", tool_code="other", tool_name="其他", status="processing", input_payload={"deadline_at": "2026-09-01T00:00:00+00:00"}, created_by=admin_user.id)
    wrong_agent = TaskJob(task_no="CA-wrong-agent", tool_code=TOOL_CODE_DAILY, tool_name="内容分析", status="pending", input_payload={"agent_code": "other-agent", "deadline_at": "2026-09-01T00:00:00+00:00"}, created_by=admin_user.id)
    terminal = TaskJob(task_no="CA-success", tool_code=TOOL_CODE_DAILY, tool_name="内容分析", status="success", input_payload={"agent_code": AGENT_CODE, "deadline_at": "2026-09-01T00:00:00+00:00"}, created_by=admin_user.id)
    test_session.add_all([overdue, other_tool, wrong_agent, terminal])
    await test_session.commit()

    count = await converge_overdue_tasks(test_session, now=datetime(2026, 9, 2, tzinfo=timezone.utc))
    assert count == 1
    assert overdue.status == "failed"
    assert overdue.error_code == "TASK_TIMEOUT"
    assert overdue.result_summary == {
        "failure_stage": "timeout",
        "database_precheck": {"status": "ready"},
        "feishu_relation": {"status": "skipped"},
        "internal_result": {"status": "skipped"},
        "delivery": {"status": "skipped"},
    }
    assert other_tool.status == "processing"
    assert wrong_agent.status == "pending"
    assert terminal.status == "success"
    timeout_logs = (await test_session.execute(select(TaskLog).where(TaskLog.task_id == overdue.id))).scalars().all()
    assert [(log.status, log.step_code) for log in timeout_logs] == [("failed", "timeout")]


@pytest.mark.asyncio
async def test_timeout_conditional_update_does_not_overwrite_success_committed_by_another_session(test_engine, test_session, admin_user):
    overdue = TaskJob(
        task_no="CA-race",
        tool_code=TOOL_CODE_DAILY,
        tool_name="内容分析",
        status="processing",
        input_payload={"agent_code": AGENT_CODE, "deadline_at": "2026-09-01T00:00:00+00:00"},
        created_by=admin_user.id,
    )
    test_session.add(overdue)
    await test_session.commit()
    factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    first_session = factory()
    second_session = factory()
    try:
        stale_task = (await first_session.execute(select(TaskJob).where(TaskJob.id == overdue.id))).scalar_one()
        await second_session.execute(update(TaskJob).where(TaskJob.id == overdue.id).values(status="success"))
        await second_session.commit()

        updated = await _timeout_task_if_active(first_session, task=stale_task, now=datetime(2026, 9, 2, tzinfo=timezone.utc))
        assert updated is False
        assert await first_session.scalar(select(TaskJob.status).where(TaskJob.id == overdue.id)) == "success"
        assert await first_session.scalar(select(TaskLog.id).where(TaskLog.task_id == overdue.id)) is None
    finally:
        await first_session.close()
        await second_session.close()


@pytest.mark.asyncio
async def test_manual_retry_only_creates_new_pending_task_from_failed_content_analysis(test_session, admin_user):
    project = Kol(
        name="重试项目",
        persona="最新定位",
        content_plan="最新计划",
        background="最新背景",
    )
    test_session.add(project)
    await test_session.flush()
    test_session.add(KolBenchmark(kol_id=project.id, account_name="当前对标", account_type="content", sec_uid="current-sec"))
    original = TaskJob(
        task_no="CA-failed",
        tool_code=TOOL_CODE_DAILY,
        tool_name="内容分析",
        status="failed",
        input_payload={
            "agent_code": AGENT_CODE,
            "task_code": "daily",
            "project_id": project.id,
            "run_type": "obsolete-run-type",
            "business_date": "2026-09-01",
            "window_start": "2026-08-29T00:00:00+08:00",
            "window_end": "2026-09-01T00:00:00+08:00",
            "triggered_at": "2026-09-01T00:00:00+00:00",
            "deadline_at": "2026-09-01T12:00:00+00:00",
            "unsafe_legacy_field": "must-not-copy",
        },
        created_by=admin_user.id,
    )
    test_session.add(original)
    await test_session.commit()

    retried = await retry_failed_task(test_session, task_id=original.id, created_by=admin_user.id, triggered_at=datetime(2026, 9, 3, 8, tzinfo=timezone.utc))
    assert retried.status == "pending"
    assert retried.id != original.id
    assert retried.output_id is None
    assert retried.input_payload == {
        "agent_code": AGENT_CODE,
        "task_code": "daily",
        "project_id": project.id,
        "run_type": "retry",
        "business_date": "2026-09-01",
        "window_start": "2026-08-29T00:00:00+08:00",
        "window_end": "2026-09-01T00:00:00+08:00",
        "triggered_at": "2026-09-03T08:00:00+00:00",
        "deadline_at": "2026-09-03T20:00:00+00:00",
        "retry_of_task_id": original.id,
    }
    assert retried.result_summary == {
        "input_limited": True,
        "input_limited_reasons": ["EXPERIENCE_MISSING", "RELATIONSHIPS_MISSING", "UNIQUE_STORY_MISSING", "EXTRA_NOTES_MISSING", "STYLE_NOTES_MISSING"],
        "controlled_test": True,
        "delivery_target": "feishu_document",
    }
    assert original.status == "failed"

    original.status = "success"
    with pytest.raises(ValueError, match="failed"):
        await retry_failed_task(test_session, task_id=original.id, created_by=admin_user.id)


@pytest.mark.asyncio
async def test_manual_retry_rejects_project_that_is_no_longer_eligible_or_ready(test_session, admin_user):
    project = Kol(name="失效重试项目", persona="定位", content_plan="计划")
    test_session.add(project)
    await test_session.flush()
    original = TaskJob(
        task_no="CA-retry-missing-config",
        tool_code=TOOL_CODE_DAILY,
        tool_name="内容分析",
        status="failed",
        input_payload={
            "agent_code": AGENT_CODE,
            "task_code": "daily",
            "project_id": project.id,
            "business_date": "2026-09-01",
            "window_start": "2026-08-29T00:00:00+08:00",
            "window_end": "2026-09-01T00:00:00+08:00",
        },
        created_by=admin_user.id,
    )
    test_session.add(original)
    await test_session.commit()

    task_count_before = await test_session.scalar(select(func.count()).select_from(TaskJob))
    with pytest.raises(ValueError, match="required configuration"):
        await retry_failed_task(test_session, task_id=original.id, created_by=admin_user.id)
    assert await test_session.scalar(select(func.count()).select_from(TaskJob)) == task_count_before
