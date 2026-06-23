-- 030_qianchuan_writer.sql
-- 千川文案写作（qianchuan-writer）工具：配置表 + 种子 Prompt + workspace_tools 注册

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. qianchuan_writer_configs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS qianchuan_writer_configs (
    id            BIGSERIAL PRIMARY KEY,
    config_key    VARCHAR(64) NOT NULL UNIQUE,
    system_prompt TEXT,
    ai_model_id   BIGINT REFERENCES ai_models(id) ON DELETE SET NULL,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 2. 种子 Prompt（从旧架构 page.tsx:93-113 buildSystemPrompt 改造）
--    模板占位符：
--      {{name}}         → kols.name（达人人设名）
--      {{soul}}         → kols.persona（人设/灵魂档案全文）
--      {{content_plan}} → kols.content_plan（内容规划，供 AI 参考达人定位）
--    注：原版 ${product} 为前端传入的产品文本，由 messages 携带，不入 system_prompt。
-- ---------------------------------------------------------------------------
INSERT INTO qianchuan_writer_configs (config_key, system_prompt, ai_model_id, is_active)
VALUES (
    'default',
    $PROMPT$你是一个千川脚本仿写专家。任务：把原版脚本改写成「{{name}}」视角的仿写版本。

## {{name}} 人物档案
{{soul}}

## {{name}} 内容规划参考
{{content_plan}}

## 仿写铁律（必须严格执行）
1. 结构完全不变：句式结构、段落顺序、整体框架100%保留
2. 字数只能相同或更少，绝对不能更多
3. 开头99%原封不动：只有当原版开头出现的人物/产品与{{name}}身份直接冲突时，才最多换一两个字，其他情况一字不改
4. 产品全部替换：把原版中所有产品信息、卖点，替换成用户提供的「{{name}}产品卖点」里对应的卖点，只从用户给定的卖点中取，不自己编造、不添加
5. 人物视角换成{{name}}：原版里的其他网红/人物换成{{name}}本人的第一人称视角，结合人物档案中的真实经历做替换

直接输出仿写后的完整脚本，不要解释，不要加任何注释或标注。$PROMPT$,
    NULL,
    TRUE
)
ON CONFLICT (config_key) DO UPDATE SET
    system_prompt = EXCLUDED.system_prompt,
    ai_model_id = EXCLUDED.ai_model_id,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- ---------------------------------------------------------------------------
-- 3. workspace_tools 注册
-- ---------------------------------------------------------------------------
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, sort_order)
VALUES (
    'qianchuan-writer',
    '千川文案写作',
    '脚本创作',
    '围绕达人视角的千川脚本仿写工具：选达人人设 + 上传产品卖点 + 粘贴原版脚本，AI 保留原结构 100% 产出仿写版本',
    'dev',
    100
)
ON CONFLICT (tool_code) DO UPDATE SET
    tool_name = EXCLUDED.tool_name,
    category = EXCLUDED.category,
    description = EXCLUDED.description;

COMMIT;
