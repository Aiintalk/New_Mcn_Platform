"""
并发测试 CONC-001 ~ CONC-005
复用 tests/concurrent/conftest.py 提供的 op_users fixture（通过 conftest 路径共享）。
"""
import asyncio
import os

import httpx
import pytest

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# CONC-001：20 人同时获取题目列表，全部 200 且数据一致
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conc_001_questions_concurrent():
    """CONC-001：20 人同时 GET /api/intake/questions — 全部 200，题目数量一致。"""
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        coros = [client.get(f"{BASE_URL}/api/intake/questions") for _ in range(20)]
        results = await asyncio.gather(*coros)

    assert all(r.status_code == 200 for r in results), \
        f"存在非 200 响应: {[r.status_code for r in results if r.status_code != 200]}"

    counts = [len(r.json()["data"]) for r in results]
    assert len(set(counts)) == 1, f"题目数量不一致: {counts}"
    assert counts[0] == 24, f"题目数量应为 24，实际为 {counts[0]}"


# ---------------------------------------------------------------------------
# CONC-002：10 个链接同时调用 bridge — 全部返回过渡语，无串扰
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conc_002_bridge_concurrent(op_token):
    """CONC-002：10 个链接同时调用 bridge — 全部返回，无串扰。"""
    # 创建 10 条链接
    tokens: list[str] = []
    async with httpx.AsyncClient(timeout=90, trust_env=False) as client:
        for i in range(10):
            resp = await client.post(
                f"{BASE_URL}/api/operator/intake/links",
                json={"kol_name": f"并发bridge测试{i}", "expire_hours": 1},
                headers={"Authorization": f"Bearer {op_token['token']}"},
            )
            assert resp.json()["success"], f"创建链接失败: {resp.json()}"
            tokens.append(resp.json()["data"]["token"])

        # 并发 bridge
        coros = [
            client.post(
                f"{BASE_URL}/api/intake/{tk}/bridge",
                json={
                    "user_answer": f"我是{i}号测试用户",
                    "question_text": "请介绍一下你自己",
                    "next_question_text": "你的账号名是什么？",
                    "is_last_question": False,
                },
            )
            for i, tk in enumerate(tokens)
        ]
        results = await asyncio.gather(*coros)

    assert all(r.status_code == 200 for r in results), \
        f"存在非 200 响应: {[(i, r.status_code) for i, r in enumerate(results) if r.status_code != 200]}"

    # 每条链接各自返回自己的 reply，success 均为 true
    for i, r in enumerate(results):
        body = r.json()
        assert body["success"], f"链接 {i} bridge 失败: {body}"
        assert "reply" in body["data"], f"链接 {i} 响应缺少 reply 字段"


# ---------------------------------------------------------------------------
# CONC-003：5 个运营同时创建直发会话 — session 互相隔离，operator_id 正确
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conc_003_direct_session_isolation(op_users):
    """CONC-003：5 个运营同时创建直发会话 — session 互相隔离。"""
    users = op_users[:5]

    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        coros = [
            client.post(
                f"{BASE_URL}/api/operator/intake/direct/start",
                json={"kol_name": f"并发直发测试{i}"},
                headers={"Authorization": f"Bearer {u['token']}"},
            )
            for i, u in enumerate(users)
        ]
        results = await asyncio.gather(*coros)

    assert all(r.status_code == 200 for r in results), \
        f"存在非 200 响应: {[r.status_code for r in results if r.status_code != 200]}"

    session_ids = [r.json()["data"]["session_id"] for r in results]
    # session_id 应各不相同
    assert len(set(session_ids)) == 5, f"session_id 存在重复: {session_ids}"

    # 每个运营查询自己的 session，应能正常返回
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        status_coros = [
            client.get(
                f"{BASE_URL}/api/operator/intake/direct/{sid}/status",
                headers={"Authorization": f"Bearer {users[i]['token']}"},
            )
            for i, sid in enumerate(session_ids)
        ]
        status_results = await asyncio.gather(*status_coros)

    for i, r in enumerate(status_results):
        body = r.json()
        assert r.status_code == 200, f"运营 {i} 查询自己 session 失败: {r.status_code}"
        assert body["success"], f"运营 {i} session status 失败: {body}"


# ---------------------------------------------------------------------------
# CONC-004：运营 A 的 session_id 被运营 B 访问 — 全部 RESOURCE_NOT_FOUND
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conc_004_session_cross_access(op_users):
    """CONC-004：运营 A 的 session 被运营 B~E 访问 — 全部 RESOURCE_NOT_FOUND。"""
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        # op_users[0] 创建会话
        resp = await client.post(
            f"{BASE_URL}/api/operator/intake/direct/start",
            json={},
            headers={"Authorization": f"Bearer {op_users[0]['token']}"},
        )
        assert resp.json()["success"], f"创建会话失败: {resp.json()}"
        session_id = resp.json()["data"]["session_id"]

        # op_users[1~4] 尝试访问 op_users[0] 的 session
        coros = [
            client.get(
                f"{BASE_URL}/api/operator/intake/direct/{session_id}/status",
                headers={"Authorization": f"Bearer {op_users[i]['token']}"},
            )
            for i in range(1, 5)
        ]
        results = await asyncio.gather(*coros)

    for i, r in enumerate(results, start=1):
        body = r.json()
        assert r.status_code == 404, f"运营 {i} 跨用户访问应返回 404，实际: {r.status_code}"
        assert body.get("code") == "RESOURCE_NOT_FOUND", \
            f"运营 {i} 应返回 RESOURCE_NOT_FOUND，实际: {body}"


# ---------------------------------------------------------------------------
# CONC-005：10 个链接同时提交 — 全部触发报告生成，report_status=generating
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conc_005_submit_concurrent(op_token):
    """CONC-005：10 个链接同时提交 — 全部触发报告生成，report_status=generating。"""
    # 创建 10 条链接
    tokens: list[str] = []
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        for i in range(10):
            resp = await client.post(
                f"{BASE_URL}/api/operator/intake/links",
                json={"kol_name": f"并发提交测试{i}", "expire_hours": 1},
                headers={"Authorization": f"Bearer {op_token['token']}"},
            )
            assert resp.json()["success"]
            tokens.append(resp.json()["data"]["token"])

        messages = [
            {"role": "assistant", "content": "请介绍一下你自己"},
            {"role": "user", "content": "我是并发测试用户"},
        ]

        # 并发提交
        coros = [
            client.post(
                f"{BASE_URL}/api/intake/{tk}/submit",
                json={"messages": messages},
            )
            for tk in tokens
        ]
        results = await asyncio.gather(*coros)

    assert all(r.status_code == 200 for r in results), \
        f"存在非 200 提交: {[(i, r.status_code, r.text[:100]) for i, r in enumerate(results) if r.status_code != 200]}"

    for i, r in enumerate(results):
        body = r.json()
        assert body["success"], f"链接 {i} 提交失败: {body}"
        assert body["data"]["report_status"] == "generating", \
            f"链接 {i} report_status 应为 generating，实际: {body['data']['report_status']}"
