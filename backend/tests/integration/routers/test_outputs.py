"""
Integration tests for outputs router - operator and admin output listing/detail/delete.
"""
from datetime import date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.core.response import ErrorCode
from app.models.content_analysis import ContentAnalysisResult
from app.models.output import Output
from app.models.task import TaskJob


SHANGHAI = ZoneInfo("Asia/Shanghai")


class TestListOutputsOperator:
    """GET /api/outputs - operator sees only own non-deleted outputs"""

    @pytest.mark.asyncio
    async def test_list_own_outputs_returns_paginated(
        self, test_client, operator_headers, operator_user, test_session
    ):
        output = Output(
            title="Test Output",
            tool_code="tool_a",
            tool_name="Tool A",
            created_by=operator_user.id,
        )
        test_session.add(output)
        await test_session.commit()

        resp = await test_client.get("/api/outputs", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "items" in data["data"]
        assert "pagination" in data["data"]
        assert data["data"]["pagination"]["total"] >= 1

    @pytest.mark.asyncio
    async def test_operator_cannot_see_other_users_outputs(
        self, test_client, operator_headers, admin_user, test_session
    ):
        output = Output(
            title="Admin Output",
            tool_code="tool_b",
            tool_name="Tool B",
            created_by=admin_user.id,
        )
        test_session.add(output)
        await test_session.commit()

        resp = await test_client.get("/api/outputs", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        titles = [item["title"] for item in data["data"]["items"]]
        assert "Admin Output" not in titles

    @pytest.mark.asyncio
    async def test_list_outputs_excludes_soft_deleted(
        self, test_client, operator_headers, operator_user, test_session
    ):
        from datetime import datetime, timezone

        active = Output(
            title="Active Output",
            tool_code="tool_c",
            tool_name="Tool C",
            created_by=operator_user.id,
        )
        deleted = Output(
            title="Deleted Output",
            tool_code="tool_d",
            tool_name="Tool D",
            created_by=operator_user.id,
            deleted_at=datetime.now(tz=timezone.utc),
        )
        test_session.add_all([active, deleted])
        await test_session.commit()

        resp = await test_client.get("/api/outputs", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        titles = [item["title"] for item in data["data"]["items"]]
        assert "Active Output" in titles
        assert "Deleted Output" not in titles

    @pytest.mark.asyncio
    async def test_list_outputs_filter_by_tool_code(
        self, test_client, operator_headers, operator_user, test_session
    ):
        output_a = Output(
            title="Filter A",
            tool_code="filter_tc_a",
            tool_name="Filter TC A",
            created_by=operator_user.id,
        )
        output_b = Output(
            title="Filter B",
            tool_code="filter_tc_b",
            tool_name="Filter TC B",
            created_by=operator_user.id,
        )
        test_session.add_all([output_a, output_b])
        await test_session.commit()

        resp = await test_client.get(
            "/api/outputs?tool_code=filter_tc_a", headers=operator_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        for item in data["data"]["items"]:
            assert item["tool_code"] == "filter_tc_a"

    @pytest.mark.asyncio
    async def test_list_outputs_requires_auth(self, test_client):
        resp = await test_client.get("/api/outputs")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_test_content_analysis_output_is_hidden_from_formal_output_center(
        self,
        test_client,
        operator_headers,
        admin_headers,
        operator_user,
        test_session,
    ):
        suffix = uuid4().hex[:10]
        task = TaskJob(
            task_no=f"ca_s28_test_output_{suffix}",
            tool_code="content-analysis",
            tool_name="内容分析",
            status="success",
            created_by=operator_user.id,
        )
        test_session.add(task)
        await test_session.flush()
        output = Output(
            title=f"仅测试结果_{suffix}",
            tool_code="content-analysis",
            tool_name="内容分析",
            task_id=task.id,
            content_json={"is_test": True},
            created_by=operator_user.id,
        )
        test_session.add(output)
        await test_session.flush()
        test_session.add(
            ContentAnalysisResult(
                result_key=f"test-result-{suffix}",
                analysis_key=f"test-analysis-{suffix}",
                task_id=task.id,
                task_code="content_analysis_weekly",
                run_type="test",
                execution_kind="account",
                project_id=None,
                sec_uid="anonymous-account",
                related_project_ids=["1001"],
                business_date=date(2026, 9, 4),
                window_start=datetime(2026, 9, 2, tzinfo=SHANGHAI),
                window_end=datetime(2026, 9, 5, tzinfo=SHANGHAI),
                context_versions={"1001": "test"},
                source_receipts={},
                status="success",
                output_id=output.id,
                is_test=True,
            )
        )
        await test_session.commit()

        operator_list = await test_client.get(
            "/api/outputs?tool_code=content-analysis",
            headers=operator_headers,
        )
        admin_list = await test_client.get(
            "/api/admin/outputs?tool_code=content-analysis",
            headers=admin_headers,
        )

        assert output.title not in {
            item["title"] for item in operator_list.json()["data"]["items"]
        }
        assert output.title not in {
            item["title"] for item in admin_list.json()["data"]["items"]
        }

class TestGetOutputOperator:
    """GET /api/outputs/{output_id} - operator sees own output with content"""

    @pytest.mark.asyncio
    async def test_get_own_output_returns_detail_with_content(
        self, test_client, operator_headers, operator_user, test_session
    ):
        output = Output(
            title="Detail Output",
            tool_code="tool_x",
            tool_name="Tool X",
            created_by=operator_user.id,
            content="This is the output content",
            content_json={"blocks": ["hello"]},
            word_count=5,
        )
        test_session.add(output)
        await test_session.commit()

        url = "/api/outputs/" + str(output.id)
        resp = await test_client.get(url, headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["title"] == "Detail Output"
        assert "content" in data["data"]
        assert data["data"]["content"] == "This is the output content"
        assert "content_json" in data["data"]

    @pytest.mark.asyncio
    async def test_get_other_users_output_returns_permission_denied(
        self, test_client, operator_headers, admin_user, test_session
    ):
        output = Output(
            title="Admin Secret",
            tool_code="tool_y",
            tool_name="Tool Y",
            created_by=admin_user.id,
        )
        test_session.add(output)
        await test_session.commit()

        url = "/api/outputs/" + str(output.id)
        resp = await test_client.get(url, headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.PERMISSION_DENIED

    @pytest.mark.asyncio
    async def test_get_nonexistent_output_returns_permission_denied(
        self, test_client, operator_headers
    ):
        resp = await test_client.get("/api/outputs/999999", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.PERMISSION_DENIED

    @pytest.mark.asyncio
    async def test_get_output_requires_auth(self, test_client):
        resp = await test_client.get("/api/outputs/1")
        assert resp.status_code == 401

class TestDeleteOutputOperator:
    """DELETE /api/outputs/{output_id} - operator soft deletes own output"""

    @pytest.mark.asyncio
    async def test_delete_own_output_succeeds(
        self, test_client, operator_headers, operator_user, test_session
    ):
        output = Output(
            title="To Delete",
            tool_code="tool_del",
            tool_name="Tool Delete",
            created_by=operator_user.id,
        )
        test_session.add(output)
        await test_session.commit()

        url = "/api/outputs/" + str(output.id)
        resp = await test_client.delete(url, headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "deleted_at" not in (data["data"] or {})

    @pytest.mark.asyncio
    async def test_delete_other_users_output_returns_permission_denied(
        self, test_client, operator_headers, admin_user, test_session
    ):
        output = Output(
            title="Admin Output",
            tool_code="tool_adm",
            tool_name="Tool Admin",
            created_by=admin_user.id,
        )
        test_session.add(output)
        await test_session.commit()

        url = "/api/outputs/" + str(output.id)
        resp = await test_client.delete(url, headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.PERMISSION_DENIED

    @pytest.mark.asyncio
    async def test_delete_nonexistent_output_returns_permission_denied(
        self, test_client, operator_headers
    ):
        resp = await test_client.delete("/api/outputs/999999", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.PERMISSION_DENIED

    @pytest.mark.asyncio
    async def test_delete_output_requires_auth(self, test_client):
        resp = await test_client.delete("/api/outputs/1")
        assert resp.status_code == 401

class TestAdminListOutputs:
    """GET /api/admin/outputs - admin sees all non-deleted outputs"""

    @pytest.mark.asyncio
    async def test_admin_sees_all_users_outputs(
        self, test_client, admin_headers, admin_user, operator_user, test_session
    ):
        adm_output = Output(
            title="Admin Output List",
            tool_code="adm_op_tool",
            tool_name="Adm Op Tool",
            created_by=admin_user.id,
        )
        op_output = Output(
            title="Op Output List",
            tool_code="op_op_tool",
            tool_name="Op Op Tool",
            created_by=operator_user.id,
        )
        test_session.add_all([adm_output, op_output])
        await test_session.commit()

        resp = await test_client.get("/api/admin/outputs", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        titles = [item["title"] for item in data["data"]["items"]]
        assert "Admin Output List" in titles
        assert "Op Output List" in titles

    @pytest.mark.asyncio
    async def test_admin_outputs_include_created_by_username(
        self, test_client, admin_headers, operator_user, test_session
    ):
        output = Output(
            title="Username Output",
            tool_code="uname_op",
            tool_name="Uname Op",
            created_by=operator_user.id,
        )
        test_session.add(output)
        await test_session.commit()

        resp = await test_client.get("/api/admin/outputs", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        target = None
        for item in data["data"]["items"]:
            if item["title"] == "Username Output":
                target = item
                break
        assert target is not None
        assert "created_by_username" in target
        assert target["created_by_username"] == operator_user.username

    @pytest.mark.asyncio
    async def test_admin_outputs_filter_by_user_id(
        self, test_client, admin_headers, admin_user, operator_user, test_session
    ):
        adm_output = Output(
            title="UID Adm Output",
            tool_code="uid_op_tool",
            tool_name="UID Op Tool",
            created_by=admin_user.id,
        )
        op_output = Output(
            title="UID Op Output",
            tool_code="uid_op_tool",
            tool_name="UID Op Tool",
            created_by=operator_user.id,
        )
        test_session.add_all([adm_output, op_output])
        await test_session.commit()

        url = "/api/admin/outputs?user_id=" + str(operator_user.id)
        resp = await test_client.get(url, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        for item in data["data"]["items"]:
            assert item["created_by"] == operator_user.id

    @pytest.mark.asyncio
    async def test_admin_outputs_requires_admin(self, test_client, operator_headers):
        resp = await test_client.get("/api/admin/outputs", headers=operator_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_outputs_requires_auth(self, test_client):
        resp = await test_client.get("/api/admin/outputs")
        assert resp.status_code == 401
