"""
Integration tests for operator_seeding_writer router.

Covers:
- Auth (4 scenarios)
- GET /kols/personas (3)
- References CRUD (5)
- Products CRUD (8)
- fetch-video (3)
- transcribe submit/poll (4)
- analyze-structure (2)
- ai-recommend (2)
- chat (5)
- save-output (3)
- export-word (2)
- outputs (2)
"""
import json
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from sqlalchemy import text


# ---------- fixtures ----------

@pytest.fixture(autouse=True)
async def ensure_config(test_session):
    """确保测试库中有激活的 seeding_writer_configs 配置。"""
    await test_session.execute(text(
        "INSERT INTO seeding_writer_configs "
        "(config_key, sp_system_prompt, parse_product_prompt, structure_analysis_prompt, "
        "ai_recommend_prompt, writing_prompt, iteration_prompt, "
        "light_model_id, heavy_model_id, is_active) "
        "VALUES (:config_key, :sp, :pp, :sa, :ar, :wp, :ip, NULL, NULL, true) "
        "ON CONFLICT (config_key) DO UPDATE SET "
        "sp_system_prompt = EXCLUDED.sp_system_prompt, "
        "writing_prompt = EXCLUDED.writing_prompt, "
        "iteration_prompt = EXCLUDED.iteration_prompt, "
        "is_active = true"
    ), {
        "config_key": "default",
        "sp": "卖点提取 {{raw_text}}",
        "pp": "文档解析",
        "sa": "结构拆解 {{transcript}}",
        "ar": "AI推荐 {{soul}} {{product_selling_points}}",
        "wp": "写作 {{name}} {{soul}} {{product_name}} {{transcript}} {{topic}}",
        "ip": "迭代 {{soul}} {{product_name}}",
    })
    await test_session.commit()


async def _create_kol(test_session, name="孙知羽", persona="人设A", content_plan="计划A"):
    result = await test_session.execute(text(
        "INSERT INTO kols (name, persona, content_plan, status, created_by) "
        "VALUES (:name, :persona, :content_plan, 'signed', NULL) "
        "RETURNING id"
    ), {"name": name, "persona": persona, "content_plan": content_plan})
    kol_id = result.scalar()
    await test_session.commit()
    return kol_id


async def _create_product(test_session, name="测试产品", created_by=None):
    result = await test_session.execute(text(
        "INSERT INTO seeding_writer_products "
        "(name, category, price, selling_points, target_audience, scenario, created_by) "
        "VALUES (:name, :category, :price, :sp, :ta, :sc, :created_by) "
        "RETURNING id"
    ), {
        "name": name, "category": "护肤", "price": "299",
        "sp": "保湿\n修护", "ta": "干皮", "sc": "早晚",
        "created_by": created_by,
    })
    pid = result.scalar()
    await test_session.commit()
    return pid


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class TestAuth:
    @pytest.mark.asyncio
    async def test_personas_no_token(self, test_client):
        resp = await test_client.get("/api/tools/seeding-writer/kols/personas")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_personas_operator_ok(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/tools/seeding-writer/kols/personas",
            headers=operator_headers,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_personas_admin_ok(self, test_client, admin_headers):
        resp = await test_client.get(
            "/api/tools/seeding-writer/kols/personas",
            headers=admin_headers,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_personas_invalid_token(self, test_client):
        resp = await test_client.get(
            "/api/tools/seeding-writer/kols/personas",
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
            "/api/tools/seeding-writer/kols/personas",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == []

    @pytest.mark.asyncio
    async def test_returns_personas(self, test_client, operator_headers, test_session):
        await _create_kol(test_session, name="测试达人X", persona="灵魂X", content_plan="规划X")
        resp = await test_client.get(
            "/api/tools/seeding-writer/kols/personas",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        names = [p["name"] for p in body["data"]]
        assert "测试达人X" in names
        target = [p for p in body["data"] if p["name"] == "测试达人X"][0]
        assert "soul_preview" in target
        assert "creator_name" in target

    @pytest.mark.asyncio
    async def test_filters_incomplete_kol(self, test_client, operator_headers, test_session):
        await test_session.execute(text(
            "INSERT INTO kols (name, persona, content_plan, status) "
            "VALUES ('无persona_seeding', NULL, '规划', 'signed')"
        ))
        await test_session.commit()
        resp = await test_client.get(
            "/api/tools/seeding-writer/kols/personas",
            headers=operator_headers,
        )
        names = [p["name"] for p in resp.json()["data"]]
        assert "无persona_seeding" not in names


# ---------------------------------------------------------------------------
# References CRUD
# ---------------------------------------------------------------------------

class TestReferences:
    @pytest.mark.asyncio
    async def test_list_empty(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session)
        resp = await test_client.get(
            f"/api/tools/seeding-writer/references?kol_id={kol_id}",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == []

    @pytest.mark.asyncio
    async def test_list_with_data(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session)
        await test_session.execute(text(
            "INSERT INTO seeding_writer_references (kol_id, title, content, type, likes, source) "
            "VALUES (:kol_id, :title, :content, :type, :likes, :source)"
        ), {
            "kol_id": kol_id, "title": "爆款素材", "content": "内容A",
            "type": "种草爆款", "likes": 100000, "source": "抖音",
        })
        await test_session.commit()
        resp = await test_client.get(
            f"/api/tools/seeding-writer/references?kol_id={kol_id}",
            headers=operator_headers,
        )
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["title"] == "爆款素材"

    @pytest.mark.asyncio
    async def test_create_reference(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session)
        resp = await test_client.post(
            "/api/tools/seeding-writer/references",
            json={
                "kol_id": kol_id,
                "title": "手动添加素材",
                "content": "这是一段素材内容",
                "type": "对标种草",
                "likes": 5000,
                "source": "小红书",
            },
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert "id" in body["data"]

    @pytest.mark.asyncio
    async def test_delete_reference(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session)
        result = await test_session.execute(text(
            "INSERT INTO seeding_writer_references (kol_id, title, content) "
            "VALUES (:kol_id, '删除测试', '内容') RETURNING id"
        ), {"kol_id": kol_id})
        ref_id = result.scalar()
        await test_session.commit()

        resp = await test_client.delete(
            f"/api/tools/seeding-writer/references/{ref_id}",
            headers=operator_headers,
        )
        assert resp.json()["success"] is True

        # Verify soft-deleted
        check = await test_session.execute(text(
            "SELECT deleted_at FROM seeding_writer_references WHERE id = :id"
        ), {"id": ref_id})
        assert check.scalar() is not None

    @pytest.mark.asyncio
    async def test_import_from_douyin_success(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session)
        with patch(
            "app.routers.operator_seeding_writer.tikhub_adapter.fetch_video_by_share_url",
            new_callable=AsyncMock,
            return_value={"title": "视频标题", "play_url": "https://example.com/v.mp4", "digg_count": 200000},
        ), patch(
            "app.routers.operator_seeding_writer._download_video",
            new_callable=AsyncMock,
            return_value=b"video_bytes",
        ), patch(
            "app.routers.operator_seeding_writer.oss_adapter.upload_file",
            new_callable=AsyncMock,
        ), patch(
            "app.routers.operator_seeding_writer.oss_adapter.get_download_url",
            new_callable=AsyncMock,
            return_value="https://signed-url.example.com/audio.mp4",
        ), patch(
            "app.routers.operator_seeding_writer.asr_adapter.transcribe",
            new_callable=AsyncMock,
            return_value="ASR转录文本",
        ):
            resp = await test_client.post(
                "/api/tools/seeding-writer/references/import-from-douyin",
                json={"kol_id": kol_id, "share_url": "https://v.douyin.com/xxx/"},
                headers=operator_headers,
            )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["title"] == "视频标题"
        assert body["data"]["content"] == "ASR转录文本"


# ---------------------------------------------------------------------------
# Products CRUD
# ---------------------------------------------------------------------------

class TestProducts:
    @pytest.mark.asyncio
    async def test_list_products(self, test_client, operator_headers, test_session):
        await _create_product(test_session, name="产品列表测试")
        resp = await test_client.get(
            "/api/tools/seeding-writer/products",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert "items" in body["data"]
        assert "pagination" in body["data"]

    @pytest.mark.asyncio
    async def test_create_product(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/seeding-writer/products",
            json={"name": "新产品A", "category": "护肤", "price": "199"},
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert "id" in body["data"]

    @pytest.mark.asyncio
    async def test_update_product(self, test_client, operator_headers, test_session):
        pid = await _create_product(test_session, name="更新前")
        resp = await test_client.put(
            f"/api/tools/seeding-writer/products/{pid}",
            json={"name": "更新后", "price": "399"},
            headers=operator_headers,
        )
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_delete_product(self, test_client, operator_headers, test_session):
        pid = await _create_product(test_session, name="删除测试")
        resp = await test_client.delete(
            f"/api/tools/seeding-writer/products/{pid}",
            headers=operator_headers,
        )
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_company_shared(self, test_client, admin_user, operator_user, test_session):
        """产品公司共享：admin 创建的产品 operator 也能看到。"""
        # Insert product created by admin
        await test_session.execute(text(
            "INSERT INTO seeding_writer_products (name, created_by) "
            "VALUES ('admin创建的产品', :uid)"
        ), {"uid": admin_user.id})
        await test_session.commit()

        # Operator should see it
        from app.core.security import create_access_token
        op_token = create_access_token(
            user_id=int(operator_user.id),
            username=str(operator_user.username),
            role=str(operator_user.role),
            token_version=int(operator_user.token_version),
        )
        resp = await test_client.get(
            "/api/tools/seeding-writer/products",
            headers={"Authorization": f"Bearer {op_token}"},
        )
        names = [item["name"] for item in resp.json()["data"]["items"]]
        assert "admin创建的产品" in names

    @pytest.mark.asyncio
    async def test_create_product_empty_name(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/seeding-writer/products",
            json={"name": ""},
            headers=operator_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_update_nonexistent_product(self, test_client, operator_headers):
        resp = await test_client.put(
            "/api/tools/seeding-writer/products/999999",
            json={"name": "不存在"},
            headers=operator_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_product(self, test_client, operator_headers):
        resp = await test_client.delete(
            "/api/tools/seeding-writer/products/999999",
            headers=operator_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Products /parse-document
# ---------------------------------------------------------------------------

class TestParseDocument:
    @pytest.mark.asyncio
    async def test_parse_document_success(self, test_client, operator_headers):
        """文档解析成功（mock AI 返回 JSON）。"""
        async def mock_stream(*args, **kwargs):
            yield '{"name": " parsed_product", "category": "test"}'

        with patch(
            "app.routers.operator_seeding_writer.yunwu_adapter.chat_stream",
            side_effect=mock_stream,
        ):
            resp = await test_client.post(
                "/api/tools/seeding-writer/products/parse-document",
                files={"files": ("test.txt", b"Product info content here for testing", "text/plain")},
                headers=operator_headers,
            )
        body = resp.json()
        assert body["success"] is True
        assert "name" in body["data"]
        assert "_rawText" in body["data"]

    @pytest.mark.asyncio
    async def test_parse_document_no_files(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/seeding-writer/products/parse-document",
            files={},
            headers=operator_headers,
        )
        assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# /extract-selling-points (流式)
# ---------------------------------------------------------------------------

class TestExtractSellingPoints:
    @pytest.mark.asyncio
    async def test_extract_sp_success(self, test_client, operator_headers):
        async def mock_stream(*args, **kwargs):
            yield "卖点1\n卖点2\n卖点3"

        with patch(
            "app.routers.operator_seeding_writer.yunwu_adapter.chat_stream",
            side_effect=mock_stream,
        ):
            resp = await test_client.post(
                "/api/tools/seeding-writer/products/extract-selling-points",
                json={"raw_text": "产品资料原文内容"},
                headers=operator_headers,
            )
        assert resp.status_code == 200
        content = resp.text
        assert "卖点1" in content

    @pytest.mark.asyncio
    async def test_extract_sp_empty_raw_text(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/seeding-writer/products/extract-selling-points",
            json={"raw_text": ""},
            headers=operator_headers,
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /fetch-video
# ---------------------------------------------------------------------------

class TestFetchVideo:
    @pytest.mark.asyncio
    async def test_fetch_video_success(self, test_client, operator_headers):
        with patch(
            "app.routers.operator_seeding_writer.tikhub_adapter.fetch_video_by_share_url",
            new_callable=AsyncMock,
            return_value={"aweme_id": "123", "title": "测试视频", "digg_count": 100000, "play_url": "https://example.com/p.mp4"},
        ):
            resp = await test_client.post(
                "/api/tools/seeding-writer/fetch-video",
                json={"share_url": "https://v.douyin.com/xxx/"},
                headers=operator_headers,
            )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["title"] == "测试视频"
        assert body["data"]["digg_count"] == 100000

    @pytest.mark.asyncio
    async def test_fetch_video_empty_url(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/seeding-writer/fetch-video",
            json={"share_url": ""},
            headers=operator_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_fetch_video_tikhub_error(self, test_client, operator_headers):
        with patch(
            "app.routers.operator_seeding_writer.tikhub_adapter.fetch_video_by_share_url",
            new_callable=AsyncMock,
            side_effect=RuntimeError("TikHub error"),
        ):
            resp = await test_client.post(
                "/api/tools/seeding-writer/fetch-video",
                json={"share_url": "https://v.douyin.com/xxx/"},
                headers=operator_headers,
            )
        assert resp.status_code == 502


# ---------------------------------------------------------------------------
# /transcribe/submit + /poll
# ---------------------------------------------------------------------------

class TestTranscribe:
    @pytest.mark.asyncio
    async def test_submit_success(self, test_client, operator_headers):
        with patch(
            "app.routers.operator_seeding_writer._download_video",
            new_callable=AsyncMock,
            return_value=b"video",
        ), patch(
            "app.routers.operator_seeding_writer.oss_adapter.upload_file",
            new_callable=AsyncMock,
        ), patch(
            "app.routers.operator_seeding_writer.oss_adapter.get_download_url",
            new_callable=AsyncMock,
            return_value="https://signed.example.com/a.mp4",
        ), patch(
            "app.routers.operator_seeding_writer.asr_adapter.submit_transcription",
            new_callable=AsyncMock,
            return_value="task_abc123",
        ):
            resp = await test_client.post(
                "/api/tools/seeding-writer/transcribe/submit",
                json={"play_url": "https://example.com/video.mp4"},
                headers=operator_headers,
            )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["task_id"] == "task_abc123"

    @pytest.mark.asyncio
    async def test_poll_processing(self, test_client, operator_headers):
        with patch(
            "app.routers.operator_seeding_writer.asr_adapter.query_transcription",
            new_callable=AsyncMock,
            return_value={"StatusText": "RUNNING"},
        ):
            resp = await test_client.post(
                "/api/tools/seeding-writer/transcribe/poll",
                json={"task_id": "abc123"},
                headers=operator_headers,
            )
        body = resp.json()
        assert body["data"]["status"] == "processing"

    @pytest.mark.asyncio
    async def test_poll_done(self, test_client, operator_headers):
        with patch(
            "app.routers.operator_seeding_writer.asr_adapter.query_transcription",
            new_callable=AsyncMock,
            return_value={
                "StatusText": "SUCCESS",
                "Result": {"Sentences": [{"Text": "完整的"}, {"Text": "文案"}]},
            },
        ):
            resp = await test_client.post(
                "/api/tools/seeding-writer/transcribe/poll",
                json={"task_id": "abc123"},
                headers=operator_headers,
            )
        body = resp.json()
        assert body["data"]["status"] == "done"
        assert body["data"]["text"] == "完整的文案"

    @pytest.mark.asyncio
    async def test_poll_error(self, test_client, operator_headers):
        with patch(
            "app.routers.operator_seeding_writer.asr_adapter.query_transcription",
            new_callable=AsyncMock,
            return_value={"StatusText": "FAILED", "StatusCode": 500},
        ):
            resp = await test_client.post(
                "/api/tools/seeding-writer/transcribe/poll",
                json={"task_id": "abc123"},
                headers=operator_headers,
            )
        assert resp.status_code == 502


# ---------------------------------------------------------------------------
# /analyze-structure (流式)
# ---------------------------------------------------------------------------

class TestAnalyzeStructure:
    @pytest.mark.asyncio
    async def test_analyze_success(self, test_client, operator_headers):
        async def mock_stream(*args, **kwargs):
            yield "结构拆解结果"

        with patch(
            "app.routers.operator_seeding_writer.yunwu_adapter.chat_stream",
            side_effect=mock_stream,
        ):
            resp = await test_client.post(
                "/api/tools/seeding-writer/analyze-structure",
                json={"transcript": "对标文案内容"},
                headers=operator_headers,
            )
        assert resp.status_code == 200
        assert "结构拆解" in resp.text

    @pytest.mark.asyncio
    async def test_analyze_empty_transcript(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/seeding-writer/analyze-structure",
            json={"transcript": ""},
            headers=operator_headers,
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /ai-recommend (流式)
# ---------------------------------------------------------------------------

class TestAiRecommend:
    @pytest.mark.asyncio
    async def test_ai_recommend_success(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session)
        pid = await _create_product(test_session)

        async def mock_stream(*args, **kwargs):
            yield "推荐角度1\n推荐角度2"

        with patch(
            "app.routers.operator_seeding_writer.yunwu_adapter.chat_stream",
            side_effect=mock_stream,
        ):
            resp = await test_client.post(
                "/api/tools/seeding-writer/ai-recommend",
                json={"persona_id": kol_id, "product_id": pid, "transcript": "对标文案"},
                headers=operator_headers,
            )
        assert resp.status_code == 200
        assert "推荐角度" in resp.text

    @pytest.mark.asyncio
    async def test_ai_recommend_product_not_found(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session)
        resp = await test_client.post(
            "/api/tools/seeding-writer/ai-recommend",
            json={"persona_id": kol_id, "product_id": 999999},
            headers=operator_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /chat (流式)
# ---------------------------------------------------------------------------

class TestChat:
    @pytest.mark.asyncio
    async def test_chat_writing_success(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session)
        pid = await _create_product(test_session)

        async def mock_stream(*args, **kwargs):
            yield "脚本文案"

        with patch(
            "app.routers.operator_seeding_writer.yunwu_adapter.chat_stream",
            side_effect=mock_stream,
        ):
            resp = await test_client.post(
                "/api/tools/seeding-writer/chat",
                json={
                    "scene": "writing",
                    "persona_id": kol_id,
                    "product_id": pid,
                    "transcript": "对标文案",
                    "topic": "夏日防晒",
                    "messages": [{"role": "user", "content": "写脚本"}],
                },
                headers=operator_headers,
            )
        assert resp.status_code == 200
        assert "脚本文案" in resp.text

    @pytest.mark.asyncio
    async def test_chat_iteration_success(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session)
        pid = await _create_product(test_session)

        async def mock_stream(*args, **kwargs):
            yield "修改后脚本"

        with patch(
            "app.routers.operator_seeding_writer.yunwu_adapter.chat_stream",
            side_effect=mock_stream,
        ):
            resp = await test_client.post(
                "/api/tools/seeding-writer/chat",
                json={
                    "scene": "iteration",
                    "persona_id": kol_id,
                    "product_id": pid,
                    "messages": [{"role": "user", "content": "再改改"}],
                },
                headers=operator_headers,
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_chat_invalid_scene(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/seeding-writer/chat",
            json={
                "scene": "invalid",
                "persona_id": 1,
                "product_id": 1,
                "messages": [{"role": "user", "content": "test"}],
            },
            headers=operator_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_chat_empty_messages(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/seeding-writer/chat",
            json={
                "scene": "writing",
                "persona_id": 1,
                "product_id": 1,
                "messages": [],
            },
            headers=operator_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_chat_missing_product(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session)
        resp = await test_client.post(
            "/api/tools/seeding-writer/chat",
            json={
                "scene": "writing",
                "persona_id": kol_id,
                "product_id": 0,
                "messages": [{"role": "user", "content": "test"}],
            },
            headers=operator_headers,
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /save-output
# ---------------------------------------------------------------------------

class TestSaveOutput:
    @pytest.mark.asyncio
    async def test_save_success(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/seeding-writer/save-output",
            json={"content": "脚本内容", "title": "测试保存", "topic": "选题A"},
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert "output_id" in body["data"]

    @pytest.mark.asyncio
    async def test_save_empty_content(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/seeding-writer/save-output",
            json={"content": ""},
            headers=operator_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_save_account_isolation(self, test_client, operator_headers, admin_headers, test_session):
        """保存的 output 只有创建者能看到。"""
        resp = await test_client.post(
            "/api/tools/seeding-writer/save-output",
            json={"content": "我的脚本"},
            headers=operator_headers,
        )
        assert resp.json()["success"] is True

        # Admin should not see operator's outputs
        resp2 = await test_client.get(
            "/api/tools/seeding-writer/outputs",
            headers=admin_headers,
        )
        items = resp2.json()["data"]["items"]
        assert all(item["content"] != "我的脚本" for item in items)


# ---------------------------------------------------------------------------
# /export-word
# ---------------------------------------------------------------------------

class TestExportWord:
    @pytest.mark.asyncio
    async def test_export_success(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/seeding-writer/export-word",
            json={"content": "脚本正文内容", "filename": "测试种草脚本"},
            headers=operator_headers,
        )
        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("content-disposition", "")

    @pytest.mark.asyncio
    async def test_export_empty_content(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/tools/seeding-writer/export-word",
            json={"content": ""},
            headers=operator_headers,
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /outputs
# ---------------------------------------------------------------------------

class TestOutputs:
    @pytest.mark.asyncio
    async def test_outputs_pagination(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/tools/seeding-writer/outputs",
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert "pagination" in body["data"]

    @pytest.mark.asyncio
    async def test_outputs_account_isolation(self, test_client, operator_headers, admin_headers):
        """operator 看不到 admin 的 outputs（反之亦然）。"""
        # Admin saves an output
        await test_client.post(
            "/api/tools/seeding-writer/save-output",
            json={"content": "admin私有脚本"},
            headers=admin_headers,
        )

        # Operator should not see it
        resp = await test_client.get(
            "/api/tools/seeding-writer/outputs",
            headers=operator_headers,
        )
        items = resp.json()["data"]["items"]
        assert all("admin私有脚本" != item["content"] for item in items)
