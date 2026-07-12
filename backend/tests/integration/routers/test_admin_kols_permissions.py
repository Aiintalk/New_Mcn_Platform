"""
Integration tests for permission boundaries on admin_kols router (PR #25 follow-up).

Covers the new `require_admin_or_operator` permission (2026-07-12):
- GET  /api/admin/kols        → admin / operator (read path放宽)
- GET  /api/admin/kols/{id}   → admin / operator
- POST /api/admin/kols        → admin only (unchanged)
- 写路径保持 require_admin 不变（不在本文件覆盖，由 test_admin_kols.py 覆盖）

5 个权限场景：
1. admin   → 200 + success=True
2. operator → 200 + success=True（新权限）
3. viewer  → 403（角色不允许）
4. 无 token → 401（未认证）
5. 未改密 admin → 403（强制改密检查）

参考契约：backend/docs/base/MCN_M2_Base_API.md §6A
"""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from passlib.context import CryptContext
from app.core.security import create_access_token
from app.models.user import User

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# 局部 fixture：viewer + 未改密 admin
# ---------------------------------------------------------------------------
# 放在文件内（而非全局 conftest）以保持本 PR 的改动内聚。
# 未来若其他权限测试需要 viewer / force_password fixture，可提取到 tests/conftest.py。

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_DEFAULT_PASSWORD = "Test@123456"


@pytest_asyncio.fixture
async def viewer_user(test_session) -> User:
    """viewer 角色（已改密）。用于验证角色拒绝。"""
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"test_viewer_{suffix}",
        real_name="测试查看者",
        password_hash=_pwd_context.hash(_DEFAULT_PASSWORD),
        role="viewer",
        status="enabled",
        password_changed_at=datetime.now(tz=timezone.utc),
    )
    test_session.add(user)
    await test_session.commit()
    await test_session.refresh(user)
    return user


@pytest.fixture
def viewer_token(viewer_user: User) -> str:
    return create_access_token(
        user_id=int(viewer_user.id),
        username=str(viewer_user.username),
        role=str(viewer_user.role),
        token_version=int(viewer_user.token_version),
    )


@pytest.fixture
def viewer_headers(viewer_token: str) -> dict:
    return {"Authorization": f"Bearer {viewer_token}"}


@pytest_asyncio.fixture
async def force_password_admin_user(test_session) -> User:
    """admin 角色但未改密（password_changed_at=None）。
    用于验证 require_admin_or_operator 中的强制改密检查。"""
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"test_force_pwd_admin_{suffix}",
        real_name="未改密管理员",
        password_hash=_pwd_context.hash(_DEFAULT_PASSWORD),
        role="admin",
        status="enabled",
        password_changed_at=None,
    )
    test_session.add(user)
    await test_session.commit()
    await test_session.refresh(user)
    return user


@pytest.fixture
def force_password_token(force_password_admin_user: User) -> str:
    return create_access_token(
        user_id=int(force_password_admin_user.id),
        username=str(force_password_admin_user.username),
        role=str(force_password_admin_user.role),
        token_version=int(force_password_admin_user.token_version),
    )


@pytest.fixture
def force_password_headers(force_password_token: str) -> dict:
    return {"Authorization": f"Bearer {force_password_token}"}


# ---------------------------------------------------------------------------
# 5 个权限场景
# ---------------------------------------------------------------------------


async def test_admin_can_list_kols(test_client, admin_headers):
    """admin 角色 GET /api/admin/kols 返回 200 + success=True。"""
    resp = await test_client.get("/api/admin/kols", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


async def test_operator_can_list_kols(test_client, operator_headers):
    """operator 角色 GET /api/admin/kols 返回 200 + success=True（PR #25 新放宽的权限）。"""
    resp = await test_client.get("/api/admin/kols", headers=operator_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


async def test_viewer_cannot_list_kols(test_client, viewer_headers):
    """viewer 角色 GET /api/admin/kols 返回 403（角色不允许）。"""
    resp = await test_client.get("/api/admin/kols", headers=viewer_headers)
    assert resp.status_code == 403


async def test_unauth_cannot_list_kols(test_client):
    """无 token GET /api/admin/kols 返回 401（未认证）。"""
    resp = await test_client.get("/api/admin/kols")
    assert resp.status_code == 401


async def test_force_password_admin_gets_403(test_client, force_password_headers):
    """未改密用户即使角色正确也返回 403（强制改密检查先于角色检查）。"""
    resp = await test_client.get("/api/admin/kols", headers=force_password_headers)
    assert resp.status_code == 403
