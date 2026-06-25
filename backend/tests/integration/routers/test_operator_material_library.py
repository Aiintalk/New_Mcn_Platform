"""
Integration tests for operator_material_library router.

Covers:
- Auth (2 scenarios: operator OK / no token)
- GET /kols (empty + with data)
- GET /kols/{id} (not found + with data)
- PUT /kols/{id}/profile (update persona + content_plan + writes OperationLog)
- POST /kols/{id}/references (create + invalid type)
- DELETE /kols/{id}/references/{id} (delete + not found)
- GET /kols/{id}/intake (no intake data)
"""
import pytest
from sqlalchemy import text


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class TestAuth:
    @pytest.mark.asyncio
    async def test_operator_ok(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/tools/material-library/kols",
            headers=operator_headers,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_no_token(self, test_client):
        resp = await test_client.get("/api/tools/material-library/kols")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /kols — 红人列表
# ---------------------------------------------------------------------------

class TestListKols:
    @pytest.mark.asyncio
    async def test_returns_list(self, test_client, operator_headers, test_session):
        # Ensure at least one kol exists
        await test_session.execute(text(
            "INSERT INTO kols (name, status) VALUES ('ListTestKol', 'signed')"
        ))
        await test_session.commit()

        resp = await test_client.get(
            "/api/tools/material-library/kols",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)
        assert len(body["data"]) >= 1

    @pytest.mark.asyncio
    async def test_search_by_name(self, test_client, operator_headers, test_session):
        # Create a uniquely named kol
        await test_session.execute(text(
            "INSERT INTO kols (name, status) VALUES ('UniqueSearchKol_xyz', 'signed')"
        ))
        await test_session.commit()

        resp = await test_client.get(
            "/api/tools/material-library/kols?search=UniqueSearchKol_xyz",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert len(body["data"]) >= 1
        assert any("UniqueSearchKol_xyz" in k["name"] for k in body["data"])

    @pytest.mark.asyncio
    async def test_list_has_summary_fields(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/tools/material-library/kols",
            headers=operator_headers,
        )
        body = resp.json()
        if len(body["data"]) > 0:
            kol = body["data"][0]
            for field in ("id", "name", "has_persona", "has_content_plan",
                          "reference_count", "has_intake"):
                assert field in kol


# ---------------------------------------------------------------------------
# GET /kols/{kol_id} — 红人详情
# ---------------------------------------------------------------------------

class TestGetKolDetail:
    @pytest.mark.asyncio
    async def test_not_found(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/tools/material-library/kols/999999",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is False

    @pytest.mark.asyncio
    async def test_returns_detail(self, test_client, operator_headers, test_session):
        # Create a kol with persona
        await test_session.execute(text(
            "INSERT INTO kols (name, persona, content_plan, status) "
            "VALUES ('DetailTestKol', '这是soul.md内容', '这是内容规划', 'signed')"
        ))
        await test_session.commit()
        result = await test_session.execute(text(
            "SELECT id FROM kols WHERE name = 'DetailTestKol'"
        ))
        kol_id = result.scalar()

        resp = await test_client.get(
            f"/api/tools/material-library/kols/{kol_id}",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["name"] == "DetailTestKol"
        assert body["data"]["persona"] == "这是soul.md内容"
        assert body["data"]["content_plan"] == "这是内容规划"
        assert "references" in body["data"]


# ---------------------------------------------------------------------------
# PUT /kols/{kol_id}/profile — 更新人格档案
# ---------------------------------------------------------------------------

class TestUpdateProfile:
    @pytest.mark.asyncio
    async def test_update_persona(self, test_client, operator_headers, test_session):
        await test_session.execute(text(
            "INSERT INTO kols (name, status) VALUES ('ProfileTestKol', 'signed')"
        ))
        await test_session.commit()
        result = await test_session.execute(text(
            "SELECT id FROM kols WHERE name = 'ProfileTestKol'"
        ))
        kol_id = result.scalar()

        resp = await test_client.put(
            f"/api/tools/material-library/kols/{kol_id}/profile",
            headers=operator_headers,
            json={"persona": "更新后的soul.md"},
        )
        body = resp.json()
        assert body["success"] is True
        assert "persona" in body["data"]["updated_fields"]

    @pytest.mark.asyncio
    async def test_update_writes_operation_log(self, test_client, operator_headers, test_session):
        await test_session.execute(text(
            "INSERT INTO kols (name, status) VALUES ('LogTestKol', 'signed')"
        ))
        await test_session.commit()
        result = await test_session.execute(text(
            "SELECT id FROM kols WHERE name = 'LogTestKol'"
        ))
        kol_id = result.scalar()

        await test_client.put(
            f"/api/tools/material-library/kols/{kol_id}/profile",
            headers=operator_headers,
            json={"content_plan": "更新内容规划"},
        )

        log_count = await test_session.execute(text(
            "SELECT COUNT(*) FROM operation_logs "
            "WHERE action = 'material_library_update_profile'"
        ))
        assert int(log_count.scalar()) >= 1


# ---------------------------------------------------------------------------
# POST /kols/{kol_id}/references — 添加素材
# ---------------------------------------------------------------------------

class TestCreateReference:
    @pytest.mark.asyncio
    async def test_create_success(self, test_client, operator_headers, test_session):
        await test_session.execute(text(
            "INSERT INTO kols (name, status) VALUES ('RefTestKol', 'signed')"
        ))
        await test_session.commit()
        result = await test_session.execute(text(
            "SELECT id FROM kols WHERE name = 'RefTestKol'"
        ))
        kol_id = result.scalar()

        resp = await test_client.post(
            f"/api/tools/material-library/kols/{kol_id}/references",
            headers=operator_headers,
            json={
                "title": "测试爆款文案",
                "likes": 9999,
                "source": "抖音",
                "type": "红人爆款文案",
                "content": "这是一条测试文案内容",
            },
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["title"] == "测试爆款文案"
        assert body["data"]["type"] == "红人爆款文案"
        assert body["data"]["likes"] == 9999

    @pytest.mark.asyncio
    async def test_create_invalid_type(self, test_client, operator_headers, test_session):
        await test_session.execute(text(
            "INSERT INTO kols (name, status) VALUES ('InvalidTypeKol', 'signed')"
        ))
        await test_session.commit()
        result = await test_session.execute(text(
            "SELECT id FROM kols WHERE name = 'InvalidTypeKol'"
        ))
        kol_id = result.scalar()

        resp = await test_client.post(
            f"/api/tools/material-library/kols/{kol_id}/references",
            headers=operator_headers,
            json={
                "title": "测试",
                "type": "无效类型",
                "content": "内容",
            },
        )
        body = resp.json()
        assert body["success"] is False


# ---------------------------------------------------------------------------
# DELETE /kols/{kol_id}/references/{ref_id} — 删除素材
# ---------------------------------------------------------------------------

class TestDeleteReference:
    @pytest.mark.asyncio
    async def test_delete_success(self, test_client, operator_headers, test_session):
        # Setup: create kol + reference
        await test_session.execute(text(
            "INSERT INTO kols (name, status) VALUES ('DelRefKol', 'signed')"
        ))
        await test_session.commit()
        result = await test_session.execute(text("SELECT id FROM kols WHERE name = 'DelRefKol'"))
        kol_id = result.scalar()

        create_resp = await test_client.post(
            f"/api/tools/material-library/kols/{kol_id}/references",
            headers=operator_headers,
            json={"title": "待删除", "type": "风格参考", "content": "内容"},
        )
        ref_id = create_resp.json()["data"]["id"]

        # Delete
        resp = await test_client.delete(
            f"/api/tools/material-library/kols/{kol_id}/references/{ref_id}",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True

    @pytest.mark.asyncio
    async def test_delete_not_found(self, test_client, operator_headers, test_session):
        await test_session.execute(text(
            "INSERT INTO kols (name, status) VALUES ('NotFoundDelKol', 'signed')"
        ))
        await test_session.commit()
        result = await test_session.execute(text("SELECT id FROM kols WHERE name = 'NotFoundDelKol'"))
        kol_id = result.scalar()

        resp = await test_client.delete(
            f"/api/tools/material-library/kols/{kol_id}/references/999999",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is False


# ---------------------------------------------------------------------------
# GET /kols/{kol_id}/intake — 入驻问卷数据
# ---------------------------------------------------------------------------

class TestGetIntake:
    @pytest.mark.asyncio
    async def test_no_intake_data(self, test_client, operator_headers, test_session):
        await test_session.execute(text(
            "INSERT INTO kols (name, status) VALUES ('NoIntakeKol', 'signed')"
        ))
        await test_session.commit()
        result = await test_session.execute(text("SELECT id FROM kols WHERE name = 'NoIntakeKol'"))
        kol_id = result.scalar()

        resp = await test_client.get(
            f"/api/tools/material-library/kols/{kol_id}/intake",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"] is None
