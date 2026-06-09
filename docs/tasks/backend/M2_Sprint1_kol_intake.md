# MCN_Backend_Agent — M2 Sprint 1 任务指令（红人入驻问卷）

> 角色：MCN_Backend_Agent（后端开发 Claude）  
> 工作目录：`backend/`  
> PM 生成时间：2026-06-08  
> 前置条件：M1 全部验收通过，AI Key 池、yunwu_adapter.chat() 可用  
> 完成后：回传 PM，等待前端联调

---

## M2 Sprint 1 目标

实现红人入驻问卷（kol-intake）功能迁移。

**核心交互模式：AI 主导多轮对话（非静态表单）**

```
运营 → 生成一次性分享链接
  ↓
博主打开链接 → 进入 AI 对话界面
  ↓
AI 扮演面试官，主动开场并引导博主逐步回答 24 道问题
（来回多轮，AI 根据回答追问、引导，不是静态表单提交）
  ↓
博主点击「生成报告」→ 后台基于完整对话历史生成评估报告
  ↓
博主在有效期内下载报告（docx / PDF 两种格式）
运营可查看完整对话记录 + 报告
```

---

## 一、数据库迁移（006_kol_intake.sql）

新建文件 `backend/migrations/006_kol_intake.sql`

```sql
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

-- ⚠️ 重要：system_prompt 内容请从旧架构文件迁移：
--    旧架构文件：D:\2026年工作\AI工具箱\0516_te\prompts\kol-intake.ts
--
-- conversation_bridge:
--   system_prompt ← BRIDGE_SYSTEM_PROMPT 常量（完整复制）
--   推荐模型：claude-haiku-4-5-20251001，provider=yunwu，max_tokens=300
--   ⚠️ 后端拼接 system_prompt 时，需在 BRIDGE_SYSTEM_PROMPT 后追加 24 道题目列表，
--      作为 AI 的访谈提纲（AI 需覆盖所有必填题后方可提示博主「可以生成报告了」）
--
-- report_generation:
--   system_prompt ← buildIntakeReportPrompt 函数体中的模板（{qa_content} 替代 ${sections.join('\n\n')}）
--   推荐模型：claude-opus-4-6，provider=yunwu
--   extended thinking：budget_tokens=6000（云雾兼容性见注意事项）
--
-- ai_model_id 初始 NULL，管理员在后台「问卷配置」→「AI 配置」绑定
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
```

---

## 二、ORM 模型

新建 `backend/app/models/kol_intake.py`，定义 4 个 SQLAlchemy 模型：

- `KolIntakeQuestion`（映射 kol_intake_questions，含 category / question_type / max_items）
- `KolIntakeConfig`（映射 kol_intake_configs）
- `KolIntakeLink`（映射 kol_intake_links）
- `KolIntakeSubmission`（映射 kol_intake_submissions，含 messages / docx_path / pdf_path）

在 `backend/app/models/__init__.py` 中 import 这 4 个模型。

---

## 三、API 路由

### 3.1 公开接口（无需鉴权）`backend/app/routers/intake_public.py`

---

**GET `/api/intake/{token}`** — 校验链接，返回初始状态

成功响应（200）：
```json
{
  "valid": true,
  "kol_name": "张三",
  "already_submitted": false,
  "existing_messages": []
}
```

- `already_submitted: true` 时，`existing_messages` 返回历史对话（供只读展示）
- 首次访问写入 `kol_intake_links.used_at`（后续访问不覆盖）
- 过期 token → `410`，不存在 → `404`

---

**POST `/api/intake/{token}/chat`** — AI 多轮对话接口（核心接口）

请求体：
```json
{
  "messages": [
    {"role": "assistant", "content": "你好！我是…（AI 开场白）"},
    {"role": "user",      "content": "我叫小红"}
  ]
}
```

- **第一次调用**：`messages` 为空数组 `[]`，后端让 AI 生成开场白
- **后续调用**：传入完整对话历史（含上一条用户消息）

逻辑：
1. 校验 token（有效、未过期、未提交）
2. 读取 `kol_intake_configs` WHERE `config_key='conversation_bridge'`，获取 system_prompt 和 ai_model
3. 后端在 system_prompt 末尾追加题目提纲（从 kol_intake_questions 读取所有 is_active=TRUE 的题目，按 order_num 排列，必填题标注★）
4. 调用 `yunwu_adapter.chat(messages=messages, system=full_system_prompt, max_tokens=300)`
5. 返回 AI 回复

成功响应（200）：
```json
{
  "reply": "太好了！那请问你的抖音账号名叫什么？",
  "role": "assistant"
}
```

若 `ai_model_id` 为 NULL → 返回 `{"reply": null, "error": "AI对话暂未配置"}`

---

**POST `/api/intake/{token}/submit`** — 提交完整对话，触发报告生成

请求体：
```json
{
  "messages": [
    {"role": "assistant", "content": "你好！…"},
    {"role": "user",      "content": "我叫小红"},
    {"role": "assistant", "content": "…"},
    {"role": "user",      "content": "…"}
  ]
}
```

逻辑：
1. 校验 token（有效、未过期、未提交）
2. 写入 `kol_intake_submissions`（messages 存入，`report_status='pending'`）
3. 更新 `kol_intake_links.submitted_at = NOW()`
4. FastAPI `BackgroundTasks` 异步触发 `generate_intake_report(submission_id)`
5. 立即返回

成功响应（200）：
```json
{
  "submission_id": 5,
  "report_status": "generating"
}
```

**背景任务 `generate_intake_report(submission_id)`：**

```
1. report_status = 'generating'，commit
2. 读取 kol_intake_configs WHERE config_key='report_generation'
3. 将 messages 对话历史格式化为 qa_content 文本：
   过滤掉纯引导话语，提取问答对，格式：
   "问：你希望粉丝怎么叫你？\n答：小红\n\n问：…\n答：…"
4. 替换 system_prompt 中的 {qa_content} 占位符
5. 调用 yunwu_adapter.chat()（使用 report_generation 配置的 model）
   extended thinking 参数：extra_body={"thinking": {"type": "enabled", "budget_tokens": 6000}}
   若 API 返回 400/422 → 降级为普通调用，ai_report_raw 记录 thinking_supported=false
6. ai_report = AI 返回文本（Markdown 格式），ai_report_raw = 原始响应
7. 调用 generate_docx(submission_id, ai_report) → 存入 storage/intake_reports/{id}.docx
8. 调用 generate_pdf(submission_id, ai_report)  → 存入 storage/intake_reports/{id}.pdf
   （PDF 可用 reportlab 或 weasyprint 生成，也可将 docx 转 pdf）
9. report_status='ready'，report_generated_at=NOW()，docx_path=…，pdf_path=…，commit
10. 异常时：report_status='failed'，commit
```

---

**GET `/api/intake/{token}/status`** — 轮询报告生成状态

```json
{
  "report_status": "ready",
  "download_ready": true
}
```

---

**GET `/api/intake/{token}/download`** — 博主下载报告

Query 参数：`?format=docx`（默认）或 `?format=pdf`

条件：token 未过期 + `report_status='ready'`

- 读取对应 `docx_path` 或 `pdf_path`，FileResponse 返回
- 首次下载写入 `kol_downloaded_at`
- `Content-Disposition: attachment; filename="MCN红人入驻评估报告.docx"` 或 `.pdf`

---

### 3.2 运营端接口（operator 角色）`backend/app/routers/operator_intake.py`

JWT 鉴权，`current_user.role in ["operator", "admin"]`。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/operator/intake/links` | 生成分享链接 |
| GET  | `/api/operator/intake/links` | 自己的链接列表 |
| GET  | `/api/operator/intake/submissions` | 自己链接下的提交列表 |
| GET  | `/api/operator/intake/submissions/{id}` | 提交详情（含 messages + ai_report） |
| GET  | `/api/operator/intake/submissions/{id}/download` | 运营下载报告 |

**POST `/api/operator/intake/links`** 请求体：
```json
{ "kol_name": "张三", "expires_hours": 24 }
```

逻辑：
1. 检查 `workspace_tools` WHERE `tool_code='kol-intake'` AND `status='online'`
   - 不满足 → 返回 `403`，错误信息：`"红人入驻问卷功能已下架，暂无法创建新链接"`
2. 生成 token：`secrets.token_urlsafe(32)`
3. `expires_at = NOW() + timedelta(hours=expires_hours)`（最小1小时，最大30天）
4. 写入 `kol_intake_links`

响应：`{ id, token, kol_name, expires_at, share_url: "/intake/{token}" }`

> ⚠️ 注意：公开接口（`/chat` `/submit` `/download` `/status`）**不检查**工具状态。
> 已生成的链接在有效期内继续可用，下架只阻止新建链接，不影响现存链接。

**运营下载条件**（满足其一）：
1. `link.expires_at < NOW()`（链接已过期，博主下载窗口关闭）
2. `submission.kol_downloaded_at IS NOT NULL`（博主已下载过）

不满足时返回 403：`"链接仍在有效期内，请等待博主下载或链接到期后再操作"`

Query 参数同样支持 `?format=docx`（默认）或 `?format=pdf`

---

### 3.3 管理员接口（admin 角色）`backend/app/routers/admin_intake.py`

**题目管理：**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET    | `/api/admin/intake/questions` | 题目列表（按 order_num，含 category） |
| POST   | `/api/admin/intake/questions` | 新增题目 |
| PATCH  | `/api/admin/intake/questions/{id}` | 编辑题目 |
| DELETE | `/api/admin/intake/questions/{id}` | 软删除（is_active=false） |
| PUT    | `/api/admin/intake/questions/reorder` | 批量更新 order_num |

**AI 配置管理：**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/intake/configs` | 获取两条配置（含 ai_model 信息） |
| PUT | `/api/admin/intake/configs/{key}` | 更新配置（key = conversation_bridge / report_generation） |

PUT 请求体：`{ "ai_model_id": 3, "system_prompt": "…" }`

**提交记录（admin 可看全部）：**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/intake/submissions` | 全部提交（含 operator 信息） |
| GET | `/api/admin/intake/submissions/{id}` | 详情（含 messages + ai_report） |

---

## 四、报告文件生成

### 4.1 docx（`backend/app/services/intake_report.py`）

依赖：`python-docx`（加入 requirements.txt）

文档结构：
```
新红人分析报告 · [博主昵称]
──────────────────────────────
生成时间：2026-06-08 14:30

对话摘要
  （从 messages 中提取问答对，格式化展示）

AI 综合评估
  [ai_report 正文，Markdown 转换为 Word 段落]
──────────────────────────────
本报告由达人说平台自动生成
```

### 4.2 PDF

推荐方案：安装 `weasyprint`，将 Markdown 报告先渲染为 HTML，再转 PDF。
备选方案：安装 `reportlab` 直接生成 PDF。

两个文件均存入 `backend/storage/intake_reports/`，启动时 `os.makedirs(..., exist_ok=True)`。

---

## 五、路由注册

`backend/app/main.py`：

```python
from app.routers import intake_public, operator_intake, admin_intake

app.include_router(intake_public.router, tags=["intake-public"])
app.include_router(operator_intake.router, prefix="/api/operator", tags=["operator-intake"])
app.include_router(admin_intake.router,   prefix="/api/admin",    tags=["admin-intake"])
```

---

## 六、注意事项

1. **BackgroundTasks 与 DB Session**：背景任务需独立创建 Session，`async with AsyncSessionLocal() as db:`，不能复用请求中的 db。

2. **Extended thinking 兼容性**：云雾为 OpenAI 兼容接口，extended thinking 参数可能不透传。建议：先尝试传 `extra_body={"thinking": {"type": "enabled", "budget_tokens": 6000}}`，若返回 400/422 则降级普通调用，`ai_report_raw` 记录 `thinking_supported: false`。

3. **对话历史大小**：24 道题预计对话轮次 30-60 条消息，存为 JSONB 无压力。每次 `/chat` 调用需传入完整 messages，后端不做服务端 session 缓存，由前端维护。

4. **题目提纲注入**：每次 `/chat` 调用时，后端实时从 DB 读取所有 `is_active=TRUE` 的题目，追加到 system_prompt 末尾，格式如下（AI 据此引导对话覆盖所有必填题）：
   ```
   【访谈提纲（需覆盖所有★必填项）】
   基本信息
   ★ 1. 你希望粉丝怎么叫你？
   ★ 2. 你的抖音账号名叫什么？
   …
   加分项（选填，能问到更好）
   24. 发 1-3 条你自己账号上最满意的视频链接。
   ```

5. **提交幂等**：`kol_intake_submissions` 上有 `UNIQUE(link_id)`，重复提交直接 409 即可。

---

## 七、验收标准

1. `GET /api/intake/{token}` 过期返回 410，已提交返回 `already_submitted: true` + 历史 messages
2. `POST /api/intake/{token}/chat` 首次调用（messages=[]）返回 AI 开场白；携带历史调用时 AI 继续对话
3. `POST /api/intake/{token}/submit` 立即返回 `report_status: generating`，后台异步完成报告生成
4. `GET /api/intake/{token}/status` 生成完成后返回 `report_status: ready`
5. `GET /api/intake/{token}/download?format=docx` 和 `?format=pdf` 均可下载对应文件
6. 运营下载：链接有效期内且博主未下载时返回 403
7. 管理员可通过 `PUT /api/admin/intake/configs/conversation_bridge` 更换对话模型
8. 题目 CRUD 正常，新增/修改题目后下次对话自动生效（实时从 DB 读取）
