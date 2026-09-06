"""migration 060 的范围与安全约束。"""
from pathlib import Path


MIGRATION = Path(__file__).parents[3] / "migrations" / "060_content_analysis_runtime.sql"


def test_migration_060_creates_only_the_five_approved_content_analysis_tables() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    created = {
        line.split()[5]
        for line in sql.splitlines()
        if line.strip().upper().startswith("CREATE TABLE IF NOT EXISTS")
    }
    assert created == {
        "content_analysis_results",
        "content_analysis_deliveries",
        "content_analysis_library_items",
        "content_analysis_cross_project_opportunities",
        "content_analysis_account_baselines",
    }
    assert "content_analysis_basic_analyses" not in sql
    assert "content_analysis_library_events" not in sql


def test_migration_060_has_no_seed_credentials_or_task_configuration() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "insert into" not in sql
    assert "app_secret" not in sql
    assert "agent_task_configs" not in sql
