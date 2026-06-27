"""
Integration tests for operator_subtitle router — Sprint 19 字幕提取迁移

Covers:
- 4 auth scenarios (no token / operator OK / admin OK / invalid token)
- POST /extract (success via share_text + success via file_url + empty input + tikhub failure + asr failure)
- POST /batch (create + status transitions, mock _run_batch)
- GET /batch/{job_code} (found + not found + cross-user 404)
- GET /batches (我的批量任务列表 + 分页 + 空列表 + 跨用户隔离)
- POST /mindmap (success + empty transcript + AI failure + JSON parse failure + config missing)
- POST /save-output (success + empty content + account isolation)
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock

import pytest
from passlib.context import CryptContext
from sqlalchemy import text

from app.core.security import create_access_token
from app.models.user import User

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


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
    """POST /extract 测试。

    extract 改异步后，HTTP 响应只返回 {job_code, status}，
    实际的解析+ASR 在 _run_single_extract 后台任务里跑（见 TestRunSingleExtract）。
    """

    @pytest.mark.asyncio
    async def test_extract_success_via_share_text(
        self, test_client, operator_headers, test_session
    ):
        """share_text 提交 → 立即返回 job_code（mock _run_single_extract 不实际跑）。"""
        with patch(
            "app.routers.operator_subtitle._run_single_extract",
            AsyncMock(return_value=None),
        ):
            resp = await test_client.post(
                "/api/tools/subtitle/extract",
                headers=operator_headers,
                json={"share_text": "https://v.douyin.com/xxx/"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["status"] == "processing"
        job_code = body["data"]["job_code"]
        assert job_code.startswith("sub_")

        # DB 校验：subtitle_jobs (kind='single', total=1) + 1 个 subtitle_items
        job_row = (await test_session.execute(text(
            "SELECT sj.kind, sj.status, sj.total, si.original_url "
            "FROM subtitle_jobs sj "
            "LEFT JOIN subtitle_items si ON si.job_id = sj.id "
            "WHERE sj.job_code = :jc"
        ), {"jc": job_code})).fetchone()
        assert job_row is not None
        assert job_row.kind == "single"
        assert job_row.status == "processing"
        assert job_row.total == 1

        item_count = (await test_session.execute(text(
            "SELECT COUNT(*) FROM subtitle_items si "
            "JOIN subtitle_jobs sj ON sj.id = si.job_id WHERE sj.job_code = :jc"
        ), {"jc": job_code})).scalar()
        assert item_count == 1

        # OperationLog 应写入（按 job_code 精确匹配，避免被其他测试的日志污染）
        log_exists = (await test_session.execute(text(
            "SELECT EXISTS(SELECT 1 FROM operation_logs "
            "WHERE action = 'subtitle_extract' AND detail::json->>'job_code' = :jc)"
        ), {"jc": job_code})).scalar()
        assert log_exists

    @pytest.mark.asyncio
    async def test_extract_success_via_file_url(
        self, test_client, operator_headers, test_session
    ):
        """file_url 提交 → 立即返回 job_code，original_url 带 file:// 前缀。"""
        with patch(
            "app.routers.operator_subtitle._run_single_extract",
            AsyncMock(return_value=None),
        ):
            resp = await test_client.post(
                "/api/tools/subtitle/extract",
                headers=operator_headers,
                json={"file_url": "https://oss.example.com/audio/uploaded.mp3"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["status"] == "processing"

        # 校验 original_url 用 file:// 前缀（后台任务按此分流走 file_url 分支）
        original_url = (await test_session.execute(text(
            "SELECT si.original_url FROM subtitle_items si "
            "JOIN subtitle_jobs sj ON sj.id = si.job_id "
            "WHERE sj.job_code = :jc"
        ), {"jc": body["data"]["job_code"]})).scalar()
        assert original_url == "file://https://oss.example.com/audio/uploaded.mp3"

    @pytest.mark.asyncio
    async def test_extract_empty_input(self, test_client, operator_headers):
        """share_text 和 file_url 都为空 → 400"""
        resp = await test_client.post(
            "/api/tools/subtitle/extract",
            headers=operator_headers,
            json={},
        )
        assert resp.status_code == 400


class TestRunSingleExtract:
    """_run_single_extract 后台任务测试（直接调函数，绕过 HTTP 层）。

    覆盖：成功路径（视频元信息存 meta_json）+ tikhub 失败 + ASR 失败 + file_url 分支。
    """

    @pytest.mark.asyncio
    async def test_run_single_extract_success_via_share_text(
        self, test_client, operator_headers, test_session
    ):
        """share_text 模式：tikhub + ASR 都成功 → job.status=completed, item.meta_json 有视频元信息。"""
        with patch(
            "app.routers.operator_subtitle._run_single_extract",
            AsyncMock(return_value=None),
        ):
            # 1. HTTP 提交创建 job（mock 后台任务不实际跑）
            resp = await test_client.post(
                "/api/tools/subtitle/extract",
                headers=operator_headers,
                json={"share_text": "https://v.douyin.com/xxx/"},
            )
        job_code = resp.json()["data"]["job_code"]
        job_id = (await test_session.execute(text(
            "SELECT id FROM subtitle_jobs WHERE job_code = :jc"
        ), {"jc": job_code})).scalar()
        user_id = (await test_session.execute(text(
            "SELECT created_by FROM subtitle_jobs WHERE id = :jid"
        ), {"jid": job_id})).scalar()

        # 2. 真实跑 _run_single_extract（mock tikhub + asr）
        from app.routers.operator_subtitle import _run_single_extract
        with patch(
            "app.routers.operator_subtitle.tikhub_adapter.fetch_video_by_share_url",
            AsyncMock(return_value={
                "aweme_id": "7012345",
                "title": "测试视频",
                "digg_count": 50000,
                "play_url": "https://example.com/play.mp4",
                "audio_url": "https://example.com/audio.mp3",
                "cover_url": "https://example.com/cover.jpg",
                "nickname": "测试作者",
            }),
        ), patch(
            "app.routers.operator_subtitle.asr_adapter.transcribe",
            AsyncMock(return_value="这是字幕文本"),
        ):
            await _run_single_extract(job_id, user_id)

        # 3. 校验最终状态
        row = (await test_session.execute(text(
            "SELECT sj.status, sj.success, sj.failed, si.title, si.transcript, si.meta_json, si.status AS item_status "
            "FROM subtitle_jobs sj JOIN subtitle_items si ON si.job_id = sj.id "
            "WHERE sj.id = :jid"
        ), {"jid": job_id})).fetchone()
        assert row.status == "completed"
        assert row.success == 1
        assert row.failed == 0
        assert row.item_status == "success"
        assert row.title == "测试视频"
        assert row.transcript == "这是字幕文本"
        # meta_json 含完整视频元信息
        import json as _json
        meta = _json.loads(row.meta_json)
        assert meta["play_url"] == "https://example.com/play.mp4"
        assert meta["audio_url"] == "https://example.com/audio.mp3"
        assert meta["cover_url"] == "https://example.com/cover.jpg"
        assert meta["nickname"] == "测试作者"
        assert meta["digg_count"] == 50000
        assert meta["aweme_id"] == "7012345"

    @pytest.mark.asyncio
    async def test_run_single_extract_success_via_file_url(
        self, test_client, operator_headers, test_session
    ):
        """file_url 模式：跳过 tikhub 直接 ASR，meta_json 为 NULL。"""
        with patch(
            "app.routers.operator_subtitle._run_single_extract",
            AsyncMock(return_value=None),
        ):
            resp = await test_client.post(
                "/api/tools/subtitle/extract",
                headers=operator_headers,
                json={"file_url": "https://oss.example.com/audio/uploaded.mp3"},
            )
        job_code = resp.json()["data"]["job_code"]
        job_id = (await test_session.execute(text(
            "SELECT id FROM subtitle_jobs WHERE job_code = :jc"
        ), {"jc": job_code})).scalar()
        user_id = (await test_session.execute(text(
            "SELECT created_by FROM subtitle_jobs WHERE id = :jid"
        ), {"jid": job_id})).scalar()

        from app.routers.operator_subtitle import _run_single_extract
        with patch(
            "app.routers.operator_subtitle.asr_adapter.transcribe",
            AsyncMock(return_value="文件字幕"),
        ):
            await _run_single_extract(job_id, user_id)

        row = (await test_session.execute(text(
            "SELECT sj.status, si.transcript, si.meta_json FROM subtitle_jobs sj "
            "JOIN subtitle_items si ON si.job_id = sj.id WHERE sj.id = :jid"
        ), {"jid": job_id})).fetchone()
        assert row.status == "completed"
        assert row.transcript == "文件字幕"
        assert row.meta_json is None  # file_url 模式不存视频元信息

    @pytest.mark.asyncio
    async def test_run_single_extract_tikhub_failure(
        self, test_client, operator_headers, test_session
    ):
        """tikhub 抛错 → job.status=failed, item.error 有错信息。"""
        with patch(
            "app.routers.operator_subtitle._run_single_extract",
            AsyncMock(return_value=None),
        ):
            resp = await test_client.post(
                "/api/tools/subtitle/extract",
                headers=operator_headers,
                json={"share_text": "https://v.douyin.com/xxx/"},
            )
        job_code = resp.json()["data"]["job_code"]
        job_id = (await test_session.execute(text(
            "SELECT id FROM subtitle_jobs WHERE job_code = :jc"
        ), {"jc": job_code})).scalar()
        user_id = (await test_session.execute(text(
            "SELECT created_by FROM subtitle_jobs WHERE id = :jid"
        ), {"jid": job_id})).scalar()

        from app.routers.operator_subtitle import _run_single_extract
        with patch(
            "app.routers.operator_subtitle.tikhub_adapter.fetch_video_by_share_url",
            AsyncMock(side_effect=RuntimeError("tikhub error")),
        ):
            await _run_single_extract(job_id, user_id)

        row = (await test_session.execute(text(
            "SELECT sj.status, sj.failed, si.status AS item_status, si.error "
            "FROM subtitle_jobs sj JOIN subtitle_items si ON si.job_id = sj.id "
            "WHERE sj.id = :jid"
        ), {"jid": job_id})).fetchone()
        assert row.status == "failed"
        assert row.failed == 1
        assert row.item_status == "failed"
        assert "tikhub error" in row.error

    @pytest.mark.asyncio
    async def test_run_single_extract_asr_failure(
        self, test_client, operator_headers, test_session
    ):
        """tikhub 成功但 ASR 抛错 → job.status=failed, item.error 含 ASR 错。"""
        with patch(
            "app.routers.operator_subtitle._run_single_extract",
            AsyncMock(return_value=None),
        ):
            resp = await test_client.post(
                "/api/tools/subtitle/extract",
                headers=operator_headers,
                json={"share_text": "https://v.douyin.com/xxx/"},
            )
        job_code = resp.json()["data"]["job_code"]
        job_id = (await test_session.execute(text(
            "SELECT id FROM subtitle_jobs WHERE job_code = :jc"
        ), {"jc": job_code})).scalar()
        user_id = (await test_session.execute(text(
            "SELECT created_by FROM subtitle_jobs WHERE id = :jid"
        ), {"jid": job_id})).scalar()

        from app.routers.operator_subtitle import _run_single_extract
        with patch(
            "app.routers.operator_subtitle.tikhub_adapter.fetch_video_by_share_url",
            AsyncMock(return_value={
                "aweme_id": "1", "title": "T", "digg_count": 0,
                "play_url": "p", "audio_url": "https://example.com/a.mp3",
            }),
        ), patch(
            "app.routers.operator_subtitle.asr_adapter.transcribe",
            AsyncMock(side_effect=RuntimeError("ASR timeout")),
        ):
            await _run_single_extract(job_id, user_id)

        row = (await test_session.execute(text(
            "SELECT sj.status, si.error FROM subtitle_jobs sj "
            "JOIN subtitle_items si ON si.job_id = sj.id WHERE sj.id = :jid"
        ), {"jid": job_id})).fetchone()
        assert row.status == "failed"
        assert "ASR timeout" in row.error


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
        assert "access_code" not in data  # 已改用 created_by 绑定用户身份

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

        # OperationLog 写入（EXISTS + job_code 匹配，避免其他测试用例污染计数）
        log_exists = (await test_session.execute(text(
            "SELECT EXISTS(SELECT 1 FROM operation_logs "
            "WHERE action = 'subtitle_batch_create' "
            "AND detail::json->>'job_code' = :jc)"
        ), {"jc": data["job_code"]})).scalar()
        assert log_exists is True

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
# GET /batch/{job_code} — 查询（仅自己创建的）
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
    async def test_query_other_user_404(
        self, test_client, operator_headers, test_session
    ):
        """operator A 创建的 job，operator B 查 → 404（通过 created_by 隔离）"""
        # 1. operator A 创建
        with patch(
            "app.routers.operator_subtitle._run_batch",
            AsyncMock(return_value=None),
        ):
            create_resp = await test_client.post(
                "/api/tools/subtitle/batch",
                headers=operator_headers,
                json={"items": [{"share_text": "https://v.douyin.com/a/"}]},
            )
        job_code = create_resp.json()["data"]["job_code"]

        # 2. 创建 operator B
        suffix = uuid.uuid4().hex[:8]
        user_b = User(
            username=f"test_operator_b_{suffix}",
            real_name="运营B",
            password_hash=_pwd_context.hash("Test@123456"),
            role="operator",
            status="enabled",
            password_changed_at=datetime.now(tz=timezone.utc),
        )
        test_session.add(user_b)
        await test_session.commit()
        await test_session.refresh(user_b)
        token_b = create_access_token(
            user_id=int(user_b.id),
            username=str(user_b.username),
            role=str(user_b.role),
            token_version=int(user_b.token_version),
        )
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # 3. operator B 查 A 的 job_code → 404
        resp = await test_client.get(
            f"/api/tools/subtitle/batch/{job_code}",
            headers=headers_b,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /batches — 我的批量任务列表（分页 + 绑定 created_by）
# ---------------------------------------------------------------------------

class TestBatchesList:
    @pytest.mark.asyncio
    async def test_list_my_batches(self, test_client, operator_headers, test_session):
        """列表只返回当前用户创建的任务"""
        with patch(
            "app.routers.operator_subtitle._run_batch",
            AsyncMock(return_value=None),
        ):
            await test_client.post(
                "/api/tools/subtitle/batch",
                headers=operator_headers,
                json={"items": [{"share_text": "https://v.douyin.com/list1/"}]},
            )
            await test_client.post(
                "/api/tools/subtitle/batch",
                headers=operator_headers,
                json={"items": [{"share_text": "https://v.douyin.com/list2/"}]},
            )

        resp = await test_client.get(
            "/api/tools/subtitle/batches",
            headers=operator_headers,
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert len(body["items"]) == 2
        assert all(it["job_code"].startswith("sub_") for it in body["items"])
        # 按 created_at 倒序
        assert body["items"][0]["created_at"] >= body["items"][1]["created_at"]
        # pagination 字段
        assert body["pagination"]["page"] == 1
        assert body["pagination"]["page_size"] == 20
        assert body["pagination"]["total"] == 2

    @pytest.mark.asyncio
    async def test_list_pagination(self, test_client, operator_headers):
        """分页参数正确传递"""
        with patch(
            "app.routers.operator_subtitle._run_batch",
            AsyncMock(return_value=None),
        ):
            for i in range(3):
                await test_client.post(
                    "/api/tools/subtitle/batch",
                    headers=operator_headers,
                    json={"items": [{"share_text": f"https://v.douyin.com/p{i}/"}]},
                )

        resp = await test_client.get(
            "/api/tools/subtitle/batches?page=1&page_size=2",
            headers=operator_headers,
        )
        body = resp.json()["data"]
        assert len(body["items"]) == 2
        assert body["pagination"]["total"] == 3
        assert body["pagination"]["total_pages"] == 2

    @pytest.mark.asyncio
    async def test_list_empty(self, test_client, operator_headers):
        """无任务 → 空列表"""
        resp = await test_client.get(
            "/api/tools/subtitle/batches",
            headers=operator_headers,
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["items"] == []
        assert body["pagination"]["total"] == 0

    @pytest.mark.asyncio
    async def test_list_account_isolation(
        self, test_client, operator_headers, test_session
    ):
        """operator A 创建的任务不出现在 operator B 的列表里"""
        # A 创建
        with patch(
            "app.routers.operator_subtitle._run_batch",
            AsyncMock(return_value=None),
        ):
            await test_client.post(
                "/api/tools/subtitle/batch",
                headers=operator_headers,
                json={"items": [{"share_text": "https://v.douyin.com/iso/"}]},
            )

        # 创建 operator B
        suffix = uuid.uuid4().hex[:8]
        user_b = User(
            username=f"test_op_iso_{suffix}",
            real_name="运营隔离",
            password_hash=_pwd_context.hash("Test@123456"),
            role="operator",
            status="enabled",
            password_changed_at=datetime.now(tz=timezone.utc),
        )
        test_session.add(user_b)
        await test_session.commit()
        await test_session.refresh(user_b)
        token_b = create_access_token(
            user_id=int(user_b.id),
            username=str(user_b.username),
            role=str(user_b.role),
            token_version=int(user_b.token_version),
        )
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # B 看自己列表 → 空（看不到 A 的）
        resp = await test_client.get(
            "/api/tools/subtitle/batches",
            headers=headers_b,
        )
        body = resp.json()["data"]
        assert body["items"] == []
        assert body["pagination"]["total"] == 0


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
