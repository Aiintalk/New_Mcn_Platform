from pathlib import Path

import pytest

from scripts.run_migrations import (
    AppliedMigration,
    MigrationChecksumMismatch,
    MigrationError,
    build_migration_plan,
    discover_migrations,
    strip_transaction_control,
)


def _write_migration(directory: Path, name: str, sql: str = "SELECT 1;") -> Path:
    path = directory / name
    path.write_text(sql, encoding="utf-8")
    return path


def test_discover_migrations_orders_duplicate_versions_by_filename(tmp_path: Path):
    _write_migration(tmp_path, "045_subtitle_item_meta.sql")
    _write_migration(tmp_path, "044_subtitle_job_kind_and_soft_delete.sql")
    _write_migration(tmp_path, "045_retrospective.sql")
    _write_migration(tmp_path, "050_material_library_media.sql")

    migrations = discover_migrations(tmp_path)

    assert [item.filename for item in migrations] == [
        "044_subtitle_job_kind_and_soft_delete.sql",
        "045_retrospective.sql",
        "045_subtitle_item_meta.sql",
        "050_material_library_media.sql",
    ]


def test_build_plan_requires_explicit_baseline_for_existing_database(tmp_path: Path):
    _write_migration(tmp_path, "049_previous.sql")
    _write_migration(tmp_path, "050_material_library_media.sql")
    migrations = discover_migrations(tmp_path)

    plan = build_migration_plan(
        migrations=migrations,
        applied={},
        baseline_through=49,
    )

    assert [item.migration.filename for item in plan if item.action == "baseline"] == [
        "049_previous.sql"
    ]
    assert [item.migration.filename for item in plan if item.action == "apply"] == [
        "050_material_library_media.sql"
    ]


def test_build_plan_rejects_changed_applied_migration(tmp_path: Path):
    migration_path = _write_migration(tmp_path, "050_material_library_media.sql")
    migration = discover_migrations(tmp_path)[0]
    migration_path.write_text("SELECT 2;", encoding="utf-8")
    changed_migration = discover_migrations(tmp_path)[0]

    with pytest.raises(MigrationChecksumMismatch, match="050_material_library_media.sql"):
        build_migration_plan(
            migrations=[changed_migration],
            applied={
                migration.filename: AppliedMigration(
                    filename=migration.filename,
                    checksum_sha256=migration.checksum_sha256,
                    execution_kind="applied",
                )
            },
        )


def test_build_plan_can_adopt_a_verified_manually_applied_file(tmp_path: Path):
    _write_migration(tmp_path, "050_material_library_media.sql")
    _write_migration(tmp_path, "053_eval_core.sql")
    migrations = discover_migrations(tmp_path)

    plan = build_migration_plan(
        migrations=migrations,
        applied={},
        adopt_existing={"053_eval_core.sql"},
    )

    assert [(item.migration.filename, item.action) for item in plan] == [
        ("050_material_library_media.sql", "apply"),
        ("053_eval_core.sql", "baseline"),
    ]


def test_build_plan_rejects_unknown_adopt_filename(tmp_path: Path):
    _write_migration(tmp_path, "050_material_library_media.sql")
    migrations = discover_migrations(tmp_path)

    with pytest.raises(MigrationError, match="053_missing.sql"):
        build_migration_plan(
            migrations=migrations,
            applied={},
            adopt_existing={"053_missing.sql"},
        )


def test_strip_transaction_control_keeps_migration_body():
    sql = """-- migration
BEGIN;
ALTER TABLE sample ADD COLUMN value TEXT;
COMMIT;
"""

    assert strip_transaction_control(sql) == (
        "-- migration\n"
        "ALTER TABLE sample ADD COLUMN value TEXT;\n"
    )
