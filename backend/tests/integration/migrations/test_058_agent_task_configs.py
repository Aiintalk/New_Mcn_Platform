"""迁移 058：智能体配置按智能体隔离，并拒绝非数组项目范围。"""
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.agent_task_config import AgentTaskConfig
from scripts.run_migrations import strip_transaction_control


def _test_database_url() -> str:
    return "postgresql://mcn_user:admin123@localhost:5432/mcn_test"


@pytest.mark.asyncio
async def test_058_creates_isolated_agent_config_with_array_guard_and_nullable_editor():
    migration_path = Path(__file__).parents[3] / "migrations/058_agent_task_configs.sql"
    migration_sql = strip_transaction_control(migration_path.read_text(encoding="utf-8"))
    schema = f"agent_task_config_{uuid4().hex}"
    connection = await asyncpg.connect(_test_database_url())
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(f'SET search_path TO "{schema}"')
        await connection.execute("CREATE TABLE users (id BIGINT PRIMARY KEY)")
        await connection.execute(
            """
            CREATE FUNCTION set_updated_at() RETURNS trigger AS $$
            BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
            $$ LANGUAGE plpgsql;
            """
        )

        await connection.execute(migration_sql)
        await connection.execute(migration_sql)
        await connection.execute(
            "INSERT INTO users (id) VALUES (1), (2)"
        )
        await connection.execute(
            """
            INSERT INTO agent_task_configs (agent_code, selected_project_ids, updated_by)
            VALUES ('content-analysis', '[11, 12]'::jsonb, 1)
            """
        )

        assert await connection.fetchval(
            "SELECT selected_project_ids FROM agent_task_configs "
            "WHERE agent_code = 'content-analysis'"
        ) == "[11, 12]"
        with pytest.raises(asyncpg.CheckViolationError):
            await connection.execute(
                "INSERT INTO agent_task_configs (agent_code, selected_project_ids) "
                "VALUES ('another-agent', '{\"project_id\": 1}'::jsonb)"
            )
        with pytest.raises(asyncpg.UniqueViolationError):
            await connection.execute(
                "INSERT INTO agent_task_configs (agent_code, selected_project_ids) "
                "VALUES ('content-analysis', '[]'::jsonb)"
            )

        await connection.execute("DELETE FROM users WHERE id = 1")
        assert await connection.fetchval(
            "SELECT updated_by IS NULL FROM agent_task_configs "
            "WHERE agent_code = 'content-analysis'"
        ) is True
    finally:
        await connection.execute("SET search_path TO public")
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()


@pytest.mark.asyncio
async def test_orm_metadata_rejects_non_array_selected_project_ids(test_session):
    config = AgentTaskConfig(
        agent_code=f"orm-array-guard-{uuid4().hex}",
        selected_project_ids={"project_id": 1},
    )
    test_session.add(config)
    with pytest.raises(IntegrityError):
        await test_session.commit()
    await test_session.rollback()
