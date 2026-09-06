"""迁移 059：共享报告根目录与正式自动任务幂等约束。"""
import json
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from scripts.run_migrations import strip_transaction_control


def _test_database_url() -> str:
    return "postgresql://mcn_user:admin123@localhost:5432/mcn_test"


@pytest.mark.asyncio
async def test_059_adds_nullable_report_root_and_scoped_formal_auto_run_key_uniqueness():
    migration_path = Path(__file__).parents[3] / "migrations/059_agent_task_config_stage2.sql"
    migration_sql = strip_transaction_control(migration_path.read_text(encoding="utf-8"))
    schema = f"agent_task_stage2_{uuid4().hex}"
    connection = await asyncpg.connect(_test_database_url())
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(f'SET search_path TO "{schema}"')
        await connection.execute("CREATE TABLE agent_task_configs (id BIGSERIAL PRIMARY KEY)")
        await connection.execute(
            """
            CREATE TABLE task_jobs (
                id BIGSERIAL PRIMARY KEY,
                tool_code VARCHAR(64) NOT NULL,
                input_payload JSONB
            )
            """
        )

        await connection.execute(migration_sql)
        await connection.execute(migration_sql)

        assert await connection.fetchval(
            """
            SELECT is_nullable = 'YES'
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'agent_task_configs'
              AND column_name = 'report_root_ref'
            """
        ) is True
        await connection.execute(
            "INSERT INTO agent_task_configs (report_root_ref) VALUES (NULL), ('folder-ref')"
        )

        formal_payload = {
            "agent_code": "content-analysis",
            "task_code": "daily",
            "run_type": "auto",
            "run_key": "daily-project-1-2026-09-04",
        }
        await connection.execute(
            "INSERT INTO task_jobs (tool_code, input_payload) VALUES ($1, $2::jsonb)",
            "content-analysis-daily",
            json.dumps(formal_payload),
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await connection.execute(
                "INSERT INTO task_jobs (tool_code, input_payload) VALUES ($1, $2::jsonb)",
                "content-analysis-daily",
                json.dumps(formal_payload),
            )

        for run_type, tool_code in (
            ("test", "content-analysis-daily"),
            ("manual_retry", "content-analysis-daily"),
            ("auto", "other-tool"),
        ):
            payload = {**formal_payload, "run_type": run_type}
            await connection.execute(
                "INSERT INTO task_jobs (tool_code, input_payload) VALUES ($1, $2::jsonb)",
                tool_code,
                json.dumps(payload),
            )
    finally:
        await connection.execute("SET search_path TO public")
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()
