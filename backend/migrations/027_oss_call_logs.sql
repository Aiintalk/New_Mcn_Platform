-- OSS 调用日志表
CREATE TABLE IF NOT EXISTS oss_call_logs (
  id            BIGSERIAL PRIMARY KEY,
  credential_id BIGINT       NOT NULL REFERENCES service_credentials(id) ON DELETE SET NULL,
  user_id       BIGINT       REFERENCES users(id) ON DELETE SET NULL,  -- nullable: 系统调用无用户上下文
  operation     VARCHAR(16)  NOT NULL,  -- upload / download / delete
  status        VARCHAR(32)  NOT NULL,  -- success / fail
  latency_ms    INT,
  oss_key       TEXT,
  error_message TEXT,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_oss_call_logs_credential ON oss_call_logs(credential_id);
CREATE INDEX IF NOT EXISTS idx_oss_call_logs_user       ON oss_call_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_oss_call_logs_operation  ON oss_call_logs(operation);
CREATE INDEX IF NOT EXISTS idx_oss_call_logs_status     ON oss_call_logs(status);
CREATE INDEX IF NOT EXISTS idx_oss_call_logs_created_at ON oss_call_logs(created_at);
