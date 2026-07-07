"""Integration tests for operator_selling_point router."""
import io
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from sqlalchemy import text


# ---------- fixtures ----------

@pytest.fixture(autouse=True)
async def ensure_config(test_session):
    """确保测试库中有激活的 selling_point_configs 配置。"""
    await test_session.execute(text(
        "INSERT INTO selling_point_configs (config_key, system_prompt, is_active) "
        "VALUES ('extract', '测试Prompt', true) "
        "ON CONFLICT (config_key) DO NOTHING"
    ))
    await test_session.commit()


# ---------- Auth ----------

class TestAuth:
    @pytest.mark.asyncio
    async def test_chat_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/selling-point-extractor/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_parse_file_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/selling-point-extractor/parse-file",
            files={"file": ("test.txt", b"content", "text/plain")},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_history_get_unauthorized(self, test_client):
        resp = await test_client.get("/api/tools/selling-point-extractor/history")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_history_post_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/selling-point-extractor/history",
            json={"result": "内容"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_history_delete_unauthorized(self, test_client):
        resp = await test_client.delete(
            "/api/tools/selling-point-extractor/history?id=1",
        )
        assert resp.status_code == 401


# ---------- Response Format ----------

class TestResponseFormat:
    """验证所有非流式接口返回标准 {success, code, message, data} 结构。"""

    @pytest.mark.asyncio
    async def test_parse_file_envelope(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/selling-point-extractor/parse-file",
            files={"file": ("t.txt", b"hello", "text/plain")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        body = resp.json()
        assert body["success"] is True
        assert body["code"] == "OK"
        assert "text" in body["data"]
        assert "filename" in body["data"]

    @pytest.mark.asyncio
    async def test_history_list_envelope(self, test_client, operator_token, test_session):
        await test_session.execute(
            text("DELETE FROM outputs WHERE tool_code='selling-point-extractor'")
        )
        await test_session.commit()
        resp = await test_client.get(
            "/api/tools/selling-point-extractor/history",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        body = resp.json()
        assert body["success"] is True
        assert body["code"] == "OK"
        assert "records" in body["data"]

    @pytest.mark.asyncio
    async def test_save_history_envelope(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/selling-point-extractor/history",
            json={"result": "卖点卡"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        body = resp.json()
        assert body["success"] is True
        assert body["code"] == "OK"
        assert "id" in body["data"]

    @pytest.mark.asyncio
    async def test_delete_history_envelope(self, test_client, operator_token):
        save_resp = await test_client.post(
            "/api/tools/selling-point-extractor/history",
            json={"result": "待删除"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        record_id = save_resp.json()["data"]["id"]
        resp = await test_client.delete(
            f"/api/tools/selling-point-extractor/history?id={record_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        body = resp.json()
        assert body["success"] is True
        assert body["code"] == "OK"


# ---------- Chat ----------

class TestChat:
    @pytest.mark.asyncio
    async def test_empty_messages_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/selling-point-extractor/chat",
            json={"messages": []},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_config_inactive_returns_503(self, test_client, operator_token, test_session):
        await test_session.execute(
            text("UPDATE selling_point_configs SET is_active=false WHERE config_key='extract'")
        )
        await test_session.commit()

        resp = await test_client.post(
            "/api/tools/selling-point-extractor/chat",
            json={"messages": [{"role": "user", "content": "分析"}]},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 503

        # 恢复
        await test_session.execute(
            text("UPDATE selling_point_configs SET is_active=true WHERE config_key='extract'")
        )
        await test_session.commit()

    @pytest.mark.asyncio
    async def test_chat_streams_plain_text(self, test_client, operator_token):
        async def mock_stream(*args, **kwargs):
            for chunk in ["【机制】", "无特别机制"]:
                yield chunk

        with patch(
            "app.routers.operator_selling_point.yunwu_adapter.chat_stream",
            side_effect=mock_stream,
        ), patch("app.routers.operator_selling_point.AsyncSessionLocal") as mock_sl:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sess.add = MagicMock()
            mock_sess.commit = AsyncMock()
            mock_sl.return_value = mock_sess

            resp = await test_client.post(
                "/api/tools/selling-point-extractor/chat",
                json={"messages": [{"role": "user", "content": "分析产品"}]},
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        assert "【机制】" in resp.text

    @pytest.mark.asyncio
    async def test_chat_error_yields_error_marker(self, test_client, operator_token):
        async def mock_stream_error(*args, **kwargs):
            raise RuntimeError("AI 不可用")
            yield

        with patch(
            "app.routers.operator_selling_point.yunwu_adapter.chat_stream",
            side_effect=mock_stream_error,
        ), patch("app.routers.operator_selling_point.AsyncSessionLocal") as mock_sl:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sess.add = MagicMock()
            mock_sess.commit = AsyncMock()
            mock_sl.return_value = mock_sess

            resp = await test_client.post(
                "/api/tools/selling-point-extractor/chat",
                json={"messages": [{"role": "user", "content": "分析"}]},
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 200
        assert "[ERROR]" in resp.text

    @pytest.mark.asyncio
    async def test_chat_retries_on_503_then_succeeds(self, test_client, operator_token):
        """PR #18: 503/502/429/timeout 时自动重试，最多 3 次。第一次 503，第二次成功。"""
        call_count = 0

        def chat_stream_factory(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                async def raising():
                    raise RuntimeError("503 Service Unavailable")
                    yield
                return raising()
            else:
                async def ok():
                    yield "重试后成功"
                return ok()

        with patch(
            "app.routers.operator_selling_point.yunwu_adapter.chat_stream",
            side_effect=chat_stream_factory,
        ), patch("app.routers.operator_selling_point.AsyncSessionLocal") as mock_sl, \
           patch("app.routers.operator_selling_point.asyncio.sleep", new_callable=AsyncMock):
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sess.add = MagicMock()
            mock_sess.commit = AsyncMock()
            mock_sl.return_value = mock_sess

            resp = await test_client.post(
                "/api/tools/selling-point-extractor/chat",
                json={"messages": [{"role": "user", "content": "分析"}]},
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 200
        assert "重试后成功" in resp.text
        assert "[ERROR]" not in resp.text
        # 第一次失败 + 第二次成功 = 2 次调用
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_chat_yields_error_after_max_retries(self, test_client, operator_token):
        """PR #18: 持续可重试错误（503）超过最大重试次数后 yield [ERROR]。"""
        call_count = 0

        def chat_stream_factory(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            async def raising():
                raise RuntimeError("503 Service Unavailable")
                yield
            return raising()

        with patch(
            "app.routers.operator_selling_point.yunwu_adapter.chat_stream",
            side_effect=chat_stream_factory,
        ), patch("app.routers.operator_selling_point.AsyncSessionLocal") as mock_sl, \
           patch("app.routers.operator_selling_point.asyncio.sleep", new_callable=AsyncMock):
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sess.add = MagicMock()
            mock_sess.commit = AsyncMock()
            mock_sl.return_value = mock_sess

            resp = await test_client.post(
                "/api/tools/selling-point-extractor/chat",
                json={"messages": [{"role": "user", "content": "分析"}]},
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 200
        assert "[ERROR]" in resp.text
        assert "503" in resp.text
        # _RETRY_DELAYS = [2, 4] → delays = [0, 2, 4] → 共 3 次尝试
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_chat_passes_default_provider_when_no_model(
        self, test_client, operator_token, test_session
    ):
        """无 ai_model_id 时，chat_stream 调用应传 provider='yunwu'（默认）。"""
        # 确保配置无 ai_model_id
        await test_session.execute(
            text("UPDATE selling_point_configs SET ai_model_id=NULL WHERE config_key='extract'")
        )
        await test_session.commit()

        async def mock_stream(*args, **kwargs):
            yield "test"

        with patch(
            "app.routers.operator_selling_point.yunwu_adapter.chat_stream",
            side_effect=mock_stream,
        ) as mock_fn, patch("app.routers.operator_selling_point.AsyncSessionLocal") as mock_sl:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sess.add = MagicMock()
            mock_sess.commit = AsyncMock()
            mock_sl.return_value = mock_sess

            await test_client.post(
                "/api/tools/selling-point-extractor/chat",
                json={"messages": [{"role": "user", "content": "分析"}]},
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert mock_fn.call_args.kwargs["provider"] == "yunwu"

    @pytest.mark.asyncio
    async def test_chat_passes_provider_from_ai_model(
        self, test_client, operator_token, test_session
    ):
        """ai_models 表 provider=siliconflow 时，chat_stream 调用应传 provider='siliconflow'。"""
        # 插入 siliconflow provider 的 ai_model
        await test_session.execute(text(
            "INSERT INTO ai_models (name, provider, model_id, status) "
            "VALUES ('Qwen3-Omni', 'siliconflow', 'Qwen/Qwen3-Omni', 'active') "
            "ON CONFLICT DO NOTHING"
        ))
        row = (await test_session.execute(text(
            "SELECT id FROM ai_models WHERE model_id='Qwen/Qwen3-Omni' AND provider='siliconflow'"
        ))).fetchone()
        ai_model_id = row[0]
        await test_session.execute(text(
            "UPDATE selling_point_configs SET ai_model_id=:mid WHERE config_key='extract'"
        ), {"mid": ai_model_id})
        await test_session.commit()

        async def mock_stream(*args, **kwargs):
            yield "test"

        with patch(
            "app.routers.operator_selling_point.yunwu_adapter.chat_stream",
            side_effect=mock_stream,
        ) as mock_fn, patch("app.routers.operator_selling_point.AsyncSessionLocal") as mock_sl:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sess.add = MagicMock()
            mock_sess.commit = AsyncMock()
            mock_sl.return_value = mock_sess

            await test_client.post(
                "/api/tools/selling-point-extractor/chat",
                json={"messages": [{"role": "user", "content": "分析"}]},
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert mock_fn.call_args.kwargs["provider"] == "siliconflow"
        assert mock_fn.call_args.kwargs["model_id"] == "Qwen/Qwen3-Omni"


# ---------- Parse File ----------

class TestParseFile:
    @pytest.mark.asyncio
    async def test_parse_txt(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/selling-point-extractor/parse-file",
            files={"file": ("brief.txt", "产品卖点内容".encode(), "text/plain")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "text" in data and "filename" in data
        assert "产品卖点" in data["text"]

    @pytest.mark.asyncio
    async def test_parse_doc_returns_hint(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/selling-point-extractor/parse-file",
            files={"file": ("old.doc", b"\xd0\xcf\x11", "application/msword")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert ".doc 格式暂不支持" in resp.json()["data"]["text"]

    @pytest.mark.asyncio
    async def test_parse_docx(self, test_client, operator_token):
        from docx import Document
        doc = Document()
        doc.add_paragraph("玻尿酸保湿成分")
        buf = io.BytesIO(); doc.save(buf); buf.seek(0)
        resp = await test_client.post(
            "/api/tools/selling-point-extractor/parse-file",
            files={"file": ("p.docx", buf.read(),
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert "玻尿酸" in resp.json()["data"]["text"]


# ---------- History ----------

class TestHistory:
    @pytest.mark.asyncio
    async def test_empty_list(self, test_client, operator_token, test_session):
        await test_session.execute(
            text("DELETE FROM outputs WHERE tool_code='selling-point-extractor'")
        )
        await test_session.commit()

        resp = await test_client.get(
            "/api/tools/selling-point-extractor/history",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["records"] == []

    @pytest.mark.asyncio
    async def test_save_and_list(self, test_client, operator_token, test_session):
        await test_session.execute(
            text("DELETE FROM outputs WHERE tool_code='selling-point-extractor'")
        )
        await test_session.commit()

        save_resp = await test_client.post(
            "/api/tools/selling-point-extractor/history",
            json={"productName": "测试产品", "result": "卖点卡内容"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert save_resp.status_code == 200
        assert save_resp.json()["success"] is True

        list_resp = await test_client.get(
            "/api/tools/selling-point-extractor/history",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        records = list_resp.json()["data"]["records"]
        assert any(r["productName"] == "测试产品" for r in records)

    @pytest.mark.asyncio
    async def test_save_and_get_single(self, test_client, operator_token):
        save_resp = await test_client.post(
            "/api/tools/selling-point-extractor/history",
            json={
                "productName": "单条查询产品",
                "result": "完整卖点卡内容",
                "chatHistory": [{"role": "user", "content": "分析"}],
                "briefFiles": [{"name": "b.pdf", "text": "说明"}],
                "scriptFiles": [],
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert save_resp.status_code == 200
        record_id = save_resp.json()["data"]["id"]

        get_resp = await test_client.get(
            f"/api/tools/selling-point-extractor/history?id={record_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert get_resp.status_code == 200
        rec = get_resp.json()["data"]["record"]
        assert rec["productName"] == "单条查询产品"
        assert len(rec["briefFiles"]) == 1

    @pytest.mark.asyncio
    async def test_get_nonexistent_404(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/selling-point-extractor/history?id=999999",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_soft_delete(self, test_client, operator_token, test_session):
        save_resp = await test_client.post(
            "/api/tools/selling-point-extractor/history",
            json={"productName": "待删除", "result": "内容"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        record_id = save_resp.json()["data"]["id"]

        del_resp = await test_client.delete(
            f"/api/tools/selling-point-extractor/history?id={record_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert del_resp.status_code == 200
        assert del_resp.json()["success"] is True

        # 验证物理记录仍在，deleted_at 已设置
        row = (await test_session.execute(
            text(f"SELECT deleted_at FROM outputs WHERE id={record_id}")
        )).fetchone()
        assert row is not None
        assert row[0] is not None

        # 查询已删除记录返回 404
        get_resp = await test_client.get(
            f"/api/tools/selling-point-extractor/history?id={record_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_result_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/selling-point-extractor/history",
            json={"result": "   "},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_default_product_name(self, test_client, operator_token):
        save_resp = await test_client.post(
            "/api/tools/selling-point-extractor/history",
            json={"result": "卖点内容"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        record_id = save_resp.json()["data"]["id"]
        get_resp = await test_client.get(
            f"/api/tools/selling-point-extractor/history?id={record_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert get_resp.json()["data"]["record"]["productName"] == "未命名产品"

    @pytest.mark.asyncio
    async def test_delete_already_deleted_returns_404(self, test_client, operator_token):
        save_resp = await test_client.post(
            "/api/tools/selling-point-extractor/history",
            json={"result": "内容"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        record_id = save_resp.json()["data"]["id"]
        await test_client.delete(
            f"/api/tools/selling-point-extractor/history?id={record_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        resp2 = await test_client.delete(
            f"/api/tools/selling-point-extractor/history?id={record_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp2.status_code == 404


# ---------- OperationLog ----------

class TestOperationLog:
    """验证用户操作写入 operation_logs 表。"""

    @pytest.mark.asyncio
    async def test_save_history_writes_op_log(self, test_client, operator_token, test_session):
        save_resp = await test_client.post(
            "/api/tools/selling-point-extractor/history",
            json={"productName": "日志验证产品", "result": "卖点卡"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        record_id = save_resp.json()["data"]["id"]

        rows = (await test_session.execute(text(
            "SELECT action, target_type, target_id FROM operation_logs "
            "WHERE action = 'selling_point_save_history' ORDER BY id DESC LIMIT 1"
        ))).fetchone()
        assert rows is not None
        assert rows[0] == "selling_point_save_history"
        assert rows[1] == "output"
        assert str(rows[2]) == str(record_id)

    @pytest.mark.asyncio
    async def test_delete_history_writes_op_log(self, test_client, operator_token, test_session):
        save_resp = await test_client.post(
            "/api/tools/selling-point-extractor/history",
            json={"result": "待删除内容"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        record_id = save_resp.json()["data"]["id"]

        await test_client.delete(
            f"/api/tools/selling-point-extractor/history?id={record_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )

        rows = (await test_session.execute(text(
            "SELECT action, target_type, target_id FROM operation_logs "
            "WHERE action = 'selling_point_delete_history' ORDER BY id DESC LIMIT 1"
        ))).fetchone()
        assert rows is not None
        assert rows[0] == "selling_point_delete_history"
        assert rows[1] == "output"
        assert str(rows[2]) == str(record_id)

    @pytest.mark.asyncio
    async def test_parse_file_writes_op_log(self, test_client, operator_token, test_session):
        await test_client.post(
            "/api/tools/selling-point-extractor/parse-file",
            files={"file": ("log_test.txt", b"content", "text/plain")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )

        rows = (await test_session.execute(text(
            "SELECT action, target_type FROM operation_logs "
            "WHERE action = 'selling_point_parse_file' ORDER BY id DESC LIMIT 1"
        ))).fetchone()
        assert rows is not None
        assert rows[0] == "selling_point_parse_file"
        assert rows[1] == "file"
