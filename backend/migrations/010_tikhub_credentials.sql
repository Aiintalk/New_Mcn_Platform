-- TikHub 专用 Key 池，参考 credentials 表结构
CREATE TABLE IF NOT EXISTS tikhub_credentials (
  id              BIGSERIAL PRIMARY KEY,
  provider        VARCHAR(64)  NOT NULL DEFAULT 'tikhub',
  label           VARCHAR(128),
  api_key         TEXT         NOT NULL,
  base_url        VARCHAR(512) NOT NULL DEFAULT 'https://api.tikhub.io',
  status          VARCHAR(32)  NOT NULL DEFAULT 'active',  -- active/inactive
  active_requests INT          NOT NULL DEFAULT 0,
  max_concurrent  INT          NOT NULL DEFAULT 5,
  max_users       INT          NOT NULL DEFAULT 10,
  last_tested_at  TIMESTAMPTZ,
  last_latency_ms INT,
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_tikhub_credentials_status ON tikhub_credentials(status);
CREATE INDEX IF NOT EXISTS idx_tikhub_credentials_provider ON tikhub_credentials(provider);
