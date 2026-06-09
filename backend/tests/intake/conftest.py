"""
kol-intake 测试公共 fixtures。
op_users / run_concurrent / admin_token 来自 tests/concurrent/conftest.py，通过
pytest_plugins 共享，避免重复实现。
"""
import asyncio
import os

import httpx
import pytest

# Windows 系统代理设置会让 httpx 把 localhost 请求通过代理转发，导致 502。
# trust_env=False 禁用代理读取，直连服务。
_CLIENT_DEFAULTS: dict = {"trust_env": False}

# 复用并发测试的 session 级 fixtures（op_users、run_concurrent、admin_token）
pytest_plugins = ["tests.concurrent.conftest"]

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
ADMIN_USER = os.getenv("TEST_ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("TEST_ADMIN_PASS", "Admin@123456")
DB_URL = os.getenv("TEST_DB_URL", "postgresql://postgres:admin123@localhost:5432/mcn_m1")

# 测试用临时账号配置
_OP_USERNAME = "intake_test_op"
_OP_INITIAL_PASS = "Mcn@123"
_OP_FINAL_PASS = "Test@9999"


async def _admin_token() -> str:
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        resp = await client.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": ADMIN_USER, "password": ADMIN_PASS},
        )
        data = resp.json()
        assert data["success"], f"Admin login failed: {data}"
        return data["data"]["access_token"]


async def _get_or_create_operator() -> dict:
    """创建或复用一个 intake_test_op 账号，返回 {user_id, token}。"""
    admin = await _admin_token()
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        # 尝试创建
        resp = await client.post(
            f"{BASE_URL}/api/admin/users",
            json={"username": _OP_USERNAME, "real_name": "测试运营", "role": "operator"},
            headers={"Authorization": f"Bearer {admin}"},
        )
        body = resp.json()

        if body.get("success"):
            user_id = body["data"]["id"]
        elif body.get("code") == "USERNAME_ALREADY_EXISTS":
            # 已存在，先重置密码再拿 user_id
            user_resp = await client.get(
                f"{BASE_URL}/api/admin/users?page=1&page_size=100",
                headers={"Authorization": f"Bearer {admin}"},
            )
            users = user_resp.json()["data"]["items"]
            user = next((u for u in users if u["username"] == _OP_USERNAME), None)
            if user is None:
                raise RuntimeError(f"Cannot find existing user {_OP_USERNAME}")
            user_id = user["id"]
            await client.post(
                f"{BASE_URL}/api/admin/users/{user_id}/reset-password",
                headers={"Authorization": f"Bearer {admin}"},
            )
        else:
            raise RuntimeError(f"Failed to create operator: {body}")

        # 用初始密码登录，改密
        pre_resp = await client.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": _OP_USERNAME, "password": _OP_INITIAL_PASS},
        )
        pre_token = pre_resp.json()["data"]["access_token"]

        await client.post(
            f"{BASE_URL}/api/auth/change-password",
            json={
                "old_password": _OP_INITIAL_PASS,
                "new_password": _OP_FINAL_PASS,
                "confirm_password": _OP_FINAL_PASS,
            },
            headers={"Authorization": f"Bearer {pre_token}"},
        )

        # 用新密码重新登录
        token_resp = await client.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": _OP_USERNAME, "password": _OP_FINAL_PASS},
        )
        token = token_resp.json()["data"]["access_token"]

    return {"user_id": user_id, "token": token}


@pytest.fixture(scope="module")
async def op_token():
    """模块级运营 token fixture，测试结束后删除账号。"""
    data = await _get_or_create_operator()
    yield data
    # teardown
    admin = await _admin_token()
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        await client.delete(
            f"{BASE_URL}/api/admin/users/{data['user_id']}",
            headers={"Authorization": f"Bearer {admin}"},
        )


@pytest.fixture(scope="module")
async def intake_link(op_token):
    """创建一条测试用分享链接，返回 token 字符串。"""
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        resp = await client.post(
            f"{BASE_URL}/api/operator/intake/links",
            json={"kol_name": "测试红人", "expire_hours": 24},
            headers={"Authorization": f"Bearer {op_token['token']}"},
        )
        data = resp.json()
        assert data["success"], f"创建链接失败: {data}"
        return data["data"]["token"]
