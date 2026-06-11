-- 009_persona_positioning.sql
-- 人格定位报告（persona-positioning）迁移

-- 1. 人格定位报告存档
CREATE TABLE IF NOT EXISTS persona_reports (
    id                  SERIAL PRIMARY KEY,
    operator_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Step 1 输入
    douyin_id           VARCHAR(200),               -- 用户填写的抖音号或链接（原始输入）
    douyin_nickname     VARCHAR(200),               -- TikHub 解析出的账号昵称
    top10_text          TEXT,                       -- TikHub 返回的 TOP10 视频文案
    recent30_text       TEXT,                       -- TikHub 返回的最近30天视频文案
    questionnaire_files JSONB DEFAULT '[]',         -- 上传的问卷文件列表 [{filename, text}]
    supplement_text     TEXT,                       -- 补充备注（文本输入）
    supplement_files    JSONB DEFAULT '[]',         -- 上传的补充资料文件列表 [{filename, text}]

    -- Step 2 输入（对标资料，可选）
    benchmark_profile_files  JSONB DEFAULT '[]',   -- 对标人格档案文件列表 [{filename, text}]
    benchmark_plan_files     JSONB DEFAULT '[]',   -- 对标内容规划文件列表 [{filename, text}]

    -- Step 3 生成结果
    profile_result      TEXT,                       -- 人格档案（===SPLIT=== 前）
    plan_result         TEXT,                       -- 内容规划（===SPLIT=== 后）
    raw_output          TEXT,                       -- AI 原始完整输出（含 ===SPLIT===）
    influencer_name     VARCHAR(200),               -- 从 AI 输出或输入中提取的达人名字

    -- 文件路径
    profile_docx_path   VARCHAR(500),               -- storage/persona_reports/{id}_profile.docx
    plan_docx_path      VARCHAR(500),               -- storage/persona_reports/{id}_plan.docx

    -- 状态
    status              VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- pending / generating / ready / failed
    generated_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ                 -- 软删除
);

CREATE INDEX IF NOT EXISTS idx_persona_reports_operator ON persona_reports(operator_id);
CREATE INDEX IF NOT EXISTS idx_persona_reports_status   ON persona_reports(status);


-- 2. AI 配置（persona_generation）
INSERT INTO kol_intake_configs (config_key, system_prompt)
VALUES ('persona_generation', NULL)
ON CONFLICT (config_key) DO NOTHING;
-- ai_model_id 初始 NULL，管理员在后台绑定
-- system_prompt：管理员在后台填入（从旧架构 generate/route.ts 的 SYSTEM_PROMPT 常量复制）


-- 3. 注册到功能管理（workspace_tools）
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, tags, sort_order)
VALUES (
    'persona-positioning',
    '人格定位',
    '内容策划',
    '输入达人资料 → AI 生成人格档案 + 内容规划，支持导出 Word',
    'dev',
    '["AI生成","人格档案","内容规划","docx","TikHub"]'::jsonb,
    20
)
ON CONFLICT (tool_code) DO NOTHING;
