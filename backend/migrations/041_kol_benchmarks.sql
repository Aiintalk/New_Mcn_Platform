-- 达人对标账号（工作台首页展示，与 benchmark_analyses 独立）
CREATE TABLE IF NOT EXISTS kol_benchmarks (
    id           BIGSERIAL PRIMARY KEY,
    kol_id       BIGINT NOT NULL REFERENCES kols(id) ON DELETE CASCADE,
    account_name VARCHAR(200) NOT NULL,
    account_type VARCHAR(20)  NOT NULL CHECK (account_type IN ('content','livestream')),
    description  TEXT,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    created_by   BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kol_benchmarks_kol_id ON kol_benchmarks(kol_id);
CREATE TRIGGER trg_kol_benchmarks_updated
    BEFORE UPDATE ON kol_benchmarks
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
