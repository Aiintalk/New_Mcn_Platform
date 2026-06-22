-- service_credentials 表加测试结果字段（OSS 凭证测试端点保存）
ALTER TABLE service_credentials ADD COLUMN IF NOT EXISTS last_tested_at  TIMESTAMPTZ;
ALTER TABLE service_credentials ADD COLUMN IF NOT EXISTS last_latency_ms INTEGER;
