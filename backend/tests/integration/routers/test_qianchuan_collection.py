"""Integration tests for operator_qianchuan_collection (Sprint 12)."""
import pytest
from sqlalchemy import text as sa_text


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestAuth:
    @pytest.mark.asyncio
    async def test_get_personas_unauthorized(self, test_client):
        resp = await test_client.get("/api/tools/qianchuan-collection/personas")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_scripts_unauthorized(self, test_client):
        resp = await test_client.get("/api/tools/qianchuan-collection/scripts?pool=global")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_post_script_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/scripts",
            json={"pool": "global", "title": "test", "content": "content"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_operator_can_access(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/qianchuan-collection/personas",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------

class TestPersonas:
    @pytest.mark.asyncio
    async def test_get_personas_empty(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/qianchuan-collection/personas",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "personas" in data["data"]

    @pytest.mark.asyncio
    async def test_create_persona_success(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/personas",
            json={"name": "测试达人A"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["name"] == "测试达人A"

    @pytest.mark.asyncio
    async def test_create_persona_duplicate_409(self, test_client, operator_token):
        # 先创建
        await test_client.post(
            "/api/tools/qianchuan-collection/personas",
            json={"name": "重复达人B"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        # 再创建同名
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/personas",
            json={"name": "重复达人B"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "PERSONA_EXISTS"

    @pytest.mark.asyncio
    async def test_create_persona_empty_name_422(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/personas",
            json={"name": "   "},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_delete_persona_success_cascades_scripts(self, test_client, operator_token):
        # 创建达人
        await test_client.post(
            "/api/tools/qianchuan-collection/personas",
            json={"name": "待删达人C"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        # 为该达人添加脚本
        await test_client.post(
            "/api/tools/qianchuan-collection/scripts",
            json={
                "pool": "persona",
                "persona_name": "待删达人C",
                "title": "待删脚本",
                "content": "这条脚本应随达人删除",
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        # 删除达人
        resp = await test_client.delete(
            "/api/tools/qianchuan-collection/personas/待删达人C",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["ok"] is True

        # 该达人脚本应不可见（软删除）
        scripts_resp = await test_client.get(
            "/api/tools/qianchuan-collection/scripts?pool=persona&persona_name=待删达人C",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert scripts_resp.json()["data"]["total"] == 0

    @pytest.mark.asyncio
    async def test_delete_persona_not_found_404(self, test_client, operator_token):
        resp = await test_client.delete(
            "/api/tools/qianchuan-collection/personas/不存在的达人XYZ",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Scripts — GET
# ---------------------------------------------------------------------------

class TestGetScripts:
    @pytest.mark.asyncio
    async def test_get_scripts_invalid_pool_400(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/qianchuan-collection/scripts?pool=invalid_pool",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_get_global_scripts_pagination(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/qianchuan-collection/scripts?pool=global&page=1&page_size=5",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "scripts" in data
        assert "total" in data
        assert "page" in data
        assert data["page_size"] == 5

    @pytest.mark.asyncio
    async def test_get_scripts_persona_mode(self, test_client, operator_token):
        # 先创建达人和脚本
        await test_client.post(
            "/api/tools/qianchuan-collection/personas",
            json={"name": "查询测试达人D"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        await test_client.post(
            "/api/tools/qianchuan-collection/scripts",
            json={
                "pool": "persona",
                "persona_name": "查询测试达人D",
                "title": "达人D脚本",
                "content": "测试达人D的脚本内容",
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        resp = await test_client.get(
            "/api/tools/qianchuan-collection/scripts?pool=persona&persona_name=查询测试达人D",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 1
        assert all(s["pool"] == "persona" for s in data["scripts"])

    @pytest.mark.asyncio
    async def test_get_scripts_search(self, test_client, operator_token):
        # 先创建一条独特标题的脚本
        unique_title = "UNIQUE_SEARCH_TITLE_12345"
        await test_client.post(
            "/api/tools/qianchuan-collection/scripts",
            json={"pool": "global", "title": unique_title, "content": "搜索测试内容"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        # 搜索
        resp = await test_client.get(
            f"/api/tools/qianchuan-collection/scripts?pool=global&q={unique_title}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 1
        assert any(s["title"] == unique_title for s in data["scripts"])

    @pytest.mark.asyncio
    async def test_get_scripts_missing_pool_422(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/qianchuan-collection/scripts",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_scripts_persona_missing_name_400(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/qianchuan-collection/scripts?pool=persona",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Scripts — POST
# ---------------------------------------------------------------------------

class TestCreateScript:
    @pytest.mark.asyncio
    async def test_create_global_script_success(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/scripts",
            json={
                "pool": "global",
                "title": "全网爆款脚本测试",
                "content": "这是一段全网高跑量千川脚本正文",
                "likes": 50000,
                "source": "抖音",
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "id" in data["data"]

    @pytest.mark.asyncio
    async def test_create_persona_script_success(self, test_client, operator_token):
        # 先创建达人
        await test_client.post(
            "/api/tools/qianchuan-collection/personas",
            json={"name": "创建脚本达人E"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/scripts",
            json={
                "pool": "persona",
                "persona_name": "创建脚本达人E",
                "title": "达人E的脚本",
                "content": "达人E脚本内容",
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert "id" in resp.json()["data"]

    @pytest.mark.asyncio
    async def test_create_script_with_script_date(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/scripts",
            json={
                "pool": "global",
                "title": "带日期的脚本",
                "content": "内容",
                "script_date": "2026-01-15",
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_create_script_invalid_date_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/scripts",
            json={
                "pool": "global",
                "title": "无效日期脚本",
                "content": "内容",
                "script_date": "not-a-date",
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_persona_script_persona_not_found_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/scripts",
            json={
                "pool": "persona",
                "persona_name": "不存在的达人ZZZZZ",
                "title": "脚本",
                "content": "正文",
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "PERSONA_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_create_script_empty_title_422(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/scripts",
            json={"pool": "global", "title": "", "content": "内容"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_script_empty_content_422(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/scripts",
            json={"pool": "global", "title": "标题", "content": ""},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_persona_script_missing_persona_name_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/scripts",
            json={"pool": "persona", "title": "脚本", "content": "正文"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Scripts — DELETE
# ---------------------------------------------------------------------------

class TestDeleteScript:
    @pytest.mark.asyncio
    async def test_delete_script_success(self, test_client, operator_token):
        # 先创建
        create_resp = await test_client.post(
            "/api/tools/qianchuan-collection/scripts",
            json={"pool": "global", "title": "待删脚本", "content": "待删内容"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        script_id = create_resp.json()["data"]["id"]

        # 删除
        resp = await test_client.delete(
            f"/api/tools/qianchuan-collection/scripts/{script_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["ok"] is True

    @pytest.mark.asyncio
    async def test_delete_script_not_found_404(self, test_client, operator_token):
        resp = await test_client.delete(
            "/api/tools/qianchuan-collection/scripts/9999999",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_script_twice_404(self, test_client, operator_token):
        # 创建
        create_resp = await test_client.post(
            "/api/tools/qianchuan-collection/scripts",
            json={"pool": "global", "title": "重复删除脚本", "content": "内容"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        script_id = create_resp.json()["data"]["id"]
        # 第一次删
        await test_client.delete(
            f"/api/tools/qianchuan-collection/scripts/{script_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        # 第二次删 → 404
        resp = await test_client.delete(
            f"/api/tools/qianchuan-collection/scripts/{script_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# parse-file
# ---------------------------------------------------------------------------

class TestParseFile:
    @pytest.mark.asyncio
    async def test_parse_txt_success(self, test_client, operator_token):
        content = "这是一段千川脚本内容测试"
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/parse-file",
            files={"file": ("script.txt", content.encode("utf-8"), "text/plain")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["text"] == content
        assert data["data"]["filename"] == "script.txt"

    @pytest.mark.asyncio
    async def test_parse_unsupported_format_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/parse-file",
            files={"file": ("script.xlsx", b"data", "application/vnd.ms-excel")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "UNSUPPORTED_FORMAT"

    @pytest.mark.asyncio
    async def test_parse_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/parse-file",
            files={"file": ("script.txt", b"hello", "text/plain")},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_parse_md_success(self, test_client, operator_token):
        content = "# 脚本标题\n\n这是脚本内容"
        resp = await test_client.post(
            "/api/tools/qianchuan-collection/parse-file",
            files={"file": ("script.md", content.encode("utf-8"), "text/markdown")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["filename"] == "script.md"
