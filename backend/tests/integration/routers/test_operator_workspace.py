"""
Integration tests for operator_workspace router.

Covers:
- GET /{kol_id}/dashboard  (聚合：kol info + benchmarks + active_products)
- GET/POST/PUT/DELETE /{kol_id}/benchmarks
- GET/PUT /{kol_id}/active-products
"""
import pytest
from sqlalchemy import text


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

async def _create_kol(test_session, name="测试达人"):
    result = await test_session.execute(text(
        "INSERT INTO kols (name, status) VALUES (:name, 'signed') RETURNING id"
    ), {"name": name})
    kid = result.scalar()
    await test_session.commit()
    return kid


async def _create_product(test_session, nickname="测试产品"):
    result = await test_session.execute(text(
        "INSERT INTO qianchuan_products (nickname, mechanism_exclusive) VALUES (:n, false) RETURNING id"
    ), {"n": nickname})
    pid = result.scalar()
    await test_session.commit()
    return pid


async def _create_benchmark(test_session, kol_id, account_name="小鹿", account_type="content"):
    result = await test_session.execute(text(
        "INSERT INTO kol_benchmarks (kol_id, account_name, account_type, sort_order) "
        "VALUES (:kid, :name, :type, 0) RETURNING id"
    ), {"kid": kol_id, "name": account_name, "type": account_type})
    bid = result.scalar()
    await test_session.commit()
    return bid


# ---------------------------------------------------------------------------
# GET /{kol_id}/dashboard
# ---------------------------------------------------------------------------

class TestDashboard:
    @pytest.mark.asyncio
    async def test_dashboard_no_token(self, test_client, test_session):
        kid = await _create_kol(test_session)
        resp = await test_client.get(f"/api/operator/workspace/{kid}/dashboard")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_dashboard_kol_not_found(self, test_client, operator_headers):
        resp = await test_client.get("/api/operator/workspace/999999/dashboard",
                                     headers=operator_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_dashboard_structure(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session, "仪表盘达人")
        resp = await test_client.get(f"/api/operator/workspace/{kid}/dashboard",
                                     headers=operator_headers)
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert "kol" in data
        assert "benchmarks" in data
        assert "content" in data["benchmarks"]
        assert "livestream" in data["benchmarks"]
        assert "active_products" in data

    @pytest.mark.asyncio
    async def test_dashboard_with_benchmarks(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        await _create_benchmark(test_session, kid, "小鹿内容", "content")
        await _create_benchmark(test_session, kid, "橙子直播", "livestream")
        resp = await test_client.get(f"/api/operator/workspace/{kid}/dashboard",
                                     headers=operator_headers)
        data = resp.json()["data"]
        assert len(data["benchmarks"]["content"]) == 1
        assert len(data["benchmarks"]["livestream"]) == 1
        assert data["benchmarks"]["content"][0]["account_name"] == "小鹿内容"


# ---------------------------------------------------------------------------
# Benchmarks CRUD
# ---------------------------------------------------------------------------

class TestBenchmarks:
    @pytest.mark.asyncio
    async def test_create_benchmark(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        resp = await test_client.post(
            f"/api/operator/workspace/{kid}/benchmarks",
            json={"account_name": "新账号", "account_type": "content", "description": "测试简介"},
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["account_name"] == "新账号"
        assert body["data"]["account_type"] == "content"

    @pytest.mark.asyncio
    async def test_create_benchmark_invalid_type(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        resp = await test_client.post(
            f"/api/operator/workspace/{kid}/benchmarks",
            json={"account_name": "非法类型", "account_type": "invalid"},
            headers=operator_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_benchmark(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        bid = await _create_benchmark(test_session, kid, "原名称")
        resp = await test_client.put(
            f"/api/operator/workspace/{kid}/benchmarks/{bid}",
            json={"account_name": "新名称", "account_type": "livestream"},
            headers=operator_headers,
        )
        assert resp.json()["data"]["account_name"] == "新名称"

    @pytest.mark.asyncio
    async def test_delete_benchmark(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        bid = await _create_benchmark(test_session, kid, "待删对标")
        resp = await test_client.delete(
            f"/api/operator/workspace/{kid}/benchmarks/{bid}",
            headers=operator_headers,
        )
        assert resp.json()["success"] is True
        # 验证物理删除
        row = await test_session.execute(
            text("SELECT id FROM kol_benchmarks WHERE id = :id"), {"id": bid}
        )
        assert row.scalar() is None

    @pytest.mark.asyncio
    async def test_delete_benchmark_not_found(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        resp = await test_client.delete(
            f"/api/operator/workspace/{kid}/benchmarks/999999",
            headers=operator_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Active Products
# ---------------------------------------------------------------------------

class TestActiveProducts:
    @pytest.mark.asyncio
    async def test_list_active_products_empty(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        resp = await test_client.get(f"/api/operator/workspace/{kid}/active-products",
                                     headers=operator_headers)
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == []

    @pytest.mark.asyncio
    async def test_update_active_products(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        pid1 = await _create_product(test_session, "产品A")
        pid2 = await _create_product(test_session, "产品B")
        resp = await test_client.put(
            f"/api/operator/workspace/{kid}/active-products",
            json={"product_ids": [pid1, pid2]},
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert set(body["data"]["active_product_ids"]) == {pid1, pid2}

    @pytest.mark.asyncio
    async def test_update_active_products_replaces(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        pid1 = await _create_product(test_session, "旧产品")
        pid2 = await _create_product(test_session, "新产品")
        # 先设置 pid1
        await test_client.put(f"/api/operator/workspace/{kid}/active-products",
                               json={"product_ids": [pid1]}, headers=operator_headers)
        # 替换成 pid2
        await test_client.put(f"/api/operator/workspace/{kid}/active-products",
                               json={"product_ids": [pid2]}, headers=operator_headers)
        resp = await test_client.get(f"/api/operator/workspace/{kid}/active-products",
                                     headers=operator_headers)
        ids = [p["id"] for p in resp.json()["data"]]
        assert pid2 in ids
        assert pid1 not in ids

    @pytest.mark.asyncio
    async def test_update_active_products_invalid_id(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        resp = await test_client.put(
            f"/api/operator/workspace/{kid}/active-products",
            json={"product_ids": [999999]},
            headers=operator_headers,
        )
        assert resp.status_code == 400
