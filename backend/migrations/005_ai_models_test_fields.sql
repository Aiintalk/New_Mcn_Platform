-- ai_models 表加测试结果字段
ALTER TABLE ai_models ADD COLUMN IF NOT EXISTS last_tested_at  TIMESTAMPTZ;
ALTER TABLE ai_models ADD COLUMN IF NOT EXISTS last_latency_ms INTEGER;
