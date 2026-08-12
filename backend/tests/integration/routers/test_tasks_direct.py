"""
Direct-call coverage tests for tasks.py。

直调 list_tasks / get_task / admin_list_tasks / admin_get_task，
稳定覆盖端点体（status/tool_code/user_id 过滤 + PERMISSION_DENIED + TASK_NOT_FOUND）。
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.models.task import TaskJob, TaskLog
from app.routers.tasks import admin_get_task, admin_list_tasks, get_task, list_tasks


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(test_session):
    """清本文件 seed 的 cov_% task（保留 task_id=1 等其他测试依赖的行）。"""
    from sqlalchemy import select
    cov_ids = (await test_session.execute(
        select(TaskJob.id).where(TaskJob.task_no.like("cov_%"))
    )).scalars().all()
    if cov_ids:
        await test_session.execute(delete(TaskLog).where(TaskLog.task_id.in_(cov_ids)))
    await test_session.execute(delete(TaskJob).where(TaskJob.task_no.like("cov_%")))
    await test_session.commit()
    yield


async def _seed_task(test_session, user_id, **kwargs) -> TaskJob:
    suffix = uuid.uuid4().hex[:8]
    defaults = dict(
        task_no=f"cov_{suffix}",
        tool_code="qianchuan-writer",
        tool_name="千川仿写",
        status="processing",
    )
    defaults.update(kwargs)
    task = TaskJob(created_by=user_id, **defaults)
    test_session.add(task)
    await test_session.commit()
    await test_session.refresh(task)
    return task


# ---------------------------------------------------------------------------
# GET /tasks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_tasks_filters(test_session, operator_user):
    """status / tool_code 过滤 + 非法 page_size 落回 20。"""
    await _seed_task(test_session, operator_user.id, status="processing", tool_code="seeding-writer")
    await _seed_task(test_session, operator_user.id, status="done", tool_code="qianchuan-writer")

    resp = await list_tasks(
        page=1, page_size=999, status="done", tool_code="qianchuan-writer", current_user=operator_user,
    )
    assert resp.data["pagination"]["page_size"] == 20
    assert resp.data["pagination"]["total"] == 1
    assert resp.data["items"][0]["status"] == "done"


@pytest.mark.asyncio
async def test_list_tasks_other_user_invisible(test_session, operator_user, admin_user):
    """他人任务不可见。"""
    await _seed_task(test_session, admin_user.id)
    resp = await list_tasks(page=1, page_size=20, status="", tool_code="", current_user=operator_user)
    assert resp.data["pagination"]["total"] == 0


# ---------------------------------------------------------------------------
# GET /tasks/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_task_own_with_logs(test_session, operator_user):
    """自己的 task + task_logs 关联读出。"""
    task = await _seed_task(test_session, operator_user.id)
    test_session.add(TaskLog(task_id=task.id, step_code="start", step_name="开始", status="done", message="ok"))
    await test_session.commit()

    resp = await get_task(task_id=task.id, current_user=operator_user)
    assert resp.data["id"] == task.id
    assert len(resp.data["task_logs"]) == 1
    assert resp.data["task_logs"][0]["step_code"] == "start"


@pytest.mark.asyncio
async def test_get_task_not_own_denied(test_session, operator_user, admin_user):
    """他人 task → PERMISSION_DENIED。"""
    task = await _seed_task(test_session, admin_user.id)
    resp = await get_task(task_id=task.id, current_user=operator_user)
    assert resp.success is False


# ---------------------------------------------------------------------------
# GET /admin/tasks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_list_tasks_user_filter(test_session, operator_user, admin_user):
    """admin 看 all + user_id 过滤。"""
    await _seed_task(test_session, operator_user.id)
    await _seed_task(test_session, admin_user.id)

    resp = await admin_list_tasks(
        page=1, page_size=20, status="", tool_code="", user_id=operator_user.id, current_user=admin_user,
    )
    assert resp.data["pagination"]["total"] == 1
    assert resp.data["items"][0]["created_by_username"] == operator_user.username


# ---------------------------------------------------------------------------
# GET /admin/tasks/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_get_task_not_found(test_session, admin_user):
    """不存在 → TASK_NOT_FOUND。"""
    resp = await admin_get_task(task_id=99999999, current_user=admin_user)
    assert resp.success is False


@pytest.mark.asyncio
async def test_admin_get_task_with_creator(test_session, operator_user, admin_user):
    """admin 看任意 task + creator username。"""
    task = await _seed_task(test_session, operator_user.id)
    resp = await admin_get_task(task_id=task.id, current_user=admin_user)
    assert resp.data["created_by_username"] == operator_user.username
