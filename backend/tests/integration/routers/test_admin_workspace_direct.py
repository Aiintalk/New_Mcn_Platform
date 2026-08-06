"""
Direct-call coverage tests for admin_workspace.py。

直调 admin_list_tools / admin_update_tool，覆盖 status 过滤、RESOURCE_NOT_FOUND、
所有 PATCH 字段写入 + OperationLog。
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete
from starlette.requests import Request

from app.models.workspace import WorkspaceTool
from app.routers.admin_workspace import UpdateToolRequest, admin_list_tools, admin_update_tool


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(test_session):
    """清本文件 seed 的 cov_tool_% 行（保留 seed 工具数据）。"""
    await test_session.execute(delete(WorkspaceTool).where(WorkspaceTool.tool_code.like("cov_tool_%")))
    await test_session.commit()
    yield


def _make_request() -> Request:
    return Request({"type": "http", "headers": [(b"user-agent", b"pytest")], "client": ("127.0.0.1", 0)})


async def _seed_tool(test_session, **kwargs) -> WorkspaceTool:
    suffix = uuid.uuid4().hex[:8]
    defaults = dict(
        tool_code=f"cov_tool_{suffix}",
        tool_name=f"测试工具_{suffix}",
    )
    defaults.update(kwargs)
    tool = WorkspaceTool(**defaults)
    test_session.add(tool)
    await test_session.commit()
    await test_session.refresh(tool)
    return tool


# ---------------------------------------------------------------------------
# GET /tools
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_tools_status_filter(test_session, admin_user):
    """status 过滤 + sort_order 排序（只看本测试 seed 的 cov_tool_%）。"""
    await _seed_tool(test_session, status="online", sort_order=2)
    await _seed_tool(test_session, status="dev", sort_order=1)
    await _seed_tool(test_session, status="online", sort_order=3)

    resp = await admin_list_tools(status="online", current_user=admin_user)
    items = [i for i in resp.data["items"] if i["tool_code"].startswith("cov_tool_")]
    assert len(items) == 2
    assert all(i["status"] == "online" for i in items)
    # 按 sort_order asc
    assert items[0]["sort_order"] <= items[1]["sort_order"]


@pytest.mark.asyncio
async def test_list_tools_no_filter(test_session, admin_user):
    """无 status → 全部（断言至少含本测试的 2 个 cov_tool_）。"""
    await _seed_tool(test_session, status="online")
    await _seed_tool(test_session, status="dev")
    resp = await admin_list_tools(status="", current_user=admin_user)
    codes = [i["tool_code"] for i in resp.data["items"]]
    cov = [c for c in codes if c.startswith("cov_tool_")]
    assert len(cov) == 2


# ---------------------------------------------------------------------------
# PATCH /tools/{tool_code}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_tool_not_found(test_session, admin_user):
    """不存在 → RESOURCE_NOT_FOUND。"""
    body = UpdateToolRequest(tool_name="x")
    resp = await admin_update_tool(
        tool_code="no_such_tool", body=body, request=_make_request(), current_user=admin_user,
    )
    assert resp.success is False


@pytest.mark.asyncio
async def test_update_tool_all_fields(test_session, admin_user):
    """PATCH 所有字段（含 tags/config/sort_order）。"""
    tool = await _seed_tool(test_session)
    body = UpdateToolRequest(
        tool_name="新名",
        category="writing",
        description="描述",
        status="online",
        tags=["a", "b"],
        config={"k": "v"},
        sort_order=42,
    )
    resp = await admin_update_tool(
        tool_code=tool.tool_code, body=body, request=_make_request(), current_user=admin_user,
    )
    assert resp.success is True
    assert resp.data["tool_name"] == "新名"
    assert resp.data["category"] == "writing"
    assert resp.data["status"] == "online"
    assert resp.data["tags"] == ["a", "b"]
    assert resp.data["config"] == {"k": "v"}
    assert resp.data["sort_order"] == 42


@pytest.mark.asyncio
async def test_update_tool_partial_empty_body(test_session, admin_user):
    """PATCH 空请求体 → 不更新字段但仍写 log + 返回 tool。"""
    tool = await _seed_tool(test_session, tool_name="原名")
    body = UpdateToolRequest()
    resp = await admin_update_tool(
        tool_code=tool.tool_code, body=body, request=_make_request(), current_user=admin_user,
    )
    assert resp.success is True
    assert resp.data["tool_name"] == "原名"
