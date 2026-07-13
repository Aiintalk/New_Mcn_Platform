-- 每名红人只能保留一个当前商品。
-- 如历史数据存在多条关联，本迁移明确中止，避免自动删除运营选择。

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM kol_active_products
        GROUP BY kol_id
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'kol_active_products 存在同一红人的多个当前商品；请先人工确认并清理重复关联后重试迁移';
    END IF;
END $$;

ALTER TABLE kol_active_products
    ADD CONSTRAINT uq_kol_active_products_kol UNIQUE (kol_id);

COMMIT;
