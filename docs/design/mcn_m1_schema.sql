-- =====================================================================
-- MCN 内容工作台 M1 — 数据库基线建表脚本 (PostgreSQL)
-- 第一部分：核心表（原方案 10 张，kols 与 kol_profiles 合并后为 9 张）（字段为按交互图/API 推导的基线设计）
-- 第二部分：地基期建议一并创建的 2 张增补表（来自《架构变更增补 v1》）
-- 注：标有「增补」的列是为避免日后 ALTER 而提前预留，可按需删减。
-- 建表顺序已按外键依赖排好，可从上到下直接执行。
-- =====================================================================

-- 通用：自动维护 updated_at 的触发器函数
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;


-- =====================================================================
-- 第一部分：9 张核心表
-- =====================================================================

-- 1) users 用户账号、角色、密码、状态
CREATE TABLE users (
  id                  BIGSERIAL PRIMARY KEY,
  username            VARCHAR(64)  NOT NULL UNIQUE,
  password_hash       VARCHAR(255) NOT NULL,
  name                VARCHAR(64),
  role                VARCHAR(16)  NOT NULL DEFAULT 'operator',  -- admin / operator
  status              VARCHAR(16)  NOT NULL DEFAULT 'enabled',   -- enabled / disabled
  password_changed_at TIMESTAMPTZ,                               -- NULL = 首次登录需强制改密
  token_version       INT          NOT NULL DEFAULT 0,           -- 增补：登出/改密自增使旧 JWT 失效
  last_login_at       TIMESTAMPTZ,
  created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 2) workspace_tools 内容工作台工具配置
CREATE TABLE workspace_tools (
  id          BIGSERIAL PRIMARY KEY,
  tool_code   VARCHAR(64)  NOT NULL UNIQUE,                -- persona-writer 等
  name        VARCHAR(64)  NOT NULL,
  category    VARCHAR(32),
  description TEXT,
  status      VARCHAR(16)  NOT NULL DEFAULT 'dev',          -- online / dev / archived / disabled
  config      JSONB        NOT NULL DEFAULT '{}'::jsonb,     -- 增补：阈值等 {like_threshold, opening_timeout_sec}
  sort_order  INT          NOT NULL DEFAULT 0,
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_tools_updated BEFORE UPDATE ON workspace_tools
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 3) kols 红人管理（基础数据 + 人格档案，合并原 kols 与 kol_profiles）
CREATE TABLE kols (
  id           BIGSERIAL PRIMARY KEY,
  name         VARCHAR(64)  NOT NULL,
  category     VARCHAR(32),                                  -- 品类：美妆护肤 等
  platform     VARCHAR(32)  DEFAULT 'douyin',
  external_id  VARCHAR(128),                                 -- 平台账号标识（可选）
  avatar_url   VARCHAR(512),                                 -- 头像（可选）
  persona      TEXT,                                         -- 人格档案 / 人设描述
  content_plan TEXT,                                         -- 内容规划文本（前 8 行用于风格预览）
  style_notes  TEXT,                                         -- 风格备注：语速、开头/结尾习惯等
  status       VARCHAR(16)  NOT NULL DEFAULT 'active',        -- active / archived
  created_by   BIGINT       REFERENCES users(id),
  created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_kols_status ON kols(status);
CREATE TRIGGER trg_kols_updated BEFORE UPDATE ON kols
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 4) task_jobs 工具任务记录（一次工具会话 = 一个 job）
CREATE TABLE task_jobs (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT       NOT NULL REFERENCES users(id),
  tool_code   VARCHAR(64)  NOT NULL,
  status      VARCHAR(16)  NOT NULL DEFAULT 'pending',       -- pending/processing/success/failed/cancelled
  input       JSONB        NOT NULL DEFAULT '{}'::jsonb,
  error_msg   TEXT,
  started_at  TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_task_jobs_user   ON task_jobs(user_id, created_at DESC);
CREATE INDEX idx_task_jobs_status ON task_jobs(status);

-- 5) task_logs 任务执行日志
CREATE TABLE task_logs (
  id         BIGSERIAL PRIMARY KEY,
  task_id    BIGINT       NOT NULL REFERENCES task_jobs(id) ON DELETE CASCADE,
  step       VARCHAR(32),                                   -- verify/analyze/generate/rewrite/export
  level      VARCHAR(8)   NOT NULL DEFAULT 'info',           -- info / warn / error
  message    TEXT,
  meta       JSONB        NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_task_logs_task ON task_logs(task_id);

-- 6) outputs 工具最终产出
CREATE TABLE outputs (
  id         BIGSERIAL PRIMARY KEY,
  task_id    BIGINT       REFERENCES task_jobs(id),
  user_id    BIGINT       NOT NULL REFERENCES users(id),
  tool_code  VARCHAR(64)  NOT NULL,
  kol_id     BIGINT       REFERENCES kols(id),
  title      VARCHAR(255),
  content    TEXT         NOT NULL,                          -- 终稿正文
  word_count INT,
  status     VARCHAR(16)  NOT NULL DEFAULT 'final',          -- final / draft
  created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_outputs_user ON outputs(user_id, created_at DESC);
CREATE TRIGGER trg_outputs_updated BEFORE UPDATE ON outputs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 7) files Word 导出文件和附件记录
CREATE TABLE files (
  id         BIGSERIAL PRIMARY KEY,
  output_id  BIGINT       REFERENCES outputs(id) ON DELETE CASCADE,
  user_id    BIGINT       NOT NULL REFERENCES users(id),
  file_name  VARCHAR(255) NOT NULL,
  file_type  VARCHAR(32),                                   -- docx 等
  oss_key    VARCHAR(512) NOT NULL,                          -- 对象存储 key（非公开 URL；下载时换签名 URL）
  size_bytes BIGINT,
  created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_files_output ON files(output_id);

-- 8) operation_logs 用户操作日志
CREATE TABLE operation_logs (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT       REFERENCES users(id),             -- 系统行为可为 NULL
  action      VARCHAR(64)  NOT NULL,                         -- login / create_user / export / tool_online ...
  target_type VARCHAR(32),
  target_id   VARCHAR(64),
  detail      JSONB        NOT NULL DEFAULT '{}'::jsonb,
  ip          VARCHAR(64),
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_op_logs_user ON operation_logs(user_id, created_at DESC);
CREATE INDEX idx_op_logs_action ON operation_logs(action);

-- 9) external_service_logs AI / TikHub / OSS / ASR 调用日志
CREATE TABLE external_service_logs (
  id            BIGSERIAL PRIMARY KEY,
  user_id       BIGINT       REFERENCES users(id),
  task_id       BIGINT       REFERENCES task_jobs(id),
  service       VARCHAR(16)  NOT NULL,                       -- ai / tikhub / oss / asr
  endpoint      VARCHAR(128),                                -- 增补：TikHub 接口 / OSS 操作
  model         VARCHAR(64),                                 -- 增补：AI 型号
  tokens_in     INT,                                         -- 增补
  tokens_out    INT,                                         -- 增补
  credits       INT,                                         -- 增补：TikHub 积分增量
  audio_seconds INT,                                         -- 增补：ASR 音频时长
  duration_ms   INT,                                         -- 调用耗时
  status        VARCHAR(16)  NOT NULL DEFAULT 'success',      -- success / timeout / failed
  error_msg     TEXT,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_ext_logs_service ON external_service_logs(service, created_at DESC);
CREATE INDEX idx_ext_logs_task    ON external_service_logs(task_id);


-- =====================================================================
-- 第二部分：地基期建议一并创建的 2 张增补表
-- 理由：表结构是地基，最不该后补；提前建好可避免 M1 中途迁移。
-- =====================================================================

-- 工具会话 / 草稿持久化（人设仿写多步状态的落点；P0）
CREATE TABLE tool_sessions (
  id         BIGSERIAL PRIMARY KEY,
  user_id    BIGINT       NOT NULL REFERENCES users(id),
  tool_code  VARCHAR(64)  NOT NULL,
  status     VARCHAR(16)  NOT NULL DEFAULT 'active',          -- active / finalized / abandoned
  step       VARCHAR(32),                                     -- select_kol/verify/generate/rewrite/done
  context    JSONB        NOT NULL DEFAULT '{}'::jsonb,        -- kol_id、对标解析、结构分析、参数
  drafts     JSONB        NOT NULL DEFAULT '[]'::jsonb,        -- [{version, content, created_at}]
  messages   JSONB        NOT NULL DEFAULT '[]'::jsonb,        -- 多轮修改对话历史
  output_id  BIGINT       REFERENCES outputs(id),              -- finalize 后回填
  created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_tool_sessions_user ON tool_sessions(user_id, status);
CREATE TRIGGER trg_tool_sessions_updated BEFORE UPDATE ON tool_sessions
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 把 task_jobs 关联到会话（建完 tool_sessions 后补这一列）
ALTER TABLE task_jobs ADD COLUMN session_id BIGINT REFERENCES tool_sessions(id);

-- 密钥池（AI/TikHub/ASR 多 key 轮换；OSS 单组凭证可不入池）
CREATE TABLE service_credentials (
  id             BIGSERIAL PRIMARY KEY,
  provider       VARCHAR(32)  NOT NULL,                       -- ai / tikhub / asr / oss
  label          VARCHAR(64)  NOT NULL,
  secret_enc     TEXT         NOT NULL,                        -- 加密密文
  secret_tail    VARCHAR(8)   NOT NULL,                        -- 后四位，仅展示
  status         VARCHAR(16)  NOT NULL DEFAULT 'enabled',      -- enabled / disabled / cooldown
  weight         INT          NOT NULL DEFAULT 1,
  quota_used     BIGINT       DEFAULT 0,
  quota_limit    BIGINT,
  fail_count     INT          NOT NULL DEFAULT 0,
  cooldown_until TIMESTAMPTZ,
  last_used_at   TIMESTAMPTZ,
  created_by     BIGINT       REFERENCES users(id),
  created_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_cred_provider_status ON service_credentials(provider, status);

-- 让 external_service_logs 记录用了哪把 key（便于按 key 统计与排障）
ALTER TABLE external_service_logs
  ADD COLUMN credential_id BIGINT REFERENCES service_credentials(id);
