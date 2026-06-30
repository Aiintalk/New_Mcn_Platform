-- retrospective_configs：复盘 AI 配置（Sprint 22）
CREATE TABLE IF NOT EXISTS retrospective_configs (
    id              BIGSERIAL PRIMARY KEY,
    config_key      VARCHAR(64) NOT NULL UNIQUE,
    system_prompt   TEXT,
    ai_model_id     BIGINT REFERENCES ai_models(id) ON DELETE SET NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TRIGGER trg_retrospective_configs_updated
    BEFORE UPDATE ON retrospective_configs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
INSERT INTO retrospective_configs (config_key, is_active)
VALUES ('default', TRUE)
ON CONFLICT (config_key) DO NOTHING;

-- retrospective_sessions：复盘记录表（Sprint 22）
CREATE TABLE IF NOT EXISTS retrospective_sessions (
    id               BIGSERIAL PRIMARY KEY,
    kol_id           BIGINT NOT NULL REFERENCES kols(id) ON DELETE CASCADE,
    created_by       BIGINT REFERENCES users(id) ON DELETE SET NULL,
    title            VARCHAR(200) NOT NULL,
    status           VARCHAR(20)  NOT NULL DEFAULT 'draft',   -- draft / done
    live_data        TEXT,
    material_data    TEXT,
    review_text      TEXT,
    live_script      TEXT,
    material_scripts JSONB,
    result           TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_retrospective_sessions_kol_id ON retrospective_sessions(kol_id);
CREATE TRIGGER trg_retrospective_sessions_updated
    BEFORE UPDATE ON retrospective_sessions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
