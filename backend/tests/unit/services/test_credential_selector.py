"""Unit tests for app.services.credential_selector — key pool selection logic."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.credential_selector import pick_credential, report_failure, report_success


def _mock_credential_row(id=1, weight=1, status="enabled", cooldown_until=None,
                          quota_limit=None, quota_used=0, config=None):
    return {
        "id": id,
        "weight": weight,
        "status": status,
        "cooldown_until": cooldown_until,
        "quota_limit": quota_limit,
        "quota_used": quota_used,
        "config": config or {},
    }


class TestPickCredential:
    @pytest.mark.asyncio
    async def test_pick_credential_no_available_raises_runtime_error(self):
        mock_db = AsyncMock()
        # db.execute returns a result; result.mappings().all() returns []
        # Use MagicMock for result because .mappings().all() are sync calls
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        with pytest.raises(RuntimeError, match="No available credential"):
            await pick_credential("ai", mock_db)

    @pytest.mark.asyncio
    async def test_pick_credential_returns_credential(self):
        mock_db = AsyncMock()
        row = _mock_credential_row(id=10, weight=5)

        # First execute: raw SQL query returns mapping result (sync methods)
        mapping_result = MagicMock()
        mapping_result.mappings.return_value.all.return_value = [row]

        # Second execute: ORM query returns scalar (sync method)
        orm_cred = MagicMock()
        orm_cred.id = 10
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = orm_cred

        mock_db.execute.side_effect = [mapping_result, scalar_result]

        with patch("app.services.credential_selector.random.choices", return_value=[row]):
            result = await pick_credential("ai", mock_db)
        assert result.id == 10

    @pytest.mark.asyncio
    async def test_pick_credential_filters_by_model(self):
        mock_db = AsyncMock()
        rows = [
            _mock_credential_row(id=1, config={"model": "gpt-4"}),
            _mock_credential_row(id=2, config={"model": "claude"}),
        ]

        mapping_result = MagicMock()
        mapping_result.mappings.return_value.all.return_value = rows

        orm_cred = MagicMock()
        orm_cred.id = 2
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = orm_cred

        mock_db.execute.side_effect = [mapping_result, scalar_result]

        with patch("app.services.credential_selector.random.choices", return_value=[rows[1]]):
            result = await pick_credential("ai", mock_db, model="claude")
            assert result.id == 2


class TestReportSuccess:
    @pytest.mark.asyncio
    async def test_report_success_executes_update(self):
        mock_db = AsyncMock()
        await report_success(42, mock_db)
        assert mock_db.execute.call_count == 1
        assert mock_db.commit.call_count == 1


class TestReportFailure:
    @pytest.mark.asyncio
    async def test_report_failure_increments_fail_count(self):
        mock_db = AsyncMock()
        mock_row = MagicMock()
        mock_row.fail_count = 1

        # First execute: SELECT returns row
        select_result = MagicMock()
        select_result.fetchone.return_value = mock_row

        # Second execute: UPDATE
        mock_db.execute.side_effect = [select_result, AsyncMock()]

        await report_failure(42, mock_db)
        assert mock_db.commit.call_count == 1
        # Check update params
        update_call = mock_db.execute.call_args_list[1]
        params = update_call[0][1]
        assert params["fail_count"] == 2

    @pytest.mark.asyncio
    async def test_report_failure_triggers_cooldown_at_threshold(self):
        mock_db = AsyncMock()
        mock_row = MagicMock()
        mock_row.fail_count = 2  # Will become 3

        select_result = MagicMock()
        select_result.fetchone.return_value = mock_row
        mock_db.execute.side_effect = [select_result, AsyncMock()]

        await report_failure(42, mock_db)

        update_call = mock_db.execute.call_args_list[1]
        params = update_call[0][1]
        assert params["fail_count"] == 3
        assert params["cooldown_until"] is not None

    @pytest.mark.asyncio
    async def test_report_failure_no_cooldown_below_threshold(self):
        mock_db = AsyncMock()
        mock_row = MagicMock()
        mock_row.fail_count = 0

        select_result = MagicMock()
        select_result.fetchone.return_value = mock_row
        mock_db.execute.side_effect = [select_result, AsyncMock()]

        await report_failure(42, mock_db)

        update_call = mock_db.execute.call_args_list[1]
        params = update_call[0][1]
        assert params["fail_count"] == 1
        assert params["cooldown_until"] is None
