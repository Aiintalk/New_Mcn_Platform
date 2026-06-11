-- =====================================================================
-- 008_schema_catchup.sql
-- 补全 001~007 迁移中缺失的表和字段
-- 全部使用 IF NOT EXISTS，幂等安全，可重复执行
-- =====================================================================

-- ── 1. service_credentials（TikHub / OSS / ASR 等第三方密钥）──────────
CREATE TABLE IF NOT EXISTS service_credentials (
    id             BIGSERIAL PRIMARY KEY,
    provider       VARCHAR(64)  NOT NULL,
    label          VARCHAR(128) NOT NULL,
    secret_enc     TEXT         NOT NULL,
    secret_tail    VARCHAR(16)  NOT NULL,
    status         VARCHAR(32)  NOT NULL DEFAULT 'enabled',
    weight         INTEGER      NOT NULL DEFAULT 1,
    quota_limit    BIGINT,
    quota_used     BIGINT                DEFAULT 0,
    fail_count     INTEGER      NOT NULL DEFAULT 0,
    cooldown_until TIMESTAMPTZ,
    config         JSONB,
    created_by     BIGINT REFERENCES users(id),
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── 2. outputs（产出中心）────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS outputs (
    id           BIGSERIAL PRIMARY KEY,
    title        VARCHAR(255) NOT NULL,
    tool_code    VARCHAR(64)  NOT NULL,
    tool_name    VARCHAR(128) NOT NULL,
    task_id      BIGINT REFERENCES task_jobs(id),
    content      TEXT,
    content_json JSONB,
    word_count   INTEGER,
    file_id      BIGINT,
    created_by   BIGINT       NOT NULL REFERENCES users(id),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at   TIMESTAMPTZ
);

-- ── 3. files（文件记录）──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS files (
    id           BIGSERIAL PRIMARY KEY,
    filename     VARCHAR(255) NOT NULL,
    file_type    VARCHAR(64),
    file_size    BIGINT,
    oss_key      TEXT         NOT NULL,
    content_type VARCHAR(128),
    output_id    BIGINT REFERENCES outputs(id),
    task_id      BIGINT REFERENCES task_jobs(id),
    created_by   BIGINT       NOT NULL REFERENCES users(id),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at   TIMESTAMPTZ
);

-- ── 4. tool_sessions（工具会话）──────────────────────────────────────
CREATE TABLE IF NOT EXISTS tool_sessions (
    id           BIGSERIAL PRIMARY KEY,
    tool_code    VARCHAR(64)  NOT NULL,
    current_step VARCHAR(64),
    context      JSONB,
    drafts       JSONB,
    messages     JSONB,
    status       VARCHAR(32)  NOT NULL DEFAULT 'draft',
    created_by   BIGINT       NOT NULL REFERENCES users(id),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── 5. external_service_logs（第三方服务调用日志）───────────────────
CREATE TABLE IF NOT EXISTS external_service_logs (
    id            BIGSERIAL PRIMARY KEY,
    service       VARCHAR(64)  NOT NULL,
    action        VARCHAR(128) NOT NULL,
    task_id       BIGINT REFERENCES task_jobs(id),
    credential_id BIGINT REFERENCES service_credentials(id),
    request_body  JSONB,
    response_body JSONB,
    tokens_in     INTEGER,
    tokens_out    INTEGER,
    tokens_used   INTEGER,
    credits       NUMERIC,
    audio_seconds INTEGER,
    duration_ms   INTEGER,
    status        VARCHAR(32)  NOT NULL,
    error_code    VARCHAR(128),
    error_message TEXT,
    request_hash  VARCHAR(128),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── 6. kols 表补字段（001_init.sql 建表时缺少的列）────────────────────
ALTER TABLE kols ADD COLUMN IF NOT EXISTS account_name   VARCHAR(128);
ALTER TABLE kols ADD COLUMN IF NOT EXISTS sec_uid        VARCHAR(128);
ALTER TABLE kols ADD COLUMN IF NOT EXISTS avatar_url     TEXT;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS signature      TEXT;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS follower_count BIGINT;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS video_count    INTEGER;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS owner          VARCHAR(128);
ALTER TABLE kols ADD COLUMN IF NOT EXISTS tikhub_raw     JSONB;

-- ── 7. workspace_tools 补字段 ────────────────────────────────────────
ALTER TABLE workspace_tools ADD COLUMN IF NOT EXISTS config JSONB;

-- ── 完成提示 ──────────────────────────────────────────────────────────
DO $$
BEGIN
  RAISE NOTICE '✅ 008_schema_catchup 执行完成';
END
$$;
