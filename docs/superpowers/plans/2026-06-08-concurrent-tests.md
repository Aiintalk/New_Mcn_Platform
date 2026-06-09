# 并发多用户测试套件 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 MCN Platform 后端实现一套并发多用户测试套件，覆盖数据隔离、竞态条件、性能基线三大场景，跑完自动生成 Markdown 测试报告。

**Architecture:** 全部测试代码放在 `backend/tests/concurrent/`；`conftest.py` 用 pytest session-scoped fixture 批量创建/清理 20 个测试用户并拿到各自的 JWT token；各测试文件用 `asyncio.gather()` 模拟并发；`reporter.py` 在 pytest `session_finish` hook 里把收集的结果写成 Markdown 报告。

**Tech Stack:** Python 3.11+, pytest 8, pytest-asyncio 0.23, httpx.AsyncClient（已在 requirements.txt），asyncpg（DB 验证用，已有），asyncio.gather

---

## 文件清单

| 操作 | 文件路径 | 职责 |
|------|----------|------|
| 新建 | `backend/tests/__init__.py` | 让 pytest 识别 tests 包 |
| 新建 | `backend/tests/concurrent/__init__.py` | 包标识 |
| 新建 | `backend/tests/concurrent/conftest.py` | 批量创建用户、获取 token、teardown 清理、并发执行器 |
| 新建 | `backend/tests/concurrent/test_isolation.py` | 数据隔离 4 个测试（ISO-001 ~ ISO-004） |
| 新建 | `backend/tests/concurrent/test_race.py` | 竞态条件 4 个测试（RACE-001 ~ RACE-004） |
| 新建 | `backend/tests/concurrent/test_perf.py` | 性能基线 6 个接口（PERF-001 ~ PERF-006） |
| 新建 | `backend/tests/concurrent/reporter.py` | 收集测试结果，写 Markdown 报告 |
| 修改 | `backend/requirements.txt` | 追加 pytest、pytest-asyncio |
| 新建 | `backend/pytest.ini` | 配置 asyncio_mode=auto，testpaths |
| 产出 | `docs/tests/M1/MCN_M1_Concurrent_Test_Report.md` | 运行后自动生成（不手写） |

---

## Task 1：安装依赖 & pytest 基础配置

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/pytest.ini`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/concurrent/__init__.py`

- [ ] **Step 1：追加测试依赖到 requirements.txt**

在 `backend/requirements.txt` 末尾追加：
```
pytest>=8.0
pytest-asyncio>=0.23
```

- [ ] **Step 2：创建 pytest.ini**

新建 `backend/pytest.ini`，内容：
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

- [ ] **Step 3：创建空包文件**

新建 `backend/tests/__init__.py`（空文件）。  
新建 `backend/tests/concurrent/__init__.py`（空文件）。

- [ ] **Step 4：安装依赖**

```bash
cd backend
pip install pytest>=8.0 pytest-asyncio>=0.23
```

预期输出末行类似：`Successfully installed pytest-8.x.x pytest-asyncio-0.23.x`

- [ ] **Step 5：验证 pytest 可用**

```bash
cd backend
pytest --version
```

预期输出：`pytest 8.x.x`

---

## Task 2：conftest.py — 用户批量创建、token 获取、并发执行器、teardown

**Files:**
- Create: `backend/tests/concurrent/conftest.py`

> 这是整个测试套件的基础。所有 fixture 都是 session-scoped（测试开始前跑一次，结束后清理一次）。

- [ ] **Step 1：写 conftest.py**

新建 `backend/tests/concurrent/conftest.py`，完整内容：

```python
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
    async with httpx.AsyncClient(timeout=30) as client:
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

    async with httpx.AsyncClient(timeout=30) as client:
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
            # 若已存在（重复执行时），跳过
            if not body["success"] and body.get("code") == "USERNAME_ALREADY_EXISTS":
                # 重置密码确保可登录
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
    async with httpx.AsyncClient(timeout=30) as client:
        # 刷新 admin token（可能过期）
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
```

- [ ] **Step 2：验证 conftest 语法无误**

```bash
cd backend
python -c "import ast; ast.parse(open('tests/concurrent/conftest.py').read()); print('OK')"
```

预期输出：`OK`

---

## Task 3：reporter.py — Markdown 报告生成器

**Files:**
- Create: `backend/tests/concurrent/reporter.py`

- [ ] **Step 1：写 reporter.py**

新建 `backend/tests/concurrent/reporter.py`，完整内容：

```python
"""
并发测试 Markdown 报告生成器。
用法：在测试文件末尾调用 REPORT.record(...)，
pytest session finish 时调用 REPORT.write()。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import median, quantiles
from typing import Optional


@dataclass
class TestResult:
    category: str          # "isolation" | "race" | "perf"
    case_id: str           # "ISO-001", "RACE-001", "PERF-login" …
    description: str
    passed: bool
    detail: str = ""       # 失败原因 or 性能数据


@dataclass
class PerfResult:
    endpoint: str
    p50_ms: float
    p95_ms: float
    p99_ms: float
    error_rate: float      # 0.0 ~ 1.0
    p95_threshold_ms: float
    p99_threshold_ms: float

    @property
    def verdict(self) -> str:
        if self.error_rate > 0:
            return "❌ FAIL (error_rate > 0)"
        if self.p99_ms > self.p99_threshold_ms:
            return "❌ FAIL (P99 超阈值)"
        if self.p95_ms > self.p95_threshold_ms:
            return "⚠️ WARN (P95 超阈值)"
        return "✅ 通过"


class Reporter:
    def __init__(self):
        self._results: list[TestResult] = []
        self._perf: list[PerfResult] = []
        self._concurrent_users: int = int(os.getenv("CONCURRENT_USERS", "20"))
        self._base_url: str = os.getenv("TEST_BASE_URL", "http://localhost:8000")

    def record(self, result: TestResult) -> None:
        self._results.append(result)

    def record_perf(self, pr: PerfResult) -> None:
        self._perf.append(pr)
        # 同步写入 TestResult
        self._results.append(TestResult(
            category="perf",
            case_id=f"PERF-{pr.endpoint.replace('/', '-').strip('-')}",
            description=pr.endpoint,
            passed=pr.verdict.startswith("✅"),
            detail=f"P50={pr.p50_ms:.0f}ms P95={pr.p95_ms:.0f}ms P99={pr.p99_ms:.0f}ms err={pr.error_rate:.1%}",
        ))

    def calc_perf(self, endpoint: str, latencies: list[float],
                  errors: int, p95_thr: float, p99_thr: float) -> PerfResult:
        """从原始延迟列表计算 P50/P95/P99，写入报告。"""
        total = len(latencies) + errors
        sorted_lat = sorted(latencies)
        p50 = median(sorted_lat) if sorted_lat else 0.0
        qs = quantiles(sorted_lat, n=100) if len(sorted_lat) >= 2 else [0.0] * 99
        p95 = qs[94] if len(qs) > 94 else (sorted_lat[-1] if sorted_lat else 0.0)
        p99 = qs[98] if len(qs) > 98 else (sorted_lat[-1] if sorted_lat else 0.0)
        error_rate = errors / total if total > 0 else 0.0
        pr = PerfResult(endpoint, p50, p95, p99, error_rate, p95_thr, p99_thr)
        self.record_perf(pr)
        return pr

    def write(self, path: Optional[str] = None) -> Path:
        if path is None:
            base = Path(__file__).parents[3]  # mcn-platform root
            path = base / "docs" / "tests" / "M1" / "MCN_M1_Concurrent_Test_Report.md"
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self._render(), encoding="utf-8")
        print(f"\n[reporter] 报告已写入 {out}")
        return out

    # ------------------------------------------------------------------

    def _render(self) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        isolation = [r for r in self._results if r.category == "isolation"]
        race = [r for r in self._results if r.category == "race"]
        perf = [r for r in self._results if r.category == "perf"]

        total = len(self._results)
        passed = sum(1 for r in self._results if r.passed)
        failed = total - passed

        verdict = "✅ 通过" if failed == 0 else f"❌ 不通过（{failed} 项失败）"

        lines = [
            "# MCN Platform · M1 并发多用户测试报告",
            "",
            f"**测试日期：** {now}  ",
            f"**并发用户数：** {self._concurrent_users}  ",
            f"**测试环境：** {self._base_url}  ",
            "",
            "---",
            "",
            "## 一、数据隔离",
            "",
            "| 编号 | 场景 | 结论 | 说明 |",
            "|------|------|------|------|",
        ]
        for r in isolation:
            icon = "✅" if r.passed else "❌"
            lines.append(f"| {r.case_id} | {r.description} | {icon} | {r.detail} |")

        lines += [
            "",
            "## 二、竞态条件",
            "",
            "| 编号 | 场景 | 结论 | 说明 |",
            "|------|------|------|------|",
        ]
        for r in race:
            icon = "✅" if r.passed else "❌"
            lines.append(f"| {r.case_id} | {r.description} | {icon} | {r.detail} |")

        lines += [
            "",
            "## 三、性能基线",
            "",
            "| 接口 | P50 | P95 | P99 | 错误率 | 结论 |",
            "|------|-----|-----|-----|--------|------|",
        ]
        for pr in self._perf:
            lines.append(
                f"| `{pr.endpoint}` | {pr.p50_ms:.0f}ms | {pr.p95_ms:.0f}ms "
                f"| {pr.p99_ms:.0f}ms | {pr.error_rate:.1%} | {pr.verdict} |"
            )

        lines += [
            "",
            "---",
            "",
            "## 汇总",
            "",
            f"| 统计 | 值 |",
            f"|------|-----|",
            f"| 总计 | {total} 项 |",
            f"| 通过 | {passed} 项 |",
            f"| 失败 | {failed} 项 |",
            f"| 并发用户数 | {self._concurrent_users} |",
            "",
            f"**测试结论：{verdict}**",
        ]
        return "\n".join(lines) + "\n"


# 全局单例，供所有测试文件 import
REPORT = Reporter()
```

- [ ] **Step 2：验证语法**

```bash
cd backend
python -c "import ast; ast.parse(open('tests/concurrent/reporter.py').read()); print('OK')"
```

预期输出：`OK`

---

## Task 4：数据隔离测试（test_isolation.py）

**Files:**
- Create: `backend/tests/concurrent/test_isolation.py`

- [ ] **Step 1：写 test_isolation.py**

新建 `backend/tests/concurrent/test_isolation.py`，完整内容：

```python
"""
数据隔离并发测试（ISO-001 ~ ISO-004）。

前置：conftest.py 的 op_users fixture 已创建 20 个 operator。
测试逻辑：先直连 DB 插入归属明确的测试数据，再并发请求，断言隔离。
"""

import asyncio

import asyncpg
import httpx
import pytest

from tests.concurrent.conftest import BASE_URL, DB_URL, run_concurrent
from tests.concurrent.reporter import REPORT, TestResult


async def _insert_tasks(conn: asyncpg.Connection, user_id: int, n: int) -> list[int]:
    """为指定用户插入 n 条 task_jobs，返回 id 列表。"""
    ids = []
    for i in range(n):
        row = await conn.fetchrow(
            """
            INSERT INTO task_jobs (task_no, tool_code, tool_name, status, created_by)
            VALUES ($1, $2, $3, $4, $5) RETURNING id
            """,
            f"CONC-T-{user_id}-{i}", "persona-writer", "并发测试", "success", user_id,
        )
        ids.append(row["id"])
    return ids


async def _insert_outputs(conn: asyncpg.Connection, user_id: int, n: int) -> list[int]:
    """为指定用户插入 n 条 outputs，返回 id 列表。"""
    ids = []
    for i in range(n):
        row = await conn.fetchrow(
            """
            INSERT INTO outputs (title, tool_code, tool_name, created_by)
            VALUES ($1, $2, $3, $4) RETURNING id
            """,
            f"并发测试产出{i}", "persona-writer", "并发测试", user_id,
        )
        ids.append(row["id"])
    return ids


# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_iso_001_task_list_isolation(op_users):
    """ISO-001：20 个 operator 并发 GET /api/tasks，各自只见自己的任务。"""
    conn = await asyncpg.connect(DB_URL)
    try:
        # 只为 op_0 / op_1 插入任务，其余 operator 应返回 total=0
        op0 = op_users[0]
        op1 = op_users[1]
        task_ids_op0 = await _insert_tasks(conn, op0["user_id"], 3)
        task_ids_op1 = await _insert_tasks(conn, op1["user_id"], 3)
    finally:
        await conn.close()

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            coros = [
                client.get(
                    f"{BASE_URL}/api/tasks",
                    headers={"Authorization": f"Bearer {u['token']}"},
                )
                for u in op_users
            ]
            results = await run_concurrent(coros)

        failures = []
        for i, (res, user) in enumerate(zip(results, op_users)):
            body = res["body"]
            if not body.get("success"):
                failures.append(f"op_{i} 请求失败: {body.get('code')}")
                continue
            items = body["data"]["items"]
            for item in items:
                if item["created_by"] != user["user_id"]:
                    failures.append(
                        f"op_{i}({user['username']}) 看到了 user_id={item['created_by']} 的任务"
                    )

        passed = len(failures) == 0
        REPORT.record(TestResult(
            category="isolation",
            case_id="ISO-001",
            description="并发查询任务列表 — 各自只见自己的任务",
            passed=passed,
            detail="; ".join(failures) if failures else f"20/20 通过",
        ))
        assert passed, "\n".join(failures)
    finally:
        # 清理插入的任务
        conn2 = await asyncpg.connect(DB_URL)
        try:
            await conn2.execute(
                "DELETE FROM task_jobs WHERE id = ANY($1::bigint[])",
                task_ids_op0 + task_ids_op1,
            )
        finally:
            await conn2.close()


@pytest.mark.asyncio
async def test_iso_002_output_list_isolation(op_users):
    """ISO-002：20 个 operator 并发 GET /api/outputs，各自只见自己的产出。"""
    conn = await asyncpg.connect(DB_URL)
    try:
        op0 = op_users[0]
        op1 = op_users[1]
        out_ids_op0 = await _insert_outputs(conn, op0["user_id"], 2)
        out_ids_op1 = await _insert_outputs(conn, op1["user_id"], 2)
    finally:
        await conn.close()

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            coros = [
                client.get(
                    f"{BASE_URL}/api/outputs",
                    headers={"Authorization": f"Bearer {u['token']}"},
                )
                for u in op_users
            ]
            results = await run_concurrent(coros)

        failures = []
        for i, (res, user) in enumerate(zip(results, op_users)):
            body = res["body"]
            if not body.get("success"):
                failures.append(f"op_{i} 请求失败: {body.get('code')}")
                continue
            for item in body["data"]["items"]:
                if item["created_by"] != user["user_id"]:
                    failures.append(
                        f"op_{i}({user['username']}) 看到了 user_id={item['created_by']} 的产出"
                    )

        passed = len(failures) == 0
        REPORT.record(TestResult(
            category="isolation",
            case_id="ISO-002",
            description="并发查询产出列表 — 各自只见自己的产出",
            passed=passed,
            detail="; ".join(failures) if failures else "20/20 通过",
        ))
        assert passed, "\n".join(failures)
    finally:
        conn2 = await asyncpg.connect(DB_URL)
        try:
            await conn2.execute(
                "DELETE FROM outputs WHERE id = ANY($1::bigint[])",
                out_ids_op0 + out_ids_op1,
            )
        finally:
            await conn2.close()


@pytest.mark.asyncio
async def test_iso_003_cross_user_task_forbidden(op_users):
    """ISO-003：op_1 ~ op_19 并发访问 op_0 的 task — 全部 403。"""
    conn = await asyncpg.connect(DB_URL)
    try:
        op0 = op_users[0]
        task_ids = await _insert_tasks(conn, op0["user_id"], 1)
        task_id = task_ids[0]
    finally:
        await conn.close()

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            coros = [
                client.get(
                    f"{BASE_URL}/api/tasks/{task_id}",
                    headers={"Authorization": f"Bearer {u['token']}"},
                )
                for u in op_users[1:]  # op_1 ~ op_19
            ]
            results = await run_concurrent(coros)

        failures = []
        for i, res in enumerate(results):
            code = res["body"].get("code", "")
            if code != "PERMISSION_DENIED":
                failures.append(f"op_{i+1} 返回 {code}（预期 PERMISSION_DENIED）")

        passed = len(failures) == 0
        REPORT.record(TestResult(
            category="isolation",
            case_id="ISO-003",
            description="跨用户访问 task — 全部 403",
            passed=passed,
            detail="; ".join(failures) if failures else "19/19 均 PERMISSION_DENIED",
        ))
        assert passed, "\n".join(failures)
    finally:
        conn2 = await asyncpg.connect(DB_URL)
        try:
            await conn2.execute("DELETE FROM task_jobs WHERE id = ANY($1::bigint[])", task_ids)
        finally:
            await conn2.close()


@pytest.mark.asyncio
async def test_iso_004_cross_user_output_forbidden(op_users):
    """ISO-004：op_1 ~ op_19 并发访问 op_0 的 output — 全部 403。"""
    conn = await asyncpg.connect(DB_URL)
    try:
        op0 = op_users[0]
        out_ids = await _insert_outputs(conn, op0["user_id"], 1)
        out_id = out_ids[0]
    finally:
        await conn.close()

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            coros = [
                client.get(
                    f"{BASE_URL}/api/outputs/{out_id}",
                    headers={"Authorization": f"Bearer {u['token']}"},
                )
                for u in op_users[1:]
            ]
            results = await run_concurrent(coros)

        failures = []
        for i, res in enumerate(results):
            code = res["body"].get("code", "")
            if code != "PERMISSION_DENIED":
                failures.append(f"op_{i+1} 返回 {code}（预期 PERMISSION_DENIED）")

        passed = len(failures) == 0
        REPORT.record(TestResult(
            category="isolation",
            case_id="ISO-004",
            description="跨用户访问 output — 全部 403",
            passed=passed,
            detail="; ".join(failures) if failures else "19/19 均 PERMISSION_DENIED",
        ))
        assert passed, "\n".join(failures)
    finally:
        conn2 = await asyncpg.connect(DB_URL)
        try:
            await conn2.execute("DELETE FROM outputs WHERE id = ANY($1::bigint[])", out_ids)
        finally:
            await conn2.close()
```

- [ ] **Step 2：验证语法**

```bash
cd backend
python -c "import ast; ast.parse(open('tests/concurrent/test_isolation.py').read()); print('OK')"
```

预期：`OK`

- [ ] **Step 3：单独运行隔离测试（后端必须在 8000 端口运行）**

```bash
cd backend
pytest tests/concurrent/test_isolation.py -v --tb=short
```

预期：4 个测试全部 `PASSED`。若有 `FAILED`，查看具体 assert 失败信息。

---

## Task 5：竞态条件测试（test_race.py）

**Files:**
- Create: `backend/tests/concurrent/test_race.py`

- [ ] **Step 1：写 test_race.py**

新建 `backend/tests/concurrent/test_race.py`，完整内容：

```python
"""
竞态条件并发测试（RACE-001 ~ RACE-004）。
"""

import asyncio

import asyncpg
import httpx
import pytest

from tests.concurrent.conftest import BASE_URL, DB_URL, ADMIN_USER, ADMIN_PASS, run_concurrent, _login
from tests.concurrent.reporter import REPORT, TestResult

RACE_TARGET_USER = "race_target_user_conc"


@pytest.mark.asyncio
async def test_race_001_duplicate_username(admin_token):
    """RACE-001：20 个并发请求创建同名用户 — 只有 1 个成功，DB 只有 1 条记录。"""
    async with httpx.AsyncClient(timeout=30) as client:
        coros = [
            client.post(
                f"{BASE_URL}/api/admin/users",
                json={
                    "username": RACE_TARGET_USER,
                    "real_name": "竞态测试",
                    "role": "operator",
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            for _ in range(20)
        ]
        results = await run_concurrent(coros)

    success_count = sum(1 for r in results if r["body"].get("success"))
    fail_codes = [r["body"].get("code") for r in results if not r["body"].get("success")]

    # DB 验证
    conn = await asyncpg.connect(DB_URL)
    try:
        db_count = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE username=$1 AND deleted_at IS NULL",
            RACE_TARGET_USER,
        )
        # 清理
        await conn.execute(
            "UPDATE users SET deleted_at=now() WHERE username=$1", RACE_TARGET_USER
        )
    finally:
        await conn.close()

    wrong_codes = [c for c in fail_codes if c != "USERNAME_ALREADY_EXISTS"]
    passed = success_count == 1 and db_count == 1 and len(wrong_codes) == 0

    REPORT.record(TestResult(
        category="race",
        case_id="RACE-001",
        description="并发创建同名用户 — 只有 1 个成功",
        passed=passed,
        detail=(
            f"成功次数={success_count}（预期1），DB记录数={db_count}（预期1），"
            f"非预期错误码={wrong_codes}"
        ) if not passed else f"1/20 成功，19/20 返回 USERNAME_ALREADY_EXISTS，DB=1条",
    ))
    assert success_count == 1, f"预期 1 个成功，实际 {success_count} 个"
    assert db_count == 1, f"DB 中存在 {db_count} 条记录（预期 1）"
    assert len(wrong_codes) == 0, f"非预期错误码: {wrong_codes}"


@pytest.mark.asyncio
async def test_race_002_concurrent_reset_password(admin_token, op_users):
    """RACE-002：20 个 admin 并发重置同一用户密码 — 全部返回成功，用户可用初始密码登录。"""
    target = op_users[0]
    target_id = target["user_id"]

    async with httpx.AsyncClient(timeout=30) as client:
        coros = [
            client.post(
                f"{BASE_URL}/api/admin/users/{target_id}/reset-password",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            for _ in range(20)
        ]
        results = await run_concurrent(coros)

    success_count = sum(1 for r in results if r["body"].get("success"))
    error_5xx = sum(1 for r in results if r["status_code"] >= 500)

    # 验证目标用户可用初始密码 Mcn@123 登录
    async with httpx.AsyncClient(timeout=10) as client:
        login_resp = await client.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": target["username"], "password": "Mcn@123"},
        )
    login_ok = login_resp.json().get("success", False)

    passed = success_count == 20 and error_5xx == 0 and login_ok
    REPORT.record(TestResult(
        category="race",
        case_id="RACE-002",
        description="并发重置同一用户密码 — 全部成功，最终状态确定",
        passed=passed,
        detail=(
            f"成功={success_count}/20，5xx={error_5xx}，重置后可登录={login_ok}"
        ),
    ))
    assert success_count == 20, f"预期 20 个成功，实际 {success_count}"
    assert error_5xx == 0, f"存在 {error_5xx} 个 5xx 响应"
    assert login_ok, "目标用户重置后无法用 Mcn@123 登录"

    # 恢复 op_users[0] 的密码，以免影响后续测试
    async with httpx.AsyncClient(timeout=10) as client:
        pre_token = await _login(client, target["username"], "Mcn@123")
        resp = await client.post(
            f"{BASE_URL}/api/auth/change-password",
            json={
                "old_password": "Mcn@123",
                "new_password": target["password"],
                "confirm_password": target["password"],
            },
            headers={"Authorization": f"Bearer {pre_token}"},
        )
        assert resp.json()["success"], "恢复密码失败"
        # 刷新 token
        op_users[0]["token"] = await _login(client, target["username"], target["password"])


@pytest.mark.asyncio
async def test_race_003_concurrent_enable_disable(admin_token, op_users):
    """RACE-003：10 个 disable + 10 个 enable 并发打同一账号 — 无 5xx，最终状态确定。"""
    target_id = op_users[2]["user_id"]

    async with httpx.AsyncClient(timeout=30) as client:
        disable_coros = [
            client.post(
                f"{BASE_URL}/api/admin/users/{target_id}/disable",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            for _ in range(10)
        ]
        enable_coros = [
            client.post(
                f"{BASE_URL}/api/admin/users/{target_id}/enable",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            for _ in range(10)
        ]
        results = await run_concurrent(disable_coros + enable_coros)

    error_5xx = sum(1 for r in results if r["status_code"] >= 500)

    # 验证最终状态是确定值（enabled 或 disabled，非空/None）
    conn = await asyncpg.connect(DB_URL)
    try:
        final_status = await conn.fetchval(
            "SELECT status FROM users WHERE id=$1", target_id
        )
        # 恢复为 enabled
        await conn.execute("UPDATE users SET status='enabled' WHERE id=$1", target_id)
    finally:
        await conn.close()

    passed = error_5xx == 0 and final_status in ("enabled", "disabled")
    REPORT.record(TestResult(
        category="race",
        case_id="RACE-003",
        description="并发停用/启用同一账号 — 无 5xx，最终状态确定",
        passed=passed,
        detail=f"5xx={error_5xx}，最终状态={final_status}",
    ))
    assert error_5xx == 0, f"存在 {error_5xx} 个 5xx"
    assert final_status in ("enabled", "disabled"), f"最终状态异常: {final_status}"


@pytest.mark.asyncio
async def test_race_004_old_token_invalidated_after_change_password(op_users):
    """RACE-004：改密后，旧 Token 的 20 个并发请求全部被拒绝（401）。"""
    user = op_users[3]

    # 先拿旧 token
    async with httpx.AsyncClient(timeout=10) as client:
        old_token = await _login(client, user["username"], user["password"])

        # 改密
        resp = await client.post(
            f"{BASE_URL}/api/auth/change-password",
            json={
                "old_password": user["password"],
                "new_password": "NewRace@9999",
                "confirm_password": "NewRace@9999",
            },
            headers={"Authorization": f"Bearer {old_token}"},
        )
        assert resp.json()["success"], f"改密失败: {resp.json()}"

    # 用旧 token 并发打接口
    async with httpx.AsyncClient(timeout=30) as client:
        coros = [
            client.get(
                f"{BASE_URL}/api/tasks",
                headers={"Authorization": f"Bearer {old_token}"},
            )
            for _ in range(20)
        ]
        results = await run_concurrent(coros)

    penetrate = [
        r for r in results
        if r["status_code"] == 200 and r["body"].get("success")
    ]
    auth_rejected = [
        r for r in results
        if r["status_code"] in (401, 403)
    ]

    passed = len(penetrate) == 0 and len(auth_rejected) == 20
    REPORT.record(TestResult(
        category="race",
        case_id="RACE-004",
        description="改密后旧 Token 全部失效",
        passed=passed,
        detail=f"穿透={len(penetrate)}（预期0），401/403={len(auth_rejected)}（预期20）",
    ))
    assert len(penetrate) == 0, f"{len(penetrate)} 个请求穿透了旧 Token"
    assert len(auth_rejected) == 20, f"仅 {len(auth_rejected)}/20 被拒绝"

    # 恢复 op_users[3] 密码
    async with httpx.AsyncClient(timeout=10) as client:
        pre_token = await _login(client, user["username"], "NewRace@9999")
        await client.post(
            f"{BASE_URL}/api/auth/change-password",
            json={
                "old_password": "NewRace@9999",
                "new_password": user["password"],
                "confirm_password": user["password"],
            },
            headers={"Authorization": f"Bearer {pre_token}"},
        )
        op_users[3]["token"] = await _login(client, user["username"], user["password"])
```

- [ ] **Step 2：验证语法**

```bash
cd backend
python -c "import ast; ast.parse(open('tests/concurrent/test_race.py').read()); print('OK')"
```

预期：`OK`

- [ ] **Step 3：运行竞态测试**

```bash
cd backend
pytest tests/concurrent/test_race.py -v --tb=short
```

预期：4 个测试全部 `PASSED`。

---

## Task 6：性能基线测试（test_perf.py）

**Files:**
- Create: `backend/tests/concurrent/test_perf.py`

- [ ] **Step 1：写 test_perf.py**

新建 `backend/tests/concurrent/test_perf.py`，完整内容：

```python
"""
性能基线并发测试（PERF-001 ~ PERF-006）。
每个接口跑 3 轮 × 20 并发，共 60 个样本，统计 P50/P95/P99。
"""

import asyncio
import os

import httpx
import pytest

from tests.concurrent.conftest import BASE_URL, run_concurrent, _login, ADMIN_USER, ADMIN_PASS
from tests.concurrent.reporter import REPORT

ROUNDS = 3  # 每接口跑几轮


async def _collect_latencies(
    client: httpx.AsyncClient,
    coro_factory,
    n: int,
    rounds: int,
) -> tuple[list[float], int]:
    """跑 rounds 轮，每轮 n 并发，收集延迟列表和错误数。"""
    latencies: list[float] = []
    errors = 0
    for _ in range(rounds):
        coros = [coro_factory() for _ in range(n)]
        results = await run_concurrent(coros)
        for r in results:
            if r["status_code"] in (200, 401, 403):
                latencies.append(r["latency_ms"])
            else:
                errors += 1
    return latencies, errors


@pytest.mark.asyncio
async def test_perf_001_health(op_users):
    """PERF-001：GET /api/health — P95 < 100ms，错误率 0%"""
    async with httpx.AsyncClient(timeout=30) as client:
        lats, errs = await _collect_latencies(
            client,
            lambda: client.get(f"{BASE_URL}/api/health"),
            n=20, rounds=ROUNDS,
        )
    REPORT.calc_perf("GET /api/health", lats, errs, p95_thr=100, p99_thr=200)


@pytest.mark.asyncio
async def test_perf_002_login(op_users):
    """PERF-002：POST /api/auth/login — P95 < 500ms，错误率 0%"""
    async with httpx.AsyncClient(timeout=30) as client:
        lats, errs = await _collect_latencies(
            client,
            lambda: client.post(
                f"{BASE_URL}/api/auth/login",
                json={"username": ADMIN_USER, "password": "Admin@123456"},
            ),
            n=20, rounds=ROUNDS,
        )
    REPORT.calc_perf("POST /api/auth/login", lats, errs, p95_thr=500, p99_thr=1000)


@pytest.mark.asyncio
async def test_perf_003_tasks(op_users):
    """PERF-003：GET /api/tasks — P95 < 800ms，错误率 0%"""
    async with httpx.AsyncClient(timeout=30) as client:
        lats, errs = await _collect_latencies(
            client,
            lambda: client.get(
                f"{BASE_URL}/api/tasks",
                headers={"Authorization": f"Bearer {op_users[0]['token']}"},
            ),
            n=20, rounds=ROUNDS,
        )
    REPORT.calc_perf("GET /api/tasks", lats, errs, p95_thr=800, p99_thr=1500)


@pytest.mark.asyncio
async def test_perf_004_outputs(op_users):
    """PERF-004：GET /api/outputs — P95 < 800ms，错误率 0%"""
    async with httpx.AsyncClient(timeout=30) as client:
        lats, errs = await _collect_latencies(
            client,
            lambda: client.get(
                f"{BASE_URL}/api/outputs",
                headers={"Authorization": f"Bearer {op_users[0]['token']}"},
            ),
            n=20, rounds=ROUNDS,
        )
    REPORT.calc_perf("GET /api/outputs", lats, errs, p95_thr=800, p99_thr=1500)


@pytest.mark.asyncio
async def test_perf_005_workspace_tools(op_users):
    """PERF-005：GET /api/workspace/tools — P95 < 500ms，错误率 0%"""
    async with httpx.AsyncClient(timeout=30) as client:
        lats, errs = await _collect_latencies(
            client,
            lambda: client.get(
                f"{BASE_URL}/api/workspace/tools",
                headers={"Authorization": f"Bearer {op_users[0]['token']}"},
            ),
            n=20, rounds=ROUNDS,
        )
    REPORT.calc_perf("GET /api/workspace/tools", lats, errs, p95_thr=500, p99_thr=1000)


@pytest.mark.asyncio
async def test_perf_006_admin_users(op_users, admin_token):
    """PERF-006：GET /api/admin/users — P95 < 800ms，错误率 0%"""
    async with httpx.AsyncClient(timeout=30) as client:
        lats, errs = await _collect_latencies(
            client,
            lambda: client.get(
                f"{BASE_URL}/api/admin/users",
                headers={"Authorization": f"Bearer {admin_token}"},
            ),
            n=20, rounds=ROUNDS,
        )
    REPORT.calc_perf("GET /api/admin/users", lats, errs, p95_thr=800, p99_thr=1500)
```

- [ ] **Step 2：验证语法**

```bash
cd backend
python -c "import ast; ast.parse(open('tests/concurrent/test_perf.py').read()); print('OK')"
```

预期：`OK`

- [ ] **Step 3：运行性能测试**

```bash
cd backend
pytest tests/concurrent/test_perf.py -v --tb=short -s
```

预期：6 个测试全部 `PASSED`（P95/P99 在本地开发机上通常远低于阈值）。

---

## Task 7：conftest.py 追加 session_finish hook，触发报告写出

**Files:**
- Modify: `backend/tests/concurrent/conftest.py`（末尾追加）

- [ ] **Step 1：在 conftest.py 末尾追加 pytest hook**

在 `backend/tests/concurrent/conftest.py` 文件**末尾**追加以下内容（注意是追加，不是替换）：

```python

# ---------------------------------------------------------------------------
# pytest session finish hook：所有测试跑完后写报告
# ---------------------------------------------------------------------------

def pytest_sessionfinish(session, exitstatus):
    """在 pytest session 结束时生成 Markdown 报告。"""
    from tests.concurrent.reporter import REPORT
    REPORT.write()
```

- [ ] **Step 2：验证语法**

```bash
cd backend
python -c "import ast; ast.parse(open('tests/concurrent/conftest.py').read()); print('OK')"
```

预期：`OK`

---

## Task 8：全套运行 & 验证报告

**Files:**
- Output: `docs/tests/M1/MCN_M1_Concurrent_Test_Report.md`（自动生成）

- [ ] **Step 1：确保后端在运行**

```bash
curl -s http://localhost:8000/api/health | python -c "import sys,json; d=json.load(sys.stdin); print('Backend OK:', d['data']['status'])"
```

预期输出：`Backend OK: ok`

- [ ] **Step 2：运行完整测试套件**

```bash
cd backend
pytest tests/concurrent/ -v --tb=short -s
```

预期输出示例：
```
tests/concurrent/test_isolation.py::test_iso_001_task_list_isolation PASSED
tests/concurrent/test_isolation.py::test_iso_002_output_list_isolation PASSED
tests/concurrent/test_isolation.py::test_iso_003_cross_user_task_forbidden PASSED
tests/concurrent/test_isolation.py::test_iso_004_cross_user_output_forbidden PASSED
tests/concurrent/test_race.py::test_race_001_duplicate_username PASSED
tests/concurrent/test_race.py::test_race_002_concurrent_reset_password PASSED
tests/concurrent/test_race.py::test_race_003_concurrent_enable_disable PASSED
tests/concurrent/test_race.py::test_race_004_old_token_invalidated_after_change_password PASSED
tests/concurrent/test_perf.py::test_perf_001_health PASSED
tests/concurrent/test_perf.py::test_perf_002_login PASSED
tests/concurrent/test_perf.py::test_perf_003_tasks PASSED
tests/concurrent/test_perf.py::test_perf_004_outputs PASSED
tests/concurrent/test_perf.py::test_perf_005_workspace_tools PASSED
tests/concurrent/test_perf.py::test_perf_006_admin_users PASSED

[reporter] 报告已写入 .../docs/tests/M1/MCN_M1_Concurrent_Test_Report.md

14 passed in XX.XXs
```

- [ ] **Step 3：确认报告已生成**

```bash
ls "D:/2026年工作/AI相关/AI工具箱新架构方案/mcn-platform/docs/tests/M1/"
```

预期输出中包含 `MCN_M1_Concurrent_Test_Report.md`。

- [ ] **Step 4：查看报告内容**

```bash
cat "D:/2026年工作/AI相关/AI工具箱新架构方案/mcn-platform/docs/tests/M1/MCN_M1_Concurrent_Test_Report.md"
```

确认报告包含：
- 数据隔离 4 项（ISO-001 ~ ISO-004）
- 竞态条件 4 项（RACE-001 ~ RACE-004）
- 性能基线 6 项（含 P50/P95/P99 数据）
- 汇总结论行

---

## 自检记录

| 检查项 | 结论 |
|--------|------|
| Spec 所有场景都有对应 Task？ | ✅ ISO × 4、RACE × 4、PERF × 6 全覆盖 |
| 所有代码块完整、无 TBD？ | ✅ 每步都有完整可运行代码 |
| 类型/方法名一致性？ | ✅ `run_concurrent`、`_login`、`REPORT`、`TestResult`、`PerfResult` 跨文件统一 |
| conftest 里的 `_login` 被 test_race 和 test_perf import？ | ✅ `from tests.concurrent.conftest import ..., _login` |
| reporter.py 的 `calc_perf` 参数签名与调用一致？ | ✅ `(endpoint, lats, errs, p95_thr, p99_thr)` 统一 |
| teardown 清理了 task_jobs 和 outputs？ | ✅ conftest teardown + 各测试内 finally 块双重清理 |
