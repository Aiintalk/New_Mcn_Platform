-- values_writer_configs：价值观仿写配置表（Sprint 20）
CREATE TABLE IF NOT EXISTS values_writer_configs (
    id                        BIGSERIAL PRIMARY KEY,
    config_key                VARCHAR(64) NOT NULL UNIQUE,
    extract_values_prompt     TEXT,
    emotion_direction_prompt  TEXT,
    writing_prompt            TEXT,
    iteration_prompt          TEXT,
    model_id                  BIGINT REFERENCES ai_models(id) ON DELETE SET NULL,
    is_active                 BOOLEAN NOT NULL DEFAULT TRUE,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_values_writer_configs_updated
    BEFORE UPDATE ON values_writer_configs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 插入默认配置（带最简种子 Prompt）
INSERT INTO values_writer_configs (config_key, is_active)
VALUES ('default', TRUE)
ON CONFLICT (config_key) DO NOTHING;
