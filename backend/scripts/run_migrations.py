#!/usr/bin/env python3
"""按文件顺序执行 PostgreSQL 迁移，并用账本防止重复执行。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Sequence

import asyncpg
from dotenv import load_dotenv


MIGRATION_FILENAME = re.compile(r"^(?P<version>\d{3})_[a-z0-9][a-z0-9_.-]*\.sql$")
TRANSACTION_CONTROL = re.compile(
    r"^\s*(BEGIN|COMMIT)\s*;\s*(?:--.*)?(?:\r?\n)?$",
    re.IGNORECASE,
)
ADVISORY_LOCK_KEY = 6_129_346_295_244

LEDGER_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename         TEXT PRIMARY KEY,
    version          INTEGER NOT NULL,
    checksum_sha256  CHAR(64) NOT NULL,
    execution_kind   VARCHAR(16) NOT NULL
                     CHECK (execution_kind IN ('applied', 'baseline')),
    applied_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


class MigrationError(RuntimeError):
    """迁移执行器拒绝继续时的基础异常。"""


class MigrationChecksumMismatch(MigrationError):
    """已执行迁移的内容发生变化。"""


@dataclass(frozen=True)
class Migration:
    path: Path
    filename: str
    version: int
    checksum_sha256: str
    sql: str


@dataclass(frozen=True)
class AppliedMigration:
    filename: str
    checksum_sha256: str
    execution_kind: str


@dataclass(frozen=True)
class PlanItem:
    migration: Migration
    action: Literal["apply", "baseline", "skip"]


@dataclass
class MigrationResult:
    applied: list[str] = field(default_factory=list)
    baselined: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def discover_migrations(directory: Path) -> list[Migration]:
    if not directory.is_dir():
        raise MigrationError(f"迁移目录不存在：{directory}")

    migrations: list[Migration] = []
    for path in directory.glob("*.sql"):
        match = MIGRATION_FILENAME.fullmatch(path.name)
        if not match:
            raise MigrationError(f"迁移文件名不符合 NNN_name.sql 规范：{path.name}")
        sql = path.read_text(encoding="utf-8")
        migrations.append(
            Migration(
                path=path,
                filename=path.name,
                version=int(match.group("version")),
                checksum_sha256=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
                sql=sql,
            )
        )
    return sorted(migrations, key=lambda item: (item.version, item.filename))


def strip_transaction_control(sql: str) -> str:
    """移除迁移文件自带的最外层事务语句，由执行器统一保证原子性。"""
    return "".join(
        line
        for line in sql.splitlines(keepends=True)
        if not TRANSACTION_CONTROL.fullmatch(line)
    )


def build_migration_plan(
    migrations: Sequence[Migration],
    applied: dict[str, AppliedMigration],
    baseline_through: int | None = None,
    adopt_existing: set[str] | None = None,
) -> list[PlanItem]:
    adopt_existing = adopt_existing or set()
    known_filenames = {migration.filename for migration in migrations}
    unknown_adoptions = adopt_existing - known_filenames
    if unknown_adoptions:
        raise MigrationError(
            "待登记文件不在迁移目录："
            + ", ".join(sorted(unknown_adoptions))
        )

    plan: list[PlanItem] = []
    for migration in migrations:
        existing = applied.get(migration.filename)
        if existing:
            if existing.checksum_sha256 != migration.checksum_sha256:
                raise MigrationChecksumMismatch(
                    f"已执行迁移的校验和发生变化：{migration.filename}"
                )
            plan.append(PlanItem(migration=migration, action="skip"))
        elif (
            baseline_through is not None and migration.version <= baseline_through
        ) or migration.filename in adopt_existing:
            plan.append(PlanItem(migration=migration, action="baseline"))
        else:
            plan.append(PlanItem(migration=migration, action="apply"))
    return plan


async def _load_applied(connection: asyncpg.Connection) -> dict[str, AppliedMigration]:
    rows = await connection.fetch(
        """
        SELECT filename, checksum_sha256, execution_kind
        FROM schema_migrations
        ORDER BY version, filename
        """
    )
    return {
        row["filename"]: AppliedMigration(
            filename=row["filename"],
            checksum_sha256=row["checksum_sha256"].strip(),
            execution_kind=row["execution_kind"],
        )
        for row in rows
    }


async def _record_migration(
    connection: asyncpg.Connection,
    migration: Migration,
    execution_kind: Literal["applied", "baseline"],
) -> None:
    await connection.execute(
        """
        INSERT INTO schema_migrations
            (filename, version, checksum_sha256, execution_kind)
        VALUES ($1, $2, $3, $4)
        """,
        migration.filename,
        migration.version,
        migration.checksum_sha256,
        execution_kind,
    )


async def apply_migrations(
    connection: asyncpg.Connection,
    migrations: Sequence[Migration],
    baseline_through: int | None = None,
    adopt_existing: set[str] | None = None,
) -> MigrationResult:
    """执行待迁移文件；已有账本记录只校验、不重放 SQL 或 seed。"""
    await connection.fetchval("SELECT pg_advisory_lock($1)", ADVISORY_LOCK_KEY)
    try:
        ledger_exists = await connection.fetchval(
            "SELECT to_regclass('schema_migrations') IS NOT NULL"
        )
        has_existing_tables = await connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_tables
                WHERE schemaname = current_schema()
                  AND tablename <> 'schema_migrations'
            )
            """
        )
        if has_existing_tables and not ledger_exists and baseline_through is None:
            raise MigrationError(
                "检测到既有数据库但没有迁移账本；"
                "请先核对现有结构，再用 --baseline-through 明确登记旧库基线"
            )

        await connection.execute(LEDGER_SQL)
        applied = await _load_applied(connection)
        if baseline_through is not None:
            if not any(item.version == baseline_through for item in migrations):
                raise MigrationError(
                    f"基线版本 {baseline_through:03d} 不存在于迁移目录"
                )
            missing_baseline = [
                item.filename
                for item in migrations
                if item.version <= baseline_through and item.filename not in applied
            ]
            if applied and missing_baseline:
                raise MigrationError(
                    "迁移账本已有记录，禁止扩大旧库基线；未登记文件："
                    + ", ".join(missing_baseline)
                )

        result = MigrationResult()
        plan = build_migration_plan(
            migrations,
            applied,
            baseline_through,
            adopt_existing,
        )
        for item in plan:
            migration = item.migration
            if item.action == "skip":
                result.skipped.append(migration.filename)
                continue
            if item.action == "baseline":
                async with connection.transaction():
                    await _record_migration(connection, migration, "baseline")
                result.baselined.append(migration.filename)
                continue

            migration_sql = strip_transaction_control(migration.sql)
            async with connection.transaction():
                await connection.execute(migration_sql)
                await _record_migration(connection, migration, "applied")
            result.applied.append(migration.filename)
        return result
    finally:
        await connection.fetchval("SELECT pg_advisory_unlock($1)", ADVISORY_LOCK_KEY)


def _normalize_database_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="按顺序执行尚未写入 schema_migrations 账本的数据库迁移"
    )
    parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "migrations",
        help="迁移 SQL 所在目录",
    )
    parser.add_argument(
        "--baseline-through",
        type=int,
        help="仅供首次接管既有数据库：把指定版本及之前文件登记为已存在，不执行其 SQL",
    )
    parser.add_argument(
        "--adopt-existing",
        action="append",
        default=[],
        metavar="FILENAME",
        help="已人工核实存在的单个迁移文件，仅登记账本、不执行 SQL；可重复传入",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    backend_dir = Path(__file__).resolve().parents[1]
    load_dotenv(backend_dir / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise MigrationError("缺少 DATABASE_URL，请通过环境变量或 backend/.env 配置")

    migrations = discover_migrations(args.migrations_dir)
    connection = await asyncpg.connect(_normalize_database_url(database_url))
    try:
        result = await apply_migrations(
            connection,
            migrations,
            baseline_through=args.baseline_through,
            adopt_existing=set(args.adopt_existing),
        )
    finally:
        await connection.close()

    for filename in result.baselined:
        print(f"登记既有迁移：{filename}")
    for filename in result.applied:
        print(f"执行迁移：{filename}")
    print(
        "迁移完成："
        f"执行 {len(result.applied)}，"
        f"登记既有 {len(result.baselined)}，"
        f"跳过 {len(result.skipped)}"
    )
    return 0


def main() -> int:
    args = _parser().parse_args()
    try:
        return asyncio.run(_run(args))
    except (MigrationError, asyncpg.PostgresError) as exc:
        print(f"迁移失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
