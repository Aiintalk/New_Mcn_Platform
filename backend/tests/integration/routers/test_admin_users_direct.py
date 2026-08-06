"""
Direct-call coverage tests for admin_users.py。

直调 list_users / check_username / create_user / get_user / update_user /
reset_password / enable_user / disable_user / delete_user。
覆盖 keyword/status/role 过滤、available/suggested 分支、用户名重复、各种 404、
admin 不可删、enable/disable/reset/patch 等路径。
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete
from starlette.requests import Request

from app.models.user import User
from app.routers.admin_users import (
    CreateUserRequest,
    UpdateUserRequest,
    check_username,
    create_user,
    delete_user,
    disable_user,
    enable_user,
    get_user,
    list_users,
    reset_password,
    update_user,
)


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(test_session):
    """清本文件 seed 的 cov_u_% 用户（保留 admin_user/operator_user fixture 创建的）。"""
    await test_session.execute(delete(User).where(User.username.like("cov_u_%")))
    await test_session.commit()
    yield


def _make_request() -> Request:
    return Request({"type": "http", "headers": [(b"user-agent", b"pytest")], "client": ("127.0.0.1", 0)})


async def _seed_user(test_session, **kw) -> User:
    suffix = uuid.uuid4().hex[:8]
    defaults = dict(
        username=f"cov_u_target_{suffix}",
        real_name=f"目标用户_{suffix}",
        role="operator",
        status="enabled",
        password_hash="x",
        password_changed_at=None,
    )
    defaults.update(kw)
    u = User(**defaults)
    test_session.add(u)
    await test_session.commit()
    await test_session.refresh(u)
    return u


# ---------------------------------------------------------------------------
# GET /admin/users
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_users_filters_and_bad_page_size(test_session, admin_user):
    """keyword + role + status 过滤 + 非法 page_size 落回 20。"""
    await _seed_user(test_session, username="cov_u_alpha", real_name="阿尔法", role="operator", status="enabled")
    await _seed_user(test_session, username="cov_u_beta", real_name="贝塔", role="viewer", status="disabled")

    resp = await list_users(
        page=1, page_size=999, keyword="cov_u_alpha", status="enabled", role="operator",
        current_user=admin_user,
    )
    assert resp.data["pagination"]["page_size"] == 20
    items = [i for i in resp.data["items"] if i["username"].startswith("cov_u_alpha")]
    assert len(items) == 1


@pytest.mark.asyncio
async def test_list_users_keyword_no_match(test_session, admin_user):
    """keyword 无匹配 → 空。"""
    resp = await list_users(page=1, page_size=20, keyword="absolutely_no_such_kw_zzz",
                            status="", role="", current_user=admin_user)
    # 至少断言不报错且 pagination 字段齐全
    assert "items" in resp.data
    assert resp.data["pagination"]["page"] == 1


# ---------------------------------------------------------------------------
# GET /admin/users/check-username
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_username_empty(test_session, admin_user):
    """空 username → VALIDATION_ERROR。"""
    resp = await check_username(username="", current_user=admin_user)
    assert resp.success is False


@pytest.mark.asyncio
async def test_check_username_available(test_session, admin_user):
    """不存在 → available=True。"""
    resp = await check_username(
        username=f"cov_u_avail_{uuid.uuid4().hex[:6]}",
        current_user=admin_user,
    )
    assert resp.data["available"] is True
    assert resp.data["suggested"] is None


@pytest.mark.asyncio
async def test_check_username_taken_with_suggestion(test_session, admin_user):
    """已存在 → available=False + suggested。"""
    name = f"cov_u_taken_{uuid.uuid4().hex[:6]}"
    await _seed_user(test_session, username=name)
    # 占用 name1 让 suggested 跳到 name2
    await _seed_user(test_session, username=f"{name}1")

    resp = await check_username(username=name, current_user=admin_user)
    assert resp.data["available"] is False
    assert resp.data["suggested"] == f"{name}2"


# ---------------------------------------------------------------------------
# POST /admin/users
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_user_default_password(test_session, admin_user):
    """不传 password → 用默认 Mcn@123。"""
    suffix = uuid.uuid4().hex[:6]
    body = CreateUserRequest(
        username=f"cov_u_new_{suffix}", real_name="新建用户", role="operator",
    )
    resp = await create_user(body=body, request=_make_request(), current_user=admin_user)
    assert resp.success is True
    assert resp.data["initial_password"] == "Mcn@123"
    assert resp.data["username"] == f"cov_u_new_{suffix}"


@pytest.mark.asyncio
async def test_create_user_custom_password(test_session, admin_user):
    """传 password → 用之。"""
    suffix = uuid.uuid4().hex[:6]
    body = CreateUserRequest(
        username=f"cov_u_pw_{suffix}", real_name="x", role="operator", password="Secret@123",
    )
    resp = await create_user(body=body, request=_make_request(), current_user=admin_user)
    assert resp.data["initial_password"] == "Secret@123"


@pytest.mark.asyncio
async def test_create_user_duplicate(test_session, admin_user):
    """用户名已存在 → 错误。"""
    suffix = uuid.uuid4().hex[:6]
    uname = f"cov_u_dup_{suffix}"
    await _seed_user(test_session, username=uname)
    body = CreateUserRequest(username=uname, real_name="x", role="operator")
    resp = await create_user(body=body, request=_make_request(), current_user=admin_user)
    assert resp.success is False


# ---------------------------------------------------------------------------
# GET /admin/users/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_user_not_found(test_session, admin_user):
    resp = await get_user(user_id=99999999, current_user=admin_user)
    assert resp.success is False


@pytest.mark.asyncio
async def test_get_user_ok(test_session, admin_user):
    u = await _seed_user(test_session)
    resp = await get_user(user_id=u.id, current_user=admin_user)
    assert resp.data["id"] == u.id


# ---------------------------------------------------------------------------
# PATCH /admin/users/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_user_not_found(test_session, admin_user):
    body = UpdateUserRequest(real_name="x")
    resp = await update_user(user_id=99999999, body=body, request=_make_request(), current_user=admin_user)
    assert resp.success is False


@pytest.mark.asyncio
async def test_update_user_partial(test_session, admin_user):
    """PATCH real_name + role + status。"""
    u = await _seed_user(test_session)
    body = UpdateUserRequest(real_name="新名字", role="viewer", status="disabled")
    resp = await update_user(user_id=u.id, body=body, request=_make_request(), current_user=admin_user)
    assert resp.data["real_name"] == "新名字"
    assert resp.data["role"] == "viewer"
    assert resp.data["status"] == "disabled"


@pytest.mark.asyncio
async def test_update_user_empty_body(test_session, admin_user):
    """空 body → 不更新字段但仍写 log。"""
    u = await _seed_user(test_session, real_name="原名")
    body = UpdateUserRequest()
    resp = await update_user(user_id=u.id, body=body, request=_make_request(), current_user=admin_user)
    assert resp.data["real_name"] == "原名"


# ---------------------------------------------------------------------------
# POST /admin/users/{id}/reset-password
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reset_password_not_found(test_session, admin_user):
    resp = await reset_password(user_id=99999999, request=_make_request(), current_user=admin_user)
    assert resp.success is False


@pytest.mark.asyncio
async def test_reset_password_ok(test_session, admin_user):
    u = await _seed_user(test_session, password_hash="old", token_version=3)
    resp = await reset_password(user_id=u.id, request=_make_request(), current_user=admin_user)
    assert resp.data["initial_password"] == "Mcn@123"

    # 验证 token_version 自增
    await test_session.refresh(u)
    assert u.token_version == 4


# ---------------------------------------------------------------------------
# POST /admin/users/{id}/enable | /disable
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enable_user(test_session, admin_user):
    u = await _seed_user(test_session, status="disabled")
    resp = await enable_user(user_id=u.id, request=_make_request(), current_user=admin_user)
    assert resp.success is True
    await test_session.refresh(u)
    assert u.status == "enabled"


@pytest.mark.asyncio
async def test_enable_user_not_found(test_session, admin_user):
    resp = await enable_user(user_id=99999999, request=_make_request(), current_user=admin_user)
    assert resp.success is False


@pytest.mark.asyncio
async def test_disable_user(test_session, admin_user):
    u = await _seed_user(test_session, status="enabled")
    resp = await disable_user(user_id=u.id, request=_make_request(), current_user=admin_user)
    assert resp.success is True
    await test_session.refresh(u)
    assert u.status == "disabled"


@pytest.mark.asyncio
async def test_disable_user_not_found(test_session, admin_user):
    resp = await disable_user(user_id=99999999, request=_make_request(), current_user=admin_user)
    assert resp.success is False


# ---------------------------------------------------------------------------
# DELETE /admin/users/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_user_not_found(test_session, admin_user):
    resp = await delete_user(user_id=99999999, request=_make_request(), current_user=admin_user)
    assert resp.success is False


@pytest.mark.asyncio
async def test_delete_user_admin_forbidden(test_session, admin_user):
    """删 admin → PERMISSION_DENIED。"""
    resp = await delete_user(user_id=admin_user.id, request=_make_request(), current_user=admin_user)
    assert resp.success is False


@pytest.mark.asyncio
async def test_delete_user_ok(test_session, admin_user):
    u = await _seed_user(test_session, role="operator")
    resp = await delete_user(user_id=u.id, request=_make_request(), current_user=admin_user)
    assert resp.success is True
    await test_session.refresh(u)
    assert u.deleted_at is not None
