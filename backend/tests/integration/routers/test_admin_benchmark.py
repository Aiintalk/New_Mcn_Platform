"""
Integration tests for admin_benchmark.py router.

Covers:
- GET  /admin/benchmark/configs              — 配置列表
- PUT  /admin/benchmark/configs/{key}        — 更新配置（含 404 + happy path）
- GET  /admin/benchmark/analyses             — 分析记录列表
- GET  /admin/benchmark/analyses/{id}        — 详情（含 404 + happy path）
- POST /admin/benchmark/analyses/{id}/regenerate — 重置（含 404 + happy path）
- Auth: 401 / 403
"""
import pytest

from app.models.benchmark import BenchmarkAnalysis, BenchmarkConfig


class TestAdminBenchmark:
    @pytest.mark.asyncio
    async def test_list_configs_admin_ok(self, test_client, admin_headers):
        """GET /configs → 200 + list。"""
        resp = await test_client.get(
            "/api/admin/benchmark/configs", headers=admin_headers
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert isinstance(body["data"], list)

    @pytest.mark.asyncio
    async def test_update_config_not_found_404(self, test_client, admin_headers):
        """PUT 不存在的 config_key → 404。"""
        resp = await test_client.put(
            "/api/admin/benchmark/configs/nonexistent_key_xyz",
            json={"system_prompt": "x", "is_active": True},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_config_ok(self, test_client, admin_headers, test_session):
        """seed 一个 config → PUT 更新 → 200 + 返回 config_key。"""
        cfg = BenchmarkConfig(
            config_key="test_cfg_cov_xyz", system_prompt="old", is_active=True
        )
        test_session.add(cfg)
        await test_session.commit()

        resp = await test_client.put(
            "/api/admin/benchmark/configs/test_cfg_cov_xyz",
            json={"system_prompt": "new prompt", "is_active": False},
            headers=admin_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["config_key"] == "test_cfg_cov_xyz"

    @pytest.mark.asyncio
    async def test_list_analyses_admin_ok(self, test_client, admin_headers):
        """GET /analyses → 200 + list。"""
        resp = await test_client.get(
            "/api/admin/benchmark/analyses", headers=admin_headers
        )
        body = resp.json()
        assert resp.status_code == 200
        assert isinstance(body["data"], list)

    @pytest.mark.asyncio
    async def test_analysis_detail_not_found_404(self, test_client, admin_headers):
        resp = await test_client.get(
            "/api/admin/benchmark/analyses/999999", headers=admin_headers
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_analysis_detail_ok(
        self, test_client, admin_headers, test_session, admin_user
    ):
        """seed 一个 analysis → GET detail → 200 + 完整字段。"""
        a = BenchmarkAnalysis(
            account_name="cov_detail_account",
            model_used="glm-4.6",
            status="completed",
            created_by=admin_user.id,
        )
        test_session.add(a)
        await test_session.commit()
        await test_session.refresh(a)

        resp = await test_client.get(
            f"/api/admin/benchmark/analyses/{a.id}", headers=admin_headers
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["account_name"] == "cov_detail_account"
        assert body["data"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_regenerate_not_found_404(self, test_client, admin_headers):
        resp = await test_client.post(
            "/api/admin/benchmark/analyses/999999/regenerate",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_regenerate_resets_to_pending(
        self, test_client, admin_headers, test_session, admin_user
    ):
        """seed completed analysis → regenerate → status 重置为 pending。"""
        a = BenchmarkAnalysis(
            account_name="cov_regen_account",
            status="completed",
            profile_result="x",
            plan_result="y",
            created_by=admin_user.id,
        )
        test_session.add(a)
        await test_session.commit()
        await test_session.refresh(a)

        resp = await test_client.post(
            f"/api/admin/benchmark/analyses/{a.id}/regenerate",
            headers=admin_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_configs_no_token_401(self, test_client):
        resp = await test_client.get("/api/admin/benchmark/configs")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_configs_operator_forbidden_403(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/admin/benchmark/configs", headers=operator_headers
        )
        assert resp.status_code == 403
