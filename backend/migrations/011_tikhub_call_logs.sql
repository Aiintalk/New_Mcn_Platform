-- TikHub 调用日志表
CREATE TABLE IF NOT EXISTS tikhub_call_logs (
  id            BIGSERIAL PRIMARY KEY,
  credential_id BIGINT       NOT NULL REFERENCES tikhub_credentials(id) ON DELETE SET NULL,
  user_id       BIGINT       REFERENCES users(id) ON DELETE SET NULL,  -- nullable: 系统调用无用户上下文
  platform      VARCHAR(64)  NOT NULL,  -- douyin/instagram/youtube 等
  endpoint      VARCHAR(64)  NOT NULL,  -- user_profile/fans_info/live_products 等
  status        VARCHAR(32)  NOT NULL,  -- success/failure
  latency_ms    INT,
  error_message TEXT,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_tikhub_call_logs_credential ON tikhub_call_logs(credential_id);
CREATE INDEX IF NOT EXISTS idx_tikhub_call_logs_user ON tikhub_call_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_tikhub_call_logs_platform ON tikhub_call_logs(platform);
CREATE INDEX IF NOT EXISTS idx_tikhub_call_logs_endpoint ON tikhub_call_logs(endpoint);
CREATE INDEX IF NOT EXISTS idx_tikhub_call_logs_created_at ON tikhub_call_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_tikhub_call_logs_status ON tikhub_call_logs(status);
