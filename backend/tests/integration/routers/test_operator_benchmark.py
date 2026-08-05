"""
Integration tests for operator_benchmark.py router.

Covers:
- POST /operator/benchmark/fetch            — 抖音号/链接解析 + 视频拉取（mock tikhub_adapter）
- POST /operator/benchmark/analyze          — AI 分析（SSE 流式：error path + happy stream）
- GET  /operator/benchmark/history          — 自己的分析历史（隔离）
- GET  /operator/benchmark/history/{id}     — 历史详情（404 / 跨用户 404 / happy）
- POST /operator/benchmark/export-word      — 导出 Word（404 / NOT_READY / NO_CONTENT / happy）

外部依赖全 mock：tikhub_adapter / yunwu_adapter / benchmark_report.generate_docx。

BenchmarkConfig.config_key 是 unique，router 固定查 'analyze'；用 autouse fixture 清理
BenchmarkConfig + BenchmarkAnalysis 避免 unique 冲突与数据污染（参考 test_operator_intake_direct.py）。

错误码约定（本 router 全是 HTTPException → 真实 HTTP 码）：
- 400 INVALID_INPUT / FETCH_FAILED / NOT_READY / NO_CONTENT
- 404 NO_VIDEOS / NOT_FOUND
- 500 CONFIG_MISSING
- 401 无 token
"""
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.models.benchmark import BenchmarkAnalysis, BenchmarkConfig


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_benchmark_tables(test_session):
    """每个测试前清理 benchmark_* 表，避免 config_key unique 冲突。

    router 固定查 config_key='analyze'，残留数据会让 seed 失败。
    """
    await test_session.execute(delete(BenchmarkAnalysis))
    await test_session.execute(delete(BenchmarkConfig))
    await test_session.commit()
    yield


async def _seed_analysis(
    test_session,
    user,
    *,
    status: str = "completed",
    account_name: str = "cov_account",
    profile_result: str | None = "profile body",
    plan_result: str | None = "plan body",
    **kwargs,
) -> BenchmarkAnalysis:
    """seed 一条 BenchmarkAnalysis，默认 completed + 非空 result。"""
    a = BenchmarkAnalysis(
        account_name=account_name,
        model_used="glm-4.6",
        status=status,
        profile_result=profile_result,
        plan_result=plan_result,
        created_by=user.id,
        **kwargs,
    )
    test_session.add(a)
    await test_session.commit()
    await test_session.refresh(a)
    return a


async def _seed_analyze_config(
    test_session, *, system_prompt: str = "你是分析师"
) -> BenchmarkConfig:
    """seed config_key='analyze' 的 active BenchmarkConfig。"""
    cfg = BenchmarkConfig(
        config_key="analyze",
        system_prompt=system_prompt,
        is_active=True,
    )
    test_session.add(cfg)
    await test_session.commit()
    await test_session.refresh(cfg)
    return cfg


# ---------------------------------------------------------------------------
# POST /fetch
# ---------------------------------------------------------------------------


class TestFetchAccount:
    @pytest.mark.asyncio
    async def test_fetch_ok_mock_tikhub(self, test_client, operator_headers):
        """mock tikhub 全链 → 200 + data 字段齐。"""
        with patch(
            "app.routers.operator_benchmark.tikhub_adapter.resolve_sec_user_id",
            new_callable=AsyncMock,
            return_value={"sec_user_id": "sec_abc", "nickname": "测试号"},
        ), patch(
            "app.routers.operator_benchmark.tikhub_adapter.fetch_user_videos",
            new_callable=AsyncMock,
            return_value=[{"video_id": 1}, {"video_id": 2}],
        ), patch(
            "app.routers.operator_benchmark.tikhub_adapter.get_top10_videos",
            return_value=[{"video_id": 1}],
        ), patch(
            "app.routers.operator_benchmark.tikhub_adapter.get_recent_30day_videos",
            return_value=[{"video_id": 1}, {"video_id": 2}],
        ), patch(
            "app.routers.operator_benchmark.tikhub_adapter.format_videos_text",
            return_value="视频列表文本",
        ):
            resp = await test_client.post(
                "/api/operator/benchmark/fetch",
                json={"input": "https://v.douyin.com/xxx"},
                headers=operator_headers,
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        data = body["data"]
        assert data["sec_user_id"] == "sec_abc"
        assert data["nickname"] == "测试号"
        assert data["total_videos"] == 2
        assert data["top10_count"] == 1
        assert data["recent30_count"] == 2
        assert data["top10_text"] == "视频列表文本"
        assert data["recent30_text"] == "视频列表文本"

    @pytest.mark.asyncio
    async def test_fetch_nickname_fallback_get_user_profile(
        self, test_client, operator_headers
    ):
        """resolve_sec_user_id 不返回 nickname → 走 get_user_profile 兜底拿昵称。"""
        with patch(
            "app.routers.operator_benchmark.tikhub_adapter.resolve_sec_user_id",
            new_callable=AsyncMock,
            return_value={"sec_user_id": "sec_abc"},  # 无 nickname
        ), patch(
            "app.routers.operator_benchmark.tikhub_adapter.get_user_profile",
            new_callable=AsyncMock,
            return_value={"nickname": "兜底昵称"},
        ), patch(
            "app.routers.operator_benchmark.tikhub_adapter.fetch_user_videos",
            new_callable=AsyncMock,
            return_value=[{"video_id": 1}],
        ), patch(
            "app.routers.operator_benchmark.tikhub_adapter.get_top10_videos",
            return_value=[],
        ), patch(
            "app.routers.operator_benchmark.tikhub_adapter.get_recent_30day_videos",
            return_value=[],
        ), patch(
            "app.routers.operator_benchmark.tikhub_adapter.format_videos_text",
            return_value="x",
        ):
            resp = await test_client.post(
                "/api/operator/benchmark/fetch",
                json={"input": "douyin_id_xx"},
                headers=operator_headers,
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["nickname"] == "兜底昵称"

    @pytest.mark.asyncio
    async def test_fetch_nickname_profile_fails_returns_empty(
        self, test_client, operator_headers
    ):
        """resolve 不返回 nickname + get_user_profile 抛错 → 静默降级 nickname=''。"""
        with patch(
            "app.routers.operator_benchmark.tikhub_adapter.resolve_sec_user_id",
            new_callable=AsyncMock,
            return_value={"sec_user_id": "sec_abc"},
        ), patch(
            "app.routers.operator_benchmark.tikhub_adapter.get_user_profile",
            new_callable=AsyncMock,
            side_effect=RuntimeError("profile fetch failed"),
        ), patch(
            "app.routers.operator_benchmark.tikhub_adapter.fetch_user_videos",
            new_callable=AsyncMock,
            return_value=[{"video_id": 1}],
        ), patch(
            "app.routers.operator_benchmark.tikhub_adapter.get_top10_videos",
            return_value=[],
        ), patch(
            "app.routers.operator_benchmark.tikhub_adapter.get_recent_30day_videos",
            return_value=[],
        ), patch(
            "app.routers.operator_benchmark.tikhub_adapter.format_videos_text",
            return_value="x",
        ):
            resp = await test_client.post(
                "/api/operator/benchmark/fetch",
                json={"input": "douyin_id_xx"},
                headers=operator_headers,
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["nickname"] == ""

    @pytest.mark.asyncio
    async def test_fetch_empty_input_400(self, test_client, operator_headers):
        """空白 input → 400 INVALID_INPUT。"""
        resp = await test_client.post(
            "/api/operator/benchmark/fetch",
            json={"input": "   "},
            headers=operator_headers,
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_fetch_no_videos_404(self, test_client, operator_headers):
        """mock tikhub 返回空视频列表 → 404 NO_VIDEOS。"""
        with patch(
            "app.routers.operator_benchmark.tikhub_adapter.resolve_sec_user_id",
            new_callable=AsyncMock,
            return_value={"sec_user_id": "sec_abc", "nickname": "x"},
        ), patch(
            "app.routers.operator_benchmark.tikhub_adapter.fetch_user_videos",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await test_client.post(
                "/api/operator/benchmark/fetch",
                json={"input": "some_id"},
                headers=operator_headers,
            )
        assert resp.status_code == 404
        assert resp.json()["code"] == "NO_VIDEOS"

    @pytest.mark.asyncio
    async def test_fetch_tikhub_resolve_fails_400(self, test_client, operator_headers):
        """tikhub resolve 抛异常 → 400 FETCH_FAILED。"""
        with patch(
            "app.routers.operator_benchmark.tikhub_adapter.resolve_sec_user_id",
            new_callable=AsyncMock,
            side_effect=RuntimeError("network down"),
        ):
            resp = await test_client.post(
                "/api/operator/benchmark/fetch",
                json={"input": "some_id"},
                headers=operator_headers,
            )
        assert resp.status_code == 400
        assert resp.json()["code"] == "FETCH_FAILED"

    @pytest.mark.asyncio
    async def test_fetch_admin_role_ok(self, test_client, admin_headers):
        """admin 也能通过 require_operator 访问。"""
        with patch(
            "app.routers.operator_benchmark.tikhub_adapter.resolve_sec_user_id",
            new_callable=AsyncMock,
            return_value={"sec_user_id": "sec_abc", "nickname": "x"},
        ), patch(
            "app.routers.operator_benchmark.tikhub_adapter.fetch_user_videos",
            new_callable=AsyncMock,
            return_value=[{"video_id": 1}],
        ), patch(
            "app.routers.operator_benchmark.tikhub_adapter.get_top10_videos",
            return_value=[],
        ), patch(
            "app.routers.operator_benchmark.tikhub_adapter.get_recent_30day_videos",
            return_value=[],
        ), patch(
            "app.routers.operator_benchmark.tikhub_adapter.format_videos_text",
            return_value="x",
        ):
            resp = await test_client.post(
                "/api/operator/benchmark/fetch",
                json={"input": "id"},
                headers=admin_headers,
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_fetch_no_token_401(self, test_client):
        resp = await test_client.post(
            "/api/operator/benchmark/fetch",
            json={"input": "x"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /analyze (SSE)
# ---------------------------------------------------------------------------


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_analyze_empty_content_400(self, test_client, operator_headers):
        """top10/recent30 都为空 → 400 INVALID_INPUT。"""
        resp = await test_client.post(
            "/api/operator/benchmark/analyze",
            json={"top10_content": "  ", "recent30_content": ""},
            headers=operator_headers,
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_analyze_no_active_config_500(self, test_client, operator_headers):
        """无 active BenchmarkConfig(config_key='analyze') → 500 CONFIG_MISSING。"""
        # autouse 已清空 configs
        resp = await test_client.post(
            "/api/operator/benchmark/analyze",
            json={"top10_content": "x", "recent30_content": "y"},
            headers=operator_headers,
        )
        assert resp.status_code == 500
        assert resp.json()["code"] == "CONFIG_MISSING"

    @pytest.mark.asyncio
    async def test_analyze_config_without_prompt_500(
        self, test_client, operator_headers, test_session
    ):
        """config 存在但 system_prompt=None → 500 CONFIG_MISSING。"""
        cfg = BenchmarkConfig(
            config_key="analyze",
            system_prompt=None,
            is_active=True,
        )
        test_session.add(cfg)
        await test_session.commit()

        resp = await test_client.post(
            "/api/operator/benchmark/analyze",
            json={"top10_content": "x", "recent30_content": "y"},
            headers=operator_headers,
        )
        assert resp.status_code == 500
        assert resp.json()["code"] == "CONFIG_MISSING"

    @pytest.mark.asyncio
    async def test_analyze_inactive_config_500(
        self, test_client, operator_headers, test_session
    ):
        """config_key='analyze' 存在但 is_active=False → 仍查不到 → 500。"""
        cfg = BenchmarkConfig(
            config_key="analyze",
            system_prompt="x",
            is_active=False,
        )
        test_session.add(cfg)
        await test_session.commit()

        resp = await test_client.post(
            "/api/operator/benchmark/analyze",
            json={"top10_content": "x", "recent30_content": "y"},
            headers=operator_headers,
        )
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_analyze_happy_stream(
        self, test_client, operator_headers, test_session
    ):
        """seed config + mock chat_stream async generator → 200 + X-Analysis-Id + 流式 body。"""
        await _seed_analyze_config(test_session)

        async def _fake_stream(*args, **kwargs):
            yield "chunk1"
            yield "chunk2"

        with patch(
            "app.routers.operator_benchmark.yunwu_adapter.chat_stream",
            side_effect=_fake_stream,
        ):
            resp = await test_client.post(
                "/api/operator/benchmark/analyze",
                json={
                    "account_name": "cov_acc",
                    "top10_content": "top10 文案",
                    "recent30_content": "recent30 文案",
                },
                headers=operator_headers,
            )
        assert resp.status_code == 200
        # SSE 响应 headers 带 analysis / task id
        assert "x-analysis-id" in resp.headers
        assert "x-task-id" in resp.headers
        # httpx 自动读完流，body 应包含 mock chunk
        assert "chunk1" in resp.text
        assert "chunk2" in resp.text

    @pytest.mark.asyncio
    async def test_analyze_no_token_401(self, test_client):
        resp = await test_client.post(
            "/api/operator/benchmark/analyze",
            json={"top10_content": "x"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /history
# ---------------------------------------------------------------------------


class TestListHistory:
    @pytest.mark.asyncio
    async def test_history_empty_ok(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/operator/benchmark/history", headers=operator_headers
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert isinstance(body["data"], list)
        assert len(body["data"]) == 0

    @pytest.mark.asyncio
    async def test_history_returns_own_only(
        self,
        test_client,
        operator_headers,
        admin_headers,
        test_session,
        operator_user,
        admin_user,
    ):
        """operator 创建 2 条 + admin 创建 1 条 → operator 看到 2，admin 看到 1。"""
        test_session.add_all(
            [
                BenchmarkAnalysis(
                    account_name="A", status="completed", created_by=operator_user.id
                ),
                BenchmarkAnalysis(
                    account_name="B", status="completed", created_by=operator_user.id
                ),
                BenchmarkAnalysis(
                    account_name="C", status="completed", created_by=admin_user.id
                ),
            ]
        )
        await test_session.commit()

        resp_op = await test_client.get(
            "/api/operator/benchmark/history", headers=operator_headers
        )
        body_op = resp_op.json()
        assert resp_op.status_code == 200
        assert len(body_op["data"]) == 2
        assert {item["account_name"] for item in body_op["data"]} == {"A", "B"}

        resp_ad = await test_client.get(
            "/api/operator/benchmark/history", headers=admin_headers
        )
        body_ad = resp_ad.json()
        assert resp_ad.status_code == 200
        assert len(body_ad["data"]) == 1
        assert body_ad["data"][0]["account_name"] == "C"

    @pytest.mark.asyncio
    async def test_history_structure(
        self, test_client, operator_headers, test_session, operator_user
    ):
        """验证 list item 字段结构与契约一致。"""
        await _seed_analysis(
            test_session, operator_user, account_name="cov_struct"
        )
        resp = await test_client.get(
            "/api/operator/benchmark/history", headers=operator_headers
        )
        item = resp.json()["data"][0]
        for key in (
            "id",
            "account_name",
            "sec_user_id",
            "model_used",
            "tokens_used",
            "duration_ms",
            "status",
            "created_at",
        ):
            assert key in item, f"missing field {key}"
        assert item["account_name"] == "cov_struct"

    @pytest.mark.asyncio
    async def test_history_no_token_401(self, test_client):
        resp = await test_client.get("/api/operator/benchmark/history")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /history/{id}
# ---------------------------------------------------------------------------


class TestHistoryDetail:
    @pytest.mark.asyncio
    async def test_detail_ok(
        self, test_client, operator_headers, test_session, operator_user
    ):
        a = await _seed_analysis(
            test_session,
            operator_user,
            account_name="cov_detail",
            profile_result="profile",
            plan_result="plan",
        )
        resp = await test_client.get(
            f"/api/operator/benchmark/history/{a.id}", headers=operator_headers
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["id"] == a.id
        assert body["data"]["account_name"] == "cov_detail"
        assert body["data"]["profile_result"] == "profile"
        assert body["data"]["plan_result"] == "plan"

    @pytest.mark.asyncio
    async def test_detail_not_found_404(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/operator/benchmark/history/999999", headers=operator_headers
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_detail_cross_user_404(
        self, test_client, admin_headers, test_session, operator_user
    ):
        """operator 创建的，admin 拿不到（过滤 created_by）→ 404。"""
        a = await _seed_analysis(test_session, operator_user)
        resp = await test_client.get(
            f"/api/operator/benchmark/history/{a.id}", headers=admin_headers
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_detail_no_token_401(self, test_client):
        resp = await test_client.get("/api/operator/benchmark/history/1")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /export-word
# ---------------------------------------------------------------------------


class TestExportWord:
    @pytest.mark.asyncio
    async def test_export_profile_ok(
        self, test_client, operator_headers, test_session, operator_user, tmp_path
    ):
        """seed completed analysis + mock generate_docx → 200 FileResponse。"""
        a = await _seed_analysis(
            test_session,
            operator_user,
            status="completed",
            profile_result="profile body",
        )
        # FileResponse 会真实打开文件，必须提供一个存在的文件
        fake_file = tmp_path / "fake.docx"
        fake_file.write_bytes(b"fake docx content")

        with patch(
            "app.routers.operator_benchmark.benchmark_report.generate_docx",
            return_value=str(fake_file),
        ):
            resp = await test_client.post(
                "/api/operator/benchmark/export-word",
                json={"analysis_id": a.id, "type": "profile"},
                headers=operator_headers,
            )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        # Starlette 对非 ASCII 文件名用 RFC 5987 编码：filename*=utf-8''...
        assert resp.headers["content-disposition"].startswith("attachment;")
        assert resp.headers["content-disposition"].endswith(".docx")

    @pytest.mark.asyncio
    async def test_export_plan_ok(
        self, test_client, operator_headers, test_session, operator_user, tmp_path
    ):
        """type='plan' + plan_result 非空 → 200。"""
        a = await _seed_analysis(
            test_session,
            operator_user,
            status="completed",
            plan_result="plan body",
        )
        fake_file = tmp_path / "plan.docx"
        fake_file.write_bytes(b"plan docx")

        with patch(
            "app.routers.operator_benchmark.benchmark_report.generate_docx",
            return_value=str(fake_file),
        ):
            resp = await test_client.post(
                "/api/operator/benchmark/export-word",
                json={"analysis_id": a.id, "type": "plan"},
                headers=operator_headers,
            )
        assert resp.status_code == 200
        assert resp.headers["content-disposition"].endswith(".docx")

    @pytest.mark.asyncio
    async def test_export_not_found_404(self, test_client, operator_headers):
        """不存在的 analysis_id → 404 NOT_FOUND。"""
        resp = await test_client.post(
            "/api/operator/benchmark/export-word",
            json={"analysis_id": 999999, "type": "profile"},
            headers=operator_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_export_cross_user_404(
        self, test_client, admin_headers, test_session, operator_user
    ):
        """operator 创建的 analysis，admin 拿 → 404（过滤 created_by）。"""
        a = await _seed_analysis(test_session, operator_user)
        resp = await test_client.post(
            "/api/operator/benchmark/export-word",
            json={"analysis_id": a.id, "type": "profile"},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_export_not_ready_400(
        self, test_client, operator_headers, test_session, operator_user
    ):
        """status='generating' → 400 NOT_READY。"""
        a = await _seed_analysis(
            test_session, operator_user, status="generating"
        )
        resp = await test_client.post(
            "/api/operator/benchmark/export-word",
            json={"analysis_id": a.id, "type": "profile"},
            headers=operator_headers,
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "NOT_READY"

    @pytest.mark.asyncio
    async def test_export_no_content_400(
        self, test_client, operator_headers, test_session, operator_user
    ):
        """completed 但 profile_result=None → 400 NO_CONTENT。"""
        a = await _seed_analysis(
            test_session,
            operator_user,
            status="completed",
            profile_result=None,
        )
        resp = await test_client.post(
            "/api/operator/benchmark/export-word",
            json={"analysis_id": a.id, "type": "profile"},
            headers=operator_headers,
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "NO_CONTENT"

    @pytest.mark.asyncio
    async def test_export_no_token_401(self, test_client):
        resp = await test_client.post(
            "/api/operator/benchmark/export-word",
            json={"analysis_id": 1, "type": "profile"},
        )
        assert resp.status_code == 401
