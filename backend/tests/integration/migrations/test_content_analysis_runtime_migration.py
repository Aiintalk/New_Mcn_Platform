"""migration 060 在 PostgreSQL 中可执行且可重跑。"""
import os
from pathlib import Path
import shutil
from uuid import uuid4

import asyncpg
import pytest

from scripts.run_migrations import apply_migrations, discover_migrations


def database_url() -> str:
    return os.getenv(
        "TEST_DB_URL",
        "postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test",
    ).replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.mark.asyncio
async def test_migration_060_executes_twice_and_keeps_exact_five_tables() -> None:
    schema = f"ca_runtime_{uuid4().hex}"
    connection = await asyncpg.connect(database_url())
    sql = (
        Path(__file__).resolve().parents[3]
        / "migrations"
        / "060_content_analysis_runtime.sql"
    ).read_text(encoding="utf-8")
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(f'SET search_path TO "{schema}"')
        await connection.execute(
            """
            CREATE TABLE users (id BIGINT PRIMARY KEY);
            CREATE TABLE task_jobs (id BIGINT PRIMARY KEY);
            CREATE TABLE kols (id BIGINT PRIMARY KEY);
            CREATE TABLE outputs (id BIGINT PRIMARY KEY);
            CREATE TABLE kol_references (id BIGINT PRIMARY KEY);
            """
        )

        await connection.execute(sql)
        await connection.execute(sql)

        tables = set(
            await connection.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = $1",
                schema,
            )
        )
        names = {row["tablename"] for row in tables}
        assert {
            "content_analysis_results",
            "content_analysis_deliveries",
            "content_analysis_library_items",
            "content_analysis_cross_project_opportunities",
            "content_analysis_account_baselines",
        } <= names
    finally:
        await connection.execute("SET search_path TO public")
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()


@pytest.mark.asyncio
async def test_migrations_059_then_060_use_ordered_ledger_and_are_safe_to_repeat(
    tmp_path: Path,
) -> None:
    """联合切片不得让内容分析表早于任务配置阶段二契约落地。"""
    migrations_dir = Path(__file__).resolve().parents[3] / "migrations"
    for filename in (
        "058_agent_task_configs.sql",
        "059_agent_task_config_stage2.sql",
        "060_content_analysis_runtime.sql",
    ):
        shutil.copy2(migrations_dir / filename, tmp_path / filename)

    schema = f"ca_joint_migrations_{uuid4().hex}"
    connection = await asyncpg.connect(database_url())
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(f'SET search_path TO "{schema}"')
        await connection.execute(
            """
            CREATE TABLE agent_task_configs (id BIGSERIAL PRIMARY KEY);
            CREATE TABLE task_jobs (
                id BIGINT PRIMARY KEY,
                tool_code VARCHAR(64) NOT NULL,
                input_payload JSONB
            );
            CREATE TABLE users (id BIGINT PRIMARY KEY);
            CREATE TABLE kols (id BIGINT PRIMARY KEY);
            CREATE TABLE outputs (id BIGINT PRIMARY KEY);
            CREATE TABLE kol_references (id BIGINT PRIMARY KEY);
            """
        )

        migrations = discover_migrations(tmp_path)
        first = await apply_migrations(
            connection,
            migrations,
            baseline_through=58,
        )
        second = await apply_migrations(
            connection,
            migrations,
            baseline_through=58,
        )

        assert first.baselined == ["058_agent_task_configs.sql"]
        assert first.applied == [
            "059_agent_task_config_stage2.sql",
            "060_content_analysis_runtime.sql",
        ]
        assert second.skipped == [
            "058_agent_task_configs.sql",
            "059_agent_task_config_stage2.sql",
            "060_content_analysis_runtime.sql",
        ]
        ledger = await connection.fetch(
            """
            SELECT filename, version, execution_kind
            FROM schema_migrations
            ORDER BY version, filename
            """
        )
        assert [tuple(row.values()) for row in ledger] == [
            ("058_agent_task_configs.sql", 58, "baseline"),
            ("059_agent_task_config_stage2.sql", 59, "applied"),
            ("060_content_analysis_runtime.sql", 60, "applied"),
        ]
    finally:
        await connection.execute("SET search_path TO public")
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()
