"""
并发测试公共 fixtures。
- `admin_token`：admin 的 JWT，session 级
- `op_users`：20 个 operator 的 {username, user_id, token} 列表，session 级
- `run_concurrent`：并发执行 httpx 请求的工具函数
- 自动 teardown：测试结束后软删除所有 conc_op_* 账号及测试数据
"""

import asyncio
import os
import time
from typing import Any

import asyncpg
import httpx
import pytest

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
ADMIN_USER = os.getenv("TEST_ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("TEST_ADMIN_PASS", "Admin@123456")
DB_URL = os.getenv(
    "TEST_DB_URL",
    "postgresql://postgres:admin123@localhost:5432/mcn_m1",
)
N_USERS = int(os.getenv("CONCURRENT_USERS", "20"))
INITIAL_PASSWORD = "Mcn@123"


# ---------------------------------------------------------------------------
# 工具：单次 POST login，返回 token
# ---------------------------------------------------------------------------

async def _login(client: httpx.AsyncClient, username: str, password: str) -> str:
    resp = await client.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": username, "password": password},
    )
    data = resp.json()
    assert data["success"], f"Login failed for {username}: {data}"
    return data["data"]["access_token"]


# ---------------------------------------------------------------------------
# 工具：改密（初次登录 must_change_password=True 时调用）
# ---------------------------------------------------------------------------

async def _change_password(
    client: httpx.AsyncClient, token: str, old_pw: str, new_pw: str
) -> None:
    resp = await client.post(
        f"{BASE_URL}/api/auth/change-password",
        json={
            "old_password": old_pw,
            "new_password": new_pw,
            "confirm_password": new_pw,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    assert data["success"], f"change-password failed: {data}"


# ---------------------------------------------------------------------------
# session-scoped fixture：admin token
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
async def admin_token() -> str:
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        return await _login(client, ADMIN_USER, ADMIN_PASS)


# ---------------------------------------------------------------------------
# session-scoped fixture：批量创建 N_USERS 个 operator，改密，返回用户列表
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
async def op_users(admin_token: str) -> list[dict]:
    """
    返回列表，每项：{"username": str, "user_id": int, "token": str, "password": str}
    """
    created: list[dict] = []

    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        for i in range(N_USERS):
            username = f"conc_op_{i:03d}"
            new_pw = f"ConcTest@{i:04d}"

            # 创建用户
            resp = await client.post(
                f"{BASE_URL}/api/admin/users",
                json={"username": username, "real_name": f"并发测试{i}", "role": "operator"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            body = resp.json()
            # 若已存在（重复执行时），重置密码确保可登录
            if not body["success"] and body.get("code") == "USERNAME_ALREADY_EXISTS":
                user_resp = await client.get(
                    f"{BASE_URL}/api/admin/users?page=1&page_size=50",
                    headers={"Authorization": f"Bearer {admin_token}"},
                )
                users = user_resp.json()["data"]["items"]
                user = next((u for u in users if u["username"] == username), None)
                if user is None:
                    raise RuntimeError(f"Cannot find existing user {username}")
                user_id = user["id"]
                await client.post(
                    f"{BASE_URL}/api/admin/users/{user_id}/reset-password",
                    headers={"Authorization": f"Bearer {admin_token}"},
                )
            else:
                assert body["success"], f"Failed to create {username}: {body}"
                user_id = body["data"]["id"]

            # 用初始密码登录，改密
            pre_token = await _login(client, username, INITIAL_PASSWORD)
            await _change_password(client, pre_token, INITIAL_PASSWORD, new_pw)

            # 用新密码重新登录
            token = await _login(client, username, new_pw)

            created.append({
                "username": username,
                "user_id": user_id,
                "token": token,
                "password": new_pw,
            })

    yield created

    # -----------------------------------------------------------------------
    # Teardown：软删除所有 conc_op_* 账号
    # -----------------------------------------------------------------------
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        fresh_admin = await _login(client, ADMIN_USER, ADMIN_PASS)
        for user in created:
            await client.delete(
                f"{BASE_URL}/api/admin/users/{user['user_id']}",
                headers={"Authorization": f"Bearer {fresh_admin}"},
            )

    # 清理测试插入的 task_jobs / outputs（通过 DB 直连）
    conn = await asyncpg.connect(DB_URL)
    try:
        user_ids = [u["user_id"] for u in created]
        if user_ids:
            await conn.execute(
                "DELETE FROM task_jobs WHERE created_by = ANY($1::bigint[])", user_ids
            )
            await conn.execute(
                "DELETE FROM outputs WHERE created_by = ANY($1::bigint[])", user_ids
            )
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# 并发执行器：接受 list[coroutine]，返回结果列表
# ---------------------------------------------------------------------------

async def run_concurrent(coros: list) -> list[dict]:
    """
    并发执行所有协程，返回 list[{"success": bool, "status_code": int,
    "latency_ms": float, "body": dict}]
    """
    async def _timed(coro):
        t0 = time.perf_counter()
        try:
            result = await coro
            latency = (time.perf_counter() - t0) * 1000
            return {"success": True, "status_code": result.status_code,
                    "latency_ms": latency, "body": result.json()}
        except Exception as exc:
            latency = (time.perf_counter() - t0) * 1000
            return {"success": False, "status_code": 0,
                    "latency_ms": latency, "body": {"error": str(exc)}}

    return await asyncio.gather(*[_timed(c) for c in coros])


# ---------------------------------------------------------------------------
# 让测试文件可以直接 import run_concurrent
# ---------------------------------------------------------------------------

@pytest.fixture
def concurrent_runner():
    return run_concurrent


# ---------------------------------------------------------------------------
# pytest session finish hook：所有测试跑完后写报告
# ---------------------------------------------------------------------------

def pytest_sessionfinish(session, exitstatus):
    """在 pytest session 结束时生成 Markdown 报告。"""
    from tests.concurrent.reporter import REPORT
    REPORT.write()
