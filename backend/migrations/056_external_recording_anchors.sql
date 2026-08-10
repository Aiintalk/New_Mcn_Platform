-- 056_external_recording_anchors.sql
-- 对标账号补充远程录屏同步所需的原始输入与 TikHub 标识。

ALTER TABLE kol_benchmarks ADD COLUMN IF NOT EXISTS account_input TEXT;
ALTER TABLE kol_benchmarks ADD COLUMN IF NOT EXISTS sec_uid VARCHAR(128);
ALTER TABLE kol_benchmarks ADD COLUMN IF NOT EXISTS avatar_url TEXT;
ALTER TABLE kol_benchmarks ADD COLUMN IF NOT EXISTS follower_count BIGINT;

CREATE INDEX IF NOT EXISTS idx_kol_benchmarks_account_type
    ON kol_benchmarks(account_type);

CREATE INDEX IF NOT EXISTS idx_kol_benchmarks_sec_uid
    ON kol_benchmarks(sec_uid)
    WHERE sec_uid IS NOT NULL;

DO $$
BEGIN
  RAISE NOTICE '056_external_recording_anchors 执行完成';
END
$$;
