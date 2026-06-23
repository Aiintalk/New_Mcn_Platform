-- 032_kols_unique_douyin_id.sql
-- 对 kols.douyin_id 和 kols.sec_uid 加部分唯一索引，防止重复添加红人。
-- 参照 001_init.sql:28 idx_users_username 模式（WHERE deleted_at IS NULL）。
-- 空字符串和 NULL 都不参与唯一性约束（多条空值允许，与 users.username 惯例一致）。

CREATE UNIQUE INDEX IF NOT EXISTS idx_kols_douyin_id_unique
  ON kols(douyin_id)
  WHERE deleted_at IS NULL AND douyin_id IS NOT NULL AND douyin_id <> '';

CREATE UNIQUE INDEX IF NOT EXISTS idx_kols_sec_uid_unique
  ON kols(sec_uid)
  WHERE deleted_at IS NULL AND sec_uid IS NOT NULL AND sec_uid <> '';
