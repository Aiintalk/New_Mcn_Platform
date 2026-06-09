-- =====================================================================
-- MCN Platform — AI 管理模块建表脚本
-- =====================================================================

-- credentials：AI Key 池
CREATE TABLE IF NOT EXISTS credentials (
  id              BIGSERIAL PRIMARY KEY,
  provider        VARCHAR(64)  NOT NULL,
  label           VARCHAR(128),
  api_key         TEXT         NOT NULL,
  base_url        VARCHAR(512),
  status          VARCHAR(32)  NOT NULL DEFAULT 'active',
  active_requests INT          NOT NULL DEFAULT 0,
  max_concurrent  INT          NOT NULL DEFAULT 5,
  max_users       INT          NOT NULL DEFAULT 10,
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_credentials_provider_status ON credentials(provider, status);
CREATE TRIGGER trg_credentials_updated
  BEFORE UPDATE ON credentials
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ai_models：可用模型配置
CREATE TABLE IF NOT EXISTS ai_models (
  id         BIGSERIAL PRIMARY KEY,
  name       VARCHAR(128) NOT NULL,
  provider   VARCHAR(64)  NOT NULL DEFAULT 'yunwu',
  model_id   VARCHAR(128) NOT NULL UNIQUE,
  status     VARCHAR(32)  NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_ai_models_updated
  BEFORE UPDATE ON ai_models
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ai_call_logs：调用明细日志
CREATE TABLE IF NOT EXISTS ai_call_logs (
  id            BIGSERIAL PRIMARY KEY,
  user_id       BIGINT REFERENCES users(id),
  feature       VARCHAR(128),
  model_id      VARCHAR(128),
  credential_id BIGINT REFERENCES credentials(id),
  input_tokens  INT,
  output_tokens INT,
  latency_ms    INT,
  status        VARCHAR(32)  NOT NULL DEFAULT 'success',
  error_message TEXT,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ai_call_logs_created_at   ON ai_call_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_call_logs_credential   ON ai_call_logs(credential_id);
CREATE INDEX IF NOT EXISTS idx_ai_call_logs_model_id     ON ai_call_logs(model_id);
CREATE INDEX IF NOT EXISTS idx_ai_call_logs_user_feature ON ai_call_logs(user_id, feature);
