-- 007_kol_intake_operator_sessions.sql
-- 运营直发对话会话表（不走分享链接）

CREATE TABLE kol_intake_operator_sessions (
    id                  SERIAL PRIMARY KEY,
    operator_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kol_name            VARCHAR(200),
    messages            JSONB NOT NULL DEFAULT '[]',
    ai_report           TEXT,
    ai_report_raw       JSONB,
    report_status       VARCHAR(20) NOT NULL DEFAULT 'pending',
    report_generated_at TIMESTAMPTZ,
    docx_path           VARCHAR(500),
    pdf_path            VARCHAR(500),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_kol_intake_operator_sessions_operator
    ON kol_intake_operator_sessions(operator_id);

CREATE TRIGGER set_updated_at_kol_intake_operator_sessions
    BEFORE UPDATE ON kol_intake_operator_sessions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
