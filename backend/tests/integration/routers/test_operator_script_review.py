"""
Integration tests for Sprint 21 千川脚本预审接口.

Covers:
1. 无 token → 401
2. 管理端 GET /config → 返回 default 配置（success=True）
3. 管理端 PUT /config → 更新 direct_prompt 成功
4. 运营端 POST /review direct 模式 → 返回结构化结果（mock AI 调用）
5. 运营端 POST /review value 模式 → 返回结构化结果（mock AI 调用）
6. 运营端 POST /review 缺少 adapted_script → 422
7. 运营端 POST /save-output → 保存预审结果到 outputs 表（success/empty_content/account_isolation）
"""
import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text


_MOCK_AI_RESPONSE = json.dumps({
    "rating": "pass",
    "must_fix": [],
    "suggestions": ["建议1"],
    "passed": ["结构完整"],
})


async def _create_success_task(test_session, user_id: int, task_no: str) -> int:
    task_id = (await test_session.execute(text(
        "INSERT INTO task_jobs (task_no, tool_code, tool_name, status, created_by) "
        "VALUES (:task_no, 'qianchuan-script-review', '千川脚本预审', 'success', :uid) "
        "RETURNING id"
    ), {"task_no": task_no, "uid": user_id})).scalar_one()
    await test_session.commit()
    return task_id


class TestAuth:
    @pytest.mark.asyncio
    async def test_no_token_admin_get(self, test_client):
        resp = await test_client.get("/api/admin/qianchuan-script-review/config")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_no_token_operator_post(self, test_client):
        resp = await test_client.post(
            "/api/operator/qianchuan-script-review/review",
            json={
                "script_type": "direct",
                "original_script": "原版脚本",
                "adapted_script": "仿写脚本",
            },
        )
        assert resp.status_code == 401


class TestAdminGetConfig:
    @pytest.mark.asyncio
    async def test_get_default_config(self, test_client, admin_headers, test_session):
        resp = await test_client.get(
            "/api/admin/qianchuan-script-review/config",
            headers=admin_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["data"]["config_key"] == "default"

    @pytest.mark.asyncio
    async def test_operator_cannot_access_admin(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/admin/qianchuan-script-review/config",
            headers=operator_headers,
        )
        assert resp.status_code == 403


class TestAdminUpdateConfig:
    @pytest.mark.asyncio
    async def test_update_direct_prompt(self, test_client, admin_headers, test_session):
        payload = {
            "direct_prompt": "新的 direct prompt 内容",
            "value_prompt": None,
            "ai_model_id": None,
            "is_active": True,
        }
        resp = await test_client.put(
            "/api/admin/qianchuan-script-review/config",
            json=payload,
            headers=admin_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True

        # 验证更新已写入
        get_resp = await test_client.get(
            "/api/admin/qianchuan-script-review/config",
            headers=admin_headers,
        )
        get_body = get_resp.json()
        assert get_body["data"]["direct_prompt"] == "新的 direct prompt 内容"


class TestOperatorReview:
    @pytest.mark.asyncio
    async def test_review_direct_mode(self, test_client, operator_headers):
        with patch(
            "app.routers.operator_script_review._call_review_ai",
            new=AsyncMock(return_value=_MOCK_AI_RESPONSE),
        ):
            resp = await test_client.post(
                "/api/operator/qianchuan-script-review/review",
                json={
                    "script_type": "direct",
                    "original_script": "原版脚本内容",
                    "adapted_script": "仿写脚本内容",
                    "product": {"nickname": "大红瓶", "core_selling_point": "美白"},
                },
                headers=operator_headers,
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["data"]["rating"] == "pass"
        assert body["data"]["must_fix"] == []
        assert "建议1" in body["data"]["suggestions"]
        assert "结构完整" in body["data"]["passed"]

    @pytest.mark.asyncio
    async def test_review_records_minimal_trace_without_script_content(
        self, test_client, operator_headers, operator_user, test_session
    ):
        kol_id = (await test_session.execute(text(
            "INSERT INTO kols (name, status) VALUES ('预审留痕达人', 'signed') RETURNING id"
        ))).scalar()
        product_id = (await test_session.execute(text(
            "INSERT INTO qianchuan_products (nickname, mechanism_exclusive) "
            "VALUES ('预审留痕商品', false) RETURNING id"
        ))).scalar()
        await test_session.execute(text(
            "INSERT INTO kol_active_products (kol_id, product_id) VALUES (:kol_id, :product_id)"
        ), {"kol_id": kol_id, "product_id": product_id})
        await test_session.commit()

        with patch(
            "app.routers.operator_script_review._call_review_ai",
            new=AsyncMock(return_value=_MOCK_AI_RESPONSE),
        ):
            resp = await test_client.post(
                "/api/operator/qianchuan-script-review/review",
                json={
                    "script_type": "direct",
                    "original_script": "原版不应写入日志",
                    "adapted_script": "仿写不应写入日志",
                    "kol_id": kol_id,
                    "product_id": product_id,
                },
                headers=operator_headers,
            )

        assert resp.status_code == 200
        row = (await test_session.execute(text(
            "SELECT detail FROM operation_logs WHERE action = 'qianchuan_script_review' "
            "AND user_id = :user_id ORDER BY id DESC LIMIT 1"
        ), {"user_id": operator_user.id})).scalar_one()
        assert row["kol_id"] == kol_id
        assert row["product_id"] == product_id
        assert row["original_script_length"] == len("原版不应写入日志")
        assert row["feature"] == "qianchuan_pre_review"
        assert row["model_id"]
        assert "原版不应写入日志" not in str(row)
        assert "仿写不应写入日志" not in str(row)

    @pytest.mark.asyncio
    async def test_review_value_mode(self, test_client, operator_headers):
        with patch(
            "app.routers.operator_script_review._call_review_ai",
            new=AsyncMock(return_value=_MOCK_AI_RESPONSE),
        ):
            resp = await test_client.post(
                "/api/operator/qianchuan-script-review/review",
                json={
                    "script_type": "value",
                    "original_script": "原版价值观脚本",
                    "adapted_script": "仿写价值观脚本",
                },
                headers=operator_headers,
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["data"]["rating"] == "pass"

    @pytest.mark.asyncio
    async def test_review_missing_adapted_script(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/operator/qianchuan-script-review/review",
            json={
                "script_type": "direct",
                "original_script": "原版脚本",
            },
            headers=operator_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "invalid_result",
        [
            {"must_fix": [], "suggestions": [], "passed": []},
            {"rating": "unknown", "must_fix": [], "suggestions": [], "passed": []},
            {"rating": "pass", "must_fix": "not-a-list", "suggestions": [], "passed": []},
            {
                "rating": "fail",
                "must_fix": [{"type": "违规词", "quote": "原文"}],
                "suggestions": [],
                "passed": [],
            },
        ],
    )
    async def test_invalid_review_structure_fails_after_two_controlled_repairs(
        self,
        invalid_result,
        test_client,
        operator_headers,
        operator_user,
        test_session,
    ):
        """缺字段、非法评级或错误数组结构不能被当作成功结果。"""
        mock_ai = AsyncMock(return_value=json.dumps(invalid_result, ensure_ascii=False))
        with patch("app.routers.operator_script_review._call_review_ai", new=mock_ai):
            resp = await test_client.post(
                "/api/operator/qianchuan-script-review/review",
                json={
                    "script_type": "value",
                    "original_script": "原版脚本",
                    "adapted_script": "仿写脚本",
                },
                headers=operator_headers,
            )

        body = resp.json()
        assert body["success"] is False
        assert body["code"] == "EXTERNAL_SERVICE_ERROR"
        assert body["message"] == "AI 返回的审核结果结构不完整，请重新审核"
        assert mock_ai.await_count == 3

        task = (await test_session.execute(text(
            "SELECT id, status, error_code, error_message, input_payload, result_summary "
            "FROM task_jobs WHERE tool_code = 'qianchuan-script-review' "
            "AND created_by = :uid ORDER BY id DESC LIMIT 1"
        ), {"uid": operator_user.id})).fetchone()
        assert task.status == "failed"
        assert task.error_code == "INVALID_AI_RESULT"
        assert task.error_message == "AI 返回的审核结果结构不完整，请重新审核"
        assert task.result_summary["attempts"] == 3
        assert "原版脚本" not in str(task.input_payload)
        assert "仿写脚本" not in str(task.input_payload)

        success_logs = (await test_session.execute(text(
            "SELECT COUNT(*) FROM operation_logs WHERE action = 'qianchuan_script_review' "
            "AND user_id = :uid"
        ), {"uid": operator_user.id})).scalar_one()
        assert success_logs == 0
        failure_log = (await test_session.execute(text(
            "SELECT detail FROM operation_logs WHERE action = 'qianchuan_script_review_failed' "
            "AND target_id = :task_id ORDER BY id DESC LIMIT 1"
        ), {"task_id": task.id})).scalar_one()
        assert failure_log == {"attempts": 3, "error_code": "INVALID_AI_RESULT"}

    @pytest.mark.asyncio
    async def test_review_accepts_valid_structure_from_first_controlled_repair(
        self, test_client, operator_headers, operator_user, test_session
    ):
        """首次输出不可解析时，只修复格式；修复后的合法结构才可成功。"""
        mock_ai = AsyncMock(side_effect=[
            "```json\n{\"rating\":\"pass\"",
            _MOCK_AI_RESPONSE,
        ])
        with patch("app.routers.operator_script_review._call_review_ai", new=mock_ai):
            resp = await test_client.post(
                "/api/operator/qianchuan-script-review/review",
                json={
                    "script_type": "value",
                    "original_script": "原版脚本",
                    "adapted_script": "仿写脚本",
                },
                headers=operator_headers,
            )

        body = resp.json()
        assert body["success"] is True
        assert body["data"]["rating"] == "pass"
        assert isinstance(body["data"]["task_id"], int)
        assert mock_ai.await_count == 2
        repair_prompt = mock_ai.await_args_list[1].args[0]
        assert "只修复 JSON 结构" in repair_prompt
        assert "不得改变审核结论" in repair_prompt

        task_status = (await test_session.execute(text(
            "SELECT status FROM task_jobs WHERE id = :id AND created_by = :uid"
        ), {"id": body["data"]["task_id"], "uid": operator_user.id})).scalar_one()
        assert task_status == "success"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("invalid_raw", ["抱歉，我无法审核", '```json\n{"rating":"pass"'])
    async def test_plain_refusal_or_truncated_json_is_a_failed_task(
        self, invalid_raw, test_client, operator_headers, operator_user, test_session
    ):
        """纯文本拒答和连续截断 JSON 都不能被当作成功。"""
        mock_ai = AsyncMock(return_value=invalid_raw)
        with patch("app.routers.operator_script_review._call_review_ai", new=mock_ai):
            resp = await test_client.post(
                "/api/operator/qianchuan-script-review/review",
                json={
                    "script_type": "value",
                    "original_script": "原版脚本",
                    "adapted_script": "仿写脚本",
                },
                headers=operator_headers,
            )

        assert resp.json()["code"] == "EXTERNAL_SERVICE_ERROR"
        assert mock_ai.await_count == 3
        task = (await test_session.execute(text(
            "SELECT status, error_code FROM task_jobs WHERE tool_code = 'qianchuan-script-review' "
            "AND created_by = :uid ORDER BY id DESC LIMIT 1"
        ), {"uid": operator_user.id})).fetchone()
        assert task.status == "failed"
        assert task.error_code == "INVALID_AI_RESULT"

    @pytest.mark.asyncio
    async def test_ai_call_exception_marks_task_failed_without_success_log(
        self, test_client, operator_headers, operator_user, test_session
    ):
        mock_ai = AsyncMock(side_effect=RuntimeError("provider secret detail"))
        with patch("app.routers.operator_script_review._call_review_ai", new=mock_ai):
            resp = await test_client.post(
                "/api/operator/qianchuan-script-review/review",
                json={
                    "script_type": "value",
                    "original_script": "原版脚本",
                    "adapted_script": "仿写脚本",
                },
                headers=operator_headers,
            )

        assert resp.json()["message"] == "AI 审核失败，请重新审核"
        task = (await test_session.execute(text(
            "SELECT id, status, error_code, error_message FROM task_jobs "
            "WHERE tool_code = 'qianchuan-script-review' AND created_by = :uid "
            "ORDER BY id DESC LIMIT 1"
        ), {"uid": operator_user.id})).fetchone()
        assert task.status == "failed"
        assert task.error_code == "AI_CALL_FAILED"
        assert "provider secret detail" not in task.error_message
        success_logs = (await test_session.execute(text(
            "SELECT COUNT(*) FROM operation_logs WHERE action = 'qianchuan_script_review' "
            "AND user_id = :uid"
        ), {"uid": operator_user.id})).scalar_one()
        assert success_logs == 0
        failure_log = (await test_session.execute(text(
            "SELECT detail FROM operation_logs WHERE action = 'qianchuan_script_review_failed' "
            "AND target_id = :task_id ORDER BY id DESC LIMIT 1"
        ), {"task_id": task.id})).scalar_one()
        assert failure_log == {"attempts": 1, "error_code": "AI_CALL_FAILED"}


class TestSaveOutput:
    @pytest.mark.asyncio
    async def test_save_success(self, test_client, operator_headers, operator_user, test_session):
        task_id = await _create_success_task(test_session, operator_user.id, "SR-SAVE-SUCCESS")
        resp = await test_client.post(
            "/api/operator/qianchuan-script-review/save-output",
            json={
                "task_id": task_id,
                "title": "脚本预审_测试",
                "content": "仿写脚本原文",
                "content_json": {
                    "rating": "pass",
                    "must_fix": [],
                    "suggestions": ["建议1"],
                    "passed": ["结构完整"],
                },
            },
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert "output_id" in body["data"]

        output_id = body["data"]["output_id"]
        row = (await test_session.execute(text(
            "SELECT tool_code, tool_name, content_json, created_by "
            "FROM outputs WHERE id = :id"
        ), {"id": output_id})).fetchone()
        assert row[0] == "qianchuan-script-review"
        assert row[1] == "千川脚本预审"
        assert row[2]["rating"] == "pass"
        assert row[3] == operator_user.id

    @pytest.mark.asyncio
    async def test_save_empty_content(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/operator/qianchuan-script-review/save-output",
            json={
                "task_id": 1,
                "content": "   ",
                "content_json": {"rating": "pass"},
            },
            headers=operator_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_save_empty_content_json(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/operator/qianchuan-script-review/save-output",
            json={"task_id": 1, "content": "脚本原文", "content_json": {}},
            headers=operator_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_save_writes_operation_log(
        self, test_client, operator_headers, operator_user, test_session
    ):
        task_id = await _create_success_task(test_session, operator_user.id, "SR-SAVE-LOG")
        resp = await test_client.post(
            "/api/operator/qianchuan-script-review/save-output",
            json={
                "task_id": task_id,
                "content": "脚本原文",
                "content_json": {
                    "rating": "minor",
                    "must_fix": [{"type": "X", "quote": "y", "fix": "z"}],
                    "suggestions": [],
                    "passed": [],
                },
            },
            headers=operator_headers,
        )
        assert resp.json()["success"] is True

        log_count = (await test_session.execute(text(
            "SELECT COUNT(*) FROM operation_logs "
            "WHERE action = 'script_review_save_output' "
            "AND user_id = :uid"
        ), {"uid": operator_user.id})).scalar()
        assert log_count >= 1

    @pytest.mark.asyncio
    async def test_save_account_isolation(
        self, test_client, operator_user, operator_token, admin_token, test_session
    ):
        """operator 保存的预审结果，admin 通过全局 /outputs 看不到（账号隔离）。"""
        task_id = await _create_success_task(test_session, operator_user.id, "SR-SAVE-ISOLATION")
        resp = await test_client.post(
            "/api/operator/qianchuan-script-review/save-output",
            json={
                "task_id": task_id,
                "title": "operator专属预审",
                "content": "仿写脚本",
                "content_json": {"rating": "pass", "must_fix": [], "suggestions": [], "passed": []},
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200

        resp = await test_client.get(
            "/api/outputs?tool_code=qianchuan-script-review",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        titles = [item["title"] for item in resp.json()["data"]["items"]]
        assert "operator专属预审" not in titles

    @pytest.mark.asyncio
    async def test_save_rejects_invalid_review_structure(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/operator/qianchuan-script-review/save-output",
            json={
                "task_id": 1,
                "content": "仿写脚本",
                "content_json": {
                    "rating": "pass",
                    "must_fix": [{"type": "缺少 fix", "quote": "原文"}],
                    "suggestions": [],
                    "passed": [],
                },
            },
            headers=operator_headers,
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_REVIEW_RESULT"

    @pytest.mark.asyncio
    async def test_save_rejects_failed_task(
        self, test_client, operator_headers, operator_user, test_session
    ):
        task_id = (await test_session.execute(text(
            "INSERT INTO task_jobs (task_no, tool_code, tool_name, status, created_by) "
            "VALUES ('SR-FAILED-SAVE', 'qianchuan-script-review', '千川脚本预审', 'failed', :uid) "
            "RETURNING id"
        ), {"uid": operator_user.id})).scalar_one()
        await test_session.commit()

        resp = await test_client.post(
            "/api/operator/qianchuan-script-review/save-output",
            json={
                "task_id": task_id,
                "content": "仿写脚本",
                "content_json": {
                    "rating": "pass",
                    "must_fix": [],
                    "suggestions": [],
                    "passed": [],
                },
            },
            headers=operator_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "TASK_NOT_SUCCESS"
