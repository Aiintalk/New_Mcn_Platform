-- 031_persona_writer.sql
-- 人设脚本仿写（persona-writer）工具：配置表 + 4 种子 Prompt + workspace_tools 上线

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. persona_writer_configs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS persona_writer_configs (
    id                BIGSERIAL PRIMARY KEY,
    config_key        VARCHAR(64) NOT NULL UNIQUE,
    evaluation_prompt TEXT,
    analysis_prompt   TEXT,
    writing_prompt    TEXT,
    iteration_prompt  TEXT,
    light_model_id    BIGINT REFERENCES ai_models(id) ON DELETE SET NULL,
    heavy_model_id    BIGINT REFERENCES ai_models(id) ON DELETE SET NULL,
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 2. 种子 Prompt（从旧架构 persona-writer-web/app/page.tsx 提取改造）
--    模板占位符：
--      {{name}}              → kols.name（达人人设名）
--      {{soul}}              → kols.persona（人设/灵魂档案全文）
--      {{content_plan}}      → kols.content_plan（内容规划）
--      {{transcript}}        → 对标文案（evaluate/analyze/writing/iteration 全用）
--      {{structure_analysis}} → Step 3.1 拆解结果（writing/iteration 用）
--      {{topic}}             → 选题（writing 用）
--      {{is_custom}}         → 'true' / 'false'（writing_prompt 内部 if-else 分支）
--    注：原版 ${selectedPersona.soul} / ${transcript} 等前端变量已转为 {{var}} 后端模板。
--    模型名 qwen-flash / claude-opus 已移除（用 light_model_id / heavy_model_id 字段）。
-- ---------------------------------------------------------------------------

INSERT INTO persona_writer_configs (
    config_key,
    evaluation_prompt,
    analysis_prompt,
    writing_prompt,
    iteration_prompt,
    light_model_id,
    heavy_model_id,
    is_active
)
VALUES (
    'default',

    -- ===== evaluation_prompt（Step 2.4 开头吸引力评估，light 模型）=====
    $PROMPT_EVAL$你是一个短视频内容质量评估专家。评估以下短视频文案的开头（前3-5句）是否有足够的吸引力让普通人停下来观看。评估标准：1.前3句是否制造了好奇心、冲突感或情感共鸣 2.一个完全无关的普通人刷到会不会停下来 3.如果需要特定背景知识才能被吸引则不通过。给出"通过"或"不通过"判断和一句话理由。格式：判断：通过/不通过
理由：xxx

对标文案：
{{transcript}}$PROMPT_EVAL$,

    -- ===== analysis_prompt（Step 3.1 结构拆解，light 模型）=====
    $PROMPT_ANALYSIS$你是一个短视频脚本结构分析专家。快速拆解以下脚本的骨架结构。格式：
1. 开头（完整引用原文前2-3句）
2. 主体段落：逐段列出功能和大约字数
3. 收束方式
4. 原文总字数
5. 预估时长
不要添加评论，只输出结构拆解。

对标文案：
{{transcript}}$PROMPT_ANALYSIS$,

    -- ===== writing_prompt（Step 3.3 写作，heavy 模型，含 {{is_custom}} 双模式分支）=====
    -- 双模式语法：
    --   {{is_custom}}...{{/is_custom}}       → is_custom=true 时保留，false 时移除
    --   {{!is_custom}}...{{/!is_custom}}     → is_custom=false 时保留，true 时移除
    $PROMPT_WRITING$你是一个专业的人设内容仿写助手。直接输出，不要提问，不要确认。

## 三条铁律（硬性，必须满足）
1. 写完整脚本：从开头到结尾完整输出，系统后续会让员工替换开头。
2. 结构参考对标原文：对标原文的段落结构、节奏、逻辑关系作为骨架参考。{{is_custom}}但员工的选题想法是核心，结构为想法服务，可以根据想法适当调整段落。{{/is_custom}}{{!is_custom}}仿写必须一一对应，不能加段、不能删段、不能调换顺序。{{/!is_custom}}
3. 字数只少不多：对标原文多少字，仿写就不能超过这个字数。宁可少10%，绝不多1%。

## 优先级（从高到低）
{{is_custom}}1. 员工的选题想法——员工写的内容、观点、素材是第一位的，必须100%忠实呈现，不能改写员工的核心意思
2. 对标结构——借鉴对标文案的段落结构和节奏，但为员工的想法服务
3. 达人风格——用达人的语气和调性来包装员工的想法{{/is_custom}}
{{!is_custom}}1. 原文结构——对标文案的段落结构、节奏、逻辑链条是第一位的，必须极致一致
2. 分析结果——对标结构分析揭示了为什么这篇爆，仿写要保住这些爆点
3. 人格档案——辅助参考，了解达人调性即可，不要被它框住{{/!is_custom}}

## 创作指南
{{is_custom}}员工的选题想法是你的创作核心。你的任务是用达人的风格和对标文案的结构，把员工的想法写成一篇完整的短视频口播稿。员工写了什么就用什么，不要自作主张改变员工的观点、素材或表达方向。{{/is_custom}}
{{!is_custom}}铁律之外，放开写。你的首要任务是写出有信息差、有金句、让人想看完的内容。{{/!is_custom}}
- 口语化：短视频口播稿，像说话不像写作
- 素材来源不限于达人本人经历——可以用达人朋友的故事、最近的热点事件、明星案例、社会现象，只要能支撑论点就行
- 不是每篇都需要个人经历，有信息差和洞察比硬塞经历更重要
- 纯内容绝不出现产品/品牌名
- 结尾笃定收束
- 不说教："我想明白了"可以，"你应该明白"不行

## 参考材料（辅助，不是束缚）
以下材料帮你了解这个达人是谁、她的调性是什么。写作时可以参考，但不要被它们框住——金句、信息差、打动人的表达才是第一位的。

### 达人档案
{{soul}}

### 达人内容规划
{{content_plan}}

## 对标文案
{{transcript}}

## 对标结构分析
{{structure_analysis}}

## 选题
{{topic}}

## 输出格式
先输出 ===脚本开始=== 标记，然后输出完整脚本（从开头到结尾），然后输出 ===脚本结束=== 标记。
标记之后再附上：
- 总字数 | 对标原文字数 | 是否达标
- 三条铁律自检表（markdown表格）{{!is_custom}}
- 原创度自检：逐段对比对标原文和你的仿写，列出相似度高的句子。如果整体文字重复率超过50%，标红提醒。{{/!is_custom}}$PROMPT_WRITING$,

    -- ===== iteration_prompt（Step 3.4 多轮追问，heavy 模型）=====
    $PROMPT_ITER$你是一个专业的人设内容仿写助手，正在帮员工迭代脚本。

## 铁律（硬性）
1. 写完整脚本——从开头到结尾完整输出
2. 结构完全一致——保持对标原文的段落结构
3. 字数只少不多——不能超过对标原文字数

## 优先级
原文结构 > 分析结果 > 人格档案（辅助参考）

铁律之外放开写，写出有信息差、有金句、让人想看完的内容。素材不限于达人本人——朋友的故事、热点事件、明星案例都可以用。

## 参考材料（辅助）
### 达人档案
{{soul}}

### 达人内容规划
{{content_plan}}

### 对标文案
{{transcript}}

### 对标结构分析
{{structure_analysis}}

员工说哪里不对就改哪里，不动没问题的部分。每次输出时用 ===脚本开始=== 和 ===脚本结束=== 包裹完整脚本正文，标记之后再附自检表。不要提问，直接改。$PROMPT_ITER$,

    -- light_model_id：claude-haiku-4-5-20251001（ai_models id=2）
    2,
    -- heavy_model_id：claude-opus-4-6（ai_models id=4）
    4,
    TRUE
)
ON CONFLICT (config_key) DO UPDATE SET
    evaluation_prompt = EXCLUDED.evaluation_prompt,
    analysis_prompt   = EXCLUDED.analysis_prompt,
    writing_prompt    = EXCLUDED.writing_prompt,
    iteration_prompt  = EXCLUDED.iteration_prompt,
    light_model_id    = EXCLUDED.light_model_id,
    heavy_model_id    = EXCLUDED.heavy_model_id,
    is_active         = EXCLUDED.is_active,
    updated_at        = NOW();

-- ---------------------------------------------------------------------------
-- 3. workspace_tools：persona-writer 上线（旧表已有 status='disabled' 记录）
-- ---------------------------------------------------------------------------
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, sort_order)
VALUES (
    'persona-writer',
    '人设脚本仿写',
    '脚本创作',
    '基于达人风格 + 对标视频的脚本仿写工具：3步向导（加载风格 → 对标验证 → 仿写创作）',
    'online',
    110
)
ON CONFLICT (tool_code) DO UPDATE SET
    tool_name   = EXCLUDED.tool_name,
    category    = EXCLUDED.category,
    description = EXCLUDED.description,
    status      = 'online';

COMMIT;
