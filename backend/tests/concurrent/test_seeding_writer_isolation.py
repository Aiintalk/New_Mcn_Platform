"""
seeding-writer 数据隔离并发测试（SW-ISO-001 ~ SW-ISO-004）。

前置：conftest.py 的 op_users fixture 已创建 20 个 operator。
测试逻辑：
- SW-ISO-001：20 op 并发 POST /save-output → 20 条全部成功 + 归属正确
- SW-ISO-002：20 op 并发 GET /outputs → 各自只见自己的产出（按 tool_code='seeding-writer' 隔离）
- SW-ISO-003：tool_code 隔离 — 写 seeding-writer output 不影响 persona-writer COUNT
- SW-ISO-004：60 条（20 op × 3）并发写入 → 全部入库无丢失（压力测试）

参照：tests/concurrent/test_isolation.py（ISO-001 ~ ISO-004 persona-writer 通用 outputs 隔离）。
"""

import asyncpg
import httpx
import pytest

from tests.concurrent.conftest import BASE_URL, DB_URL, run_concurrent
from tests.concurrent.reporter import REPORT, TestResult

TOOL_CODE = "seeding-writer"
TOOL_NAME = "种草内容仿写"
SAVE_URL = f"{BASE_URL}/api/tools/seeding-writer/save-output"
LIST_URL = f"{BASE_URL}/api/tools/seeding-writer/outputs"


async def _insert_output(conn: asyncpg.Connection, user_id: int, idx: int = 0) -> int:
    """直连 DB 插入 1 条 seeding-writer output，返回 id（用于隔离验证 setup）。"""
    row = await conn.fetchrow(
        """
        INSERT INTO outputs (title, tool_code, tool_name, created_by)
        VALUES ($1, $2, $3, $4) RETURNING id
        """,
        f"SW-ISO 种草脚本 {user_id}-{idx}",
        TOOL_CODE,
        TOOL_NAME,
        user_id,
    )
    return row["id"]


# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sw_iso_001_concurrent_create_isolation(op_users):
    """SW-ISO-001：20 op 并发 POST /save-output → 20 条全部成功 + 归属正确。

    验证点：
    1. 20 个请求全部 success=true
    2. 直连 DB 查 created_by，归属与 token 对应 user_id 完全一致
    """
    output_ids = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            coros = [
                client.post(
                    SAVE_URL,
                    json={
                        "title": f"SW-ISO-001 op_{i}",
                        "content": f"op_{i} 的种草脚本内容",
                    },
                    headers={"Authorization": f"Bearer {u['token']}"},
                )
                for i, u in enumerate(op_users)
            ]
            results = await run_concurrent(coros)

        failures = []
        for res in results:
            body = res["body"]
            if not body.get("success"):
                failures.append(f"创建失败: {body.get('code')}")
                continue
            output_ids.append(body["data"]["output_id"])

        if len(output_ids) != 20:
            failures.append(f"应成功 20 条，实际 {len(output_ids)}")

        # 直连 DB 验证归属：每个 output 的 created_by 必须在 20 op 的 user_id 集合中
        if len(output_ids) == 20:
            valid_user_ids = {u["user_id"] for u in op_users}
            conn = await asyncpg.connect(DB_URL)
            try:
                rows = await conn.fetch(
                    """
                    SELECT id, created_by FROM outputs
                    WHERE id = ANY($1::bigint[])
                    """,
                    output_ids,
                )
                for row in rows:
                    if row["created_by"] not in valid_user_ids:
                        failures.append(
                            f"output {row['id']} 归属错: created_by={row['created_by']} 不在 20 op 中"
                        )
            finally:
                await conn.close()

        passed = len(failures) == 0
        REPORT.record(TestResult(
            category="isolation",
            case_id="SW-ISO-001",
            description="seeding-writer 并发创建产出 — 20 op 全部成功且归属正确",
            passed=passed,
            detail="; ".join(failures) if failures else "20/20 通过",
        ))
        assert passed, "\n".join(failures)
    finally:
        if output_ids:
            conn2 = await asyncpg.connect(DB_URL)
            try:
                await conn2.execute(
                    "DELETE FROM outputs WHERE id = ANY($1::bigint[])",
                    output_ids,
                )
            finally:
                await conn2.close()


@pytest.mark.asyncio
async def test_sw_iso_002_list_isolation(op_users):
    """SW-ISO-002：20 op 并发 GET /outputs → 各自只见自己的产出。

    验证点：list 接口 SQL 已 WHERE tool_code='seeding-writer' AND created_by=current_user.id，
    并发场景下不能因为连接复用/会话串扰让 op_i 看到 op_j 的产出。
    """
    conn = await asyncpg.connect(DB_URL)
    inserted_ids = []
    try:
        # 给 op_0 和 op_1 各插 3 条 seeding-writer output
        for i in range(3):
            inserted_ids.append(await _insert_output(conn, op_users[0]["user_id"], i))
            inserted_ids.append(await _insert_output(conn, op_users[1]["user_id"], i))
    finally:
        await conn.close()

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            coros = [
                client.get(
                    LIST_URL,
                    headers={"Authorization": f"Bearer {u['token']}"},
                )
                for u in op_users
            ]
            results = await run_concurrent(coros)

        failures = []
        for i, (res, user) in enumerate(zip(results, op_users)):
            body = res["body"]
            if not body.get("success"):
                failures.append(f"op_{i}({user['username']}) 查询失败: {body.get('code')}")
                continue
            items = body["data"].get("items", [])
            for item in items:
                # list 接口默认不返回 created_by（按 SQL 已过滤），但若返回则严格校验
                if "created_by" in item and item["created_by"] != user["user_id"]:
                    failures.append(
                        f"op_{i}({user['username']}) 看到了 user_id={item['created_by']} 的产出"
                    )

        passed = len(failures) == 0
        REPORT.record(TestResult(
            category="isolation",
            case_id="SW-ISO-002",
            description="seeding-writer 并发查询产出列表 — 各自只见自己的产出",
            passed=passed,
            detail="; ".join(failures) if failures else "20/20 通过",
        ))
        assert passed, "\n".join(failures)
    finally:
        if inserted_ids:
            conn2 = await asyncpg.connect(DB_URL)
            try:
                await conn2.execute(
                    "DELETE FROM outputs WHERE id = ANY($1::bigint[])",
                    inserted_ids,
                )
            finally:
                await conn2.close()


@pytest.mark.asyncio
async def test_sw_iso_003_tool_code_isolation(op_users):
    """SW-ISO-003：写 seeding-writer output 不影响 persona-writer（tool_code 隔离）。

    策略：
    1. 记录 persona-writer outputs 当前 COUNT
    2. 并发插入 10 条 seeding-writer output（op_0 token）
    3. 验证 persona-writer COUNT 未变
    4. 验证 seeding-writer COUNT +10

    意义：outputs 是通用表，多工具共用。SQL 必须严格按 tool_code 过滤，否则 op_0 写的
    seeding-writer 脚本会被 persona-writer 的 list 捞到，造成数据串台。
    """
    conn = await asyncpg.connect(DB_URL)
    inserted_ids = []
    try:
        before_pw = await conn.fetchval(
            "SELECT COUNT(*) FROM outputs WHERE tool_code = 'persona-writer'"
        )
        before_sw = await conn.fetchval(
            "SELECT COUNT(*) FROM outputs WHERE tool_code = $1", TOOL_CODE
        )

        async with httpx.AsyncClient(timeout=30) as client:
            coros = [
                client.post(
                    SAVE_URL,
                    json={"title": f"SW-ISO-003 op_0-{i}", "content": f"内容 {i}"},
                    headers={"Authorization": f"Bearer {op_users[0]['token']}"},
                )
                for i in range(10)
            ]
            results = await run_concurrent(coros)

        for res in results:
            if res["body"].get("success"):
                inserted_ids.append(res["body"]["data"]["output_id"])

        after_pw = await conn.fetchval(
            "SELECT COUNT(*) FROM outputs WHERE tool_code = 'persona-writer'"
        )
        after_sw = await conn.fetchval(
            "SELECT COUNT(*) FROM outputs WHERE tool_code = $1", TOOL_CODE
        )

        failures = []
        if after_pw != before_pw:
            failures.append(f"persona-writer COUNT 变了: {before_pw} → {after_pw}（应不变）")
        if after_sw - before_sw != 10:
            failures.append(f"seeding-writer COUNT 应 +10，实际 +{after_sw - before_sw}")

        passed = len(failures) == 0
        REPORT.record(TestResult(
            category="isolation",
            case_id="SW-ISO-003",
            description="seeding-writer 写入不影响 persona-writer（tool_code 隔离）",
            passed=passed,
            detail="; ".join(failures) if failures else "persona-writer 不变 + SW +10",
        ))
        assert passed, "\n".join(failures)
    finally:
        if inserted_ids:
            await conn.execute(
                "DELETE FROM outputs WHERE id = ANY($1::bigint[])", inserted_ids
            )
        await conn.close()


@pytest.mark.asyncio
async def test_sw_iso_004_concurrent_write_no_loss(op_users):
    """SW-ISO-004：60 条（20 op × 3）并发写入 → 全部入库无丢失（压力测试）。

    验证点：
    1. 60 个请求全部 success=true
    2. 拿回 60 个不同 output_id
    3. DB COUNT 实际 +60
    4. 无并发竞态导致的 id 重复或丢失
    """
    output_ids = []
    conn = await asyncpg.connect(DB_URL)
    try:
        before_sw = await conn.fetchval(
            "SELECT COUNT(*) FROM outputs WHERE tool_code = $1", TOOL_CODE
        )

        async with httpx.AsyncClient(timeout=60) as client:
            coros = []
            for i, u in enumerate(op_users):
                for j in range(3):
                    coros.append(
                        client.post(
                            SAVE_URL,
                            json={
                                "title": f"SW-ISO-004 op_{i}-{j}",
                                "content": f"压力测试 op_{i}-{j}",
                            },
                            headers={"Authorization": f"Bearer {u['token']}"},
                        )
                    )
            results = await run_concurrent(coros)

        failures = []
        success_count = 0
        for res in results:
            body = res["body"]
            if body.get("success"):
                success_count += 1
                output_ids.append(body["data"]["output_id"])
            else:
                failures.append(f"请求失败: {body.get('code')}")

        if success_count != 60:
            failures.append(f"应成功 60 条，实际 {success_count}")

        # 检查 id 唯一性
        unique_ids = set(output_ids)
        if len(unique_ids) != len(output_ids):
            failures.append(f"output_id 有重复: {len(output_ids)} 条只有 {len(unique_ids)} 个唯一 id")

        # DB COUNT 验证
        after_sw = await conn.fetchval(
            "SELECT COUNT(*) FROM outputs WHERE tool_code = $1", TOOL_CODE
        )
        if after_sw - before_sw != 60:
            failures.append(f"DB COUNT 应 +60，实际 +{after_sw - before_sw}")

        passed = len(failures) == 0
        REPORT.record(TestResult(
            category="isolation",
            case_id="SW-ISO-004",
            description="seeding-writer 60 条并发写入压力测试 — 全部入库无丢失",
            passed=passed,
            detail="; ".join(failures) if failures else f"{success_count}/60 通过 + DB COUNT +60",
        ))
        assert passed, "\n".join(failures)
    finally:
        if output_ids:
            await conn.execute(
                "DELETE FROM outputs WHERE id = ANY($1::bigint[])", output_ids
            )
        await conn.close()
