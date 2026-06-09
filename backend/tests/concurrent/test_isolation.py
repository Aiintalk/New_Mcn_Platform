"""
数据隔离并发测试（ISO-001 ~ ISO-004）。

前置：conftest.py 的 op_users fixture 已创建 20 个 operator。
测试逻辑：先直连 DB 插入归属明确的测试数据，再并发请求，断言隔离。
"""

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
            for item in body["data"]["items"]:
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
            detail="; ".join(failures) if failures else "20/20 通过",
        ))
        assert passed, "\n".join(failures)
    finally:
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
    """ISO-003：op_1 ~ op_19 并发访问 op_0 的 task — 全部 PERMISSION_DENIED。"""
    conn = await asyncpg.connect(DB_URL)
    try:
        task_ids = await _insert_tasks(conn, op_users[0]["user_id"], 1)
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
    """ISO-004：op_1 ~ op_19 并发访问 op_0 的 output — 全部 PERMISSION_DENIED。"""
    conn = await asyncpg.connect(DB_URL)
    try:
        out_ids = await _insert_outputs(conn, op_users[0]["user_id"], 1)
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
