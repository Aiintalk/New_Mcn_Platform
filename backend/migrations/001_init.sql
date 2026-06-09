-- =====================================================================
-- MCN Information System Platform M1 — 建表脚本
-- 数据库：mcn_m1
-- =====================================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

-- 1. users
CREATE TABLE users (
  id                  BIGSERIAL PRIMARY KEY,
  username            VARCHAR(64)   NOT NULL,
  real_name           VARCHAR(64)   NOT NULL,
  password_hash       TEXT          NOT NULL,
  role                VARCHAR(32)   NOT NULL DEFAULT 'operator',
  status              VARCHAR(32)   NOT NULL DEFAULT 'enabled',
  password_changed_at TIMESTAMPTZ,
  token_version       INT           NOT NULL DEFAULT 0,
  last_login_at       TIMESTAMPTZ,
  last_active_at      TIMESTAMPTZ,
  created_by          BIGINT,
  created_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
  deleted_at          TIMESTAMPTZ
);
CREATE UNIQUE INDEX idx_users_username ON users(username) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_role_status ON users(role, status);
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 2. workspace_tools
CREATE TABLE workspace_tools (
  id          BIGSERIAL PRIMARY KEY,
  tool_code   VARCHAR(64)   NOT NULL,
  tool_name   VARCHAR(128)  NOT NULL,
  category    VARCHAR(64),
  description TEXT,
  status      VARCHAR(32)   NOT NULL DEFAULT 'dev',
  tags        JSONB,
  config      JSONB,
  sort_order  INT           NOT NULL DEFAULT 0,
  created_at  TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX idx_workspace_tools_code ON workspace_tools(tool_code);
CREATE INDEX idx_workspace_tools_status ON workspace_tools(status);
CREATE TRIGGER trg_tools_updated BEFORE UPDATE ON workspace_tools
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 3. kols
CREATE TABLE kols (
  id           BIGSERIAL PRIMARY KEY,
  name         VARCHAR(128)  NOT NULL,
  category     VARCHAR(64),
  platform     VARCHAR(32)   DEFAULT 'douyin',
  external_id  VARCHAR(128),
  douyin_id    VARCHAR(128),
  avatar_url   TEXT,
  persona      TEXT,
  content_plan TEXT,
  style_notes  TEXT,
  owner_id     BIGINT        REFERENCES users(id),
  status       VARCHAR(32)   NOT NULL DEFAULT 'active',
  created_by   BIGINT        REFERENCES users(id),
  created_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
  deleted_at   TIMESTAMPTZ
);
CREATE INDEX idx_kols_status ON kols(status) WHERE deleted_at IS NULL;
CREATE TRIGGER trg_kols_updated BEFORE UPDATE ON kols
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 4. tool_sessions
CREATE TABLE tool_sessions (
  id           BIGSERIAL PRIMARY KEY,
  tool_code    VARCHAR(64)   NOT NULL,
  current_step VARCHAR(64),
  context      JSONB,
  drafts       JSONB,
  messages     JSONB,
  status       VARCHAR(32)   NOT NULL DEFAULT 'draft',
  created_by   BIGINT        NOT NULL REFERENCES users(id),
  created_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX idx_tool_sessions_user ON tool_sessions(created_by, status);
CREATE TRIGGER trg_sessions_updated BEFORE UPDATE ON tool_sessions
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 5. task_jobs
CREATE TABLE task_jobs (
  id             BIGSERIAL PRIMARY KEY,
  task_no        VARCHAR(64)   NOT NULL,
  tool_code      VARCHAR(64)   NOT NULL,
  tool_name      VARCHAR(128)  NOT NULL,
  status         VARCHAR(32)   NOT NULL DEFAULT 'pending',
  input_payload  JSONB,
  result_summary JSONB,
  error_code     VARCHAR(128),
  error_message  TEXT,
  session_id     BIGINT        REFERENCES tool_sessions(id),
  output_id      BIGINT,
  created_by     BIGINT        NOT NULL REFERENCES users(id),
  started_at     TIMESTAMPTZ,
  finished_at    TIMESTAMPTZ,
  duration_ms    INT,
  created_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX idx_task_jobs_no ON task_jobs(task_no);
CREATE INDEX idx_task_jobs_created_by ON task_jobs(created_by);
CREATE INDEX idx_task_jobs_tool_status ON task_jobs(tool_code, status);
CREATE INDEX idx_task_jobs_created_at ON task_jobs(created_at DESC);
CREATE TRIGGER trg_task_jobs_updated BEFORE UPDATE ON task_jobs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 6. task_logs
CREATE TABLE task_logs (
  id         BIGSERIAL PRIMARY KEY,
  task_id    BIGINT        NOT NULL REFERENCES task_jobs(id) ON DELETE CASCADE,
  step_code  VARCHAR(64)   NOT NULL,
  step_name  VARCHAR(128)  NOT NULL,
  status     VARCHAR(32)   NOT NULL,
  message    TEXT,
  payload    JSONB,
  created_at TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX idx_task_logs_task_id ON task_logs(task_id);

-- 7. outputs
CREATE TABLE outputs (
  id           BIGSERIAL PRIMARY KEY,
  title        VARCHAR(255)  NOT NULL,
  tool_code    VARCHAR(64)   NOT NULL,
  tool_name    VARCHAR(128)  NOT NULL,
  task_id      BIGINT        REFERENCES task_jobs(id),
  content      TEXT,
  content_json JSONB,
  word_count   INT,
  file_id      BIGINT,
  created_by   BIGINT        NOT NULL REFERENCES users(id),
  created_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
  deleted_at   TIMESTAMPTZ
);
CREATE INDEX idx_outputs_created_by ON outputs(created_by);
CREATE INDEX idx_outputs_created_at ON outputs(created_at DESC);
CREATE TRIGGER trg_outputs_updated BEFORE UPDATE ON outputs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 8. files
CREATE TABLE files (
  id           BIGSERIAL PRIMARY KEY,
  filename     VARCHAR(255)  NOT NULL,
  file_type    VARCHAR(64),
  file_size    BIGINT,
  oss_key      TEXT          NOT NULL,
  content_type VARCHAR(128),
  output_id    BIGINT        REFERENCES outputs(id),
  task_id      BIGINT        REFERENCES task_jobs(id),
  created_by   BIGINT        NOT NULL REFERENCES users(id),
  created_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
  deleted_at   TIMESTAMPTZ
);
CREATE INDEX idx_files_created_by ON files(created_by);
CREATE INDEX idx_files_output_id ON files(output_id);

-- 9. operation_logs
CREATE TABLE operation_logs (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT        REFERENCES users(id),
  username    VARCHAR(64),
  role        VARCHAR(32),
  action      VARCHAR(128)  NOT NULL,
  target_type VARCHAR(64),
  target_id   BIGINT,
  detail      JSONB,
  ip          VARCHAR(64),
  user_agent  TEXT,
  created_at  TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX idx_op_logs_user_id ON operation_logs(user_id);
CREATE INDEX idx_op_logs_action ON operation_logs(action);
CREATE INDEX idx_op_logs_created_at ON operation_logs(created_at DESC);

-- 10. external_service_logs
CREATE TABLE external_service_logs (
  id             BIGSERIAL PRIMARY KEY,
  service        VARCHAR(64)   NOT NULL,
  action         VARCHAR(128)  NOT NULL,
  task_id        BIGINT        REFERENCES task_jobs(id),
  credential_id  BIGINT,
  request_body   JSONB,
  response_body  JSONB,
  tokens_in      INT,
  tokens_out     INT,
  credits        NUMERIC,
  audio_seconds  INT,
  duration_ms    INT,
  status         VARCHAR(32)   NOT NULL,
  error_code     VARCHAR(128),
  error_message  TEXT,
  request_hash   VARCHAR(128),
  created_at     TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX idx_external_logs_service ON external_service_logs(service);
CREATE INDEX idx_external_logs_task_id ON external_service_logs(task_id);
CREATE INDEX idx_external_logs_created_at ON external_service_logs(created_at DESC);

-- 11. service_credentials
CREATE TABLE service_credentials (
  id             BIGSERIAL PRIMARY KEY,
  provider       VARCHAR(64)   NOT NULL,
  label          VARCHAR(128)  NOT NULL,
  secret_enc     TEXT          NOT NULL,
  secret_tail    VARCHAR(16)   NOT NULL,
  status         VARCHAR(32)   NOT NULL DEFAULT 'enabled',
  weight         INT           NOT NULL DEFAULT 1,
  quota_limit    BIGINT,
  quota_used     BIGINT        DEFAULT 0,
  fail_count     INT           NOT NULL DEFAULT 0,
  cooldown_until TIMESTAMPTZ,
  created_by     BIGINT        REFERENCES users(id),
  created_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX idx_cred_provider_status ON service_credentials(provider, status);
CREATE TRIGGER trg_credentials_updated BEFORE UPDATE ON service_credentials
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE external_service_logs ADD CONSTRAINT fk_ext_logs_credential
  FOREIGN KEY (credential_id) REFERENCES service_credentials(id);

-- SEED：workspace_tools 初始数据
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, tags, sort_order) VALUES
  ('persona-writer', '人设脚本仿写', '脚本创作', '选择达人 → 对标验证 → 智能仿写 → 导出文档', 'online',  '["智能生成","视频解析","文档导出"]'::jsonb, 1),
  ('benchmark',      '对标分析助手', '选题分析', '拆解对标视频结构与爆点节奏',                 'dev',     '["智能生成"]'::jsonb,                     2),
  ('qianchuan',      '千川工具组',   '投放',     '千川投放辅助工具',                           'dev',     '[]'::jsonb,                               3),
  ('review',         '复盘工具组',   '数据复盘', '内容复盘与数据分析',                         'dev',     '[]'::jsonb,                               4),
  ('subtitle',       '字幕提取',     '素材处理', '音视频字幕自动提取',                         'dev',     '[]'::jsonb,                               5);
