-- Sprint 25：用正式达人编号串联人格定位与入驻资料。
-- 旧记录保持 kol_id 为 NULL，不按姓名回填。

BEGIN;

ALTER TABLE persona_reports
    ADD COLUMN IF NOT EXISTS kol_id BIGINT;

ALTER TABLE kol_intake_links
    ADD COLUMN IF NOT EXISTS kol_id BIGINT;

ALTER TABLE kol_intake_operator_sessions
    ADD COLUMN IF NOT EXISTS kol_id BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'persona_reports'::regclass
          AND conname = 'fk_persona_reports_kol_id'
    ) THEN
        ALTER TABLE persona_reports
            ADD CONSTRAINT fk_persona_reports_kol_id
            FOREIGN KEY (kol_id) REFERENCES kols(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'kol_intake_links'::regclass
          AND conname = 'fk_kol_intake_links_kol_id'
    ) THEN
        ALTER TABLE kol_intake_links
            ADD CONSTRAINT fk_kol_intake_links_kol_id
            FOREIGN KEY (kol_id) REFERENCES kols(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'kol_intake_operator_sessions'::regclass
          AND conname = 'fk_kol_intake_operator_sessions_kol_id'
    ) THEN
        ALTER TABLE kol_intake_operator_sessions
            ADD CONSTRAINT fk_kol_intake_operator_sessions_kol_id
            FOREIGN KEY (kol_id) REFERENCES kols(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_persona_reports_kol
    ON persona_reports(kol_id);
CREATE INDEX IF NOT EXISTS idx_kol_intake_links_kol
    ON kol_intake_links(kol_id);
CREATE INDEX IF NOT EXISTS idx_kol_intake_operator_sessions_kol
    ON kol_intake_operator_sessions(kol_id);

COMMIT;
