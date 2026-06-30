-- 达人在售商品关联（多对多：kol ↔ qianchuan_product）
CREATE TABLE IF NOT EXISTS kol_active_products (
    id         BIGSERIAL PRIMARY KEY,
    kol_id     BIGINT NOT NULL REFERENCES kols(id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL REFERENCES qianchuan_products(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (kol_id, product_id)
);
CREATE INDEX IF NOT EXISTS idx_kol_active_products_kol_id
    ON kol_active_products(kol_id);
CREATE INDEX IF NOT EXISTS idx_kol_active_products_product_id
    ON kol_active_products(product_id);
