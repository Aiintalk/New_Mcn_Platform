-- 053_eval_core.sql
-- AIGC 工具回归测试评价体系 — Phase 1 数据层（11 张 eval_ 表 + 索引 + seed）
-- spec: docs/superpowers/specs/2026-07-20-aigc-evaluation-system-design.md §5.4 / §5.5
--
-- 说明：
--   * 独立 eval_ 前缀，与现有业务表物理隔离。
--   * 主数据表（dimensions/test_cases/versions/schedule_policies/strategies/judge_models）
--     用 deleted_at 软删；runs 历史记录不软删。
--   * 部分唯一索引（PG15+ NULLS NOT DISTINCT）防重复 seed + 同维度同场景同 level 重复。
--   * seed 维度权重为占位值（TBD 安雅草拟确认后调）。

-- ============================================================================
-- 1. eval_dimensions — 评分维度
-- ============================================================================
CREATE TABLE IF NOT EXISTS eval_dimensions (
    id              BIGSERIAL PRIMARY KEY,
    tool_code       VARCHAR(64)  NOT NULL,
    name            VARCHAR(64)  NOT NULL,
    display_name    VARCHAR(128),
    description     TEXT,
    default_weight  DECIMAL(5,4) NOT NULL,
    score_min       SMALLINT     NOT NULL DEFAULT 1,
    score_max       SMALLINT     NOT NULL DEFAULT 10,
    prompt_template TEXT,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_eval_dimensions_tool_active_deleted
    ON eval_dimensions (tool_code, is_active, deleted_at);
CREATE TRIGGER trg_eval_dimensions_updated
    BEFORE UPDATE ON eval_dimensions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 2. eval_rubrics — 评分细则（每等级一行；scenario_tag 维护业务场景变体）
-- ============================================================================
CREATE TABLE IF NOT EXISTS eval_rubrics (
    id            BIGSERIAL PRIMARY KEY,
    dimension_id  BIGINT      NOT NULL REFERENCES eval_dimensions(id) ON DELETE CASCADE,
    level         SMALLINT    NOT NULL,
    criteria      TEXT,
    scenario_tag  VARCHAR(64),
    is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_eval_rubrics_dim_level_scenario
    ON eval_rubrics (dimension_id, level, scenario_tag);
-- 部分唯一索引：仅 active 行强制 (dim, scenario, level) 唯一；NULLS NOT DISTINCT
-- 让 NULL scenario_tag 也算重复（防 default 变体录重，spec §5.4 B-I1）。
-- 注意：PG 语法 NULLS NOT DISTINCT 必须在 WHERE 之前。
CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_rubrics_active_dim_scenario_level
    ON eval_rubrics (dimension_id, scenario_tag, level)
    NULLS NOT DISTINCT
    WHERE is_active = true;
CREATE TRIGGER trg_eval_rubrics_updated
    BEFORE UPDATE ON eval_rubrics
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 3. eval_test_cases — 测试集样本
-- ============================================================================
CREATE TABLE IF NOT EXISTS eval_test_cases (
    id              BIGSERIAL PRIMARY KEY,
    tool_code       VARCHAR(64)  NOT NULL,
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    input_payload   JSONB        NOT NULL,
    tags            TEXT[]       NOT NULL DEFAULT '{}',
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_by      BIGINT REFERENCES users(id) ON DELETE SET NULL,
    updated_by      BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_eval_test_cases_tool_active_deleted
    ON eval_test_cases (tool_code, is_active, deleted_at);
CREATE INDEX IF NOT EXISTS idx_eval_test_cases_tags_gin
    ON eval_test_cases USING GIN (tags);
CREATE TRIGGER trg_eval_test_cases_updated
    BEFORE UPDATE ON eval_test_cases
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 4. eval_versions — 工具版本快照（不可编辑，只能创建/复制/软删）
-- ============================================================================
CREATE TABLE IF NOT EXISTS eval_versions (
    id                 BIGSERIAL PRIMARY KEY,
    tool_code          VARCHAR(64)  NOT NULL,
    name               VARCHAR(128) NOT NULL,
    description        TEXT,
    config_payload     JSONB        NOT NULL,
    parent_version_id  BIGINT REFERENCES eval_versions(id) ON DELETE SET NULL,
    source_kol_id      BIGINT REFERENCES kols(id) ON DELETE SET NULL,
    auto_run_on_create BOOLEAN      NOT NULL DEFAULT FALSE,
    auto_run_tags      TEXT[]       NOT NULL DEFAULT '{}',
    is_active          BOOLEAN      NOT NULL DEFAULT TRUE,
    created_by         BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at         TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_eval_versions_tool_active_deleted
    ON eval_versions (tool_code, is_active, deleted_at);
CREATE TRIGGER trg_eval_versions_updated
    BEFORE UPDATE ON eval_versions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 5. eval_strategies — 评测策略（v2 一期架构预留）
-- ============================================================================
CREATE TABLE IF NOT EXISTS eval_strategies (
    id                          BIGSERIAL PRIMARY KEY,
    tool_code                   VARCHAR(64)  NOT NULL,
    name                        VARCHAR(128) NOT NULL,
    description                 TEXT,
    test_case_selector          JSONB        NOT NULL DEFAULT '{}',
    dimension_weight_overrides  JSONB        NOT NULL DEFAULT '{}',
    rubric_selector             JSONB        NOT NULL DEFAULT '{}',
    scoring_model_override      VARCHAR(128),
    scoring_provider_override   VARCHAR(64),
    scoring_adapter_override    VARCHAR(64),
    business_type               VARCHAR(64),
    kol_id                      BIGINT REFERENCES kols(id) ON DELETE SET NULL,
    is_active                   BOOLEAN      NOT NULL DEFAULT TRUE,
    created_by                  BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at                  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at                  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_eval_strategies_tool_active_deleted
    ON eval_strategies (tool_code, is_active, deleted_at);
-- 部分唯一索引：仅未软删行强制 (tool_code, name) 唯一，防重复 seed default
CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_strategies_active_tool_name
    ON eval_strategies (tool_code, name)
    WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_eval_strategies_kol_id
    ON eval_strategies (kol_id);
CREATE INDEX IF NOT EXISTS idx_eval_strategies_business_type
    ON eval_strategies (business_type);
CREATE TRIGGER trg_eval_strategies_updated
    BEFORE UPDATE ON eval_strategies
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 6. eval_runs — 评测运行（不软删，归档另议）
-- ============================================================================
CREATE TABLE IF NOT EXISTS eval_runs (
    id               BIGSERIAL PRIMARY KEY,
    version_id       BIGINT      NOT NULL REFERENCES eval_versions(id) ON DELETE RESTRICT,
    strategy_id      BIGINT      NOT NULL REFERENCES eval_strategies(id) ON DELETE RESTRICT,
    name             VARCHAR(255) NOT NULL,
    trigger_type     VARCHAR(32) NOT NULL,
    status           VARCHAR(32) NOT NULL DEFAULT 'pending',
    filter_tags      TEXT[]      NOT NULL DEFAULT '{}',
    total_cases      INT         NOT NULL DEFAULT 0,
    completed_cases  INT         NOT NULL DEFAULT 0,
    failed_cases     INT         NOT NULL DEFAULT 0,
    metadata         JSONB       NOT NULL DEFAULT '{}',
    created_by       BIGINT REFERENCES users(id) ON DELETE SET NULL,
    started_at       TIMESTAMPTZ,
    finished_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_eval_runs_version_status
    ON eval_runs (version_id, status);
CREATE INDEX IF NOT EXISTS idx_eval_runs_status_created
    ON eval_runs (status, created_at);
CREATE INDEX IF NOT EXISTS idx_eval_runs_strategy_id
    ON eval_runs (strategy_id);

-- ============================================================================
-- 7. eval_case_results — 单次 case×run 生成结果
-- ============================================================================
CREATE TABLE IF NOT EXISTS eval_case_results (
    id               BIGSERIAL PRIMARY KEY,
    run_id           BIGINT      NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
    test_case_id     BIGINT      NOT NULL REFERENCES eval_test_cases(id) ON DELETE RESTRICT,
    generated_output TEXT,
    output_payload   JSONB,
    input_snapshot   JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_eval_case_results_run_testcase UNIQUE (run_id, test_case_id)
);
CREATE INDEX IF NOT EXISTS idx_eval_case_results_run_testcase
    ON eval_case_results (run_id, test_case_id);

-- ============================================================================
-- 8. eval_scores — 单次 case×维度 评分
-- ============================================================================
CREATE TABLE IF NOT EXISTS eval_scores (
    id              BIGSERIAL PRIMARY KEY,
    case_result_id  BIGINT       NOT NULL REFERENCES eval_case_results(id) ON DELETE CASCADE,
    dimension_id    BIGINT       NOT NULL REFERENCES eval_dimensions(id) ON DELETE RESTRICT,
    weight_used     DECIMAL(5,4),
    ai_score        DECIMAL(5,2),
    ai_reasoning    TEXT,
    ai_strengths    TEXT[],
    ai_weaknesses   TEXT[],
    human_score     DECIMAL(5,2),
    human_feedback  TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_eval_scores_case_dim UNIQUE (case_result_id, dimension_id)
);
CREATE INDEX IF NOT EXISTS idx_eval_scores_dim_score
    ON eval_scores (dimension_id, ai_score);
CREATE TRIGGER trg_eval_scores_updated
    BEFORE UPDATE ON eval_scores
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 9. eval_human_labels — 人工校准历史
-- ============================================================================
CREATE TABLE IF NOT EXISTS eval_human_labels (
    id          BIGSERIAL PRIMARY KEY,
    score_id    BIGINT       NOT NULL REFERENCES eval_scores(id) ON DELETE CASCADE,
    old_score   DECIMAL(5,2),
    new_score   DECIMAL(5,2),
    feedback    TEXT,
    labeled_by  BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_eval_human_labels_score_created
    ON eval_human_labels (score_id, created_at);

-- ============================================================================
-- 10. eval_schedule_policies — 定时调度策略
-- ============================================================================
CREATE TABLE IF NOT EXISTS eval_schedule_policies (
    id           BIGSERIAL PRIMARY KEY,
    name         VARCHAR(128) NOT NULL,
    cron         VARCHAR(64)  NOT NULL,
    version_id   BIGINT REFERENCES eval_versions(id) ON DELETE SET NULL,
    filter_tags  TEXT[]       NOT NULL DEFAULT '{}',
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    created_by   BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_eval_schedule_policies_active_deleted
    ON eval_schedule_policies (is_active, deleted_at);
CREATE TRIGGER trg_eval_schedule_policies_updated
    BEFORE UPDATE ON eval_schedule_policies
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 11. eval_judge_models — 评委模型候选池（v2 一期预留、内容后填）
-- ============================================================================
CREATE TABLE IF NOT EXISTS eval_judge_models (
    id                     BIGSERIAL PRIMARY KEY,
    model_id               VARCHAR(128) NOT NULL,
    provider               VARCHAR(64)  NOT NULL,
    adapter                VARCHAR(64)  NOT NULL,
    applicable_output_type VARCHAR(64)  NOT NULL,
    note                   TEXT,
    is_active              BOOLEAN      NOT NULL DEFAULT TRUE,
    created_by             BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at             TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at             TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_eval_judge_models_type_active_deleted
    ON eval_judge_models (applicable_output_type, is_active, deleted_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_judge_models_active_model_adapter
    ON eval_judge_models (model_id, adapter)
    WHERE deleted_at IS NULL;
CREATE TRIGGER trg_eval_judge_models_updated
    BEFORE UPDATE ON eval_judge_models
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- Seed: 4 个维度（安雅初稿 2026-07-26；权重起步值，跑几轮后按打分分布校准）
-- 安雅把原"文案质量"改为更可衡量的"开头钩子力"（对应前 10 秒完播），新增"仿写贴合度"。
-- 占位符对齐渲染管线：persona→{{persona}}、selling_points→{{product_info}}、reference_script→{{original_script}}。
INSERT INTO eval_dimensions (tool_code, name, display_name, description, default_weight, score_min, score_max, prompt_template, is_active)
VALUES
    ('qianchuan-writer', 'hook_strength', '开头钩子力',
     '前 10 秒（开头几句）钩子够不够强、抓不抓得住人——预判"前 10 秒留人"能力', 0.3500, 1, 10,
     '你是千川脚本文案评审专家。请对以下脚本在【开头钩子力】维度打分（1-10）。\n本维度只看开头（约前 10 秒、开头 1-3 句）把人留住的能力——预判"前 10 秒完播"，只评开头不评整条。\n\n评分标准：\n{{rubric_text}}\n\n输出格式（严格 JSON，不要任何多余文字）：\n{"score": 整数1-10, "reasoning": "...", "strengths": [...], "weaknesses": [...]}\n\n被评脚本：\n{{generated_output}}\n\n达人档案：\n{{persona}}',
     TRUE),
    ('qianchuan-writer', 'conversion_power', '种草力',
     '看完整条后是否产生明确的下单/购买冲动，冲动有多强', 0.3000, 1, 10,
     '你是千川脚本文案评审专家。请对以下脚本在【种草力】维度打分（1-10）。\n本维度评的是看完整条后产生的下单/购买冲动强度——不是"讲没讲卖点"，而是"想不想买"。\n\n评分标准：\n{{rubric_text}}\n\n输出格式（严格 JSON，不要任何多余文字）：\n{"score": 整数1-10, "reasoning": "...", "strengths": [...], "weaknesses": [...]}\n\n被评脚本：\n{{generated_output}}\n\n达人档案：\n{{persona}}\n\n产品信息：\n{{product_info}}',
     TRUE),
    ('qianchuan-writer', 'structure_fidelity', '仿写贴合度',
     '是否贴合原爆款骨架/节奏、实体替换是否自然、不为"降重"毁掉原结构', 0.2000, 1, 10,
     '你是千川脚本文案评审专家。请对以下脚本在【仿写贴合度】维度打分（1-10）。\n核心原则：贴原爆款的骨架与节奏、把实体（产品名/价格/卖点/场景）换成当前商品，而非为降重改烂。相似不是问题，跑偏才是。\n\n评分标准：\n{{rubric_text}}\n\n输出格式（严格 JSON，不要任何多余文字）：\n{"score": 整数1-10, "reasoning": "...", "strengths": [...], "weaknesses": [...]}\n\n被评脚本（仿写稿）：\n{{generated_output}}\n\n参考原版脚本：\n{{original_script}}',
     TRUE),
    ('qianchuan-writer', 'persona_consistency', '人设一致性',
     '是否符合达人 persona/语气/价值观/人设边界', 0.1500, 1, 10,
     '你是千川脚本文案评审专家。请对以下脚本在【人设一致性】维度打分（1-10）。\n本维度评是否贴合该达人 persona——语气、口头禅、用词习惯、价值观、人设边界。\n\n评分标准：\n{{rubric_text}}\n\n输出格式（严格 JSON，不要任何多余文字）：\n{"score": 整数1-10, "reasoning": "...", "strengths": [...], "weaknesses": [...]}\n\n被评脚本：\n{{generated_output}}\n\n达人档案：\n{{persona}}',
     TRUE)
ON CONFLICT DO NOTHING;

-- ============================================================================
-- Seed: rubric 等级（安雅初稿 2026-07-26）—— 4 维 × default 通用版 × 5 档（10/8/6/4/2）
-- scenario_tag NULL = default 通用版；品类变体（skincare/diet）一期结构预留但不启用匹配，故不 seed。
-- ============================================================================
INSERT INTO eval_rubrics (dimension_id, level, criteria, scenario_tag, is_active)
SELECT d.id, v.level, v.criteria, NULL::varchar, TRUE
FROM eval_dimensions d
JOIN (VALUES
  ('hook_strength'::varchar, 10::smallint, '第一句就是强钩子（痛点直击/反常识/悬念/身份认同/利益前置任一），精准戳中目标人群，看完开头几乎必然想继续看下去'::text),
  ('hook_strength', 8, '钩子较强、抓人，开头指向明确的人群或痛点，多数人会愿意看下去'),
  ('hook_strength', 6, '有钩子但力度一般（偏铺垫、进入正题慢），能留住一部分人，不够"炸"'),
  ('hook_strength', 4, '开头平淡、像正常介绍开场，没有明显留人设计，容易被划走'),
  ('hook_strength', 2, '开头没有任何钩子（自我介绍/寒暄/背景铺陈起手），前 10 秒基本留不住人'),
  ('conversion_power', 10, '看完有强烈下单冲动，几乎被说服——痛点—产品—效果链路完整可信，卖点翻译成"对我的好处"，且有自然有力的行动引导（限时/专属福利/评论区钩子等），种草不硬广'),
  ('conversion_power', 8, '看完有明确购买冲动，卖点清楚、利益点到位，有行动引导，就差临门一脚'),
  ('conversion_power', 6, '看完有一点心动但不强，卖点停留在功能罗列、没翻译成利益，行动引导偏弱或套路化'),
  ('conversion_power', 4, '看完基本无购买冲动，卖点模糊或与产品关联弱，几乎无行动引导'),
  ('conversion_power', 2, '看完毫无购买欲，没讲清楚卖什么/为什么买，像自说自话'),
  ('structure_fidelity', 10, '完整贴合原爆款的骨架与叙事节奏（钩子位置、卖点顺序、情绪曲线、结尾引导一一对应），实体替换自然贴合新商品，读起来是"同一套打法换了个品"而非另起炉灶'),
  ('structure_fidelity', 8, '骨架与节奏基本保留，实体替换到位，个别段落顺序或过渡有微调但不伤原结构'),
  ('structure_fidelity', 6, '保留了部分骨架，但有明显自行发挥/结构改动，或实体替换略生硬（新品信息硬塞进旧句式）'),
  ('structure_fidelity', 4, '大幅偏离原骨架（像重写而非仿写），或为规避重复刻意打乱结构导致节奏变差'),
  ('structure_fidelity', 2, '基本没参照原爆款结构，完全另写；或实体替换错乱（残留原品信息、张冠李戴）'),
  ('persona_consistency', 10, '完全贴合该达人 persona——语气、口头禅、用词习惯、价值观、人设边界都对，像她本人会说的话'),
  ('persona_consistency', 8, '整体符合人设，语气与用词基本对路，个别地方略通用但不违和'),
  ('persona_consistency', 6, '大致像该达人，但有明显通用 AI 腔或与其风格不符的表达'),
  ('persona_consistency', 4, '人设感弱，换成别的达人也成立，或偶有明显违背人设的说法'),
  ('persona_consistency', 2, '完全不像该达人，语气/价值观跑偏，甚至说了人设不该说的话')
) AS v(dim_name, level, criteria) ON v.dim_name = d.name
WHERE d.tool_code = 'qianchuan-writer' AND d.deleted_at IS NULL
ON CONFLICT DO NOTHING;

-- ============================================================================
-- Seed: 一条 default 策略（全超集，所有 active test_cases + 维度默认权重）
--   - test_case_selector={"all": true}
--   - dimension_weight_overrides='{}'（用维度默认权重）
--   - rubric_selector='{}'（一期用 default 变体）
--   - 三个 scoring_*_override 空（用版本快照的 scoring_*）
--   - business_type/kol_id 空（二期 per-KOL/业务策略再填）
-- ============================================================================
INSERT INTO eval_strategies (
    tool_code, name, description,
    test_case_selector, dimension_weight_overrides, rubric_selector,
    scoring_model_override, scoring_provider_override, scoring_adapter_override,
    business_type, kol_id, is_active
)
VALUES (
    'qianchuan-writer', 'default', '默认策略：全超集（全部 active test_cases + 维度默认权重 + default rubric 变体）',
    '{"all": true}'::jsonb, '{}'::jsonb, '{}'::jsonb,
    NULL, NULL, NULL,
    NULL, NULL, TRUE
)
ON CONFLICT DO NOTHING;

-- eval_judge_models 一期不 seed（候选清单 = 专项调研 TODO）；
-- 版本快照 config_payload.scoring_model_id 兜底。
