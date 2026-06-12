"""
Integration tests for workspace router — GET /api/workspace/tools, GET /api/workspace/tools/{tool_code}.
"""
import pytest

from app.core.response import ErrorCode
from app.models.workspace import WorkspaceTool


class TestListWorkspaceTools:
    """GET /api/workspace/tools"""

    @pytest.mark.asyncio
    async def test_list_tools_returns_online_and_dev_tools(
        self, test_client, admin_headers, admin_user, test_session
    ):
        # Seed two tools: one online, one dev, one offline
        online_tool = WorkspaceTool(
            tool_code="tool_online_1",
            tool_name="Online Tool",
            category="cat_a",
            status="online",
            sort_order=1,
        )
        dev_tool = WorkspaceTool(
            tool_code="tool_dev_1",
            tool_name="Dev Tool",
            category="cat_b",
            status="dev",
            sort_order=2,
        )
        offline_tool = WorkspaceTool(
            tool_code="tool_offline_1",
            tool_name="Offline Tool",
            category="cat_a",
            status="offline",
            sort_order=0,
        )
        test_session.add_all([online_tool, dev_tool, offline_tool])
        await test_session.commit()

        resp = await test_client.get("/api/workspace/tools", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        items = data["data"]["items"]
        tool_codes = {item["tool_code"] for item in items}
        # online and dev should be present, offline excluded
        assert "tool_online_1" in tool_codes
        assert "tool_dev_1" in tool_codes
        assert "tool_offline_1" not in tool_codes

    @pytest.mark.asyncio
    async def test_list_tools_sorted_by_sort_order(
        self, test_client, admin_headers, admin_user, test_session
    ):
        high_sort = WorkspaceTool(
            tool_code="sort_high",
            tool_name="Sort High",
            status="online",
            sort_order=99,
        )
        low_sort = WorkspaceTool(
            tool_code="sort_low",
            tool_name="Sort Low",
            status="online",
            sort_order=1,
        )
        test_session.add_all([high_sort, low_sort])
        await test_session.commit()

        resp = await test_client.get("/api/workspace/tools", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        items = data["data"]["items"]
        codes = [item["tool_code"] for item in items]
        # sort_low (order=1) should appear before sort_high (order=99)
        if "sort_low" in codes and "sort_high" in codes:
            assert codes.index("sort_low") < codes.index("sort_high")

    @pytest.mark.asyncio
    async def test_list_tools_requires_auth(self, test_client):
        resp = await test_client.get("/api/workspace/tools")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_tools_operator_can_access(
        self, test_client, operator_headers, operator_user
    ):
        resp = await test_client.get("/api/workspace/tools", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "items" in data["data"]

    @pytest.mark.asyncio
    async def test_list_tools_returns_list(
        self, test_client, admin_headers, admin_user
    ):
        """Endpoint returns a list (items key present, possibly empty)."""
        resp = await test_client.get("/api/workspace/tools", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"]["items"], list)


class TestGetWorkspaceTool:
    """GET /api/workspace/tools/{tool_code}"""

    @pytest.mark.asyncio
    async def test_get_online_tool_returns_detail(
        self, test_client, admin_headers, admin_user, test_session
    ):
        tool = WorkspaceTool(
            tool_code="detail_tool",
            tool_name="Detail Tool",
            category="cat_x",
            description="A tool for testing",
            status="online",
            tags=["tag1", "tag2"],
            sort_order=10,
        )
        test_session.add(tool)
        await test_session.commit()

        resp = await test_client.get(
            "/api/workspace/tools/detail_tool", headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["tool_code"] == "detail_tool"
        assert data["data"]["tool_name"] == "Detail Tool"
        assert data["data"]["status"] == "online"
        assert data["data"]["tags"] == ["tag1", "tag2"]
        assert data["data"]["description"] == "A tool for testing"

    @pytest.mark.asyncio
    async def test_get_nonexistent_tool_returns_not_found(
        self, test_client, admin_headers, admin_user
    ):
        resp = await test_client.get(
            "/api/workspace/tools/nonexistent_code", headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.RESOURCE_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_dev_tool_returns_not_found(
        self, test_client, admin_headers, admin_user, test_session
    ):
        """Only 'online' tools are returned by detail endpoint, not 'dev'."""
        tool = WorkspaceTool(
            tool_code="dev_only_tool",
            tool_name="Dev Only",
            status="dev",
            sort_order=5,
        )
        test_session.add(tool)
        await test_session.commit()

        resp = await test_client.get(
            "/api/workspace/tools/dev_only_tool", headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.RESOURCE_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_offline_tool_returns_not_found(
        self, test_client, admin_headers, admin_user, test_session
    ):
        tool = WorkspaceTool(
            tool_code="offline_detail",
            tool_name="Offline Detail",
            status="offline",
            sort_order=5,
        )
        test_session.add(tool)
        await test_session.commit()

        resp = await test_client.get(
            "/api/workspace/tools/offline_detail", headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.RESOURCE_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_tool_requires_auth(self, test_client):
        resp = await test_client.get("/api/workspace/tools/any_code")
        assert resp.status_code == 401


class TestAdminUpdateTool:
    """PATCH /api/admin/workspace/tools/{tool_code}"""

    @pytest.mark.asyncio
    async def test_update_category(
        self, test_client, admin_headers, admin_user, test_session
    ):
        """Admin can update tool category and it persists."""
        tool = WorkspaceTool(
            tool_code="cat_test_tool",
            tool_name="Category Test",
            category="old_category",
            status="online",
            sort_order=0,
        )
        test_session.add(tool)
        await test_session.commit()

        resp = await test_client.patch(
            "/api/admin/workspace/tools/cat_test_tool",
            json={"category": "new_category"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["category"] == "new_category"

    @pytest.mark.asyncio
    async def test_update_tool_name_and_category(
        self, test_client, admin_headers, admin_user, test_session
    ):
        """Multiple fields can be updated at once."""
        tool = WorkspaceTool(
            tool_code="multi_field_tool",
            tool_name="Old Name",
            category="old_cat",
            description="old desc",
            status="online",
            sort_order=0,
        )
        test_session.add(tool)
        await test_session.commit()

        resp = await test_client.patch(
            "/api/admin/workspace/tools/multi_field_tool",
            json={"tool_name": "New Name", "category": "new_cat"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["tool_name"] == "New Name"
        assert data["data"]["category"] == "new_cat"
        assert data["data"]["description"] == "old desc"  # unchanged

    @pytest.mark.asyncio
    async def test_update_nonexistent_tool_returns_not_found(
        self, test_client, admin_headers, admin_user
    ):
        resp = await test_client.patch(
            "/api/admin/workspace/tools/nonexistent_xyz",
            json={"category": "anything"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.RESOURCE_NOT_FOUND

    @pytest.mark.asyncio
    async def test_update_requires_admin(
        self, test_client, operator_headers, operator_user
    ):
        """Operator cannot access admin endpoint."""
        resp = await test_client.patch(
            "/api/admin/workspace/tools/any_tool",
            json={"category": "hack"},
            headers=operator_headers,
        )
        assert resp.status_code == 403
