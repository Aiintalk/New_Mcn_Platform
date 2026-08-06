import os
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from scripts.run_migrations import MigrationError, apply_migrations, discover_migrations


def _test_database_url() -> str:
    url = os.getenv(
        "TEST_DB_URL",
        "postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test",
    )
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.mark.asyncio
async def test_second_run_skips_migrations_and_does_not_repeat_seed(tmp_path: Path):
    (tmp_path / "001_create_seed_table.sql").write_text(
        "CREATE TABLE seed_items (name TEXT PRIMARY KEY);",
        encoding="utf-8",
    )
    (tmp_path / "002_seed_once.sql").write_text(
        "INSERT INTO seed_items (name) VALUES ('only-once');",
        encoding="utf-8",
    )
    schema = f"migration_runner_{uuid4().hex}"
    connection = await asyncpg.connect(_test_database_url())
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(f'SET search_path TO "{schema}"')
        migrations = discover_migrations(tmp_path)

        first_result = await apply_migrations(connection, migrations)
        second_result = await apply_migrations(connection, migrations)

        assert first_result.applied == [
            "001_create_seed_table.sql",
            "002_seed_once.sql",
        ]
        assert second_result.applied == []
        assert second_result.skipped == [
            "001_create_seed_table.sql",
            "002_seed_once.sql",
        ]
        assert await connection.fetchval("SELECT COUNT(*) FROM seed_items") == 1
        assert await connection.fetchval("SELECT COUNT(*) FROM schema_migrations") == 2
    finally:
        await connection.execute("SET search_path TO public")
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()


@pytest.mark.asyncio
async def test_existing_database_requires_explicit_baseline(tmp_path: Path):
    (tmp_path / "001_initial.sql").write_text(
        "CREATE TABLE business_data (id BIGINT PRIMARY KEY);",
        encoding="utf-8",
    )
    schema = f"migration_baseline_{uuid4().hex}"
    connection = await asyncpg.connect(_test_database_url())
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(f'SET search_path TO "{schema}"')
        await connection.execute("CREATE TABLE business_data (id BIGINT PRIMARY KEY)")

        with pytest.raises(MigrationError, match="--baseline-through"):
            await apply_migrations(connection, discover_migrations(tmp_path))

        assert await connection.fetchval(
            "SELECT to_regclass('schema_migrations')"
        ) is None
    finally:
        await connection.execute("SET search_path TO public")
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()


@pytest.mark.asyncio
async def test_same_baseline_command_is_safe_to_run_twice(tmp_path: Path):
    (tmp_path / "001_initial.sql").write_text(
        "CREATE TABLE business_data (id BIGINT PRIMARY KEY);",
        encoding="utf-8",
    )
    schema = f"migration_repeat_baseline_{uuid4().hex}"
    connection = await asyncpg.connect(_test_database_url())
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(f'SET search_path TO "{schema}"')
        await connection.execute("CREATE TABLE business_data (id BIGINT PRIMARY KEY)")
        migrations = discover_migrations(tmp_path)

        first_result = await apply_migrations(
            connection, migrations, baseline_through=1
        )
        second_result = await apply_migrations(
            connection, migrations, baseline_through=1
        )

        assert first_result.baselined == ["001_initial.sql"]
        assert second_result.skipped == ["001_initial.sql"]
        assert await connection.fetchval("SELECT COUNT(*) FROM business_data") == 0
    finally:
        await connection.execute("SET search_path TO public")
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()
