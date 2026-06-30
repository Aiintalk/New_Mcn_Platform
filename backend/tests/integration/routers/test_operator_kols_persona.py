"""
Integration tests for persona-details endpoints on admin_kols router.
GET/PUT /api/operator/kols/{kol_id}/persona-details
"""
import pytest
from sqlalchemy import text


async def _create_kol(test_session, name="人设达人"):
    result = await test_session.execute(text(
        "INSERT INTO kols (name, status) VALUES (:name, 'signed') RETURNING id"
    ), {"name": name})
    kid = result.scalar()
    await test_session.commit()
    return kid


class TestGetPersonaDetails:
    @pytest.mark.asyncio
    async def test_get_no_token(self, test_client, test_session):
        kid = await _create_kol(test_session)
        resp = await test_client.get(f"/api/operator/kols/{kid}/persona-details")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_empty(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        resp = await test_client.get(f"/api/operator/kols/{kid}/persona-details",
                                     headers=operator_headers)
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["kol_id"] == kid
        assert data["background"] is None

    @pytest.mark.asyncio
    async def test_get_not_found(self, test_client, operator_headers):
        resp = await test_client.get("/api/operator/kols/999999/persona-details",
                                     headers=operator_headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is False


class TestUpdatePersonaDetails:
    @pytest.mark.asyncio
    async def test_update_success(self, test_client, operator_headers, test_session):
        kid = await _create_kol(test_session)
        resp = await test_client.put(
            f"/api/operator/kols/{kid}/persona-details",
            json={"background": "85后，杭州人", "experience": "曾经当过护士"},
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["background"] == "85后，杭州人"
        assert body["data"]["experience"] == "曾经当过护士"

    @pytest.mark.asyncio
    async def test_update_partial(self, test_client, operator_headers, test_session):
        """只传部分字段，其他字段保持原值"""
        kid = await _create_kol(test_session)
        # 先写入全量
        await test_client.put(
            f"/api/operator/kols/{kid}/persona-details",
            json={"background": "初始背景", "experience": "初始经历"},
            headers=operator_headers,
        )
        # 只更新 background
        await test_client.put(
            f"/api/operator/kols/{kid}/persona-details",
            json={"background": "更新后背景"},
            headers=operator_headers,
        )
        resp = await test_client.get(f"/api/operator/kols/{kid}/persona-details",
                                     headers=operator_headers)
        data = resp.json()["data"]
        assert data["background"] == "更新后背景"
        assert data["experience"] == "初始经历"   # 未传的字段保持原值
