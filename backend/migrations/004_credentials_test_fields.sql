-- credentials 表加测试结果字段
ALTER TABLE credentials ADD COLUMN IF NOT EXISTS last_tested_at  TIMESTAMPTZ;
ALTER TABLE credentials ADD COLUMN IF NOT EXISTS last_latency_ms INTEGER;
