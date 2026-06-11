"""
Integration tests for tasks router - operator and admin task listing/detail.
"""
import pytest

from app.core.response import ErrorCode
from app.models.task import TaskJob, TaskLog


class TestListTasksOperator:
    """GET /api/tasks - operator sees only own tasks"""

    @pytest.mark.asyncio
    async def test_list_own_tasks_returns_paginated(
        self, test_client, operator_headers, operator_user, test_session
    ):
        task = TaskJob(
            task_no="TSK-001",
            tool_code="tool_a",
            tool_name="Tool A",
            status="completed",
            created_by=operator_user.id,
        )
        test_session.add(task)
        await test_session.commit()

        resp = await test_client.get("/api/tasks", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "items" in data["data"]
        assert "pagination" in data["data"]
        assert data["data"]["pagination"]["page"] == 1
        assert data["data"]["pagination"]["total"] >= 1

    @pytest.mark.asyncio
    async def test_operator_cannot_see_other_users_tasks(
        self, test_client, operator_headers, admin_user, operator_user, test_session
    ):
        admin_task = TaskJob(
            task_no="TSK-ADMIN-01",
            tool_code="tool_b",
            tool_name="Tool B",
            status="pending",
            created_by=admin_user.id,
        )
        test_session.add(admin_task)
        await test_session.commit()

        resp = await test_client.get("/api/tasks", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        task_nos = [item["task_no"] for item in data["data"]["items"]]
        assert "TSK-ADMIN-01" not in task_nos

    @pytest.mark.asyncio
    async def test_list_tasks_filter_by_status(
        self, test_client, operator_headers, operator_user, test_session
    ):
        completed = TaskJob(
            task_no="TSK-COMP",
            tool_code="tool_c",
            tool_name="Tool C",
            status="completed",
            created_by=operator_user.id,
        )
        pending = TaskJob(
            task_no="TSK-PEND",
            tool_code="tool_d",
            tool_name="Tool D",
            status="pending",
            created_by=operator_user.id,
        )
        test_session.add_all([completed, pending])
        await test_session.commit()

        resp = await test_client.get(
            "/api/tasks?status=completed", headers=operator_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        for item in data["data"]["items"]:
            assert item["status"] == "completed"

    @pytest.mark.asyncio
    async def test_list_tasks_filter_by_tool_code(
        self, test_client, operator_headers, operator_user, test_session
    ):
        task_a = TaskJob(
            task_no="TSK-TC-A",
            tool_code="filter_tool_a",
            tool_name="Filter Tool A",
            status="completed",
            created_by=operator_user.id,
        )
        task_b = TaskJob(
            task_no="TSK-TC-B",
            tool_code="filter_tool_b",
            tool_name="Filter Tool B",
            status="completed",
            created_by=operator_user.id,
        )
        test_session.add_all([task_a, task_b])
        await test_session.commit()

        resp = await test_client.get(
            "/api/tasks?tool_code=filter_tool_a", headers=operator_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        for item in data["data"]["items"]:
            assert item["tool_code"] == "filter_tool_a"

    @pytest.mark.asyncio
    async def test_list_tasks_requires_auth(self, test_client):
        resp = await test_client.get("/api/tasks")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_tasks_invalid_page_size_defaults_to_20(
        self, test_client, operator_headers, operator_user
    ):
        resp = await test_client.get(
            "/api/tasks?page_size=999", headers=operator_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["pagination"]["page_size"] == 20

class TestGetTaskOperator:
    """GET /api/tasks/{task_id} - operator sees own task with logs"""

    @pytest.mark.asyncio
    async def test_get_own_task_returns_detail_with_logs(
        self, test_client, operator_headers, operator_user, test_session
    ):
        task = TaskJob(
            task_no="TSK-DETAIL-01",
            tool_code="tool_x",
            tool_name="Tool X",
            status="processing",
            created_by=operator_user.id,
        )
        test_session.add(task)
        await test_session.flush()

        log = TaskLog(
            task_id=task.id,
            step_code="step_1",
            step_name="Step One",
            status="done",
            message="Processing step",
        )
        test_session.add(log)
        await test_session.commit()

        url = "/api/tasks/" + str(task.id)
        resp = await test_client.get(url, headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["task_no"] == "TSK-DETAIL-01"
        assert data["data"]["tool_code"] == "tool_x"
        assert "task_logs" in data["data"]
        assert len(data["data"]["task_logs"]) == 1
        assert data["data"]["task_logs"][0]["step_code"] == "step_1"

    @pytest.mark.asyncio
    async def test_get_other_users_task_returns_permission_denied(
        self, test_client, operator_headers, admin_user, test_session
    ):
        task = TaskJob(
            task_no="TSK-OTHER-01",
            tool_code="tool_y",
            tool_name="Tool Y",
            status="completed",
            created_by=admin_user.id,
        )
        test_session.add(task)
        await test_session.commit()

        url = "/api/tasks/" + str(task.id)
        resp = await test_client.get(url, headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.PERMISSION_DENIED

    @pytest.mark.asyncio
    async def test_get_nonexistent_task_returns_permission_denied(
        self, test_client, operator_headers
    ):
        resp = await test_client.get("/api/tasks/999999", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.PERMISSION_DENIED

    @pytest.mark.asyncio
    async def test_get_task_requires_auth(self, test_client):
        resp = await test_client.get("/api/tasks/1")
        assert resp.status_code == 401

class TestAdminListTasks:
    """GET /api/admin/tasks - admin sees all tasks"""

    @pytest.mark.asyncio
    async def test_admin_sees_all_users_tasks(
        self, test_client, admin_headers, admin_user, operator_user, test_session
    ):
        admin_task = TaskJob(
            task_no="TSK-ADM-LIST",
            tool_code="adm_tool",
            tool_name="Admin Tool",
            status="completed",
            created_by=admin_user.id,
        )
        op_task = TaskJob(
            task_no="TSK-OP-LIST",
            tool_code="op_tool",
            tool_name="Op Tool",
            status="pending",
            created_by=operator_user.id,
        )
        test_session.add_all([admin_task, op_task])
        await test_session.commit()

        resp = await test_client.get("/api/admin/tasks", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        task_nos = [item["task_no"] for item in data["data"]["items"]]
        assert "TSK-ADM-LIST" in task_nos
        assert "TSK-OP-LIST" in task_nos

    @pytest.mark.asyncio
    async def test_admin_tasks_include_created_by_username(
        self, test_client, admin_headers, operator_user, test_session
    ):
        task = TaskJob(
            task_no="TSK-UNAME",
            tool_code="uname_tool",
            tool_name="Username Tool",
            status="completed",
            created_by=operator_user.id,
        )
        test_session.add(task)
        await test_session.commit()

        resp = await test_client.get("/api/admin/tasks", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        target = None
        for item in data["data"]["items"]:
            if item["task_no"] == "TSK-UNAME":
                target = item
                break
        assert target is not None
        assert "created_by_username" in target
        assert target["created_by_username"] == operator_user.username

    @pytest.mark.asyncio
    async def test_admin_tasks_filter_by_user_id(
        self, test_client, admin_headers, admin_user, operator_user, test_session
    ):
        admin_task = TaskJob(
            task_no="TSK-UID-ADM",
            tool_code="uid_tool",
            tool_name="UID Tool",
            status="completed",
            created_by=admin_user.id,
        )
        op_task = TaskJob(
            task_no="TSK-UID-OP",
            tool_code="uid_tool",
            tool_name="UID Tool",
            status="completed",
            created_by=operator_user.id,
        )
        test_session.add_all([admin_task, op_task])
        await test_session.commit()

        url = "/api/admin/tasks?user_id=" + str(operator_user.id)
        resp = await test_client.get(url, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        for item in data["data"]["items"]:
            assert item["created_by"] == operator_user.id

    @pytest.mark.asyncio
    async def test_admin_tasks_requires_admin(self, test_client, operator_headers):
        resp = await test_client.get("/api/admin/tasks", headers=operator_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_tasks_requires_auth(self, test_client):
        resp = await test_client.get("/api/admin/tasks")
        assert resp.status_code == 401

class TestAdminGetTask:
    """GET /api/admin/tasks/{task_id} - admin sees any task"""

    @pytest.mark.asyncio
    async def test_admin_get_any_task_with_logs(
        self, test_client, admin_headers, operator_user, test_session
    ):
        task = TaskJob(
            task_no="TSK-ADM-DETAIL",
            tool_code="adm_detail",
            tool_name="Admin Detail",
            status="completed",
            created_by=operator_user.id,
        )
        test_session.add(task)
        await test_session.flush()

        log = TaskLog(
            task_id=task.id,
            step_code="step_final",
            step_name="Final Step",
            status="done",
            message="All done",
        )
        test_session.add(log)
        await test_session.commit()

        url = "/api/admin/tasks/" + str(task.id)
        resp = await test_client.get(url, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["task_no"] == "TSK-ADM-DETAIL"
        assert "created_by_username" in data["data"]
        assert data["data"]["created_by_username"] == operator_user.username
        assert len(data["data"]["task_logs"]) == 1

    @pytest.mark.asyncio
    async def test_admin_get_nonexistent_task_returns_not_found(
        self, test_client, admin_headers
    ):
        resp = await test_client.get("/api/admin/tasks/999999", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.TASK_NOT_FOUND

    @pytest.mark.asyncio
    async def test_admin_get_task_requires_admin(self, test_client, operator_headers):
        resp = await test_client.get("/api/admin/tasks/1", headers=operator_headers)
        assert resp.status_code == 403
