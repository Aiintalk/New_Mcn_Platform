-- 026_tiktok_review.sql
-- tiktok-review 工具：配置表 + workspace_tools 注册 + 默认 Prompt

-- ============================================================
-- 表：tiktok_review_configs
-- ============================================================
CREATE TABLE IF NOT EXISTS tiktok_review_configs (
    id            SERIAL PRIMARY KEY,
    config_key    VARCHAR(50)  NOT NULL UNIQUE,
    ai_model_id   INTEGER REFERENCES ai_models(id) ON DELETE SET NULL,
    system_prompt TEXT,
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_tiktok_review_configs_updated ON tiktok_review_configs;
CREATE TRIGGER trg_tiktok_review_configs_updated
    BEFORE UPDATE ON tiktok_review_configs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- workspace_tools 注册
-- ============================================================
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, tags, sort_order)
VALUES (
    'tiktok-review',
    'TT内容复盘',
    '内容创作',
    '上传/粘贴两条TikTok视频文案（原版爆款+仿写版），AI从7个维度对比分析差距，输出流式复盘报告，支持导出Word',
    'dev',
    '["AI生成","TikTok","复盘","内容分析","docx"]'::jsonb,
    16
)
ON CONFLICT (tool_code) DO NOTHING;

-- ============================================================
-- 默认配置（含旧工具 SYSTEM_PROMPT）
-- ============================================================
INSERT INTO tiktok_review_configs (config_key, system_prompt, is_active)
VALUES (
    'default',
    '你是一个TikTok爆款内容分析专家，精通短视频算法机制、内容策略和跨平台差异。

你的任务是对比分析两条TikTok视频——一条是爆款原版，一条是仿写版——找出仿写版没爆的原因，并给出具体可执行的改进建议。

请从以下7个维度进行**逐项对比分析**：

1. **开头钩子（前3秒）**：TikTok算法最看重的完播率起点。两版的开头设计有什么区别？哪个更有吸引力？
2. **人设/身份背书**：两个创作者的身份标签和可信度差异
3. **标题策略**：标题的点击欲望对比（TT的标题影响推荐）
4. **内容节奏**：语速、信息密度、停顿感、转场节奏
5. **视觉呈现**：场景、构图、画面信息量、产品展示方式
6. **情绪价值**：观众看完后得到了什么？有没有争议性/互动性？
7. **平台适配**：TT和ins的算法/用户偏好差异分析

**输出格式要求**：
- 每个维度先分析原版，再分析仿写版，最后给出对比结论
- 分析完7个维度后，输出「核心问题诊断」（3-5个最关键的问题）
- 最后输出「具体改进建议」（不要泛泛而谈，要具体到"下一条视频应该怎么改"）

用中文输出。',
    true
)
ON CONFLICT (config_key) DO NOTHING;
