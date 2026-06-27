-- 千川脚本预审配置表（Sprint 21）
CREATE TABLE IF NOT EXISTS qianchuan_script_review_configs (
    id              BIGSERIAL PRIMARY KEY,
    config_key      VARCHAR(64) NOT NULL UNIQUE,
    direct_prompt   TEXT,
    value_prompt    TEXT,
    ai_model_id     BIGINT REFERENCES ai_models(id) ON DELETE SET NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_qianchuan_script_review_configs_updated
    BEFORE UPDATE ON qianchuan_script_review_configs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

INSERT INTO qianchuan_script_review_configs (config_key, is_active)
VALUES ('default', TRUE)
ON CONFLICT (config_key) DO NOTHING;
