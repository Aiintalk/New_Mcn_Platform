"""Sprint 25 人格定位正式达人关联迁移测试。"""
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy.engine import make_url

from tests.conftest import TEST_DB_URL


def _asyncpg_connection_args() -> dict:
    url = make_url(TEST_DB_URL)
    return {
        "user": url.username,
        "password": url.password,
        "host": url.host,
        "port": url.port,
        "database": url.database,
    }


@pytest.mark.asyncio
async def test_055_is_idempotent_and_preserves_historical_nulls():
    """重复执行迁移不破坏旧记录，三张表都获得同一可空外键和索引。"""
    schema = f"persona_profile_{uuid4().hex}"
    migration = Path("migrations/055_kol_persona_profile_unification.sql").read_text()
    connection = await asyncpg.connect(**_asyncpg_connection_args())
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(f'SET search_path TO "{schema}"')
        await connection.execute("""
            CREATE TABLE kols (id BIGINT PRIMARY KEY);
            CREATE TABLE persona_reports (id BIGINT PRIMARY KEY);
            CREATE TABLE kol_intake_links (id BIGINT PRIMARY KEY);
            CREATE TABLE kol_intake_operator_sessions (id BIGINT PRIMARY KEY);
            INSERT INTO persona_reports (id) VALUES (1);
            INSERT INTO kol_intake_links (id) VALUES (1);
            INSERT INTO kol_intake_operator_sessions (id) VALUES (1);
        """)

        await connection.execute(migration)
        await connection.execute(migration)

        for table in (
            "persona_reports",
            "kol_intake_links",
            "kol_intake_operator_sessions",
        ):
            nullable = await connection.fetchval(
                """
                SELECT is_nullable = 'YES'
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = $1 AND column_name = 'kol_id'
                """,
                table,
            )
            assert nullable is True
            assert await connection.fetchval(
                f"SELECT kol_id IS NULL FROM {table} WHERE id = 1"
            ) is True
            assert await connection.fetchval(
                """
                SELECT count(*)
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = current_schema()
                  AND t.relname = $1
                  AND c.contype = 'f'
                  AND pg_get_constraintdef(c.oid) LIKE '%REFERENCES kols(id) ON DELETE SET NULL%'
                """,
                table,
            ) == 1
            assert await connection.fetchval(
                """
                SELECT count(*)
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND tablename = $1 AND indexdef LIKE '%(kol_id)%'
                """,
                table,
            ) >= 1
    finally:
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()
