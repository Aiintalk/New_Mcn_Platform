"""
Integration tests for operator_qianchuan_products router.

Covers:
- Auth: 401 without token, 200 operator OK, 200 admin OK
- GET  /api/operator/qianchuan-products  (list, pagination, search)
- POST /api/operator/qianchuan-products  (create, validation)
- PUT  /api/operator/qianchuan-products/{id}  (update)
- DELETE /api/operator/qianchuan-products/{id}  (soft delete)
"""
import pytest
from sqlalchemy import text


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

async def _create_product(test_session, nickname="大红瓶", mechanism_exclusive=False):
    result = await test_session.execute(text(
        "INSERT INTO qianchuan_products (nickname, core_selling_point, mechanism_exclusive) "
        "VALUES (:nickname, '美白', :me) RETURNING id"
    ), {"nickname": nickname, "me": mechanism_exclusive})
    pid = result.scalar()
    await test_session.commit()
    return pid


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestAuth:
    @pytest.mark.asyncio
    async def test_list_no_token(self, test_client):
        resp = await test_client.get("/api/operator/qianchuan-products")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_operator_ok(self, test_client, operator_headers):
        resp = await test_client.get("/api/operator/qianchuan-products", headers=operator_headers)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_admin_ok(self, test_client, admin_headers):
        resp = await test_client.get("/api/operator/qianchuan-products", headers=admin_headers)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_invalid_token(self, test_client):
        resp = await test_client.get(
            "/api/operator/qianchuan-products",
            headers={"Authorization": "Bearer invalid_xxx"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/operator/qianchuan-products
# ---------------------------------------------------------------------------

class TestListProducts:
    @pytest.mark.asyncio
    async def test_empty_list(self, test_client, operator_headers, test_session):
        await test_session.execute(text("DELETE FROM kol_active_products"))
        await test_session.execute(text("DELETE FROM qianchuan_products"))
        await test_session.commit()
        resp = await test_client.get("/api/operator/qianchuan-products", headers=operator_headers)
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["items"] == []
        assert body["data"]["pagination"]["total"] == 0

    @pytest.mark.asyncio
    async def test_returns_products(self, test_client, operator_headers, test_session):
        await _create_product(test_session, "大红瓶")
        resp = await test_client.get("/api/operator/qianchuan-products", headers=operator_headers)
        body = resp.json()
        names = [p["nickname"] for p in body["data"]["items"]]
        assert "大红瓶" in names

    @pytest.mark.asyncio
    async def test_search_by_nickname(self, test_client, operator_headers, test_session):
        await _create_product(test_session, "搜索专用产品ABC")
        resp = await test_client.get(
            "/api/operator/qianchuan-products?q=搜索专用",
            headers=operator_headers,
        )
        body = resp.json()
        assert any("搜索专用" in p["nickname"] for p in body["data"]["items"])

    @pytest.mark.asyncio
    async def test_soft_deleted_not_returned(self, test_client, operator_headers, test_session):
        pid = await _create_product(test_session, "软删测试产品")
        await test_session.execute(
            text("UPDATE qianchuan_products SET deleted_at = NOW() WHERE id = :id"), {"id": pid}
        )
        await test_session.commit()
        resp = await test_client.get("/api/operator/qianchuan-products", headers=operator_headers)
        names = [p["nickname"] for p in resp.json()["data"]["items"]]
        assert "软删测试产品" not in names


# ---------------------------------------------------------------------------
# POST /api/operator/qianchuan-products
# ---------------------------------------------------------------------------

class TestCreateProduct:
    @pytest.mark.asyncio
    async def test_create_success(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/operator/qianchuan-products",
            json={"nickname": "新品番茄精华", "core_selling_point": "提亮", "mechanism_exclusive": False},
            headers=operator_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["data"]["nickname"] == "新品番茄精华"
        assert "id" in body["data"]

    @pytest.mark.asyncio
    async def test_create_missing_nickname(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/operator/qianchuan-products",
            json={"core_selling_point": "美白"},
            headers=operator_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_with_exclusive(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/operator/qianchuan-products",
            json={"nickname": "独家机制产品", "mechanism_exclusive": True},
            headers=operator_headers,
        )
        assert resp.json()["data"]["mechanism_exclusive"] is True


# ---------------------------------------------------------------------------
# PUT /api/operator/qianchuan-products/{id}
# ---------------------------------------------------------------------------

class TestUpdateProduct:
    @pytest.mark.asyncio
    async def test_update_success(self, test_client, operator_headers, test_session):
        pid = await _create_product(test_session, "待更新产品")
        resp = await test_client.put(
            f"/api/operator/qianchuan-products/{pid}",
            json={"nickname": "已更新产品", "core_selling_point": "保湿"},
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["nickname"] == "已更新产品"

    @pytest.mark.asyncio
    async def test_update_not_found(self, test_client, operator_headers):
        resp = await test_client.put(
            "/api/operator/qianchuan-products/999999",
            json={"nickname": "不存在"},
            headers=operator_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/operator/qianchuan-products/{id}
# ---------------------------------------------------------------------------

class TestDeleteProduct:
    @pytest.mark.asyncio
    async def test_soft_delete(self, test_client, operator_headers, test_session):
        pid = await _create_product(test_session, "待删除产品")
        resp = await test_client.delete(
            f"/api/operator/qianchuan-products/{pid}",
            headers=operator_headers,
        )
        assert resp.json()["success"] is True
        # 验证 deleted_at 已设置
        row = await test_session.execute(
            text("SELECT deleted_at FROM qianchuan_products WHERE id = :id"), {"id": pid}
        )
        assert row.scalar() is not None

    @pytest.mark.asyncio
    async def test_delete_not_found(self, test_client, operator_headers):
        resp = await test_client.delete(
            "/api/operator/qianchuan-products/999999",
            headers=operator_headers,
        )
        assert resp.status_code == 404
