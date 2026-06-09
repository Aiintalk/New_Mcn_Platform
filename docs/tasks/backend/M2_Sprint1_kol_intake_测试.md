# 后端任务单 · kol-intake 功能测试 + 并发测试

> 目标：为 kol-intake 新增两类测试
> 1. 功能测试（FUNC）：验证完整业务流程
> 2. 并发测试（CONC）：验证多人同时使用时的数据隔离和稳定性
>
> 涉及文件：
> - 新建 `backend/tests/intake/conftest.py`
> - 新建 `backend/tests/intake/test_func.py`
> - 新建 `backend/tests/intake/test_concurrent.py`
>
> 复用：`tests/concurrent/conftest.py` 已有的 `op_users`、`run_concurrent`、`admin_token` fixtures

---

## 测试用例清单

### 功能测试（FUNC）

| 用例 ID | 描述 |
|---------|------|
| FUNC-001 | 获取题目列表：返回 24 道题，含必要字段 |
| FUNC-002 | 完整 KOL 对话流程：创建链接 → 回答问题 → bridge 过渡语 → 提交 → 轮询报告 |
| FUNC-003 | bridge 过渡语不含问句（不以？结尾） |
| FUNC-004 | 必填题输入「跳过」时 bridge 正常处理（不报错） |
| FUNC-005 | multi_collect 题型：bridge 携带 is_multi_collect=true 和 collect_count 正常返回 |
| FUNC-006 | 最后一题 bridge：is_last_question=true 时返回收尾语 |
| FUNC-007 | 链接过期后 bridge 报 LINK_EXPIRED |
| FUNC-008 | 运营直发会话：start → bridge → submit → status 完整流程 |
| FUNC-009 | 运营直发下载：status=ready 后 ?token= 参数鉴权下载成功 |
| FUNC-010 | 重复提交同一链接返回 409 VALIDATION_ERROR |

### 并发测试（CONC）

| 用例 ID | 描述 |
|---------|------|
| CONC-001 | 20 人同时调用 GET /intake/questions — 全部 200，数据一致 |
| CONC-002 | 10 个链接同时调用 bridge — 全部返回过渡语，无串扰 |
| CONC-003 | 5 个运营同时创建直发会话 — session 互相隔离，operator_id 正确 |
| CONC-004 | 运营 A 的 session_id 被运营 B 访问 — 全部 RESOURCE_NOT_FOUND |
| CONC-005 | 10 个链接同时提交 — 全部触发报告生成，report_status=generating |

---

## 实现参考

### intake/conftest.py

```python
"""
kol-intake 测试公共 fixtures
"""
import asyncio
import os
import time
import httpx
import asyncpg
import pytest

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
ADMIN_USER = os.getenv("TEST_ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("TEST_ADMIN_PASS", "Admin@123456")
DB_URL = os.getenv("TEST_DB_URL", "postgresql://postgres:admin123@localhost:5432/mcn_m1")


async def _admin_token() -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{BASE_URL}/api/auth/login",
                                 json={"username": ADMIN_USER, "password": ADMIN_PASS})
        return resp.json()["data"]["access_token"]


async def _operator_token() -> dict:
    """创建一个临时 operator，返回 {user_id, token}"""
    admin = await _admin_token()
    async with httpx.AsyncClient(timeout=30) as client:
        # 创建用户
        resp = await client.post(f"{BASE_URL}/api/admin/users",
            json={"username": "intake_test_op", "real_name": "测试运营", "role": "operator"},
            headers={"Authorization": f"Bearer {admin}"})
        user_id = resp.json()["data"]["id"]
        # 登录改密
        token1 = (await client.post(f"{BASE_URL}/api/auth/login",
            json={"username": "intake_test_op", "password": "Mcn@123"})).json()["data"]["access_token"]
        await client.post(f"{BASE_URL}/api/auth/change-password",
            json={"old_password": "Mcn@123", "new_password": "Test@9999", "confirm_password": "Test@9999"},
            headers={"Authorization": f"Bearer {token1}"})
        token = (await client.post(f"{BASE_URL}/api/auth/login",
            json={"username": "intake_test_op", "password": "Test@9999"})).json()["data"]["access_token"]
    return {"user_id": user_id, "token": token}


@pytest.fixture(scope="module")
async def op_token():
    data = await _operator_token()
    yield data
    # teardown
    admin = await _admin_token()
    async with httpx.AsyncClient(timeout=30) as client:
        await client.delete(f"{BASE_URL}/api/admin/users/{data['user_id']}",
                            headers={"Authorization": f"Bearer {admin}"})


@pytest.fixture(scope="module")
async def intake_link(op_token):
    """创建一条测试用分享链接，返回 token"""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{BASE_URL}/api/operator/intake/links",
            json={"kol_name": "测试红人", "expire_hours": 24},
            headers={"Authorization": f"Bearer {op_token['token']}"})
        assert resp.json()["success"]
        return resp.json()["data"]["token"]
```

### test_func.py（关键用例示意）

```python
@pytest.mark.asyncio
async def test_func_001_get_questions():
    """FUNC-001：GET /api/intake/questions 返回 24 道题"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{BASE_URL}/api/intake/questions")
    data = resp.json()
    assert data["success"]
    questions = data["data"]
    assert len(questions) == 24
    # 验证字段完整
    required_fields = {"id", "order_num", "category", "question_text", "question_type", "is_required"}
    for q in questions:
        assert required_fields.issubset(q.keys()), f"题目缺字段: {q}"


@pytest.mark.asyncio
async def test_func_003_bridge_no_question_mark(intake_link):
    """FUNC-003：bridge 过渡语不以问号结尾"""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BASE_URL}/api/intake/{intake_link}/bridge",
            json={
                "user_answer": "我叫小花",
                "question_text": "你希望粉丝怎么叫你？",
                "next_question_text": "你的抖音账号名叫什么？",
                "is_last_question": False,
            }
        )
    data = resp.json()
    assert data["success"]
    reply = data["data"]["reply"]
    if reply:  # reply="" 降级时不检查
        assert not reply.strip().endswith("？"), f"过渡语不应以问号结尾: {reply}"
        assert not reply.strip().endswith("?"),  f"过渡语不应以问号结尾: {reply}"


@pytest.mark.asyncio
async def test_func_007_expired_link_bridge():
    """FUNC-007：过期链接调用 bridge 返回 LINK_EXPIRED"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{BASE_URL}/api/intake/invalid_token_xxx/bridge",
            json={"user_answer": "test", "question_text": "test"}
        )
    assert resp.status_code in (404, 410)
```

### test_concurrent.py（关键用例示意）

```python
@pytest.mark.asyncio
async def test_conc_001_questions_concurrent():
    """CONC-001：20 人同时获取题目列表，全部 200 且数据一致"""
    async with httpx.AsyncClient(timeout=30) as client:
        coros = [client.get(f"{BASE_URL}/api/intake/questions") for _ in range(20)]
        results = await asyncio.gather(*coros)

    assert all(r.status_code == 200 for r in results)
    # 所有人拿到的题目数量一致
    counts = [len(r.json()["data"]) for r in results]
    assert len(set(counts)) == 1, f"题目数量不一致: {counts}"


@pytest.mark.asyncio
async def test_conc_004_session_isolation(op_users):
    """CONC-004：运营 A 的 session 被运营 B 访问 — RESOURCE_NOT_FOUND"""
    # op_0 创建会话
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{BASE_URL}/api/operator/intake/direct/start",
            json={}, headers={"Authorization": f"Bearer {op_users[0]['token']}"})
        session_id = resp.json()["data"]["session_id"]

        # op_1 ~ op_4 尝试访问 op_0 的 session
        coros = [
            client.get(f"{BASE_URL}/api/operator/intake/direct/{session_id}/status",
                       headers={"Authorization": f"Bearer {op_users[i]['token']}"})
            for i in range(1, 5)
        ]
        results = await asyncio.gather(*coros)

    for r in results:
        assert r.json().get("code") == "RESOURCE_NOT_FOUND"
```

---

## 运行方式

```bash
cd backend
source .venv/bin/activate

# 功能测试
pytest tests/intake/test_func.py -v

# 并发测试
pytest tests/intake/test_concurrent.py -v

# 全部跑
pytest tests/intake/ -v

# 环境变量（测试服时）
TEST_BASE_URL=http://服务器IP:8000 \
TEST_DB_URL=postgresql://mcn_user:密码@localhost:5432/mcn_db \
pytest tests/intake/ -v
```

---

## 验收标准

| 类型 | 通过条件 |
|------|----------|
| 功能测试 | FUNC-001 ~ FUNC-010 全部通过 |
| 并发测试 | CONC-001 ~ CONC-005 全部通过，无数据串扰 |
| bridge 语气 | 所有 bridge 响应不以「？」结尾 |
| 会话隔离 | 跨运营访问全部 RESOURCE_NOT_FOUND |
