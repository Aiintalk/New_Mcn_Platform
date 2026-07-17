"""Unit tests for app.core.database — get_db async generator."""
from unittest.mock import patch

import pytest

from app.core import database


class TestGetDb:
    @pytest.mark.asyncio
    async def test_get_db_yields_session_then_closes(self):
        """get_db() yields exactly one session and closes it after the consumer returns."""
        yielded_session = object()  # sentinel; identity is enough for this test

        class _Ctx:
            async def __aenter__(self):
                return yielded_session

            async def __aexit__(self, *args):
                return False

        with patch.object(database, "AsyncSessionLocal", lambda: _Ctx()):
            gen = database.get_db()
            session = await gen.__anext__()
            assert session is yielded_session

            with pytest.raises(StopAsyncIteration):
                await gen.__anext__()
