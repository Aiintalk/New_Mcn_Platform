"""
Integration tests for operator_qianchuan_writer router.

Covers:
- 4 auth scenarios (no token / operator OK / admin OK / invalid token)
- GET /kols/personas (empty + with data)
- POST /parse-file (txt success + unsupported format)
- POST /chat (stream success + AI failure)
- POST /save-output (success + account isolation)
- POST /export-word (returns docx bytes)
- GET /outputs (pagination + account isolation)
"""
import io
from unittest.mock import patch, AsyncMock

import pytest
from sqlalchemy import text


# ---------- fixtures ----------

@pytest.fixture(autouse=True)
async def ensure_config(test_session):
    """确保测试库中有激活的 qianchuan_writer_configs 配置。"""
    await test_session.execute(text(
        "INSERT INTO qianchuan_writer_configs (config_key, system_prompt, ai_model_id, is_active) "
        "VALUES ('default', '测试Prompt {{name}} {{soul}} {{content_plan}}', NULL, true) "
        "ON CONFLICT (config_key) DO UPDATE SET "
        "system_prompt = EXCLUDED.system_prompt, is_active = true"
    ))
    await test_session.commit()


async def _create_kol(test_session, name="孙知羽", persona="人设A", content_plan="计划A",
                      created_by=None):
    """创建一个有 persona+content_plan 的 kol，返回 id。"""
    result = await test_session.execute(text(
        "INSERT INTO kols (name, persona, content_plan, status, created_by) "
        "VALUES (:name, :persona, :content_plan, 'active', :created_by) "
        "RETURNING id"
    ), {
        "name": name, "persona": persona,
        "content_plan": content_plan, "created_by": created_by,
    })
    kol_id = result.scalar()
    await test_session.commit()
    return kol_id


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class TestAuth:
    @pytest.mark.asyncio
    async def test_personas_no_token(self, test_client):
        resp = await test_client.get("/api/tools/qianchuan-writer/kols/personas")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_personas_operator_ok(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/tools/qianchuan-writer/kols/personas",
            headers=operator_headers,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_personas_admin_ok(self, test_client, admin_headers):
        resp = await test_client.get(
            "/api/tools/qianchuan-writer/kols/personas",
            headers=admin_headers,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_personas_invalid_token(self, test_client):
        resp = await test_client.get(
            "/api/tools/qianchuan-writer/kols/personas",
            headers={"Authorization": "Bearer invalid_token_xxx"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /kols/personas
# ---------------------------------------------------------------------------

class TestPersonas:
    @pytest.mark.asyncio
    async def test_empty_list(self, test_client, operator_headers, test_session):
        # 清掉匹配的 kols
        await test_session.execute(text(
            "DELETE FROM kols WHERE persona IS NOT NULL AND content_plan IS NOT NULL"
        ))
        await test_session.commit()
        resp = await test_client.get(
            "/api/tools/qianchuan-writer/kols/personas",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == []

    @pytest.mark.asyncio
    async def test_returns_personas(self, test_client, operator_headers, test_session):
        await _create_kol(test_session, name="测试达人A", persona="灵魂档案A", content_plan="规划A")
        resp = await test_client.get(
            "/api/tools/qianchuan-writer/kols/personas",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        names = [p["name"] for p in body["data"]]
        assert "测试达人A" in names
        # 验证字段
        target = [p for p in body["data"] if p["name"] == "测试达人A"][0]
        assert "id" in target
        assert "soul_preview" in target
        assert "creator_name" in target

    @pytest.mark.asyncio
    async def test_filters_incomplete_kol(self, test_client, operator_headers, test_session):
        """persona 为空或 content_plan 为空的 kol 不出现。"""
        await test_session.execute(text(
            "INSERT INTO kols (name, persona, content_plan, status) "
            "VALUES ('无 persona', NULL, '规划', 'active')"
        ))
        await test_session.execute(text(
            "INSERT INTO kols (name, persona, content_plan, status) "
            "VALUES ('无 content_plan', '人设', NULL, 'active')"
        ))
        await test_session.commit()
        resp = await test_client.get(
            "/api/tools/qianchuan-writer/kols/personas",
            headers=operator_headers,
        )
        names = [p["name"] for p in resp.json()["data"]]
        assert "无 persona" not in names
        assert "无 content_plan" not in names


# ---------------------------------------------------------------------------
# POST /parse-file
# ---------------------------------------------------------------------------

class TestParseFile:
    @pytest.mark.asyncio
    async def test_txt_success(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/qianchuan-writer/parse-file",
            files={"file": ("test.txt", b"hello world content", "text/plain")},
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["code"] == "OK"
        assert "text" in body["data"]
        assert "word_count" in body["data"]
        assert "hello" in body["data"]["text"]

    @pytest.mark.asyncio
    async def test_unsupported_format(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/qianchuan-writer/parse-file",
            files={"file": ("test.xyz", b"binary", "application/octet-stream")},
            headers=operator_headers,
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["success"] is False

    @pytest.mark.asyncio
    async def test_no_token(self, test_client):
        resp = await test_client.post(
            "/api/tools/qianchuan-writer/parse-file",
            files={"file": ("test.txt", b"hello", "text/plain")},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------

class TestChat:
    @pytest.mark.asyncio
    async def test_chat_success(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session, name="AI测试达人",
                                   persona="人设", content_plan="规划")

        async def mock_stream(*args, **kwargs):
            yield "你好"
            yield "仿写完成"

        with patch(
            "app.routers.operator_qianchuan_writer.yunwu_adapter.chat_stream",
            side_effect=mock_stream,
        ), patch(
            "app.routers.operator_qianchuan_writer.AsyncSessionLocal"
        ) as mock_sl:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sl.return_value = mock_sess

            resp = await test_client.post(
                "/api/tools/qianchuan-writer/chat",
                json={
                    "messages": [{"role": "user", "content": "请仿写"}],
                    "persona_id": kol_id,
                },
                headers=operator_headers,
            )
        assert resp.status_code == 200
        assert "你好" in resp.text
        assert "仿写完成" in resp.text

    @pytest.mark.asyncio
    async def test_chat_persona_not_found(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/qianchuan-writer/chat",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "persona_id": 999999,
            },
            headers=operator_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_chat_empty_messages(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session)
        resp = await test_client.post(
            "/api/tools/qianchuan-writer/chat",
            json={"messages": [], "persona_id": kol_id},
            headers=operator_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_chat_ai_failure(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session, name="错误达人")

        async def mock_stream_error(*args, **kwargs):
            raise RuntimeError("AI 服务异常")
            yield  # noqa: unreachable — make it an async generator

        with patch(
            "app.routers.operator_qianchuan_writer.yunwu_adapter.chat_stream",
            side_effect=mock_stream_error,
        ), patch(
            "app.routers.operator_qianchuan_writer.AsyncSessionLocal"
        ) as mock_sl:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sl.return_value = mock_sess

            resp = await test_client.post(
                "/api/tools/qianchuan-writer/chat",
                json={
                    "messages": [{"role": "user", "content": "hi"}],
                    "persona_id": kol_id,
                },
                headers=operator_headers,
            )
        # 流式接口错误被吞掉并写入响应
        assert resp.status_code == 200
        assert "[ERROR]" in resp.text or "AI 服务异常" in resp.text


# ---------------------------------------------------------------------------
# POST /save-output
# ---------------------------------------------------------------------------

class TestSaveOutput:
    @pytest.mark.asyncio
    async def test_save_success(self, test_client, operator_headers, operator_user, test_session):
        resp = await test_client.post(
            "/api/tools/qianchuan-writer/save-output",
            json={
                "title": "千川仿写_测试",
                "content": "仿写内容正文",
                "product_name": "测试产品",
            },
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert "output_id" in body["data"]

        # 验证数据库写入 + 账号绑定
        output_id = body["data"]["output_id"]
        row = (await test_session.execute(text(
            "SELECT tool_code, created_by FROM outputs WHERE id = :id"
        ), {"id": output_id})).fetchone()
        assert row[0] == "qianchuan-writer"
        assert row[1] == operator_user.id

    @pytest.mark.asyncio
    async def test_save_empty_content(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/qianchuan-writer/save-output",
            json={"content": ""},
            headers=operator_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_account_isolation(self, test_client, test_session,
                                     operator_user, admin_user,
                                     operator_token, admin_token):
        """用户 A 保存的 output，用户 B 查不到。"""
        # operator 保存
        resp = await test_client.post(
            "/api/tools/qianchuan-writer/save-output",
            json={"title": "operator的", "content": "内容A"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200

        # admin 查询历史，不应该看到 operator 的 output
        resp = await test_client.get(
            "/api/tools/qianchuan-writer/outputs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        titles = [item["title"] for item in body["data"]["items"]]
        assert "operator的" not in titles


# ---------------------------------------------------------------------------
# POST /export-word
# ---------------------------------------------------------------------------

class TestExportWord:
    @pytest.mark.asyncio
    async def test_export_returns_docx(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/qianchuan-writer/export-word",
            json={"content": "# 标题\n正文段落", "filename": "千川仿写_测试"},
            headers=operator_headers,
        )
        assert resp.status_code == 200
        assert "wordprocessingml.document" in resp.headers.get("content-type", "")
        content_disp = resp.headers.get("content-disposition", "")
        assert "attachment" in content_disp
        assert len(resp.content) > 0

    @pytest.mark.asyncio
    async def test_export_empty_content(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/qianchuan-writer/export-word",
            json={"content": ""},
            headers=operator_headers,
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /outputs
# ---------------------------------------------------------------------------

class TestOutputs:
    @pytest.mark.asyncio
    async def test_pagination_envelope(self, test_client, operator_headers, operator_user, test_session):
        # 清掉该用户的历史
        await test_session.execute(text(
            "DELETE FROM outputs WHERE tool_code='qianchuan-writer' AND created_by=:uid"
        ), {"uid": operator_user.id})
        await test_session.commit()

        resp = await test_client.get(
            "/api/tools/qianchuan-writer/outputs?page=1&page_size=20",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert "items" in body["data"]
        assert "pagination" in body["data"]
        assert body["data"]["pagination"]["page"] == 1
        assert body["data"]["pagination"]["page_size"] == 20

    @pytest.mark.asyncio
    async def test_account_isolation(self, test_client, test_session,
                                     operator_user, operator_token, admin_token):
        """用户 A 只能查到自己的 outputs。"""
        # 直接向 DB 插一条属于 operator 的 output
        await test_session.execute(text(
            "INSERT INTO outputs (title, tool_code, tool_name, content, created_by) "
            "VALUES ('operator专属', 'qianchuan-writer', '千川文案写作', 'c', :uid)"
        ), {"uid": operator_user.id})
        await test_session.commit()

        # operator 自己能查到
        resp = await test_client.get(
            "/api/tools/qianchuan-writer/outputs",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        titles = [item["title"] for item in resp.json()["data"]["items"]]
        assert "operator专属" in titles

        # admin 查不到 operator 的
        resp = await test_client.get(
            "/api/tools/qianchuan-writer/outputs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        titles = [item["title"] for item in resp.json()["data"]["items"]]
        assert "operator专属" not in titles
