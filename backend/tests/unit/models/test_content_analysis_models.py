"""Sprint28 内容分析五类持久化模型合同。"""
from sqlalchemy import inspect

from app.core.database import Base


TABLES = {
    "content_analysis_results",
    "content_analysis_deliveries",
    "content_analysis_library_items",
    "content_analysis_cross_project_opportunities",
    "content_analysis_account_baselines",
}


def test_content_analysis_registers_exactly_the_five_approved_tables() -> None:
    import app.models  # noqa: F401

    assert TABLES <= set(Base.metadata.tables)
    assert not {
        "content_analysis_basic_analyses",
        "content_analysis_library_events",
    } & set(Base.metadata.tables)


def test_result_and_delivery_hold_three_layer_idempotency_and_delivery_identity() -> None:
    import app.models  # noqa: F401

    result = Base.metadata.tables["content_analysis_results"]
    delivery = Base.metadata.tables["content_analysis_deliveries"]

    assert result.c.result_key.unique
    assert result.c.analysis_key.nullable is False
    assert result.c.output_id.unique
    assert {"execution_kind", "window_start", "window_end", "context_versions", "is_test"} <= set(result.c.keys())
    assert delivery.c.document_key.unique
    assert {"target_directory", "document_id", "document_url", "status", "attempt_count", "last_error"} <= set(delivery.c.keys())


def test_library_is_one_to_one_extension_and_has_dual_project_identity_indexes() -> None:
    import app.models  # noqa: F401

    table = Base.metadata.tables["content_analysis_library_items"]
    foreign_keys = {fk.target_fullname for fk in table.c.kol_reference_id.foreign_keys}
    assert foreign_keys == {"kol_references.id"}
    assert table.c.kol_reference_id.unique
    index_names = {index.name for index in table.indexes}
    assert {
        "uq_ca_library_project_platform_content",
        "uq_ca_library_project_external_url",
    } <= index_names
    assert {"analysis", "project_assessment", "latest_metrics", "availability"} <= set(table.c.keys())


def test_baseline_and_cross_project_opportunity_have_stable_unique_keys() -> None:
    import app.models  # noqa: F401

    cross = Base.metadata.tables["content_analysis_cross_project_opportunities"]
    baseline = Base.metadata.tables["content_analysis_account_baselines"]

    assert cross.c.method_key.unique
    assert {"applicable_boundaries", "sources"} <= set(cross.c.keys())
    unique_columns = {
        tuple(constraint.columns.keys())
        for constraint in baseline.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("sec_uid", "window_start", "window_end") in unique_columns
    assert {"mean_likes", "median_likes", "sample_count", "maximum_likes", "minimum_likes", "unavailable_reason", "related_project_ids"} <= set(baseline.c.keys())


def test_orm_metadata_keeps_the_same_closed_state_and_shape_checks_as_migration() -> None:
    import app.models  # noqa: F401

    def checks(table_name: str) -> str:
        table = Base.metadata.tables[table_name]
        return " ".join(
            str(constraint.sqltext)
            for constraint in table.constraints
            if constraint.__class__.__name__ == "CheckConstraint"
        )

    assert "run_type" in checks("content_analysis_results")
    assert "execution_kind" in checks("content_analysis_results")
    assert "status" in checks("content_analysis_deliveries")
    assert "ingestion_source" in checks("content_analysis_library_items")
    library = Base.metadata.tables["content_analysis_library_items"]
    assert library.c.latest_result_id.nullable is True
    assert library.c.account_id.nullable is True
    assert "sample_count" in checks("content_analysis_account_baselines")
