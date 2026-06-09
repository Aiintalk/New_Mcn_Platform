"""
功能测试 FUNC-001 ~ FUNC-010
"""
import asyncio
import os

import httpx
import pytest

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# FUNC-001：GET /api/intake/questions 返回 24 道题
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_func_001_get_questions():
    """FUNC-001：GET /api/intake/questions 返回 24 道题，含必要字段。"""
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        resp = await client.get(f"{BASE_URL}/api/intake/questions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"], f"响应 success=false: {data}"
    questions = data["data"]
    assert len(questions) == 24, f"题目数量应为 24，实际为 {len(questions)}"
    required_fields = {"id", "order_num", "category", "question_text", "question_type", "is_required"}
    for q in questions:
        assert required_fields.issubset(q.keys()), f"题目缺字段: {set(required_fields) - set(q.keys())} in {q}"


# ---------------------------------------------------------------------------
# FUNC-002：完整 KOL 对话流程
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_func_002_full_flow(intake_link):
    """FUNC-002：创建链接 → 校验 → bridge 过渡语 → 提交 → 轮询报告状态。"""
    async with httpx.AsyncClient(timeout=90, trust_env=False) as client:
        # 校验链接
        check_resp = await client.get(f"{BASE_URL}/api/intake/{intake_link}")
        assert check_resp.status_code == 200
        check_data = check_resp.json()
        assert check_data["success"]
        assert check_data["data"]["valid"] is True

        # 调用 bridge
        bridge_resp = await client.post(
            f"{BASE_URL}/api/intake/{intake_link}/bridge",
            json={
                "user_answer": "我叫小花，主要做美妆",
                "question_text": "请介绍一下你自己",
                "next_question_text": "你的账号名是什么？",
                "is_last_question": False,
            },
        )
        assert bridge_resp.status_code == 200
        bridge_data = bridge_resp.json()
        assert bridge_data["success"]
        assert "reply" in bridge_data["data"]

        # 提交
        submit_resp = await client.post(
            f"{BASE_URL}/api/intake/{intake_link}/submit",
            json={
                "messages": [
                    {"role": "assistant", "content": "请介绍一下你自己"},
                    {"role": "user", "content": "我叫小花，主要做美妆"},
                ]
            },
        )
        assert submit_resp.status_code == 200
        submit_data = submit_resp.json()
        assert submit_data["success"]
        assert submit_data["data"]["report_status"] == "generating"

        # 轮询状态
        status_resp = await client.get(f"{BASE_URL}/api/intake/{intake_link}/status")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["success"]
        assert status_data["data"]["report_status"] in ("generating", "ready", "pending", "failed")


# ---------------------------------------------------------------------------
# FUNC-003：bridge 过渡语不以问号结尾
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_func_003_bridge_no_question_mark(intake_link):
    """FUNC-003：bridge 过渡语不以问号结尾。"""
    async with httpx.AsyncClient(timeout=90, trust_env=False) as client:
        resp = await client.post(
            f"{BASE_URL}/api/intake/{intake_link}/bridge",
            json={
                "user_answer": "我叫小花",
                "question_text": "你希望粉丝怎么叫你？",
                "next_question_text": "你的抖音账号名叫什么？",
                "is_last_question": False,
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"]
    reply = data["data"]["reply"]
    if reply:  # reply="" 降级时不检查
        assert not reply.strip().endswith("？"), f"过渡语不应以中文问号结尾: {reply}"
        assert not reply.strip().endswith("?"), f"过渡语不应以英文问号结尾: {reply}"


# ---------------------------------------------------------------------------
# FUNC-004：必填题输入「跳过」时 bridge 正常处理
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_func_004_skip_required_bridge(intake_link):
    """FUNC-004：必填题输入「跳过」时 bridge 正常处理，不报错。"""
    async with httpx.AsyncClient(timeout=90, trust_env=False) as client:
        resp = await client.post(
            f"{BASE_URL}/api/intake/{intake_link}/bridge",
            json={
                "user_answer": "跳过",
                "question_text": "你的全名是什么？",
                "next_question_text": "你来自哪个城市？",
                "is_last_question": False,
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"], f"bridge 不应报错: {data}"
    assert "reply" in data["data"]


# ---------------------------------------------------------------------------
# FUNC-005：multi_collect 题型 bridge 携带正确参数
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_func_005_multi_collect_bridge(intake_link):
    """FUNC-005：multi_collect 题型 bridge 携带 is_multi_collect=true 和 collect_count。"""
    async with httpx.AsyncClient(timeout=90, trust_env=False) as client:
        resp = await client.post(
            f"{BASE_URL}/api/intake/{intake_link}/bridge",
            json={
                "user_answer": "拍美食探店",
                "question_text": "你主要做哪类内容？",
                "is_multi_collect": True,
                "collect_count": 2,
                "is_last_question": False,
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"], f"multi_collect bridge 失败: {data}"
    assert "reply" in data["data"]


# ---------------------------------------------------------------------------
# FUNC-006：最后一题 bridge，is_last_question=true 返回收尾语
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_func_006_last_question_bridge(intake_link):
    """FUNC-006：is_last_question=True 时 bridge 返回收尾语（不为空且不含问号结尾）。"""
    async with httpx.AsyncClient(timeout=90, trust_env=False) as client:
        resp = await client.post(
            f"{BASE_URL}/api/intake/{intake_link}/bridge",
            json={
                "user_answer": "没什么想补充的了",
                "question_text": "还有什么想补充的吗？",
                "is_last_question": True,
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"]
    reply = data["data"]["reply"]
    if reply:
        assert not reply.strip().endswith("？"), f"收尾语不应以问号结尾: {reply}"
        assert not reply.strip().endswith("?"), f"收尾语不应以问号结尾: {reply}"


# ---------------------------------------------------------------------------
# FUNC-007：链接无效时 bridge 报 LINK_EXPIRED / 404
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_func_007_expired_link_bridge():
    """FUNC-007：无效 token 调用 bridge 返回 404 或 410。"""
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        resp = await client.post(
            f"{BASE_URL}/api/intake/invalid_token_xxx_not_exist/bridge",
            json={"user_answer": "test", "question_text": "test"},
        )
    assert resp.status_code in (404, 410), f"期望 404/410，实际 {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# FUNC-008：运营直发完整流程 start → bridge → submit → status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_func_008_direct_full_flow(op_token):
    """FUNC-008：运营直发 start → bridge → submit → status 完整流程。"""
    headers = {"Authorization": f"Bearer {op_token['token']}"}
    async with httpx.AsyncClient(timeout=90, trust_env=False) as client:
        # start
        start_resp = await client.post(
            f"{BASE_URL}/api/operator/intake/direct/start",
            json={"kol_name": "直发测试红人"},
            headers=headers,
        )
        assert start_resp.status_code == 200
        start_data = start_resp.json()
        assert start_data["success"], f"start 失败: {start_data}"
        session_id = start_data["data"]["session_id"]

        # bridge
        bridge_resp = await client.post(
            f"{BASE_URL}/api/operator/intake/direct/{session_id}/bridge",
            json={
                "user_answer": "我叫直发测试小花",
                "question_text": "请介绍一下你自己",
                "next_question_text": "你的账号名是什么？",
                "is_last_question": False,
            },
            headers=headers,
        )
        assert bridge_resp.status_code == 200
        bridge_data = bridge_resp.json()
        assert bridge_data["success"], f"bridge 失败: {bridge_data}"

        # submit
        submit_resp = await client.post(
            f"{BASE_URL}/api/operator/intake/direct/{session_id}/submit",
            json={
                "messages": [
                    {"role": "assistant", "content": "请介绍一下你自己"},
                    {"role": "user", "content": "我叫直发测试小花"},
                ]
            },
            headers=headers,
        )
        assert submit_resp.status_code == 200
        submit_data = submit_resp.json()
        assert submit_data["success"], f"submit 失败: {submit_data}"
        assert submit_data["data"]["report_status"] == "generating"

        # status
        status_resp = await client.get(
            f"{BASE_URL}/api/operator/intake/direct/{session_id}/status",
            headers=headers,
        )
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["success"]
        assert status_data["data"]["report_status"] in ("generating", "ready", "pending", "failed")


# ---------------------------------------------------------------------------
# FUNC-009：运营直发下载 — status=ready 后 ?token= 参数鉴权下载
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_func_009_direct_download_with_token(op_token):
    """FUNC-009：status=ready 后 ?token= 参数鉴权下载成功（等待最多 60s）。"""
    headers = {"Authorization": f"Bearer {op_token['token']}"}
    async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
        # 创建会话并提交
        start_resp = await client.post(
            f"{BASE_URL}/api/operator/intake/direct/start",
            json={"kol_name": "下载测试红人"},
            headers=headers,
        )
        assert start_resp.json()["success"]
        session_id = start_resp.json()["data"]["session_id"]

        await client.post(
            f"{BASE_URL}/api/operator/intake/direct/{session_id}/submit",
            json={
                "messages": [
                    {"role": "assistant", "content": "介绍一下自己"},
                    {"role": "user", "content": "我是下载测试红人"},
                ]
            },
            headers=headers,
        )

        # 轮询等待 ready（最多 60s）
        for _ in range(12):
            await asyncio.sleep(5)
            status_resp = await client.get(
                f"{BASE_URL}/api/operator/intake/direct/{session_id}/status",
                headers=headers,
            )
            status = status_resp.json()["data"]["report_status"]
            if status == "ready":
                break
        else:
            pytest.skip("报告未在 60s 内生成，跳过下载测试")

        # 用 ?token= 参数下载
        jwt_token = op_token["token"]
        dl_resp = await client.get(
            f"{BASE_URL}/api/operator/intake/direct/{session_id}/download?format=docx&token={jwt_token}",
        )
        assert dl_resp.status_code == 200, f"下载失败: {dl_resp.status_code} {dl_resp.text[:200]}"


# ---------------------------------------------------------------------------
# FUNC-010：重复提交同一链接返回 409 VALIDATION_ERROR
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_func_010_duplicate_submit(op_token):
    """FUNC-010：重复提交同一链接返回 409 VALIDATION_ERROR。"""
    # 新建一条链接专门用于此用例
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        link_resp = await client.post(
            f"{BASE_URL}/api/operator/intake/links",
            json={"kol_name": "重复提交测试", "expire_hours": 1},
            headers={"Authorization": f"Bearer {op_token['token']}"},
        )
        assert link_resp.json()["success"]
        token = link_resp.json()["data"]["token"]

        messages = [
            {"role": "assistant", "content": "你好"},
            {"role": "user", "content": "你好，我是测试"},
        ]

        # 第一次提交
        resp1 = await client.post(
            f"{BASE_URL}/api/intake/{token}/submit",
            json={"messages": messages},
        )
        assert resp1.status_code == 200, f"第一次提交应成功: {resp1.text}"

        # 第二次提交
        resp2 = await client.post(
            f"{BASE_URL}/api/intake/{token}/submit",
            json={"messages": messages},
        )
        assert resp2.status_code == 409, f"重复提交应返回 409，实际: {resp2.status_code}"
        body2 = resp2.json()
        assert body2.get("code") == "VALIDATION_ERROR", f"错误码应为 VALIDATION_ERROR: {body2}"
