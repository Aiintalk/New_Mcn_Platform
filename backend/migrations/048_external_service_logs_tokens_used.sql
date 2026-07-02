-- 048_external_service_logs_tokens_used.sql
-- 补 external_service_logs.tokens_used 列
--
-- 背景：001_init.sql 建表时未包含 tokens_used；008_schema_catchup.sql 用
-- CREATE TABLE IF NOT EXISTS 重建，但表已存在故跳过，该列从未被加入。
-- yunwu adapter 写日志时引用该列导致 SQL 报错，错误混入流式响应末尾显示给用户。

BEGIN;

ALTER TABLE external_service_logs
  ADD COLUMN IF NOT EXISTS tokens_used INTEGER;

COMMIT;
