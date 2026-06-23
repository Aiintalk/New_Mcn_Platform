"""
Integration tests for operator_persona_writer router.

Covers:
- 4 auth scenarios (no token / operator OK / admin OK / invalid token)
- GET /kols/personas (empty + with data + filters incomplete)
- POST /fetch-video (success + empty url + tikhub failure + likes threshold)
- POST /evaluate-opening (success + empty transcript + AI failure)
- POST /analyze-structure (success + empty transcript + AI failure)
- POST /chat (writing success + iteration success + AI failure + invalid scene + missing persona)
- POST /save-output (success + empty content + account isolation)
- POST /export-word (returns docx + empty content)
- GET /outputs (pagination + account isolation)
"""
from unittest.mock import patch, AsyncMock

import pytest
from sqlalchemy import text


# ---------- fixtures ----------

@pytest.fixture(autouse=True)
async def ensure_config(test_session):
    """确保测试库中有激活的 persona_writer_configs 配置。"""
    await test_session.execute(text(
        "INSERT INTO persona_writer_configs "
        "(config_key, evaluation_prompt, analysis_prompt, writing_prompt, iteration_prompt, "
        "light_model_id, heavy_model_id, is_active) "
        "VALUES (:config_key, :eval_prompt, :analysis_prompt, :writing_prompt, "
        ":iteration_prompt, NULL, NULL, true) "
        "ON CONFLICT (config_key) DO UPDATE SET "
        "evaluation_prompt = EXCLUDED.evaluation_prompt, "
        "analysis_prompt = EXCLUDED.analysis_prompt, "
        "writing_prompt = EXCLUDED.writing_prompt, "
        "iteration_prompt = EXCLUDED.iteration_prompt, "
        "is_active = true"
    ), {
        "config_key": "default",
        "eval_prompt": "评估Prompt {{transcript}}",
        "analysis_prompt": "分析Prompt {{transcript}}",
        "writing_prompt": "写作Prompt {{name}} {{soul}} {{content_plan}} {{transcript}} {{structure_analysis}} {{topic}} {{is_custom}}custom{{/is_custom}}{{!is_custom}}default{{/!is_custom}}",
        "iteration_prompt": "追问Prompt {{soul}} {{transcript}} {{structure_analysis}}",
    })
    await test_session.commit()


async def _create_kol(test_session, name="孙知羽", persona="人设A", content_plan="计划A",
                      created_by=None):
    """创建一个有 persona+content_plan 的 kol，返回 id。"""
    result = await test_session.execute(text(
        "INSERT INTO kols (name, persona, content_plan, status, created_by) "
        "VALUES (:name, :persona, :content_plan, 'signed', :created_by) "
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
        resp = await test_client.get("/api/tools/persona-writer/kols/personas")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_personas_operator_ok(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/tools/persona-writer/kols/personas",
            headers=operator_headers,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_personas_admin_ok(self, test_client, admin_headers):
        resp = await test_client.get(
            "/api/tools/persona-writer/kols/personas",
            headers=admin_headers,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_personas_invalid_token(self, test_client):
        resp = await test_client.get(
            "/api/tools/persona-writer/kols/personas",
            headers={"Authorization": "Bearer invalid_token_xxx"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /kols/personas
# ---------------------------------------------------------------------------

class TestPersonas:
    @pytest.mark.asyncio
    async def test_empty_list(self, test_client, operator_headers, test_session):
        await test_session.execute(text(
            "DELETE FROM kols WHERE persona IS NOT NULL AND content_plan IS NOT NULL"
        ))
        await test_session.commit()
        resp = await test_client.get(
            "/api/tools/persona-writer/kols/personas",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == []

    @pytest.mark.asyncio
    async def test_returns_personas(self, test_client, operator_headers, test_session):
        await _create_kol(test_session, name="测试达人A", persona="灵魂档案A", content_plan="规划A")
        resp = await test_client.get(
            "/api/tools/persona-writer/kols/personas",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        names = [p["name"] for p in body["data"]]
        assert "测试达人A" in names
        target = [p for p in body["data"] if p["name"] == "测试达人A"][0]
        assert "id" in target
        assert "soul_preview" in target
        assert "creator_name" in target

    @pytest.mark.asyncio
    async def test_filters_incomplete_kol(self, test_client, operator_headers, test_session):
        await test_session.execute(text(
            "INSERT INTO kols (name, persona, content_plan, status) "
            "VALUES ('无persona', NULL, '规划', 'signed')"
        ))
        await test_session.execute(text(
            "INSERT INTO kols (name, persona, content_plan, status) "
            "VALUES ('无content_plan', '人设', NULL, 'signed')"
        ))
        await test_session.commit()
        resp = await test_client.get(
            "/api/tools/persona-writer/kols/personas",
            headers=operator_headers,
        )
        names = [p["name"] for p in resp.json()["data"]]
        assert "无persona" not in names
        assert "无content_plan" not in names


# ---------------------------------------------------------------------------
# POST /fetch-video
# ---------------------------------------------------------------------------

class TestFetchVideo:
    @pytest.mark.asyncio
    async def test_fetch_video_success(self, test_client, operator_headers):
        with patch(
            "app.routers.operator_persona_writer.tikhub_adapter.fetch_video_by_share_url",
            new_callable=AsyncMock,
            return_value={
                "aweme_id": "7234",
                "title": "测试视频标题",
                "digg_count": 250000,
                "play_url": "https://example.com/play.mp4",
            },
        ):
            resp = await test_client.post(
                "/api/tools/persona-writer/fetch-video",
                json={"share_url": "https://v.douyin.com/xxx/"},
                headers=operator_headers,
            )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["title"] == "测试视频标题"
        assert body["data"]["digg_count"] == 250000
        assert body["data"]["likes_pass"] is True

    @pytest.mark.asyncio
    async def test_fetch_video_low_likes(self, test_client, operator_headers):
        with patch(
            "app.routers.operator_persona_writer.tikhub_adapter.fetch_video_by_share_url",
            new_callable=AsyncMock,
            return_value={
                "aweme_id": "123",
                "title": "低赞视频",
                "digg_count": 50000,
                "play_url": "",
            },
        ):
            resp = await test_client.post(
                "/api/tools/persona-writer/fetch-video",
                json={"share_url": "https://v.douyin.com/yyy/"},
                headers=operator_headers,
            )
        body = resp.json()
        assert body["data"]["likes_pass"] is False

    @pytest.mark.asyncio
    async def test_fetch_video_empty_url(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/persona-writer/fetch-video",
            json={"share_url": ""},
            headers=operator_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_fetch_video_tikhub_error(self, test_client, operator_headers):
        with patch(
            "app.routers.operator_persona_writer.tikhub_adapter.fetch_video_by_share_url",
            new_callable=AsyncMock,
            side_effect=RuntimeError("TikHub API failed"),
        ):
            resp = await test_client.post(
                "/api/tools/persona-writer/fetch-video",
                json={"share_url": "https://v.douyin.com/err/"},
                headers=operator_headers,
            )
        assert resp.status_code == 502

    @pytest.mark.asyncio
    async def test_fetch_video_writes_op_log(self, test_client, operator_headers, operator_user, test_session):
        with patch(
            "app.routers.operator_persona_writer.tikhub_adapter.fetch_video_by_share_url",
            new_callable=AsyncMock,
            return_value={
                "aweme_id": "999",
                "title": "日志测试",
                "digg_count": 100000,
                "play_url": "",
            },
        ):
            resp = await test_client.post(
                "/api/tools/persona-writer/fetch-video",
                json={"share_url": "https://v.douyin.com/log/"},
                headers=operator_headers,
            )
        assert resp.json()["success"] is True

        log_row = (await test_session.execute(text(
            "SELECT action, user_id FROM operation_logs "
            "WHERE action='persona_writer_fetch_video' "
            "ORDER BY created_at DESC LIMIT 1"
        ))).fetchone()
        assert log_row is not None
        assert log_row[1] == operator_user.id


# ---------------------------------------------------------------------------
# POST /evaluate-opening
# ---------------------------------------------------------------------------

class TestEvaluateOpening:
    @pytest.mark.asyncio
    async def test_evaluate_success(self, test_client, operator_headers):
        async def mock_stream(*args, **kwargs):
            yield "判断：通过"
            yield "\n理由：开头有吸引力"

        with patch(
            "app.routers.operator_persona_writer.yunwu_adapter.chat_stream",
            side_effect=mock_stream,
        ), patch(
            "app.routers.operator_persona_writer.AsyncSessionLocal"
        ) as mock_sl:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sl.return_value = mock_sess

            resp = await test_client.post(
                "/api/tools/persona-writer/evaluate-opening",
                json={"transcript": "对标文案全文"},
                headers=operator_headers,
            )
        assert resp.status_code == 200
        assert "判断：通过" in resp.text

    @pytest.mark.asyncio
    async def test_evaluate_empty_transcript(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/persona-writer/evaluate-opening",
            json={"transcript": ""},
            headers=operator_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_evaluate_ai_failure(self, test_client, operator_headers):
        async def mock_stream_error(*args, **kwargs):
            raise RuntimeError("AI 服务异常")
            yield  # noqa: unreachable

        with patch(
            "app.routers.operator_persona_writer.yunwu_adapter.chat_stream",
            side_effect=mock_stream_error,
        ), patch(
            "app.routers.operator_persona_writer.AsyncSessionLocal"
        ) as mock_sl:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sl.return_value = mock_sess

            resp = await test_client.post(
                "/api/tools/persona-writer/evaluate-opening",
                json={"transcript": "对标文案"},
                headers=operator_headers,
            )
        assert resp.status_code == 200
        assert "[ERROR]" in resp.text or "AI 服务异常" in resp.text


# ---------------------------------------------------------------------------
# POST /analyze-structure
# ---------------------------------------------------------------------------

class TestAnalyzeStructure:
    @pytest.mark.asyncio
    async def test_analyze_success(self, test_client, operator_headers):
        async def mock_stream(*args, **kwargs):
            yield "1. 开头：这是开头"
            yield "\n2. 主体：逐段拆解"

        with patch(
            "app.routers.operator_persona_writer.yunwu_adapter.chat_stream",
            side_effect=mock_stream,
        ), patch(
            "app.routers.operator_persona_writer.AsyncSessionLocal"
        ) as mock_sl:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sl.return_value = mock_sess

            resp = await test_client.post(
                "/api/tools/persona-writer/analyze-structure",
                json={"transcript": "对标文案全文"},
                headers=operator_headers,
            )
        assert resp.status_code == 200
        assert "开头" in resp.text

    @pytest.mark.asyncio
    async def test_analyze_empty_transcript(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/persona-writer/analyze-structure",
            json={"transcript": ""},
            headers=operator_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_analyze_ai_failure(self, test_client, operator_headers):
        async def mock_stream_error(*args, **kwargs):
            raise RuntimeError("AI 服务异常")
            yield  # noqa: unreachable

        with patch(
            "app.routers.operator_persona_writer.yunwu_adapter.chat_stream",
            side_effect=mock_stream_error,
        ), patch(
            "app.routers.operator_persona_writer.AsyncSessionLocal"
        ) as mock_sl:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sl.return_value = mock_sess

            resp = await test_client.post(
                "/api/tools/persona-writer/analyze-structure",
                json={"transcript": "对标文案"},
                headers=operator_headers,
            )
        assert resp.status_code == 200
        assert "[ERROR]" in resp.text or "AI 服务异常" in resp.text


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------

class TestChat:
    @pytest.mark.asyncio
    async def test_chat_writing_success(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session, name="写作测试达人",
                                   persona="人设", content_plan="规划")

        async def mock_stream(*args, **kwargs):
            yield "===脚本开始==="
            yield "脚本正文"
            yield "===脚本结束==="

        with patch(
            "app.routers.operator_persona_writer.yunwu_adapter.chat_stream",
            side_effect=mock_stream,
        ), patch(
            "app.routers.operator_persona_writer.AsyncSessionLocal"
        ) as mock_sl:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sl.return_value = mock_sess

            resp = await test_client.post(
                "/api/tools/persona-writer/chat",
                json={
                    "scene": "writing",
                    "topic_mode": "custom",
                    "persona_id": kol_id,
                    "transcript": "对标文案",
                    "structure_analysis": "结构分析",
                    "topic": "我的选题",
                    "messages": [{"role": "user", "content": "请仿写"}],
                },
                headers=operator_headers,
            )
        assert resp.status_code == 200
        assert "脚本正文" in resp.text

    @pytest.mark.asyncio
    async def test_chat_iteration_success(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session, name="追问测试达人",
                                   persona="人设", content_plan="规划")

        async def mock_stream(*args, **kwargs):
            yield "修改后的脚本"

        with patch(
            "app.routers.operator_persona_writer.yunwu_adapter.chat_stream",
            side_effect=mock_stream,
        ), patch(
            "app.routers.operator_persona_writer.AsyncSessionLocal"
        ) as mock_sl:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sl.return_value = mock_sess

            resp = await test_client.post(
                "/api/tools/persona-writer/chat",
                json={
                    "scene": "iteration",
                    "persona_id": kol_id,
                    "transcript": "对标文案",
                    "structure_analysis": "结构分析",
                    "messages": [{"role": "user", "content": "把结尾改一下"}],
                },
                headers=operator_headers,
            )
        assert resp.status_code == 200
        assert "修改后的脚本" in resp.text

    @pytest.mark.asyncio
    async def test_chat_persona_not_found(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/persona-writer/chat",
            json={
                "scene": "writing",
                "persona_id": 999999,
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers=operator_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_chat_invalid_scene(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session)
        resp = await test_client.post(
            "/api/tools/persona-writer/chat",
            json={
                "scene": "invalid",
                "persona_id": kol_id,
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers=operator_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_chat_empty_messages(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session)
        resp = await test_client.post(
            "/api/tools/persona-writer/chat",
            json={
                "scene": "writing",
                "persona_id": kol_id,
                "messages": [],
            },
            headers=operator_headers,
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /save-output
# ---------------------------------------------------------------------------

class TestSaveOutput:
    @pytest.mark.asyncio
    async def test_save_success(self, test_client, operator_headers, operator_user, test_session):
        resp = await test_client.post(
            "/api/tools/persona-writer/save-output",
            json={
                "title": "人设仿写_测试",
                "content": "仿写内容正文",
                "topic": "测试选题",
            },
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert "output_id" in body["data"]

        output_id = body["data"]["output_id"]
        row = (await test_session.execute(text(
            "SELECT tool_code, created_by FROM outputs WHERE id = :id"
        ), {"id": output_id})).fetchone()
        assert row[0] == "persona-writer"
        assert row[1] == operator_user.id

    @pytest.mark.asyncio
    async def test_save_empty_content(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/persona-writer/save-output",
            json={"content": ""},
            headers=operator_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_account_isolation(self, test_client, test_session,
                                     operator_user, admin_user,
                                     operator_token, admin_token):
        """用户 A 保存的 output，用户 B 查不到。"""
        resp = await test_client.post(
            "/api/tools/persona-writer/save-output",
            json={"title": "operator的", "content": "内容A"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200

        resp = await test_client.get(
            "/api/tools/persona-writer/outputs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        titles = [item["title"] for item in resp.json()["data"]["items"]]
        assert "operator的" not in titles


# ---------------------------------------------------------------------------
# POST /export-word
# ---------------------------------------------------------------------------

class TestExportWord:
    @pytest.mark.asyncio
    async def test_export_returns_docx(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/persona-writer/export-word",
            json={"content": "# 标题\n正文段落", "filename": "人设仿写_测试"},
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
            "/api/tools/persona-writer/export-word",
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
        await test_session.execute(text(
            "DELETE FROM outputs WHERE tool_code='persona-writer' AND created_by=:uid"
        ), {"uid": operator_user.id})
        await test_session.commit()

        resp = await test_client.get(
            "/api/tools/persona-writer/outputs?page=1&page_size=20",
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
        await test_session.execute(text(
            "INSERT INTO outputs (title, tool_code, tool_name, content, created_by) "
            "VALUES ('operator专属', 'persona-writer', '人设脚本仿写', 'c', :uid)"
        ), {"uid": operator_user.id})
        await test_session.commit()

        resp = await test_client.get(
            "/api/tools/persona-writer/outputs",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        titles = [item["title"] for item in resp.json()["data"]["items"]]
        assert "operator专属" in titles

        resp = await test_client.get(
            "/api/tools/persona-writer/outputs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        titles = [item["title"] for item in resp.json()["data"]["items"]]
        assert "operator专属" not in titles
