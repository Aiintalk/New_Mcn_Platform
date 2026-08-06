import os
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from scripts.run_migrations import strip_transaction_control


def _test_database_url() -> str:
    url = os.getenv(
        "TEST_DB_URL",
        "postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test",
    )
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.mark.asyncio
async def test_050_upgrades_old_material_rows_and_is_idempotent():
    migration_path = (
        Path(__file__).parents[3] / "migrations" / "050_material_library_media.sql"
    )
    migration_sql = strip_transaction_control(
        migration_path.read_text(encoding="utf-8")
    )
    schema = f"material_media_{uuid4().hex}"
    connection = await asyncpg.connect(_test_database_url())
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(f'SET search_path TO "{schema}"')
        await connection.execute(
            """
            CREATE TABLE kol_references (
                id BIGSERIAL PRIMARY KEY,
                title VARCHAR(500) NOT NULL,
                content TEXT NOT NULL,
                deleted_at TIMESTAMPTZ
            )
            """
        )
        reference_id = await connection.fetchval(
            """
            INSERT INTO kol_references (title, content)
            VALUES ('旧素材', '旧正文')
            RETURNING id
            """
        )

        with pytest.raises(asyncpg.UndefinedColumnError):
            await connection.fetchval(
                "SELECT data_description FROM kol_references WHERE id = $1",
                reference_id,
            )

        await connection.execute(migration_sql)

        migrated = await connection.fetchrow(
            """
            SELECT title, content, data_description, document_name,
                   video_oss_key, video_name, video_content_type, video_size
            FROM kol_references
            WHERE id = $1
            """,
            reference_id,
        )
        assert dict(migrated) == {
            "title": "旧素材",
            "content": "旧正文",
            "data_description": None,
            "document_name": None,
            "video_oss_key": None,
            "video_name": None,
            "video_content_type": None,
            "video_size": None,
        }

        await connection.execute(
            """
            UPDATE kol_references
            SET data_description = '完播率 28%',
                document_name = '脚本.docx',
                document_type = 'application/docx',
                document_size = 123,
                video_oss_key = 'material-library/test/private.mp4',
                video_name = 'private.mp4',
                video_content_type = 'video/mp4',
                video_size = 456
            WHERE id = $1
            """,
            reference_id,
        )
        before_second_run = dict(
            await connection.fetchrow(
                "SELECT * FROM kol_references WHERE id = $1", reference_id
            )
        )

        await connection.execute(migration_sql)

        assert dict(
            await connection.fetchrow(
                "SELECT * FROM kol_references WHERE id = $1", reference_id
            )
        ) == before_second_run
        assert await connection.fetchval("SELECT COUNT(*) FROM kol_references") == 1
    finally:
        await connection.execute("SET search_path TO public")
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()
