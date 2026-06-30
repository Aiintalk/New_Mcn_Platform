-- kol_workspace_configs：红人工作台个性化配置（Sprint 23）
-- 每个红人一条记录，控制工作台 tab 显示 + 各 AI 模块专属 Prompt

CREATE TABLE IF NOT EXISTS kol_workspace_configs (
    id               BIGSERIAL PRIMARY KEY,
    kol_id           BIGINT NOT NULL UNIQUE REFERENCES kols(id) ON DELETE CASCADE,
    enabled_tabs     JSONB NOT NULL DEFAULT
        '["dashboard","persona","references","products","qianchuan-writer",
          "seeding-writer","persona-writer","livestream-writer","livestream-review",
          "values-writer","script-review","retrospective"]'::jsonb,
    prompt_overrides JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kol_workspace_configs_kol_id
    ON kol_workspace_configs(kol_id);

CREATE TRIGGER trg_kol_workspace_configs_updated
    BEFORE UPDATE ON kol_workspace_configs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
