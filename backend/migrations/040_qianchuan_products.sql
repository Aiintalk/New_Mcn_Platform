-- 千川产品库（千川直播带货场景，与 seeding_writer_products 独立）
CREATE TABLE IF NOT EXISTS qianchuan_products (
    id                   BIGSERIAL PRIMARY KEY,
    nickname             VARCHAR(100) NOT NULL,
    core_selling_point   VARCHAR(200),
    visualization        TEXT,
    mechanism            TEXT,
    mechanism_exclusive  BOOLEAN NOT NULL DEFAULT FALSE,
    endorsement          TEXT,
    user_feedback        TEXT,
    unique_selling       TEXT,
    awards               VARCHAR(500),
    efficacy_proof       TEXT,
    created_by           BIGINT REFERENCES users(id) ON DELETE SET NULL,
    deleted_at           TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_qianchuan_products_nickname
    ON qianchuan_products(nickname) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_qianchuan_products_created_by
    ON qianchuan_products(created_by);
CREATE TRIGGER trg_qianchuan_products_updated
    BEFORE UPDATE ON qianchuan_products
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
