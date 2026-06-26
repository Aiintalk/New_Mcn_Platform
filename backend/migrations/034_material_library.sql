-- 034_material_library.sql
-- 素材库（material-library）工具：2 张表 + soul_generator Prompt + workspace_tools 上线
-- soul.md / content-plan.md 复用 kols.persona / kols.content_plan 字段，不新建 profile 表

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. kol_references（红人参考素材 — 6 种类型手动录入）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kol_references (
    id          BIGSERIAL PRIMARY KEY,
    kol_id      BIGINT NOT NULL REFERENCES kols(id) ON DELETE CASCADE,
    title       VARCHAR(500) NOT NULL,
    likes       INT,
    source      VARCHAR(100) DEFAULT '抖音',
    type        VARCHAR(50) NOT NULL,   -- 红人爆款文案/红人喜欢的内容/风格参考/千川爆款文案/千川喜欢的内容/千川风格参考
    content     TEXT NOT NULL,
    created_by  BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_kol_references_kol_type   ON kol_references(kol_id, type) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_kol_references_kol_recent ON kol_references(kol_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_kol_references_created_by ON kol_references(created_by);

-- ---------------------------------------------------------------------------
-- 2. material_library_configs（管理端 AI 配置 — soul_generator Prompt + 模型）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS material_library_configs (
    id            BIGSERIAL PRIMARY KEY,
    config_key    VARCHAR(64) NOT NULL UNIQUE,
    ai_model_id   BIGINT REFERENCES ai_models(id) ON DELETE SET NULL,
    system_prompt TEXT,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 3. 种子 Prompt：soul_generator（从入驻问卷数据生成人格档案初稿）
--    占位符：
--      {{kol_name}}         → 红人名
--      {{intake_answers}}   → 入驻问卷回答（JSON 格式化文本）
--      {{intake_report}}    → 入驻问卷 AI 分析报告
-- ---------------------------------------------------------------------------
INSERT INTO material_library_configs (config_key, ai_model_id, system_prompt, is_active)
VALUES (
    'soul_generator',
    -- claude-sonnet-4-6（ai_models id=3，平衡速度和质量）
    3,
    $PROMPT_SOUL$你是一位资深的人设定位专家，擅长为抖音达人打造有辨识度、有权威感、有温度的人格档案。

你的任务：根据以下红人入驻问卷数据和 AI 分析报告，生成一份完整的人格档案（soul.md）。

## 输出格式（严格按此结构，用 Markdown）

# {{kol_name}} · 人格档案

## 一、一句话定位
**（用一句加粗的话概括达人的核心价值主张，要有冲突感和记忆点）**

## 二、基本信息
（用表格列出：年龄、城市、家庭、教育背景、职业经历、账号定位、粉丝量级、内容赛道、商业模式、客单价等——从问卷数据提取，没有的留空）

## 三、人设内核

### 3.1 权威来源
（从经历中提炼 2-3 个权威维度，每个维度标注适用场景）

### 3.2 与用户的关系
（达人 vs 粉丝的关系定位：是闺蜜/导师/过来人/内行人？）

### 3.3 差异化锚点
（与同类达人相比，不可复制的独特优势）

## 四、经历素材库
（将问卷中的职业经历、独特经历分类整理，标注每条经历适合的内容场景）

## 五、说话风格
（从问卷的"说话风格"字段 + AI 报告推断：语气、措辞习惯、表达节奏）

## 六、禁区
（从问卷的"绝不做的内容"字段提取，列出内容红线）

---
注意：
- 每个section必须有实质内容，不要留空或写"暂无"
- 如果某个字段问卷中没有，用你的专业知识合理推断并标注"(推断)"
- 语言要有力度，像写给运营团队的作战手册，不像机器生成的模板
- 总字数控制在 3000-5000 字

## 红人名
{{kol_name}}

## 入驻问卷回答
{{intake_answers}}

## AI 分析报告
{{intake_report}}$PROMPT_SOUL$,
    TRUE
)
ON CONFLICT (config_key) DO UPDATE SET
    ai_model_id   = EXCLUDED.ai_model_id,
    system_prompt = EXCLUDED.system_prompt,
    is_active     = EXCLUDED.is_active,
    updated_at    = NOW();

-- ---------------------------------------------------------------------------
-- 4. workspace_tools：material-library 注册（dev 状态，测试通过后改 online）
-- ---------------------------------------------------------------------------
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, sort_order)
VALUES (
    'material-library',
    '素材库',
    '内容工作台',
    '红人素材中枢：人格档案（soul.md）+ 内容规划 + 参考素材管理（6种类型）+ 入驻问卷AI生成初稿',
    'dev',
    130
)
ON CONFLICT (tool_code) DO UPDATE SET
    tool_name   = EXCLUDED.tool_name,
    category    = EXCLUDED.category,
    description = EXCLUDED.description;

COMMIT;
