"""
Integration tests for operator homepage router - stats and trend endpoints.
"""
import pytest

from app.models.task import TaskJob
from app.models.output import Output


class TestHomepageStats:
    """GET /api/operator/homepage/stats"""

    @pytest.mark.asyncio
    async def test_stats_returns_expected_structure(
        self, test_client, operator_headers, operator_user
    ):
        resp = await test_client.get(
            "/api/operator/homepage/stats", headers=operator_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        fields = [
            "today_outputs",
            "today_outputs_change",
            "week_outputs",
            "week_outputs_change",
            "in_progress_tasks",
            "week_token_usage",
            "week_tool_count",
            "tool_usage_breakdown",
            "recent_tools",
            "last_login_at",
        ]
        for field in fields:
            assert field in data["data"], f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_stats_counts_own_outputs_only(
        self, test_client, operator_headers, operator_user, test_session
    ):
        output = Output(
            title="Stats Output",
            tool_code="stats_tool",
            tool_name="Stats Tool",
            created_by=operator_user.id,
        )
        test_session.add(output)
        await test_session.commit()

        resp = await test_client.get(
            "/api/operator/homepage/stats", headers=operator_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["today_outputs"] >= 1

    @pytest.mark.asyncio
    async def test_stats_counts_in_progress_tasks(
        self, test_client, operator_headers, operator_user, test_session
    ):
        task = TaskJob(
            task_no="STATS-PROC",
            tool_code="stats_proc",
            tool_name="Stats Processing",
            status="processing",
            created_by=operator_user.id,
        )
        test_session.add(task)
        await test_session.commit()

        resp = await test_client.get(
            "/api/operator/homepage/stats", headers=operator_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["in_progress_tasks"] >= 1

    @pytest.mark.asyncio
    async def test_stats_excludes_deleted_outputs(
        self, test_client, operator_headers, operator_user, test_session
    ):
        from datetime import datetime, timezone

        active = Output(
            title="Active Stats",
            tool_code="active_stats",
            tool_name="Active Stats",
            created_by=operator_user.id,
        )
        deleted = Output(
            title="Deleted Stats",
            tool_code="deleted_stats",
            tool_name="Deleted Stats",
            created_by=operator_user.id,
            deleted_at=datetime.now(tz=timezone.utc),
        )
        test_session.add_all([active, deleted])
        await test_session.commit()

        resp = await test_client.get(
            "/api/operator/homepage/stats", headers=operator_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["today_outputs"] >= 1

    @pytest.mark.asyncio
    async def test_stats_tool_usage_breakdown_structure(
        self, test_client, operator_headers, operator_user, test_session
    ):
        task = TaskJob(
            task_no="STATS-BRK",
            tool_code="breakdown_tool",
            tool_name="Breakdown Tool",
            status="completed",
            created_by=operator_user.id,
        )
        test_session.add(task)
        await test_session.commit()

        resp = await test_client.get(
            "/api/operator/homepage/stats", headers=operator_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        breakdown = data["data"]["tool_usage_breakdown"]
        if breakdown:
            assert "tool_name" in breakdown[0]
            assert "tool_code" in breakdown[0]
            assert "count" in breakdown[0]
            assert "percentage" in breakdown[0]

    @pytest.mark.asyncio
    async def test_stats_requires_auth(self, test_client):
        resp = await test_client.get("/api/operator/homepage/stats")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_stats_admin_can_access(self, test_client, admin_headers, admin_user):
        resp = await test_client.get(
            "/api/operator/homepage/stats", headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


class TestHomepageTrend:
    """GET /api/operator/homepage/trend"""

    @pytest.mark.asyncio
    async def test_trend_returns_7_days(
        self, test_client, operator_headers, operator_user
    ):
        resp = await test_client.get(
            "/api/operator/homepage/trend", headers=operator_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        trend = data["data"]["trend"]
        assert len(trend) == 7
        for entry in trend:
            assert "date" in entry
            assert "count" in entry

    @pytest.mark.asyncio
    async def test_trend_dates_are_mm_dd_format(
        self, test_client, operator_headers, operator_user
    ):
        resp = await test_client.get(
            "/api/operator/homepage/trend", headers=operator_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        for entry in data["data"]["trend"]:
            assert len(entry["date"]) == 5
            assert entry["date"][2] == "-"

    @pytest.mark.asyncio
    async def test_trend_counts_own_outputs(
        self, test_client, operator_headers, operator_user, test_session
    ):
        output = Output(
            title="Trend Output",
            tool_code="trend_tool",
            tool_name="Trend Tool",
            created_by=operator_user.id,
        )
        test_session.add(output)
        await test_session.commit()

        resp = await test_client.get(
            "/api/operator/homepage/trend", headers=operator_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        today_count = data["data"]["trend"][-1]["count"]
        assert today_count >= 1

    @pytest.mark.asyncio
    async def test_trend_requires_auth(self, test_client):
        resp = await test_client.get("/api/operator/homepage/trend")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_trend_admin_can_access(self, test_client, admin_headers, admin_user):
        resp = await test_client.get(
            "/api/operator/homepage/trend", headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["data"]["trend"]) == 7
