-- ASR 调用日志表（阿里云智能语音交互 - 录音文件识别）
CREATE TABLE IF NOT EXISTS asr_call_logs (
  id            BIGSERIAL PRIMARY KEY,
  credential_id BIGINT       NOT NULL REFERENCES service_credentials(id) ON DELETE SET NULL,
  user_id       BIGINT       REFERENCES users(id) ON DELETE SET NULL,  -- nullable: 系统调用无用户上下文
  operation     VARCHAR(16)  NOT NULL,  -- submit / query
  status        VARCHAR(32)  NOT NULL,  -- success / fail
  latency_ms    INT,
  task_id       TEXT,                   -- ASR 任务 ID（阿里云 SubmitTask 返回）
  audio_url     TEXT,                   -- 输入音频 URL（submit 时记录）
  error_message TEXT,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_asr_call_logs_credential ON asr_call_logs(credential_id);
CREATE INDEX IF NOT EXISTS idx_asr_call_logs_user       ON asr_call_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_asr_call_logs_operation  ON asr_call_logs(operation);
CREATE INDEX IF NOT EXISTS idx_asr_call_logs_status     ON asr_call_logs(status);
CREATE INDEX IF NOT EXISTS idx_asr_call_logs_created_at ON asr_call_logs(created_at);
