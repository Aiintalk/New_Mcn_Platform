-- 006_kol_intake.sql
-- 红人入驻问卷系统（AI 对话模式）

-- 1. 问卷题目配置（AI 对话引导脚本）
-- 注意：这 24 道题是 AI 面试官的引导提纲，不是前端表单字段
CREATE TABLE kol_intake_questions (
    id            SERIAL PRIMARY KEY,
    order_num     INTEGER NOT NULL DEFAULT 0,
    category      VARCHAR(50) NOT NULL DEFAULT '',   -- 分组标题（基本信息/生活与家庭等）
    question_text TEXT NOT NULL,
    question_type VARCHAR(20) NOT NULL DEFAULT 'text',
    -- text：单条回答
    -- multi_collect：需收集多条（如经历、视频链接），最多 max_items 条
    max_items     INTEGER DEFAULT NULL,              -- multi_collect 时有效
    is_required   BOOLEAN NOT NULL DEFAULT TRUE,     -- 必填题 AI 必须覆盖
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_updated_at_kol_intake_questions
    BEFORE UPDATE ON kol_intake_questions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 初始化 24 道题（来源：旧架构 lib/questions.ts）
INSERT INTO kol_intake_questions
    (order_num, category, question_text, question_type, max_items, is_required)
VALUES
-- 基本信息
(1,  '基本信息',     '你希望粉丝怎么叫你？',                                                'text',          NULL, TRUE),
(2,  '基本信息',     '你的抖音账号名叫什么？',                                               'text',          NULL, TRUE),
(3,  '基本信息',     '年龄和所在城市？',                                                     'text',          NULL, TRUE),
-- 生活与家庭
(4,  '生活与家庭',   '你现在的情感状态是？',                                                 'text',          NULL, TRUE),
(5,  '生活与家庭',   '有小孩吗？几个、多大？',                                               'text',          NULL, TRUE),
(6,  '生活与家庭',   '和父母的关系怎么样？用一两句话说说。',                                  'text',          NULL, TRUE),
-- 野心评估
(7,  '野心评估',     '你现在的直播频率是怎么样的？一周几次、每次多久？',                       'text',          NULL, TRUE),
(8,  '野心评估',     '能接受搬家到北京/杭州/广州吗？',                                       'text',          NULL, TRUE),
(9,  '野心评估',     '你现在每天的时间大概怎么安排的？从早到晚说说。',                         'text',          NULL, TRUE),
-- 人品评估
(10, '人品评估',     '你上一份工作或合作是怎么结束的？',                                      'text',          NULL, TRUE),
(11, '人品评估',     '有没有跟人合伙或合作分钱的经历？最后怎么处理的？',                       'text',          NULL, TRUE),
(12, '人品评估',     '有没有一次你觉得被不公平对待的经历？你当时怎么做的？',                   'text',          NULL, TRUE),
(13, '人品评估',     '你觉得什么样的人你绝对不会合作？',                                      'text',          NULL, TRUE),
-- 职业经历
(14, '职业经历',     '用一句话介绍你自己——你会怎么跟陌生人说？',                              'text',          NULL, TRUE),
(15, '职业经历',     '你的职业路线是什么？做过什么、怎么走到今天的？',                         'text',          NULL, TRUE),
-- 独特经历（★★★ 最重要）
(16, '独特经历',     '说 1-3 件你经历过的、大多数人没经历过的事。先说第一件！',               'multi_collect',    3, TRUE),
-- 个性与表达
(17, '个性与表达',   '你说话最大的特点是什么？举一句你经常说的话或口头禅。',                   'text',          NULL, TRUE),
(18, '个性与表达',   '有没有你绝对不会说的话、绝对不想做的内容？',                            'text',          NULL, TRUE),
-- 特殊背书与资质（选填）
(19, '特殊背书与资质','有没有什么很厉害的证书、头衔、或者听起来就让人"哇"的背景？',            'text',          NULL, FALSE),
-- 内容方向（选填）
(20, '内容方向',     '你想靠什么让观众记住你？',                                             'text',          NULL, FALSE),
(21, '内容方向',     '你最想影响什么样的人？',                                               'text',          NULL, FALSE),
(22, '内容方向',     '有没有你喜欢的博主？请给出 ta 的抖音号并说说喜欢/不喜欢什么？',          'text',          NULL, FALSE),
-- 加分项（选填）
(23, '加分项',       '发 1-3 条你在全抖音上最喜欢的视频链接。',                              'multi_collect',    3, FALSE),
(24, '加分项',       '发 1-3 条你自己账号上最满意的视频链接。',                              'multi_collect',    3, FALSE);


-- 2. AI 配置（对话 bridge + 报告生成）
CREATE TABLE kol_intake_configs (
    id                   SERIAL PRIMARY KEY,
    config_key           VARCHAR(50) NOT NULL UNIQUE,
    -- 'conversation_bridge'：多轮对话模型配置
    -- 'report_generation'：报告生成模型配置
    ai_model_id          INTEGER REFERENCES ai_models(id) ON DELETE SET NULL,
    system_prompt        TEXT,           -- AI 面试官角色设定
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_updated_at_kol_intake_configs
    BEFORE UPDATE ON kol_intake_configs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

INSERT INTO kol_intake_configs (config_key, system_prompt) VALUES
('conversation_bridge', NULL),
('report_generation',   NULL);


-- 3. 分享链接
CREATE TABLE kol_intake_links (
    id           SERIAL PRIMARY KEY,
    token        VARCHAR(64) NOT NULL UNIQUE,   -- secrets.token_urlsafe(32)
    operator_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kol_name     VARCHAR(200),                  -- 运营预填的红人姓名
    expires_at   TIMESTAMPTZ NOT NULL,
    used_at      TIMESTAMPTZ,                   -- 博主首次访问时间
    submitted_at TIMESTAMPTZ,                   -- 博主提交（生成报告）时间
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_kol_intake_links_token    ON kol_intake_links(token);
CREATE INDEX idx_kol_intake_links_operator ON kol_intake_links(operator_id);


-- 4. 对话记录与报告
CREATE TABLE kol_intake_submissions (
    id                     SERIAL PRIMARY KEY,
    link_id                INTEGER NOT NULL REFERENCES kol_intake_links(id) ON DELETE CASCADE,
    UNIQUE (link_id),                            -- 一个链接只能提交一次
    messages               JSONB NOT NULL DEFAULT '[]',
    -- 对话历史格式：
    -- [{role: "assistant"|"user", content: "消息文本", ts: "2026-06-08T14:30:00Z"}]
    ai_report              TEXT,                 -- AI 生成的报告正文（Markdown）
    ai_report_raw          JSONB,                -- AI 原始响应（含 usage 等元数据）
    report_status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- pending / generating / ready / failed
    report_generated_at    TIMESTAMPTZ,
    docx_path              VARCHAR(500),         -- storage/intake_reports/{id}.docx
    pdf_path               VARCHAR(500),         -- storage/intake_reports/{id}.pdf
    kol_downloaded_at      TIMESTAMPTZ,
    operator_downloaded_at TIMESTAMPTZ,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_updated_at_kol_intake_submissions
    BEFORE UPDATE ON kol_intake_submissions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_kol_intake_submissions_link ON kol_intake_submissions(link_id);


-- 5. 注册到功能管理（workspace_tools）
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, tags, sort_order)
VALUES (
    'kol-intake',
    '红人入驻问卷',
    '红人管理',
    '运营生成一次性链接 → AI 对话式采集博主信息 → 生成入驻评估报告',
    'dev',
    '["AI对话","报告生成","docx","PDF"]'::jsonb,
    10
);
