"""Unit tests for app.core.seed — seed_initial_data admin bootstrap."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core import seed
from app.models.user import User


def _mock_session_ctx(mock_session):
    """Build a callable that mimics AsyncSessionLocal() returning an async ctx mgr.

    seed does `async with AsyncSessionLocal() as session:`, so the patched
    name must return an object supporting `async with`.
    """

    class _Ctx:
        async def __aenter__(self):
            return mock_session

        async def __aexit__(self, *args):
            pass

    return lambda: _Ctx()


def _make_mock_session(existing_user=None):
    """Mock session whose execute().scalar_one_or_none() returns `existing_user`.

    `session.add` is sync in SQLAlchemy, so it must be a MagicMock (not AsyncMock),
    otherwise calling it produces an un-awaited coroutine warning.
    """
    session = AsyncMock()
    session.add = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing_user
    session.execute.return_value = result
    return session


class TestSeedInitialData:
    @pytest.mark.asyncio
    async def test_returns_early_when_admin_already_exists(self):
        existing_admin = MagicMock(spec=User)
        session = _make_mock_session(existing_user=existing_admin)

        with patch.object(seed, "AsyncSessionLocal", _mock_session_ctx(session)):
            await seed.seed_initial_data()

        # Must not write anything — admin already there.
        session.add.assert_not_called()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_creates_admin_when_none_exists(self):
        session = _make_mock_session(existing_user=None)

        with patch.object(seed, "AsyncSessionLocal", _mock_session_ctx(session)):
            await seed.seed_initial_data()

        # Exactly one User added and commit awaited.
        session.add.assert_called_once()
        added = session.add.call_args.args[0]
        assert isinstance(added, User)
        assert added.role == "admin"
        assert added.status == "enabled"
        assert added.password_changed_at is None  # force change on first login
        session.commit.assert_awaited_once()
