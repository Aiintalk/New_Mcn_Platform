"""内容分析运行结果、投递、项目库、跨项目机会和账号基准。"""
from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class ContentAnalysisResult(Base):
    """不可变 Output 正文的专业检索索引。"""

    __tablename__ = "content_analysis_results"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    result_key = Column(String(128), nullable=False, unique=True)
    analysis_key = Column(String(128), nullable=False)
    task_id = Column(BigInteger, ForeignKey("task_jobs.id"), nullable=False)
    task_code = Column(String(64), nullable=False)
    run_type = Column(String(16), nullable=False)
    execution_kind = Column(String(32), nullable=False)
    project_id = Column(BigInteger, ForeignKey("kols.id"), nullable=True)
    sec_uid = Column(String(128), nullable=True)
    related_project_ids = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    business_date = Column(Date, nullable=False)
    window_start = Column(TIMESTAMP(timezone=True), nullable=False)
    window_end = Column(TIMESTAMP(timezone=True), nullable=False)
    context_versions = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    source_receipts = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status = Column(String(32), nullable=False)
    output_id = Column(BigInteger, ForeignKey("outputs.id"), nullable=False, unique=True)
    is_test = Column(Boolean, nullable=False, default=False, server_default=text("FALSE"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "run_type IN ('auto', 'test', 'retry')",
            name="ck_ca_results_run_type",
        ),
        CheckConstraint(
            "execution_kind IN ('project', 'account', 'weekly_batch_finalize')",
            name="ck_ca_results_execution_kind",
        ),
        CheckConstraint(
            "status IN ('success', 'no_content')",
            name="ck_ca_results_status",
        ),
        CheckConstraint(
            "window_start < window_end",
            name="ck_ca_results_window",
        ),
        CheckConstraint(
            "(execution_kind = 'project' AND project_id IS NOT NULL AND sec_uid IS NULL) "
            "OR (execution_kind = 'account' AND project_id IS NULL AND sec_uid IS NOT NULL) "
            "OR (execution_kind = 'weekly_batch_finalize' AND project_id IS NULL AND sec_uid IS NULL)",
            name="ck_ca_results_execution_identity",
        ),
        Index("ix_ca_results_analysis_key", "analysis_key"),
        Index(
            "ix_ca_results_project_date",
            "project_id",
            "business_date",
            postgresql_where=text("project_id IS NOT NULL"),
        ),
        Index(
            "ix_ca_results_account_window",
            "sec_uid",
            "window_end",
            postgresql_where=text("sec_uid IS NOT NULL"),
        ),
    )


class ContentAnalysisDelivery(Base):
    """独立于分析结果的飞书投递幂等状态。"""

    __tablename__ = "content_analysis_deliveries"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    document_key = Column(String(128), nullable=False, unique=True)
    target_directory = Column(Text, nullable=False)
    document_id = Column(String(256), nullable=True)
    document_url = Column(Text, nullable=True)
    status = Column(String(32), nullable=False)
    attempt_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    last_error = Column(Text, nullable=True)
    internal_result_ids = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    is_test = Column(Boolean, nullable=False, default=False, server_default=text("FALSE"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'success', 'failed')",
            name="ck_ca_deliveries_status",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_ca_deliveries_attempt_count",
        ),
    )


class ContentAnalysisLibraryItem(Base):
    """KolReference 的一对一结构化内容分析扩展。"""

    __tablename__ = "content_analysis_library_items"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    kol_reference_id = Column(
        BigInteger,
        ForeignKey("kol_references.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    project_id = Column(BigInteger, ForeignKey("kols.id", ondelete="CASCADE"), nullable=False)
    platform = Column(String(32), nullable=False, default="unknown", server_default="unknown")
    account_id = Column(String(128), nullable=True)
    platform_content_id = Column(String(256), nullable=True)
    external_url = Column(Text, nullable=True)
    category = Column(String(32), nullable=False)
    ingestion_source = Column(
        String(16), nullable=False, default="analysis", server_default="analysis"
    )
    analysis = Column(JSONB, nullable=False)
    project_assessment = Column(JSONB, nullable=False)
    latest_metrics = Column(JSONB, nullable=False)
    confidence = Column(String(32), nullable=False)
    priority = Column(Integer, nullable=True)
    opening_status = Column(String(32), nullable=False)
    opening_fragment = Column(Text, nullable=True)
    opening_unavailable_reason = Column(Text, nullable=True)
    availability = Column(String(16), nullable=False, default="enabled", server_default="enabled")
    latest_result_id = Column(
        BigInteger,
        ForeignKey("content_analysis_results.id"),
        nullable=True,
    )
    disabled_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "category IN ('persona', 'qianchuan')",
            name="ck_ca_library_category",
        ),
        CheckConstraint(
            "availability IN ('enabled', 'disabled')",
            name="ck_ca_library_availability",
        ),
        CheckConstraint(
            "ingestion_source IN ('analysis', 'manual')",
            name="ck_ca_library_ingestion_source",
        ),
        Index(
            "uq_ca_library_project_platform_content",
            "project_id",
            "platform_content_id",
            unique=True,
            postgresql_where=text("platform_content_id IS NOT NULL"),
        ),
        Index(
            "uq_ca_library_project_external_url",
            "project_id",
            "external_url",
            unique=True,
            postgresql_where=text("external_url IS NOT NULL"),
        ),
    )


class ContentAnalysisCrossProjectOpportunity(Base):
    """公司级规范化方法机会；不自动复制进任何项目库。"""

    __tablename__ = "content_analysis_cross_project_opportunities"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    method_key = Column(String(128), nullable=False, unique=True)
    method_payload = Column(JSONB, nullable=False)
    applicable_boundaries = Column(JSONB, nullable=False)
    sources = Column(JSONB, nullable=False)
    latest_result_id = Column(
        BigInteger,
        ForeignKey("content_analysis_results.id"),
        nullable=False,
    )
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class ContentAnalysisAccountBaseline(Base):
    """账号最近三十个完整自然日的人设点赞基准。"""

    __tablename__ = "content_analysis_account_baselines"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    sec_uid = Column(String(128), nullable=False)
    window_start = Column(TIMESTAMP(timezone=True), nullable=False)
    window_end = Column(TIMESTAMP(timezone=True), nullable=False)
    mean_likes = Column(Numeric(18, 4), nullable=True)
    median_likes = Column(Numeric(18, 4), nullable=True)
    sample_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    maximum_likes = Column(BigInteger, nullable=True)
    minimum_likes = Column(BigInteger, nullable=True)
    unavailable_reason = Column(Text, nullable=True)
    related_project_ids = Column(JSONB, nullable=False)
    latest_result_id = Column(
        BigInteger,
        ForeignKey("content_analysis_results.id"),
        nullable=False,
    )
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "sample_count >= 0",
            name="ck_ca_baseline_sample_count",
        ),
        CheckConstraint(
            "(sample_count = 0 AND unavailable_reason IS NOT NULL "
            "AND mean_likes IS NULL AND median_likes IS NULL "
            "AND maximum_likes IS NULL AND minimum_likes IS NULL) OR "
            "(sample_count > 0 AND unavailable_reason IS NULL "
            "AND mean_likes IS NOT NULL AND median_likes IS NOT NULL "
            "AND maximum_likes IS NOT NULL AND minimum_likes IS NOT NULL)",
            name="ck_ca_baseline_values",
        ),
        UniqueConstraint(
            "sec_uid",
            "window_start",
            "window_end",
            name="uq_ca_baseline_account_window",
        ),
    )
