-- Sprint28 内容分析执行结果、投递、项目库、跨项目机会与账号基准。
-- 仅建已批准的五类持久化；完整不可变正文保存在 outputs.content_json。

CREATE TABLE IF NOT EXISTS content_analysis_results (
    id BIGSERIAL PRIMARY KEY,
    result_key VARCHAR(128) NOT NULL UNIQUE,
    analysis_key VARCHAR(128) NOT NULL,
    task_id BIGINT NOT NULL REFERENCES task_jobs(id),
    task_code VARCHAR(64) NOT NULL,
    run_type VARCHAR(16) NOT NULL CHECK (run_type IN ('auto', 'test', 'retry')),
    execution_kind VARCHAR(32) NOT NULL
        CHECK (execution_kind IN ('project', 'account', 'weekly_batch_finalize')),
    project_id BIGINT REFERENCES kols(id),
    sec_uid VARCHAR(128),
    related_project_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    business_date DATE NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    context_versions JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_receipts JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(32) NOT NULL CHECK (status IN ('success', 'no_content')),
    output_id BIGINT NOT NULL UNIQUE REFERENCES outputs(id),
    is_test BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (window_start < window_end),
    CHECK (
        (execution_kind = 'project' AND project_id IS NOT NULL AND sec_uid IS NULL)
        OR (execution_kind = 'account' AND project_id IS NULL AND sec_uid IS NOT NULL)
        OR (execution_kind = 'weekly_batch_finalize' AND project_id IS NULL AND sec_uid IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS ix_ca_results_analysis_key
    ON content_analysis_results (analysis_key);
CREATE INDEX IF NOT EXISTS ix_ca_results_project_date
    ON content_analysis_results (project_id, business_date DESC)
    WHERE project_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_ca_results_account_window
    ON content_analysis_results (sec_uid, window_end DESC)
    WHERE sec_uid IS NOT NULL;

CREATE TABLE IF NOT EXISTS content_analysis_deliveries (
    id BIGSERIAL PRIMARY KEY,
    document_key VARCHAR(128) NOT NULL UNIQUE,
    target_directory TEXT NOT NULL,
    document_id VARCHAR(256),
    document_url TEXT,
    status VARCHAR(32) NOT NULL CHECK (status IN ('pending', 'success', 'failed')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_error TEXT,
    internal_result_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_test BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS content_analysis_library_items (
    id BIGSERIAL PRIMARY KEY,
    kol_reference_id BIGINT NOT NULL UNIQUE REFERENCES kol_references(id) ON DELETE CASCADE,
    project_id BIGINT NOT NULL REFERENCES kols(id) ON DELETE CASCADE,
    platform VARCHAR(32) NOT NULL DEFAULT 'unknown',
    account_id VARCHAR(128),
    platform_content_id VARCHAR(256),
    external_url TEXT,
    category VARCHAR(32) NOT NULL CHECK (category IN ('persona', 'qianchuan')),
    ingestion_source VARCHAR(16) NOT NULL DEFAULT 'analysis'
        CHECK (ingestion_source IN ('analysis', 'manual')),
    analysis JSONB NOT NULL,
    project_assessment JSONB NOT NULL,
    latest_metrics JSONB NOT NULL,
    confidence VARCHAR(32) NOT NULL,
    priority INTEGER,
    opening_status VARCHAR(32) NOT NULL,
    opening_fragment TEXT,
    opening_unavailable_reason TEXT,
    availability VARCHAR(16) NOT NULL DEFAULT 'enabled'
        CHECK (availability IN ('enabled', 'disabled')),
    latest_result_id BIGINT REFERENCES content_analysis_results(id),
    disabled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ca_library_project_platform_content
    ON content_analysis_library_items (project_id, platform_content_id)
    WHERE platform_content_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_ca_library_project_external_url
    ON content_analysis_library_items (project_id, external_url)
    WHERE external_url IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_ca_library_project_category_availability
    ON content_analysis_library_items (project_id, category, availability);

CREATE TABLE IF NOT EXISTS content_analysis_cross_project_opportunities (
    id BIGSERIAL PRIMARY KEY,
    method_key VARCHAR(128) NOT NULL UNIQUE,
    method_payload JSONB NOT NULL,
    applicable_boundaries JSONB NOT NULL,
    sources JSONB NOT NULL,
    latest_result_id BIGINT NOT NULL REFERENCES content_analysis_results(id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS content_analysis_account_baselines (
    id BIGSERIAL PRIMARY KEY,
    sec_uid VARCHAR(128) NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    mean_likes NUMERIC(18, 4),
    median_likes NUMERIC(18, 4),
    sample_count INTEGER NOT NULL DEFAULT 0 CHECK (sample_count >= 0),
    maximum_likes BIGINT,
    minimum_likes BIGINT,
    unavailable_reason TEXT,
    related_project_ids JSONB NOT NULL,
    latest_result_id BIGINT NOT NULL REFERENCES content_analysis_results(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_ca_baseline_account_window UNIQUE (sec_uid, window_start, window_end),
    CHECK (
        (sample_count = 0 AND unavailable_reason IS NOT NULL
            AND mean_likes IS NULL AND median_likes IS NULL
            AND maximum_likes IS NULL AND minimum_likes IS NULL)
        OR
        (sample_count > 0 AND unavailable_reason IS NULL
            AND mean_likes IS NOT NULL AND median_likes IS NOT NULL
            AND maximum_likes IS NOT NULL AND minimum_likes IS NOT NULL)
    )
);
