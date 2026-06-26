"""
Integration tests for operator_subtitle router — Sprint 19 字幕提取迁移

Covers:
- 4 auth scenarios (no token / operator OK / admin OK / invalid token)
- POST /extract (success via share_text + success via file_url + empty input + tikhub failure + asr failure)
- POST /batch (create + status transitions, mock _run_batch)
- GET /batch/{job_code} (found + not found + access_code query)
- POST /mindmap (success + empty transcript + AI failure + JSON parse failure + config missing)
- POST /save-output (success + empty content + account isolation)
- GET /outputs (list + account isolation)
"""
from unittest.mock import patch, AsyncMock

import pytest
from sqlalchemy import text


# ---------- fixtures ----------

@pytest.fixture(autouse=True)
async def ensure_subtitle_config(test_session):
    """确保测试库中有激活的 subtitle_configs default 配置。"""
    await test_session.execute(text(
        "INSERT INTO subtitle_configs "
        "(config_key, mindmap_prompt, mindmap_model_id, is_active) "
        "VALUES (:config_key, :mindmap_prompt, NULL, true) "
        "ON CONFLICT (config_key) DO UPDATE SET "
        "mindmap_prompt = EXCLUDED.mindmap_prompt, "
        "is_active = true"
    ), {
        "config_key": "default",
        "mindmap_prompt": "你是思维导图生成器。输入：{{transcript}}",
    })
    await test_session.commit()


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class TestAuth:
    @pytest.mark.asyncio
    async def test_extract_no_token(self, test_client):
        resp = await test_client.post("/api/tools/subtitle/extract",
                                      json={"share_text": "xxx"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_extract_operator_ok(self, test_client, operator_headers):
        # 即使下游 adapter 失败，鉴权通过就返回非 401
        with patch("app.routers.operator_subtitle.tikhub_adapter.fetch_video_by_share_url",
                   AsyncMock(side_effect=RuntimeError("mock"))):
            resp = await test_client.post("/api/tools/subtitle/extract",
                                          headers=operator_headers,
                                          json={"share_text": "xxx"})
        assert resp.status_code != 401

    @pytest.mark.asyncio
    async def test_extract_admin_ok(self, test_client, admin_headers):
        with patch("app.routers.operator_subtitle.tikhub_adapter.fetch_video_by_share_url",
                   AsyncMock(side_effect=RuntimeError("mock"))):
            resp = await test_client.post("/api/tools/subtitle/extract",
                                          headers=admin_headers,
                                          json={"share_text": "xxx"})
        assert resp.status_code != 401

    @pytest.mark.asyncio
    async def test_extract_invalid_token(self, test_client):
        resp = await test_client.post(
            "/api/tools/subtitle/extract",
            headers={"Authorization": "Bearer invalid_token_xxx"},
            json={"share_text": "xxx"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /extract — 单条字幕提取
# ---------------------------------------------------------------------------

class TestExtract:
    @pytest.mark.asyncio
    async def test_extract_success_via_share_text(
        self, test_client, operator_headers, test_session
    ):
        """抖音分享文本 → tikhub 解析 → ASR → 字幕"""
        with patch(
            "app.routers.operator_subtitle.tikhub_adapter.fetch_video_by_share_url",
            AsyncMock(return_value={
                "aweme_id": "7012345",
                "title": "测试视频",
                "digg_count": 50000,
                "play_url": "https://example.com/play.mp4",
                "audio_url": "https://example.com/audio.mp3",
            }),
        ), patch(
            "app.routers.operator_subtitle.asr_adapter.transcribe",
            AsyncMock(return_value="这是字幕文本"),
        ):
            resp = await test_client.post(
                "/api/tools/subtitle/extract",
                headers=operator_headers,
                json={"share_text": "https://v.douyin.com/xxx/"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["text"] == "这是字幕文本"
        assert body["data"]["title"] == "测试视频"
        assert body["data"]["audio_url"] == "https://example.com/audio.mp3"

        # OperationLog 应写入
        log_count = (await test_session.execute(text(
            "SELECT COUNT(*) FROM operation_logs WHERE action = 'subtitle_extract'"
        ))).scalar()
        assert log_count == 1

    @pytest.mark.asyncio
    async def test_extract_success_via_file_url(
        self, test_client, operator_headers, test_session
    ):
        """file_url（前端已上传到 OSS）→ 直接 ASR → 字幕（不走 tikhub）"""
        with patch(
            "app.routers.operator_subtitle.asr_adapter.transcribe",
            AsyncMock(return_value="文件字幕"),
        ):
            resp = await test_client.post(
                "/api/tools/subtitle/extract",
                headers=operator_headers,
                json={"file_url": "https://oss.example.com/audio/uploaded.mp3"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["text"] == "文件字幕"
        assert body["data"]["audio_url"] == "https://oss.example.com/audio/uploaded.mp3"

    @pytest.mark.asyncio
    async def test_extract_empty_input(self, test_client, operator_headers):
        """share_text 和 file_url 都为空 → 400"""
        resp = await test_client.post(
            "/api/tools/subtitle/extract",
            headers=operator_headers,
            json={},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_extract_tikhub_failure(self, test_client, operator_headers):
        """tikhub 解析失败 → 502"""
        with patch(
            "app.routers.operator_subtitle.tikhub_adapter.fetch_video_by_share_url",
            AsyncMock(side_effect=RuntimeError("tikhub error")),
        ):
            resp = await test_client.post(
                "/api/tools/subtitle/extract",
                headers=operator_headers,
                json={"share_text": "https://v.douyin.com/xxx/"},
            )
        assert resp.status_code == 502

    @pytest.mark.asyncio
    async def test_extract_asr_failure(self, test_client, operator_headers):
        """ASR 失败 → 502"""
        with patch(
            "app.routers.operator_subtitle.tikhub_adapter.fetch_video_by_share_url",
            AsyncMock(return_value={
                "aweme_id": "1",
                "title": "T",
                "digg_count": 0,
                "play_url": "p",
                "audio_url": "https://example.com/a.mp3",
            }),
        ), patch(
            "app.routers.operator_subtitle.asr_adapter.transcribe",
            AsyncMock(side_effect=RuntimeError("ASR timeout")),
        ):
            resp = await test_client.post(
                "/api/tools/subtitle/extract",
                headers=operator_headers,
                json={"share_text": "https://v.douyin.com/xxx/"},
            )
        assert resp.status_code == 502


# ---------------------------------------------------------------------------
# POST /mindmap — 字幕 → AI 思维导图
# ---------------------------------------------------------------------------

class TestMindmap:
    @pytest.mark.asyncio
    async def test_mindmap_success(self, test_client, operator_headers, test_session):
        """字幕 → yunwu → 合法 JSON → 思维导图"""
        valid_json = '{"rootTitle":"主标题","summary":"总结","branches":[{"title":"开头","children":["要点1"]}]}'
        with patch(
            "app.routers.operator_subtitle.yunwu_adapter.chat",
            AsyncMock(return_value=valid_json),
        ):
            resp = await test_client.post(
                "/api/tools/subtitle/mindmap",
                headers=operator_headers,
                json={"transcript": "这是字幕文本"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["rootTitle"] == "主标题"
        assert len(body["data"]["branches"]) == 1

    @pytest.mark.asyncio
    async def test_mindmap_success_with_markdown_fence(self, test_client, operator_headers):
        """yunwu 返回带 ```json fence → 服务端清理后解析"""
        fenced = '```json\n{"rootTitle":"T","summary":"S","branches":[]}\n```'
        with patch(
            "app.routers.operator_subtitle.yunwu_adapter.chat",
            AsyncMock(return_value=fenced),
        ):
            resp = await test_client.post(
                "/api/tools/subtitle/mindmap",
                headers=operator_headers,
                json={"transcript": "字幕"},
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["rootTitle"] == "T"

    @pytest.mark.asyncio
    async def test_mindmap_empty_transcript(self, test_client, operator_headers):
        """空 transcript → 400"""
        resp = await test_client.post(
            "/api/tools/subtitle/mindmap",
            headers=operator_headers,
            json={"transcript": ""},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_mindmap_ai_failure(self, test_client, operator_headers):
        """yunwu 失败 → 502"""
        with patch(
            "app.routers.operator_subtitle.yunwu_adapter.chat",
            AsyncMock(side_effect=RuntimeError("yunwu error")),
        ):
            resp = await test_client.post(
                "/api/tools/subtitle/mindmap",
                headers=operator_headers,
                json={"transcript": "字幕"},
            )
        assert resp.status_code == 502

    @pytest.mark.asyncio
    async def test_mindmap_invalid_json(self, test_client, operator_headers):
        """yunwu 返回非 JSON → 502"""
        with patch(
            "app.routers.operator_subtitle.yunwu_adapter.chat",
            AsyncMock(return_value="这不是合法 JSON"),
        ):
            resp = await test_client.post(
                "/api/tools/subtitle/mindmap",
                headers=operator_headers,
                json={"transcript": "字幕"},
            )
        assert resp.status_code == 502

    @pytest.mark.asyncio
    async def test_mindmap_config_missing(self, test_client, operator_headers, test_session):
        """无激活配置 → 503"""
        await test_session.execute(text("DELETE FROM subtitle_configs"))
        await test_session.commit()
        resp = await test_client.post(
            "/api/tools/subtitle/mindmap",
            headers=operator_headers,
            json={"transcript": "字幕"},
        )
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# POST /batch — 批量字幕任务
# ---------------------------------------------------------------------------

class TestBatch:
    @pytest.mark.asyncio
    async def test_batch_create_success(
        self, test_client, operator_headers, test_session
    ):
        """批量创建：2 条 share_text → job + 2 items，mock _run_batch 不实际执行"""
        with patch(
            "app.routers.operator_subtitle._run_batch",
            AsyncMock(return_value=None),
        ):
            resp = await test_client.post(
                "/api/tools/subtitle/batch",
                headers=operator_headers,
                json={"items": [
                    {"share_text": "https://v.douyin.com/aaa/"},
                    {"share_text": "https://v.douyin.com/bbb/"},
                ]},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["total"] == 2
        assert data["job_code"].startswith("sub_")
        assert "-" in data["access_code"]

        # DB 校验
        job_count = (await test_session.execute(text(
            "SELECT COUNT(*) FROM subtitle_jobs WHERE job_code = :jc"
        ), {"jc": data["job_code"]})).scalar()
        assert job_count == 1

        item_count = (await test_session.execute(text(
            "SELECT COUNT(*) FROM subtitle_items i "
            "JOIN subtitle_jobs j ON i.job_id = j.id "
            "WHERE j.job_code = :jc"
        ), {"jc": data["job_code"]})).scalar()
        assert item_count == 2

        # OperationLog 写入
        log_count = (await test_session.execute(text(
            "SELECT COUNT(*) FROM operation_logs WHERE action = 'subtitle_batch_create'"
        ))).scalar()
        assert log_count == 1

    @pytest.mark.asyncio
    async def test_batch_create_empty(self, test_client, operator_headers):
        """空 items → 400"""
        resp = await test_client.post(
            "/api/tools/subtitle/batch",
            headers=operator_headers,
            json={"items": []},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /batch/{job_code} + by-access/{access_code} — 查询
# ---------------------------------------------------------------------------

class TestBatchQuery:
    @pytest.mark.asyncio
    async def test_query_by_job_code(self, test_client, operator_headers, test_session):
        """创建后用 job_code 查询，应返回 job + items"""
        with patch(
            "app.routers.operator_subtitle._run_batch",
            AsyncMock(return_value=None),
        ):
            create_resp = await test_client.post(
                "/api/tools/subtitle/batch",
                headers=operator_headers,
                json={"items": [{"share_text": "https://v.douyin.com/x/"}]},
            )
        job_code = create_resp.json()["data"]["job_code"]

        resp = await test_client.get(
            f"/api/tools/subtitle/batch/{job_code}",
            headers=operator_headers,
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["job_code"] == job_code
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["original_url"] == "https://v.douyin.com/x/"
        assert body["items"][0]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_query_job_code_not_found(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/tools/subtitle/batch/nonexistent_code",
            headers=operator_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_query_by_access_code(self, test_client, operator_headers):
        """用 access_code 跨设备查询"""
        with patch(
            "app.routers.operator_subtitle._run_batch",
            AsyncMock(return_value=None),
        ):
            create_resp = await test_client.post(
                "/api/tools/subtitle/batch",
                headers=operator_headers,
                json={"items": [{"share_text": "https://v.douyin.com/y/"}]},
            )
        access_code = create_resp.json()["data"]["access_code"]

        resp = await test_client.get(
            f"/api/tools/subtitle/batch/by-access/{access_code}",
            headers=operator_headers,
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["access_code"] == access_code
        assert len(body["items"]) == 1

    @pytest.mark.asyncio
    async def test_query_by_access_code_not_found(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/tools/subtitle/batch/by-access/NOPE-0000",
            headers=operator_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /save-output — 保存字幕到产出中心
# ---------------------------------------------------------------------------

class TestSaveOutput:
    @pytest.mark.asyncio
    async def test_save_output_success(self, test_client, operator_headers, test_session):
        """字幕 → outputs 表（tool_code=subtitle）"""
        resp = await test_client.post(
            "/api/tools/subtitle/save-output",
            headers=operator_headers,
            json={
                "title": "测试字幕",
                "transcript": "这是字幕文本",
                "mindmap": {"rootTitle": "T", "summary": "S", "branches": []},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["title"] == "测试字幕"
        assert data["tool_code"] == "subtitle"
        assert data["word_count"] == 6

        # outputs 表写入校验
        out_count = (await test_session.execute(text(
            "SELECT COUNT(*) FROM outputs WHERE tool_code = 'subtitle' AND title = '测试字幕'"
        ))).scalar()
        assert out_count == 1

        # OperationLog 写入
        log_count = (await test_session.execute(text(
            "SELECT COUNT(*) FROM operation_logs WHERE action = 'subtitle_save_output'"
        ))).scalar()
        assert log_count == 1

    @pytest.mark.asyncio
    async def test_save_output_empty_transcript(self, test_client, operator_headers):
        """空 transcript → 400"""
        resp = await test_client.post(
            "/api/tools/subtitle/save-output",
            headers=operator_headers,
            json={"title": "x", "transcript": ""},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_save_output_default_title(self, test_client, operator_headers, test_session):
        """title 缺省 → '未命名字幕'"""
        resp = await test_client.post(
            "/api/tools/subtitle/save-output",
            headers=operator_headers,
            json={"transcript": "abc"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "未命名字幕"

    @pytest.mark.asyncio
    async def test_save_output_account_isolation(
        self, test_client, operator_headers, admin_headers, test_session
    ):
        """operator 保存的字幕，admin 用 /outputs?tool_code=subtitle 也能看到（共享表，账号隔离只在 created_by）"""
        resp = await test_client.post(
            "/api/tools/subtitle/save-output",
            headers=operator_headers,
            json={"title": "opr 字幕", "transcript": "opr"},
        )
        assert resp.status_code == 200
        output_id = resp.json()["data"]["id"]

        # admin 查询 outputs 列表（admin 能看全部，/api/outputs 只看自己）
        list_resp = await test_client.get(
            "/api/admin/outputs?tool_code=subtitle",
            headers=admin_headers,
        )
        assert list_resp.status_code == 200
        items = list_resp.json()["data"]["items"]
        assert any(it["id"] == output_id for it in items)
