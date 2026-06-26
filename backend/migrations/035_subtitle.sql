-- 035_subtitle.sql
-- 字幕提取（subtitle-extractor）迁移 - Sprint 19
-- 旧架构：Ai_Toolbox/subtitle-extractor-web（Next.js + SQLite）
-- 新架构：subtitle_jobs + subtitle_items + subtitle_configs（PostgreSQL）
-- 公共服务走 adapter（tikhub / oss / asr / yunwu），思维导图 Prompt 上提到管理端可配

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. subtitle_jobs — 批量字幕任务表（参照旧 batch_jobs）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS subtitle_jobs (
  id           BIGSERIAL PRIMARY KEY,
  job_code     VARCHAR(32) NOT NULL UNIQUE,    -- 服务端生成（如 sub_20260625_a1b2c3d4）
  status       VARCHAR(16) NOT NULL DEFAULT 'processing',  -- processing / completed / failed
  phase        VARCHAR(64) NOT NULL DEFAULT '',            -- 当前阶段描述（用于前端展示）
  total        INT NOT NULL DEFAULT 0,
  success      INT NOT NULL DEFAULT 0,
  failed       INT NOT NULL DEFAULT 0,
  created_by   BIGINT REFERENCES users(id) ON DELETE SET NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subtitle_jobs_created_by ON subtitle_jobs(created_by);
CREATE INDEX IF NOT EXISTS idx_subtitle_jobs_status     ON subtitle_jobs(status);
CREATE INDEX IF NOT EXISTS idx_subtitle_jobs_created_at ON subtitle_jobs(created_at DESC);

-- ---------------------------------------------------------------------------
-- 2. subtitle_items — 批量任务条目（参照旧 batch_items）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS subtitle_items (
  id            BIGSERIAL PRIMARY KEY,
  job_id        BIGINT NOT NULL REFERENCES subtitle_jobs(id) ON DELETE CASCADE,
  row_number    INT NOT NULL,
  original_url  TEXT NOT NULL DEFAULT '',       -- 原始分享文本/链接
  title         TEXT NOT NULL DEFAULT '',       -- 视频标题（解析后填充）
  transcript    TEXT NOT NULL DEFAULT '',       -- 字幕文本（ASR 成功后填充）
  status        VARCHAR(16) NOT NULL DEFAULT 'pending',  -- pending / processing / success / failed
  error         TEXT NOT NULL DEFAULT '',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (job_id, row_number)
);

CREATE INDEX IF NOT EXISTS idx_subtitle_items_job   ON subtitle_items(job_id);
CREATE INDEX IF NOT EXISTS idx_subtitle_items_status ON subtitle_items(status);

-- ---------------------------------------------------------------------------
-- 3. subtitle_configs — 管理端配置（思维导图 Prompt + AI 模型）
--    占位符：{{transcript}} → 用户字幕文本
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS subtitle_configs (
  id                BIGSERIAL PRIMARY KEY,
  config_key        VARCHAR(64) NOT NULL UNIQUE,
  mindmap_prompt    TEXT,
  mindmap_model_id  BIGINT REFERENCES ai_models(id) ON DELETE SET NULL,
  is_active         BOOLEAN NOT NULL DEFAULT TRUE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 4. seed 默认思维导图 Prompt（参照旧 app/api/mindmap/route.ts::MINDMAP_SYSTEM_PROMPT）
--    默认模型：claude-haiku-4-5-20251001（ai_models.id=2，速度快、成本低，适合结构化输出）
-- ---------------------------------------------------------------------------
INSERT INTO subtitle_configs (config_key, mindmap_prompt, mindmap_model_id, is_active)
VALUES (
  'default',
  $PROMPT_MINDMAP$你是一名内容运营专家，擅长分析短视频脚本结构。
请根据以下视频字幕文案，从运营视角提炼出思维导图结构。
你必须严格输出合法 JSON，不要输出任何其他内容，不要添加 markdown 代码块标记。
JSON格式如下：
{
  "rootTitle": "视频核心主题（一句话）",
  "summary": "一句话总结整体内容",
  "branches": [
    {
      "title": "开头钩子",
      "children": ["子要点1", "子要点2"]
    }
  ]
}
参考维度：开头钩子、用户痛点、核心卖点、内容逻辑、转化动作、可复用建议。
每个维度如与视频内容不符可省略，但至少输出 3 个维度。

## 输入字幕
{{transcript}}$PROMPT_MINDMAP$,
  2,
  TRUE
)
ON CONFLICT (config_key) DO UPDATE SET
  mindmap_prompt   = EXCLUDED.mindmap_prompt,
  mindmap_model_id = EXCLUDED.mindmap_model_id,
  is_active        = EXCLUDED.is_active,
  updated_at       = NOW();

-- ---------------------------------------------------------------------------
-- 5. workspace_tools.subtitle: dev → online
--    原 sort_order=5（早期占位），调到 140（与 material-library 的 130 同档）
-- ---------------------------------------------------------------------------
UPDATE workspace_tools
SET status     = 'online',
    sort_order = 140,
    tool_name  = '字幕提取',
    category   = '内容工作台',
    description = '抖音视频字幕提取（单条/批量）+ 思维导图分析 + 多格式导出',
    updated_at = NOW()
WHERE tool_code = 'subtitle';

COMMIT;
