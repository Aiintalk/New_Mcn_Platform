# M2 Sprint 3 — 人格定位（persona-positioning）迁移需求文档

> **版本**：v1 补遗（2026-06-24 整理）
> **作者**：MCN_PM_Agent（基于 v1/v2 任务单 + PM 记忆 + 契约文档反推）
> **实际完成日期**：2026-06-11
> **状态**：✅ 已完成并上线（本文档为事后补齐的功能完成链文档）
> **原始任务单**：
> - `backend/docs/tasks/M2_Sprint3_persona_positioning.md`（v1，636 行）
> - `backend/docs/tasks/M2_Sprint3_后端任务_persona_positioning_v2_修复Bug.md`（v2，227 行）
> - `frontend/docs/tasks/M2_Sprint3_persona_positioning.md`（v1，544 行）

---

## 一、背景与目标

### 1.1 背景

旧架构 `Ai_Toolbox/persona-positioning-web/`（Next.js 独立应用）已运行，提供"人格定位"功能：
运营输入达人资料（抖音号 + 问卷 + 补充资料），AI 流式生成**人格档案** + **内容规划**两份 Markdown，
支持 Word 导出、历史记录、多轮优化对话。

M2 Sprint 3 将该功能 **1:1 迁移**到新架构（FastAPI + React/Vite），同时补齐：
- 鉴权（JWT + operator/admin 角色）
- AI 调用日志（ai_call_logs + external_service_logs）
- 结果存档（persona_reports 表 + outputs 产出双写）
- TikHub 凭证池（tikhub_credentials + tikhub_call_logs）
- 配置化（kol_intake_configs 管理 Prompt + AI 模型）

### 1.2 目标

| # | 目标 | 验收 |
|---|------|------|
| 1 | 运营可在新架构生成人格档案 + 内容规划 | Step 1→2→3 全流程跑通 |
| 2 | TikHub 抖音号解析复用凭证池 | 无单 token 限流问题 |
| 3 | AI 调用走 yunwu adapter 凭证池 | AiCallLog 自动写入 |
| 4 | 报告存档 + 产出中心双写 | 历史列表 + 产出中心可见 |
| 5 | Word 导出（档案 + 规划各一份） | 文件名 UTF-8 编码 |
| 6 | 多轮优化对话（SSE 流式） | 采纳后替换当前内容 |
| 7 | 历史记录管理（查看 + 删除） | 软删除，不物理删 |

### 1.3 与旧架构的关系

| 项 | 旧架构 | 新架构 |
|----|--------|--------|
| 前端框架 | Next.js 独立应用 | React 19 + Vite（统一前端） |
| 后端 | Node.js Route Handlers | FastAPI（统一后端） |
| 鉴权 | 无（独立工具） | JWT + operator/admin 角色 |
| AI 调用 | 直连 OpenAI | yunwu adapter 凭证池 |
| 抖音解析 | 直连 TikHub | tikhub adapter 凭证池 |
| 存档 | 文件系统 JSON | PostgreSQL persona_reports + outputs 表 |
| Prompt 管理 | 硬编码常量 | kol_intake_configs 管理员可配 |
| 日志 | 无 | ai_call_logs + external_service_logs + operation_logs |

### 1.4 与 M2 Sprint 1 的关系

**前置依赖**：M2 Sprint 1 kol-intake（KOL 入驻问卷）必须先完成。
- 复用 `kol_intake_submissions` 表（导入达人资料）
- 复用 `kol_intake_configs` 表（`config_key='persona_generation'`）
- 复用 `yunwu_adapter` / `tikhub_adapter`

---

## 二、范围

### 2.1 在范围（本次迁移）

| # | 改动 | 说明 |
|---|------|------|
| 1 | 数据库迁移 008 | `persona_reports` 表 + 注册 `workspace_tools` |
| 2 | ORM 模型 | `PersonaReport` |
| 3 | 文件解析服务 | `services/file_parser.py`（.docx/.pdf/.txt/.md） |
| 4 | Word 生成服务 | `services/persona_docx.py`（Markdown → docx） |
| 5 | 后端 10 个 API | `routers/persona.py` |
| 6 | 前端类型 + API 层 | `types/persona.ts` + `api/persona.ts` |
| 7 | 前端三步向导页面 | `pages/operator/PersonaPage.tsx`（546 行） |
| 8 | 前端路由 + 菜单 | `/workspace/persona-positioning` |
| 9 | TikHub adapter 扩展 | `resolve_sec_user_id` / `fetch_user_videos` |
| 10 | yunwu adapter 扩展 | `chat_stream`（SSE 流式 + 自动写日志） |
| 11 | 产出双写 | 生成完成后同步写 `outputs` 表 |
| 12 | 管理端配置入口 | 「工具配置 → 人格定位」绑 AI 模型 + Prompt |
| 13 | 测试 + 契约 + 文档 | 后端 221/221 + 前端 71/71 全绿 |

### 2.2 不在范围（后续独立任务）

| 项 | 原因 | 后续路径 |
|----|------|---------|
| 对标分析下拉选择 | 新架构无对标分析模块，Step 2 仅保留文件上传 | 对标分析迁移时再加 |
| 同步到素材库 | 新架构无素材库模块 | 素材库迁移时再加 |
| SSE 断线重连 | 已有空内容保护（Bug 4 修复），未做自动重连 | 视使用反馈再加 |
| TikHub 502 重试 | Sprint 17 期间确认 Cloudflare gateway 间歇性故障 | 加 retry 机制作为独立任务 |

### 2.3 v2 新增功能（Web 版增强）

相对旧架构的增量：

| 功能 | 说明 |
|------|------|
| KOL 入驻导入 | Step 1 下拉选已完成的 KOL 入驻提交，自动填充达人资料 |
| 优化对话 | Step 3 多轮 AI chat，可采纳优化结果替换当前档案/规划 |
| 历史详情/删除 | 报告列表支持查看详情和软删除 |
| Web 版 Prompt | 含运营指定方向 A/B 分支（不是旧版 prompt） |

---

## 三、数据库设计

### 3.1 Migration 008 — persona_reports 表

**文件**：`backend/migrations/008_persona_positioning.sql`

```sql
CREATE TABLE persona_reports (
    id                  SERIAL PRIMARY KEY,
    operator_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Step 1 输入
    douyin_id           VARCHAR(200),
    douyin_nickname     VARCHAR(200),
    top10_text          TEXT,
    recent30_text       TEXT,
    questionnaire_files JSONB DEFAULT '[]',
    supplement_text     TEXT,
    supplement_files    JSONB DEFAULT '[]',

    -- Step 2 输入（对标资料，可选）
    benchmark_profile_files  JSONB DEFAULT '[]',
    benchmark_plan_files     JSONB DEFAULT '[]',

    -- Step 3 生成结果
    profile_result      TEXT,    -- 人格档案（===SPLIT=== 前）
    plan_result         TEXT,    -- 内容规划（===SPLIT=== 后）
    raw_output          TEXT,    -- AI 原始完整输出（含 ===SPLIT===）
    influencer_name     VARCHAR(200),

    -- Word 文件路径
    profile_docx_path   VARCHAR(500),
    plan_docx_path      VARCHAR(500),

    -- 状态
    status              VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- pending / generating / ready / failed
    generated_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_updated_at_persona_reports
    BEFORE UPDATE ON persona_reports
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_persona_reports_operator ON persona_reports(operator_id);
CREATE INDEX idx_persona_reports_status   ON persona_reports(status);

-- 复用 kol_intake_configs 表（config_key='persona_generation'）
INSERT INTO kol_intake_configs (config_key, system_prompt)
VALUES ('persona_generation', NULL)
ON CONFLICT (config_key) DO NOTHING;

-- 注册 workspace_tools
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, tags, sort_order)
VALUES (
    'persona-positioning', '人格定位', '内容策划',
    '输入达人资料 → AI 生成人格档案 + 内容规划，支持导出 Word',
    'dev',
    '["AI生成","人格档案","内容规划","docx","TikHub"]'::jsonb,
    20
);
```

### 3.2 字段说明

| 字段 | 用途 | 是否可空 |
|------|------|---------|
| `operator_id` | 创建人（运营） | NOT NULL |
| `douyin_id` | Step 1 原始输入 | NULL |
| `douyin_nickname` | TikHub 解析出的昵称 | NULL |
| `top10_text` / `recent30_text` | TikHub 视频文案 | NULL |
| `questionnaire_files` | 问卷文件列表 `[{filename, text}]` | 默认 `[]` |
| `supplement_text` / `supplement_files` | 补充备注 | NULL/`[]` |
| `benchmark_*_files` | Step 2 对标文件 | 默认 `[]` |
| `profile_result` / `plan_result` | 拆分后的生成结果 | NULL（generating 状态时） |
| `raw_output` | AI 原始完整输出（含 `===SPLIT===`） | NULL |
| `influencer_name` | 从 profile_result 首行提取 | NULL |
| `profile_docx_path` / `plan_docx_path` | Word 文件路径 | NULL（未生成时） |
| `status` | `pending` / `generating` / `ready` / `failed` | NOT NULL，默认 `pending` |
| `generated_at` | 生成完成时间 | NULL |

### 3.3 状态机

```
pending     ──(generate 调用)──►  generating
generating  ──(成功)──►           ready
generating  ──(失败/空内容)──►    failed
ready/failed──(重新生成)──►       generating
```

**关键保护**（v2 Bug 4 修复）：`_finalize_report` 检查 `raw_output` 非空，空内容直接置 `failed`。

### 3.4 其他表（已有，本次复用）

| 表 | 用途 | 引入 Sprint |
|----|------|------------|
| `kol_intake_submissions` | Step 1 KOL 导入数据源 | Sprint 1 |
| `kol_intake_configs` | Prompt + AI 模型配置（`config_key='persona_generation'`） | Sprint 1 |
| `tikhub_credentials` | TikHub 凭证池 | Sprint 3（migration 010） |
| `tikhub_call_logs` | TikHub 调用日志 | Sprint 3（migration 011） |
| `ai_call_logs` | AI 调用日志（feature=`persona_generation` / `persona_optimize`） | 已有 |
| `external_service_logs` | TikHub 调用统一日志（service=`tikhub`） | 已有 |
| `outputs` | 产出中心（tool_code=`persona-positioning`） | 已有 |
| `operation_logs` | 用户操作日志 | 已有 |

---

## 四、后端 API（10 个）

**文件**：`backend/app/routers/persona.py`

所有接口需 JWT 鉴权（`role in ["operator", "admin"]`）。

### 4.1 POST `/api/persona/fetch-douyin` — 解析抖音账号

**请求**：`{ "url": "抖音号/链接/分享文本" }`

**逻辑**：
1. `tikhub_adapter.resolve_sec_user_id(url)` → `sec_user_id` + `nickname`
2. `tikhub_adapter.fetch_user_videos(sec_user_id, max_pages=10)` → 所有视频
3. 取 TOP10（按点赞）+ 最近 30 天，格式化为文本
4. 写 `external_service_logs`（service=`tikhub`，action=`resolve_sec_user_id` / `fetch_user_videos`）

**响应**：
```json
{
  "nickname": "小红",
  "sec_user_id": "...",
  "total_videos": 156,
  "top10_count": 10,
  "recent30_count": 8,
  "top10_text": "第1条 | 2026-05-01 | 点赞 2.3万\n...",
  "recent30_text": "..."
}
```

### 4.2 POST `/api/persona/parse-file` — 解析上传文件

**请求**：`multipart/form-data`，字段 `file`

**支持格式**：.docx / .pdf / .txt / .md（截断 8000 字符）

**响应**：`{ "text": "提取的纯文本" }`

### 4.3 POST `/api/persona/generate` — SSE 流式生成（核心）

**请求**：
```json
{
  "influencer_info": "问卷内容（必填）",
  "top10_content": "TOP10 视频文案（可选）",
  "supplement_text": "补充备注（可选）",
  "benchmark_text": "对标资料（可选）",
  "douyin_id": "...", "douyin_nickname": "...", "recent30_text": "...",
  "questionnaire_files": [{"filename": "...", "text": "..."}],
  "supplement_files": [...],
  "benchmark_profile_files": [...],
  "benchmark_plan_files": [...]
}
```

**逻辑**：
1. 校验 `influencer_info` 非空
2. 读 `kol_intake_configs WHERE config_key='persona_generation'`，取 system_prompt + ai_model
3. 若 `ai_model_id` 为 NULL → `400 {"error": "AI 模型未配置，请联系管理员"}`
4. 构建 user_message（对标资料 + 问答采集 + TOP10 + 补充资料 + 生成指令）
5. 插入 `PersonaReport`（status=`generating`），拿 `report_id`
6. 调 `yunwu_adapter.chat_stream()`，SSE 流式返回
7. Header 加 `X-Report-Id: {report_id}`（前端存储）
8. 流完成后的后台任务（`BackgroundTasks`）：
   - 拆分 `raw_output`（`===SPLIT===` 前后）
   - 从 `profile_result` 首行提取 `influencer_name`（格式：`# {名字} · 人格档案 v1.0`）
   - 生成两份 Word（`profile_docx_path` + `plan_docx_path`）
   - 更新 `PersonaReport`：status=`ready`，`generated_at=NOW()`
   - **产出双写**：插入 `outputs` 表（详见 §七）
   - 写 `OperationLog`（action=`generate_persona_report`）
   - 异常 → status=`failed`
   - **空内容保护**（v2 Bug 4）：`raw_output` 为空直接置 `failed`，不标 `ready`

**SSE 响应**：
```
Content-Type: text/event-stream
X-Report-Id: 42

data: 第一部分流式内容...

data: ===SPLIT===

data: 第二部分流式内容...

data: [DONE]
```

### 4.4 POST `/api/persona/export-word` — 导出 Word

**请求**：`{ "report_id": 42, "type": "profile" | "plan" }`

**逻辑**：
1. 查 PersonaReport WHERE `id=? AND operator_id=current_user.id`
2. 取对应 docx_path，文件存在 → `FileResponse`
3. 文件不存在 → 实时生成后返回

**Content-Disposition**：
```
attachment; filename*=UTF-8''人格档案_{influencer_name}_{date}.docx
attachment; filename*=UTF-8''内容规划_{influencer_name}_{date}.docx
```

### 4.5 GET `/api/persona/reports` — 历史报告列表

返回当前运营最近 50 条（按 `created_at` 倒序）。

**响应**：`[{id, influencer_name, douyin_nickname, status, created_at}, ...]`

### 4.6 GET `/api/persona/reports/{id}` — 报告详情

**条件**：`operator_id = current_user.id`

**响应**：完整 PersonaReport（含 `profile_result` / `plan_result` / `raw_output`）

### 4.7 GET `/api/persona/kol-submissions` — KOL 入驻列表（v2）

**逻辑**：
1. 查 `kol_intake_submissions WHERE status='completed'`，按 `submitted_at` 倒序
2. 去重：同一 `nickname` 只保留最新一条
3. 每条解析 `answers` JSONB → 格式化带标签文本（昵称/年龄城市/情感状态/子女情况/...）
4. 附加 `report` 字段（AI 入驻报告全文）

**响应**：`[{id, nickname, submitted_at, formatted_answers, report}, ...]`

### 4.8 POST `/api/persona/optimize` — 优化对话 SSE 流式（v2）

**请求**：
```json
{
  "messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
  "current_content": "当前档案/规划全文",
  "content_type": "profile" | "plan",
  "influencer_info": "达人基础信息",
  "benchmark_text": "对标资料（可选）"
}
```

**逻辑**：
1. 动态构建 system prompt（运营修改意见 > 一切；输出完整版本非 diff；保持原格式；不清楚先确认）
2. 调 `yunwu_adapter.chat_stream()`
3. 写 `ai_call_log`（feature=`persona_optimize`）

### 4.9 DELETE `/api/persona/reports/{id}` — 软删除（v2）

**条件**：`operator_id = current_user.id AND deleted_at IS NULL`

**逻辑**：软删除（设置 `deleted_at`），不物理删除（符合一票否决项）。

**响应**：`success_response(data={"deleted": true})`

### 4.10 GET `/api/persona/questionnaire-template` — 下载问卷模板

调用 `generate_questionnaire_template()` 生成问卷 docx，直接返回。

**问卷结构**（10 题，与旧架构 `export-questionnaire/route.ts` 完全一致）：
- 基本信息（4 题，均必填）
- 个人特色（3 题，均必填）
- 内容方向（3 题，选填）

**样式**：紫色主题，有页眉页脚。

---

## 五、前端设计

### 5.1 新增文件

```
frontend/src/
├── pages/operator/
│   └── PersonaPage.tsx          # 主页面（546 行）
├── api/
│   └── persona.ts               # API 层
└── types/
    └── persona.ts               # 类型定义
```

### 5.2 三步向导交互

```
Step 1 · 填写达人资料
  ├─ A: 抖音号解析（选填）
  │   └─ 输入框 + 「解析」按钮 → fetchDouyin()
  ├─ B: 导入达人资料（必填至少一个）
  │   ├─ 方式 1：KOL 入驻下拉（getKolSubmissions）
  │   └─ 方式 2：上传文件（.docx/.pdf/.txt/.md + 下载问卷模板）
  └─ C: 补充信息（选填）
      └─ Textarea + 文件上传
  └─ 下一步按钮条件：hasInfluencerData && hasParsedDouyin

Step 2 · 上传对标资料（可跳过）
  ├─ 对标人格档案（多文件）
  └─ 对标内容规划（多文件）
  └─ 底部：「上一步」 / 「跳过，直接生成」 / 「下一步，开始生成」

Step 3 · 生成结果展示
  ├─ 进入即触发 handleGenerate()（SSE 流）
  ├─ 双 Tab：「人格档案」 / 「内容规划」
  ├─ 每个 Tab 下方：「导出 Word」 / 「复制」 / 「优化{档案|规划}」
  ├─ 「重新开始」回到 Step 1
  └─ 抽屉（页面头部按钮，所有步骤可见）：
      ├─ 历史记录列表（getPersonaReports）
      ├─ 点击加载详情（getPersonaReportDetail + setStep(3)）
      └─ 删除（deletePersonaReport，软删）
```

### 5.3 SSE 流式处理

**核心**：用 `===SPLIT===` 分隔 profile 和 plan。

```typescript
const decoder = new TextDecoder();
let fullText = '';
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  fullText += decoder.decode(value, { stream: true });
  const parts = fullText.split('===SPLIT===');
  setProfileResult(parts[0].trim());
  if (parts.length > 1) setPlanResult(parts[1].trim());
}
```

**ReportId 时机**：从 HTTP 响应 Header `X-Report-Id` 取，在开始读 stream 前已拿到。

### 5.4 卸载中止（v2 Bug 4 修复）

```typescript
useEffect(() => {
  return () => {
    abortRef.current?.abort();
    optimizeAbortRef.current?.abort();
  };
}, []);
```

组件卸载时中止进行中的 SSE，避免后端把空内容标 `ready`。

### 5.5 API 层路径常量（v2 Bug 2 修复）

`api/persona.ts` 拆两套常量：

```typescript
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
const API = '/api/persona';                          // request.ts 封装用
const FETCH_BASE = `${BASE_URL}/api/persona`;        // 原生 fetch 用（SSE/Blob/multipart）
```

### 5.6 历史抽屉渲染（v2 Bug 3 修复）

历史抽屉 + 优化对话 Overlay 从 `{step === 3 && (...)}` 块内**移到组件最外层**，使其在任何步骤都能渲染（按钮在头部，不在 Step 3 内）。

### 5.7 历史加载自动跳转（v2 Bug 5 修复）

`loadHistoryDetail()` 加载完成后 `setStep(3)`，否则 Step 1/2 点历史看不到 Step 3 的渲染块。

### 5.8 路由 + 菜单

**运营端**：`/workspace/persona-positioning`，菜单放在「创作中心」子菜单（UI 布局规范）。

**管理端**：「工具配置 → 功能配置 → 人格定位」卡片，绑定 AI 模型 + 编辑 Prompt。

---

## 六、Word 文档生成服务

**文件**：`backend/app/services/persona_docx.py`

```python
async def generate_persona_docx(
    report_id: int,
    doc_type: str,           # "profile" 或 "plan"
    content: str,            # Markdown 内容
    influencer_name: str
) -> str:
    """
    将 Markdown 转 Word，返回路径：
    storage/persona_reports/{report_id}_{doc_type}.docx
    """
```

**支持的 Markdown 格式**：
- `# ## ### ####` → HEADING 1-4
- `- ` / `* ` → 无序列表
- `1. ` → 有序列表
- `> ` → 引用（斜体 + 缩进）
- `**text**` → 粗体
- 空行 → 空段落

**文档头部**：
```
{influencer_name} · {人格档案|内容规划}
生成时间：2026-XX-XX XX:XX:XX

（正文）
```

**存储路径**：`backend/storage/persona_reports/`，启动时 `os.makedirs(..., exist_ok=True)`。

---

## 七、产出中心双写规则

生成完成后，**同时写 `outputs` 表**，运营在「产出中心 → AI 产出」tab 可见。

```python
output = Output(
    title=f"{influencer_name} · 人格档案 + 内容规划",
    tool_code="persona-positioning",
    tool_name="人格定位",
    content=raw_output,                    # 完整 AI 输出（含 ===SPLIT===）
    content_json={
        "report_id": report.id,
        "influencer_name": influencer_name,
        "profile_result": profile_result,
        "plan_result": plan_result,
    },
    word_count=len(raw_output),
    created_by=current_user.id,
)
session.add(output)
```

**字段映射**：

| Output 字段 | 来源 |
|-------------|------|
| `title` | `{influencer_name} · 人格档案 + 内容规划` |
| `tool_code` | `persona-positioning` |
| `tool_name` | `人格定位` |
| `content` | `raw_output` |
| `content_json` | `{report_id, influencer_name, profile_result, plan_result}` |
| `word_count` | `len(raw_output)` |
| `created_by` | `current_user.id` |

**前端产出中心预览**（v2 Bug 6 修复）：点击预览时先用列表数据开 Modal（即时响应），异步调 `getOutput(id)` 拿完整 `content` 填充。

---

## 八、日志要求

| 场景 | 日志表 | 写入位置 | feature / action |
|------|--------|---------|------------------|
| AI 生成（generate） | `ai_call_logs` | `yunwu.chat_stream()` 内部 finally | feature=`persona_generation` |
| AI 优化对话（optimize） | `ai_call_logs` | `yunwu.chat_stream()` 内部 finally | feature=`persona_optimize` |
| TikHub 抖音号解析 | `external_service_logs` | `fetch-douyin` 路由内手动写 | service=`tikhub`, action=`resolve_sec_user_id` |
| TikHub 视频列表 | `external_service_logs` | `fetch-douyin` 路由内手动写 | service=`tikhub`, action=`fetch_user_videos` |
| 生成报告完成 | `operation_logs` | generate 后台任务 | action=`generate_persona_report` |
| 导出 Word | `operation_logs` | export-word 路由 | action=`export_persona_word` |
| 删除报告 | `operation_logs` | delete 路由 | action=`delete_persona_report` |

---

## 九、系统 Prompt（Web 版，v2）

**位置**：旧架构 `persona-positioning-web/app/api/generate/route.ts` 第 7-189 行（约 170 行，完整保留）。

**管理员配置路径**：管理端「工具配置 → 人格定位 → Prompt」Textarea 编辑。

**核心差异（Web 版 vs 旧版）**：
- 「一句话定位」两种情况：A=运营指定方向 → 直接使用；B=自动分析稀缺性
- 补充资料标签：「补充资料（运营手动填写，优先级最高）」
- 新增规则：纯内容赛道达人 → 零产品/品牌展示

**优化对话 Prompt**（动态构建，不存数据库）：
```
你是一个顶级的内容策划操盘手，正在帮用户优化迭代「{内容类型}」。
## 最高优先级：运营的修改意见
用户（运营）在对话中提出的每一条修改意见都是最高优先级指令，必须严格执行。
## 当前{内容类型}
{current_content}
## 对标资料（运营选定的参照对象，按运营要求参照）
{benchmark_text}
## 达人基础信息
{influencer_info}
## 执行规则
1. 运营的修改意见 > 一切其他考量
2. 输出完整的修改后版本（不是 diff）
3. 保持原有格式和结构
4. 如果运营的要求不清楚，先简短确认再修改
5. 输出时不要加前缀，直接输出完整内容
```

---

## 十、feature 字段命名规范（调用日志页对齐）

| feature 值 | 含义 |
|-----------|------|
| `persona-positioning` | 人格定位（产出中心 tool_code） |
| `persona-generation` | AI 生成（ai_call_logs feature） |
| `persona-optimize` | AI 优化对话（ai_call_logs feature） |

---

## 十一、决策点（实施时已确认）

| # | 决策项 | 选择 | 理由 |
|---|--------|------|------|
| 1 | 表设计 | `persona_reports` 单表存所有输入 + 输出 | 便于回溯，避免 JOIN |
| 2 | 配置表 | 复用 `kol_intake_configs`（`config_key='persona_generation'`） | 不新建配置表 |
| 3 | AI 调用日志 | `yunwu.chat_stream()` 内部 finally 自动写 | 对齐红线 #6（adapter 写日志） |
| 4 | TikHub 日志 | 路由内手动写 `external_service_logs` | TikHub adapter 当前不自动写 |
| 5 | Word 文件存储 | 本地 `storage/persona_reports/` | 项目阶段暂不上 OSS |
| 6 | 文件上传 | 后端解析（`file_parser.py`），不前端解析 | 与旧架构一致 |
| 7 | `===SPLIT===` 分隔 | AI Prompt 约定 + 后端拆分 | 一请求拿两份产物 |
| 8 | 删除策略 | 软删（`deleted_at`） | 符合一票否决项（不物理删） |
| 9 | 产出双写 | 生成完成同步写 `outputs` 表 | 运营统一产出中心可见 |
| 10 | 历史抽屉渲染位置 | 组件最外层（非 Step 3 内） | 所有步骤按钮可用 |

---

## 十二、测试要求（实际结果）

| 类型 | 结果 |
|------|------|
| 后端单测 + 集成 | ✅ 221/221 通过 |
| 前端单测（vitest） | ✅ 71/71 通过 |
| 手工 E2E | ✅ 三步流程全通 |

> 详见：`docs/tests/M2_Sprint3_persona-positioning_测试报告.md`

---

## 十三、验收标准（DoD）

| 验收项 | 状态 |
|--------|------|
| Migration 008 落地，`persona_reports` 表 + 索引 + trigger | ✅ |
| `PersonaReport` ORM + 注册到 `__init__.py` | ✅ |
| `file_parser.py` 支持 .docx/.pdf/.txt/.md（截断 8000 字符） | ✅ |
| `persona_docx.py` 支持 Markdown → Word（含标题/列表/引用/粗体） | ✅ |
| `routers/persona.py` 10 个 API 全部实现 + 鉴权 | ✅ |
| 前端 `PersonaPage.tsx` 三步向导 + 优化对话 + 历史抽屉 | ✅ |
| 前端路由 `/workspace/persona-positioning` + 创作中心菜单 | ✅ |
| TikHub adapter 扩展 `resolve_sec_user_id` / `fetch_user_videos` | ✅ |
| yunwu adapter 扩展 `chat_stream`（SSE + 自动写 AiCallLog） | ✅ |
| 产出双写 `outputs` 表（tool_code=`persona-positioning`） | ✅ |
| 管理端配置入口（绑 AI 模型 + Prompt） | ✅ |
| `workspace_tools` 注册（tool_code=`persona-positioning`，status=`dev`） | ✅ |
| 后端测试 221/221 通过 | ✅ |
| 前端测试 71/71 通过 | ✅ |
| v2 6 个 Bug 全部修复（详见测试报告） | ✅ |
| 契约文档同步（Base_API §1.3 + §9 + Base_Database §8） | ✅ |
| CLAUDE.md 7 红线 + 9 一票否决项无新增触发 | ✅ |

---

## 十四、CLAUDE.md 红线自检（事后核对）

| 红线 | 状态 | 说明 |
|------|------|------|
| ① 标准信封 | ✅ | 所有非 SSE/文件下载接口走 `success_response` / `error_response` |
| ② OperationLog | ✅ | generate（后台任务）/ export-word / delete 三处均写 |
| ③ 前端走 request.ts | ✅ | 普通接口走 request.ts；SSE/Blob/multipart 是例外（有守卫白名单） |
| ④ 契约同步 | ✅ | Base_API §1.3（persona 接口）+ §9（TikHub 凭证池）+ Base_Database §8 同步 |
| ⑤ README 更新 | ✅ | 根 README + backend/docs/README + frontend/docs/README 同步 |
| ⑥ AiCallLog 由 adapter 写 | ✅ | `yunwu.chat_stream()` finally 自动写，router 不重复 |
| ⑦ AsyncSessionLocal 注册 | ✅ | persona router 用 `get_db()`，不直接 import AsyncSessionLocal |

**9 条一票否决项**：无新增触发（删除走软删，所有列表有分页或限制 50 条）。

---

## 十五、风险与已知问题

| 风险 | 影响 | 状态 |
|------|------|------|
| TikHub 502 间歇性故障 | 抖音号解析偶发失败 | ⚠️ 已知（Cloudflare gateway 问题，需加 retry） |
| SSE 断连空报告 | 刷新页面可能产生 `failed` 记录 | ✅ 已修复（v2 Bug 4，空内容保护） |
| 历史记录无分页 | 超过 50 条后看不到旧记录 | ⚠️ 已知（限制 50 条），可后续加分页 |
| `service_credentials.secret_enc` 明文 | 凭证安全风险 | ⚠️ Sprint 3 债务，后续加密 |

---

## 十六、后续任务（不在本次范围）

1. **TikHub 502 重试机制**：adapter 层加 retry（max 3 次，指数退避）
2. **对标分析下拉选择**：新架构对标分析模块迁移时再加
3. **同步到素材库**：素材库模块迁移时再加
4. **历史记录分页**：超过 50 条后的浏览方案
5. **`service_credentials.secret_enc` 加密**：Sprint 3 债务
6. **Word 文件上 OSS**：当前本地存储，迁移后跨实例可用
