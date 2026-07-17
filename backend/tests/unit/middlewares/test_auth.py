"""Unit tests for app.middlewares.auth — JWT auth middleware."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core.response import ErrorCode
from app.core.security import create_access_token
from app.middlewares.auth import (
    get_current_user,
    get_current_user_optional,
    require_admin,
    require_admin_or_operator,
    require_password_changed,
)
from app.models.user import User


def _make_user(**overrides) -> User:
    defaults = {
        "id": 1,
        "username": "testuser",
        "real_name": "Test User",
        "password_hash": "hash",
        "role": "admin",
        "status": "enabled",
        "password_changed_at": datetime.now(tz=timezone.utc),
        "token_version": 0,
        "deleted_at": None,
    }
    defaults.update(overrides)
    user = MagicMock(spec=User)
    for k, v in defaults.items():
        setattr(user, k, v)
    return user


def _mock_session_context_manager(user=None):
    """Create a mock that mimics AsyncSessionLocal() returning an async context manager.

    Usage: `async with AsyncSessionLocal() as session:` — so AsyncSessionLocal()
    must return something supporting `async with`.
    """
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user
    mock_session.execute.return_value = mock_result

    class _CtxMgr:
        async def __aenter__(self):
            return mock_session
        async def __aexit__(self, *args):
            pass

    # AsyncSessionLocal() must return the context manager
    return lambda: _CtxMgr()


@pytest.fixture
def admin_user():
    return _make_user(role="admin", password_changed_at=datetime.now(tz=timezone.utc))


@pytest.fixture
def operator_user():
    return _make_user(role="operator", password_changed_at=datetime.now(tz=timezone.utc))


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_get_current_user_missing_token_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=None)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["code"] == ErrorCode.AUTH_TOKEN_MISSING

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token="invalid.token.here")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_deleted_user_raises_401(self):
        user = _make_user(deleted_at=datetime.now(tz=timezone.utc))
        token = create_access_token(user_id=1, username="test", role="admin", token_version=0)

        with patch("app.middlewares.auth.AsyncSessionLocal", _mock_session_context_manager(user)):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(token=token)
            assert exc_info.value.detail["code"] == ErrorCode.AUTH_TOKEN_MISSING

    @pytest.mark.asyncio
    async def test_get_current_user_disabled_user_raises_403(self):
        user = _make_user(status="disabled")
        token = create_access_token(user_id=1, username="test", role="admin", token_version=0)

        with patch("app.middlewares.auth.AsyncSessionLocal", _mock_session_context_manager(user)):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(token=token)
            assert exc_info.value.status_code == 403
            assert exc_info.value.detail["code"] == ErrorCode.AUTH_USER_DISABLED

    @pytest.mark.asyncio
    async def test_get_current_user_token_version_mismatch_raises_401(self):
        user = _make_user(token_version=5)
        token = create_access_token(user_id=1, username="test", role="admin", token_version=0)

        with patch("app.middlewares.auth.AsyncSessionLocal", _mock_session_context_manager(user)):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(token=token)
            assert exc_info.value.detail["code"] == ErrorCode.AUTH_TOKEN_EXPIRED

    @pytest.mark.asyncio
    async def test_get_current_user_valid_token_returns_user(self):
        user = _make_user(token_version=0)
        token = create_access_token(user_id=1, username="test", role="admin", token_version=0)

        with patch("app.middlewares.auth.AsyncSessionLocal", _mock_session_context_manager(user)):
            result = await get_current_user(token=token)
            assert result.id == 1


class TestRequireAdmin:
    @pytest.mark.asyncio
    async def test_require_admin_admin_returns_user(self, admin_user):
        result = await require_admin(current_user=admin_user)
        assert result.role == "admin"

    @pytest.mark.asyncio
    async def test_require_admin_non_admin_raises_403(self, operator_user):
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(current_user=operator_user)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == ErrorCode.PERMISSION_DENIED

    @pytest.mark.asyncio
    async def test_require_admin_force_change_password_raises_403(self):
        user = _make_user(role="admin", password_changed_at=None)
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(current_user=user)
        assert exc_info.value.detail["code"] == ErrorCode.AUTH_FORCE_CHANGE_PASSWORD


class TestRequirePasswordChanged:
    @pytest.mark.asyncio
    async def test_require_password_changed_not_changed_raises_403(self):
        user = _make_user(password_changed_at=None)
        with pytest.raises(HTTPException) as exc_info:
            await require_password_changed(current_user=user)
        assert exc_info.value.detail["code"] == ErrorCode.AUTH_FORCE_CHANGE_PASSWORD

    @pytest.mark.asyncio
    async def test_require_password_changed_already_changed_returns_user(self, admin_user):
        result = await require_password_changed(current_user=admin_user)
        assert result.id == 1


class TestRequireAdminOrOperator:
    """require_admin_or_operator: admin + operator 都可读；其他角色拒绝。"""

    @pytest.mark.asyncio
    async def test_admin_role_returns_user(self, admin_user):
        result = await require_admin_or_operator(current_user=admin_user)
        assert result.role == "admin"

    @pytest.mark.asyncio
    async def test_operator_role_returns_user(self, operator_user):
        result = await require_admin_or_operator(current_user=operator_user)
        assert result.role == "operator"

    @pytest.mark.asyncio
    async def test_other_role_raises_403(self):
        user = _make_user(role="user")
        with pytest.raises(HTTPException) as exc_info:
            await require_admin_or_operator(current_user=user)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == ErrorCode.PERMISSION_DENIED

    @pytest.mark.asyncio
    async def test_force_change_password_raises_403(self):
        user = _make_user(role="admin", password_changed_at=None)
        with pytest.raises(HTTPException) as exc_info:
            await require_admin_or_operator(current_user=user)
        assert exc_info.value.detail["code"] == ErrorCode.AUTH_FORCE_CHANGE_PASSWORD


class TestGetCurrentUserOptional:
    """get_current_user_optional: 有 token 解析返回 User，无 token 或无效都返回 None，不抛异常。"""

    @pytest.mark.asyncio
    async def test_no_token_returns_none(self):
        result = await get_current_user_optional(token=None)
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_token_returns_none(self):
        result = await get_current_user_optional(token="invalid.token.here")
        assert result is None

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self):
        user = _make_user(token_version=0)
        token = create_access_token(user_id=1, username="test", role="admin", token_version=0)
        with patch("app.middlewares.auth.AsyncSessionLocal", _mock_session_context_manager(user)):
            result = await get_current_user_optional(token=token)
            assert result.id == 1

    @pytest.mark.asyncio
    async def test_user_not_found_returns_none(self):
        token = create_access_token(user_id=999, username="ghost", role="admin", token_version=0)
        with patch("app.middlewares.auth.AsyncSessionLocal", _mock_session_context_manager(user=None)):
            result = await get_current_user_optional(token=token)
            assert result is None

    @pytest.mark.asyncio
    async def test_deleted_user_returns_none(self):
        user = _make_user(deleted_at=datetime.now(tz=timezone.utc))
        token = create_access_token(user_id=1, username="test", role="admin", token_version=0)
        with patch("app.middlewares.auth.AsyncSessionLocal", _mock_session_context_manager(user)):
            result = await get_current_user_optional(token=token)
            assert result is None

    @pytest.mark.asyncio
    async def test_token_version_mismatch_returns_none(self):
        user = _make_user(token_version=5)
        token = create_access_token(user_id=1, username="test", role="admin", token_version=0)
        with patch("app.middlewares.auth.AsyncSessionLocal", _mock_session_context_manager(user)):
            result = await get_current_user_optional(token=token)
            assert result is None

    @pytest.mark.asyncio
    async def test_disabled_user_returns_none(self):
        user = _make_user(status="disabled")
        token = create_access_token(user_id=1, username="test", role="admin", token_version=0)
        with patch("app.middlewares.auth.AsyncSessionLocal", _mock_session_context_manager(user)):
            result = await get_current_user_optional(token=token)
            assert result is None
