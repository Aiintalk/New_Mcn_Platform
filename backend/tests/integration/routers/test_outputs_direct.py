"""
Direct-call coverage tests for outputs.py。

直调端点函数（传 db=current_user=request=），稳定覆盖端点体。
覆盖 list / get / delete（含 not own / PERMISSION_DENIED）/ admin_list / admin_get / admin_delete。
"""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import delete
from starlette.requests import Request

from app.models.output import Output
from app.routers.outputs import (
    admin_delete_output,
    admin_get_output,
    admin_list_outputs,
    delete_output,
    get_output,
    list_outputs,
)


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(test_session):
    """清 outputs 表防污染（只删本文件 seed 的 cov_out_% 行，保留其他测试数据）。"""
    await test_session.execute(delete(Output).where(Output.title.like("cov_out_%")))
    await test_session.commit()
    yield


def _make_request() -> Request:
    return Request({"type": "http", "headers": [(b"user-agent", b"pytest")], "client": ("127.0.0.1", 0)})


async def _seed_output(test_session, user_id, **kwargs) -> Output:
    suffix = uuid.uuid4().hex[:8]
    defaults = dict(
        title=f"cov_out_{suffix}",
        tool_code="qianchuan-writer",
        tool_name="千川仿写",
    )
    defaults.update(kwargs)
    out = Output(created_by=user_id, **defaults)
    test_session.add(out)
    await test_session.commit()
    await test_session.refresh(out)
    return out


# ---------------------------------------------------------------------------
# GET /outputs (operator own)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_outputs_default_page_size(test_session, operator_user):
    """page_size 非法 → 落回 20。"""
    await _seed_output(test_session, operator_user.id)
    resp = await list_outputs(page=1, page_size=999, tool_code="", current_user=operator_user)
    assert resp.data["pagination"]["page_size"] == 20
    assert len(resp.data["items"]) == 1


@pytest.mark.asyncio
async def test_list_outputs_filter_tool_code(test_session, operator_user):
    """tool_code 过滤。"""
    await _seed_output(test_session, operator_user.id, tool_code="seeding-writer")
    await _seed_output(test_session, operator_user.id, tool_code="qianchuan-writer")
    resp = await list_outputs(page=1, page_size=20, tool_code="seeding-writer", current_user=operator_user)
    assert len(resp.data["items"]) == 1
    assert resp.data["items"][0]["tool_code"] == "seeding-writer"


@pytest.mark.asyncio
async def test_list_outputs_other_user_invisible(test_session, operator_user, admin_user):
    """他人 output 不可见。"""
    await _seed_output(test_session, admin_user.id)
    resp = await list_outputs(page=1, page_size=20, tool_code="", current_user=operator_user)
    assert resp.data["pagination"]["total"] == 0


# ---------------------------------------------------------------------------
# GET /outputs/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_output_own(test_session, operator_user):
    """自己产出 → 含 content。"""
    out = await _seed_output(
        test_session, operator_user.id, content="hello", content_json={"k": "v"}
    )
    resp = await get_output(output_id=out.id, current_user=operator_user)
    assert resp.data["content"] == "hello"
    assert resp.data["content_json"] == {"k": "v"}


@pytest.mark.asyncio
async def test_get_output_not_own_denied(test_session, operator_user, admin_user):
    """他人产出 → PERMISSION_DENIED。"""
    out = await _seed_output(test_session, admin_user.id)
    resp = await get_output(output_id=out.id, current_user=operator_user)
    assert resp.success is False


# ---------------------------------------------------------------------------
# DELETE /outputs/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_output_own(test_session, operator_user):
    """删自己的 → 软删（deleted_at 落值）。"""
    out = await _seed_output(test_session, operator_user.id)
    resp = await delete_output(output_id=out.id, request=_make_request(), current_user=operator_user)
    assert resp.success is True

    # 再用 get_output 找不到（deleted_at 已软删）
    resp2 = await get_output(output_id=out.id, current_user=operator_user)
    assert resp2.success is False  # 软删后查询排除，PERMISSION_DENIED


@pytest.mark.asyncio
async def test_delete_output_not_own_denied(test_session, operator_user, admin_user):
    """删他人产出 → PERMISSION_DENIED。"""
    out = await _seed_output(test_session, admin_user.id)
    resp = await delete_output(output_id=out.id, request=_make_request(), current_user=operator_user)
    assert resp.success is False


# ---------------------------------------------------------------------------
# GET /admin/outputs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_list_outputs_filter(test_session, operator_user, admin_user):
    """admin 看全部 + user_id 过滤 + tool_code 过滤。"""
    await _seed_output(test_session, operator_user.id, tool_code="seeding-writer")
    await _seed_output(test_session, admin_user.id, tool_code="qianchuan-writer")

    resp = await admin_list_outputs(
        page=1, page_size=20, tool_code="", user_id=operator_user.id, current_user=admin_user,
    )
    assert resp.data["pagination"]["total"] == 1
    assert resp.data["items"][0]["created_by_username"] == operator_user.username


# ---------------------------------------------------------------------------
# GET /admin/outputs/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_get_output_not_found(test_session, admin_user):
    """不存在 → OUTPUT_NOT_FOUND。"""
    resp = await admin_get_output(output_id=99999999, current_user=admin_user)
    assert resp.success is False


@pytest.mark.asyncio
async def test_admin_get_output_any_user(test_session, operator_user, admin_user):
    """admin 看任意用户产出。"""
    out = await _seed_output(test_session, operator_user.id, content="x")
    resp = await admin_get_output(output_id=out.id, current_user=admin_user)
    assert resp.data["content"] == "x"


# ---------------------------------------------------------------------------
# DELETE /admin/outputs/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_delete_output(test_session, operator_user, admin_user):
    """admin 软删任意产出。"""
    out = await _seed_output(test_session, operator_user.id)
    resp = await admin_delete_output(output_id=out.id, request=_make_request(), current_user=admin_user)
    assert resp.success is True

    # 再查 → NOT_FOUND
    resp2 = await admin_get_output(output_id=out.id, current_user=admin_user)
    assert resp2.success is False


@pytest.mark.asyncio
async def test_admin_delete_output_not_found(test_session, admin_user):
    """删不存在的 → OUTPUT_NOT_FOUND。"""
    resp = await admin_delete_output(output_id=99999999, request=_make_request(), current_user=admin_user)
    assert resp.success is False
