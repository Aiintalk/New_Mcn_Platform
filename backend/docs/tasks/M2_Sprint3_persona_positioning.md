# MCN_Backend_Agent — M2 Sprint 3 任务指令（人格定位迁移）

> 角色：MCN_Backend_Agent（后端开发 Claude）
> 工作目录：`backend/`
> PM 生成时间：2026-06-11（v2 更新：补充 Web 版增强功能）
> 前置条件：M2 Sprint 1 kol-intake 全部验收通过，TikHub adapter 可用，AI Key Pool 可用
> 完成后：回传 PM，等待前端联调

---

## M2 Sprint 3 目标

将旧架构 `persona-positioning-web` 功能 **1:1 迁移**到新架构。
功能逻辑与交互完全保留，替换底层服务调用（TikHub / AI / 文件处理），补充鉴权、AI 调用日志、结果存档。

旧架构路径（仅供参考，不修改）：
`D:\2026年工作\AI相关\AI工具箱新架构方案\AI工具箱网站\Ai_Toolbox\persona-positioning-web\`

### v2 新增功能（来自 Web 版增强）

| 功能 | 说明 |
|------|------|
| KOL 入驻导入 | Step 1 下拉选已完成的 KOL 入驻提交，自动填充达人资料 |
| 优化对话 | Step 3 多轮 AI chat，可采纳优化结果替换当前档案/规划 |
| 历史详情/删除 | 报告列表支持查看详情和删除 |
| Web 版 Prompt | 使用 Web 版系统 Prompt（含运营指定方向 A/B 分支） |

### 暂不实现（后续迁移素材库时再加）

| 功能 | 原因 |
|------|------|
| 对标分析下拉选择 | 新架构无对标分析模块，Step 2 仅保留文件上传 |
| 同步到素材库 | 新架构无素材库模块，暂只做 Word 导出 |

---

## 一、数据库迁移（008_persona_positioning.sql）

新建文件 `backend/migrations/008_persona_positioning.sql`

```sql
-- 008_persona_positioning.sql
-- 人格定位报告（persona-positioning）迁移

-- 1. 人格定位报告存档
CREATE TABLE persona_reports (
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
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_updated_at_persona_reports
    BEFORE UPDATE ON persona_reports
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_persona_reports_operator ON persona_reports(operator_id);
CREATE INDEX idx_persona_reports_status   ON persona_reports(status);


-- 2. AI 配置
-- config_key = 'persona_generation'
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
);
```

---

## 二、ORM 模型

新建 `backend/app/models/persona_report.py`：

```python
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.core.database import Base

class PersonaReport(Base):
    __tablename__ = "persona_reports"

    id                       = Column(Integer, primary_key=True)
    operator_id              = Column(Integer, ForeignKey("users.id"), nullable=False)
    douyin_id                = Column(String(200))
    douyin_nickname          = Column(String(200))
    top10_text               = Column(Text)
    recent30_text            = Column(Text)
    questionnaire_files      = Column(JSONB, default=list)
    supplement_text          = Column(Text)
    supplement_files         = Column(JSONB, default=list)
    benchmark_profile_files  = Column(JSONB, default=list)
    benchmark_plan_files     = Column(JSONB, default=list)
    profile_result           = Column(Text)
    plan_result              = Column(Text)
    raw_output               = Column(Text)
    influencer_name          = Column(String(200))
    profile_docx_path        = Column(String(500))
    plan_docx_path           = Column(String(500))
    status                   = Column(String(20), nullable=False, default="pending")
    generated_at             = Column(DateTime(timezone=True))
    created_at               = Column(DateTime(timezone=True), server_default=func.now())
    updated_at               = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

在 `backend/app/models/__init__.py` 中 import `PersonaReport`。

---

## 三、文件解析服务

新建 `backend/app/services/file_parser.py`

功能：解析上传文件，提取纯文本。

```python
async def parse_uploaded_file(file: UploadFile) -> str:
    """
    支持：.docx / .pdf / .txt / .md
    .docx → python-docx extractText
    .pdf  → pypdf / pdfminer 提取文本
    .txt / .md → 直接 decode
    截断至 8000 字符（与旧架构一致）
    """
```

依赖：
- `python-docx`（requirements.txt 已有）
- `pypdf`（新增，用于 PDF 解析，比 weasyprint 更轻量）
- `.txt` / `.md` 直接读取

> ⚠️ 旧架构用 mammoth（Node.js）和 unpdf。Python 侧用 python-docx + pypdf 替代，功能等价。

---

## 四、API 路由

新建 `backend/app/routers/persona.py`

所有接口均需 JWT 鉴权，`current_user.role in ["operator", "admin"]`。

---

### 4.1 POST `/api/persona/fetch-douyin` — 解析抖音账号

请求体：`{ "url": "抖音号或链接" }`

逻辑：
1. 调用 `tikhub_adapter.resolve_sec_user_id(url)` → 获取 `sec_user_id`、`nickname`
2. 调用 `tikhub_adapter.fetch_user_videos(sec_user_id, max_pages=10)` → 获取所有视频
3. 取 TOP10（按点赞排序）+ 最近30天
4. 格式化为文本（格式与旧架构 `formatVideos` 函数一致）

响应：
```json
{
  "nickname": "小红",
  "sec_user_id": "...",
  "total_videos": 156,
  "top10_count": 10,
  "recent30_count": 8,
  "top10_text": "---\n第1条 | 2026-05-01 | 点赞 2.3万\n...",
  "recent30_text": "..."
}
```

> TikHub adapter 已在新架构中实现，直接复用，无需重写。

---

### 4.2 POST `/api/persona/parse-file` — 解析上传文件

请求：`multipart/form-data`，字段名 `file`

逻辑：调用 `file_parser.parse_uploaded_file(file)`，截断至 8000 字符。

响应：`{ "text": "提取的纯文本内容" }`

错误：`400 { "error": "PDF 解析失败，请尝试手动粘贴内容" }`

---

### 4.3 POST `/api/persona/generate` — SSE 流式生成（核心接口）

请求体：
```json
{
  "influencer_info": "问卷内容文本（必填）",
  "top10_content": "TOP10 视频文案（可选）",
  "supplement_text": "补充备注（可选）",
  "benchmark_text": "对标资料文本（可选）",

  "douyin_id": "原始输入（可选，用于存档）",
  "douyin_nickname": "解析昵称（可选，用于存档）",
  "recent30_text": "（可选，用于存档）",
  "questionnaire_files": [{"filename": "xx.docx", "text": "..."}],
  "supplement_files": [{"filename": "xx.pdf", "text": "..."}],
  "benchmark_profile_files": [{"filename": "...", "text": "..."}],
  "benchmark_plan_files": [{"filename": "...", "text": "..."}]
}
```

逻辑：
1. 校验 `influencer_info` 非空
2. 读取 `kol_intake_configs` WHERE `config_key='persona_generation'`，获取 system_prompt 和 ai_model
3. 若 `ai_model_id` 为 NULL → 返回 `400 {"error": "AI 模型未配置，请联系管理员"}`
4. 构建 user_message（与旧架构 generate/route.ts 完全一致的拼接逻辑）：
   ```
   ## 对标账号资料（如有）...{benchmark_text}
   ## 目标达人的问答采集信息...{influencer_info}
   ## 目标达人点赞TOP10视频文案（如有）...{top10_content}
   ## 补充资料（如有）...{supplement_text}
   请根据以上信息，为目标达人生成专属的人格档案和内容规划...
   ```
5. 在 DB 插入 `PersonaReport`（status='generating'），获取 `report_id`
6. 调用 `yunwu_adapter.chat_stream(messages, system_prompt, ...)` → SSE 流式返回
   - `chat_stream()` 自动写 `AiCallLog`（feature='persona_generation'）
7. 在 SSE Header 中添加 `X-Report-Id: {report_id}`（前端存储，用于后续下载）
8. 流式完成后（后台 BackgroundTasks）：
   - 拆分 raw_output：`===SPLIT===` 前为 `profile_result`，后为 `plan_result`
   - 从 `profile_result` 第一行提取 influencer_name（格式：`# {名字} · 人格档案 v1.0`）
   - 调用 `generate_persona_docx(report_id, "profile", profile_result, influencer_name)`
   - 调用 `generate_persona_docx(report_id, "plan", plan_result, influencer_name)`
   - 更新 PersonaReport：status='ready'，generated_at=NOW()，docx_path 等
   - **双写 Output 记录**：插入 `outputs` 表（见下方「产出双写规则」）
   - 写 `OperationLog`（action='generate_persona_report'）
   - 异常时：status='failed'

SSE 响应格式：
```
Content-Type: text/event-stream
X-Report-Id: 42

data: 第一部分流式内容...

data: ===SPLIT===

data: 第二部分流式内容...

data: [DONE]
```

---

### 4.4 POST `/api/persona/export-word` — 导出 Word

请求体：
```json
{
  "report_id": 42,
  "type": "profile"
}
```

type 取值：`"profile"` 或 `"plan"`

逻辑：
1. 查询 `PersonaReport` WHERE `id=report_id AND operator_id=current_user.id`
2. 取对应 docx_path（profile_docx_path 或 plan_docx_path）
3. 若文件存在 → `FileResponse` 返回
4. 若文件不存在（生成中/失败）→ 实时调用 `generate_persona_docx` 生成后返回

Content-Disposition 格式：
```
attachment; filename*=UTF-8''人格档案_{influencer_name}_{date}.docx
attachment; filename*=UTF-8''内容规划_{influencer_name}_{date}.docx
```

---

### 4.5 GET `/api/persona/reports` — 历史报告列表

响应：当前运营的报告列表（最近50条，按 created_at 倒序）
```json
[
  {
    "id": 42,
    "influencer_name": "小红",
    "douyin_nickname": "小红的抖音",
    "status": "ready",
    "created_at": "2026-06-09T10:00:00Z"
  }
]
```

---

### 4.6 GET `/api/persona/reports/{id}` — 报告详情

条件：`operator_id = current_user.id`

响应：完整 PersonaReport（含 profile_result / plan_result）

### 4.7 GET `/api/persona/kol-submissions` — KOL 入驻提交列表（v2 新增）

运营选择已完成的 KOL 入驻数据，自动导入为达人资料。

逻辑：
1. 查询 `kol_intake_submissions` WHERE `status = 'completed'`，按 `submitted_at` 倒序
2. 去重：同一 `nickname` 只保留最新一条（与旧架构 `kol-submissions/route.ts` 逻辑一致）
3. 对每条提交：
   - 解析 `answers` JSONB，格式化为带标签的文本（与旧架构 `handleImportKol` 逻辑一致）
   - 包含字段：昵称、年龄城市、情感状态、子女情况、父母关系、一句话介绍、职业经历、独特经历、说话风格、绝对不做的内容、特殊背书、内容方向、目标受众、喜欢的博主、喜欢的抖音内容、自己最满意的内容
   - 附加 `report` 字段（AI 生成的入驻报告）

响应：
```json
[
  {
    "id": 15,
    "nickname": "小红",
    "submitted_at": "2026-06-01T10:00:00Z",
    "formatted_answers": "【昵称】小红\n【年龄城市】28岁 北京\n...",
    "report": "AI 入驻报告全文..."
  }
]
```

---

### 4.8 POST `/api/persona/optimize` — 优化对话（v2 新增）

SSE 流式返回。运营可对已生成的档案/规划进行多轮 AI 优化。

请求体：
```json
{
  "messages": [
    { "role": "user", "content": "请把一句话定位改得更简洁" },
    { "role": "assistant", "content": "好的..." }
  ],
  "current_content": "当前档案或规划的完整文本",
  "content_type": "profile",
  "influencer_info": "达人基础信息文本（构建 system prompt 用）",
  "benchmark_text": "对标资料文本（可选）"
}
```

逻辑：
1. 动态构建 system prompt（与旧架构 `page.tsx` 第 411-430 行逻辑一致）：
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
2. 调用 `yunwu_adapter.chat_stream(messages, system_prompt)` → SSE 流式返回
3. 记录 `ai_call_log`

SSE 响应格式：`text/event-stream`，逐 chunk 返回。

---

### 4.9 GET `/api/persona/reports/{id}` — 报告详情（v2 新增）

补充完整响应结构。条件：`operator_id = current_user.id`。

响应：
```json
{
  "id": 42,
  "influencer_name": "小红",
  "douyin_nickname": "小红的抖音",
  "douyin_id": "xiao_hong_123",
  "status": "ready",
  "profile_result": "人格档案完整文本...",
  "plan_result": "内容规划完整文本...",
  "raw_output": "完整 AI 输出（含 ===SPLIT===）...",
  "created_at": "2026-06-09T10:00:00Z",
  "generated_at": "2026-06-09T10:03:00Z"
}
```

---

### 4.10 DELETE `/api/persona/reports/{id}` — 删除报告（v2 新增）

逻辑：软删除（设置 `deleted_at`），非物理删除（符合项目一票否决项）。

条件：`operator_id = current_user.id AND deleted_at IS NULL`

响应：`success_response(data={"deleted": true})`

---

## 五、Web 版系统 Prompt（v2 更新）

> ⚠️ 使用 Web 版 prompt（含运营指定方向 A/B 分支），不是旧版 prompt。
> 完整 prompt 位于旧架构 `persona-positioning-web/app/api/generate/route.ts` 第 7-189 行。
> 管理员在后台「功能配置」中编辑时以 Web 版 prompt 为默认值。

核心差异（Web 版 vs 旧版）：
- 「一句话定位」有两种情况：A=运营指定方向 → 直接使用；B=自动分析稀缺性
- 补充资料标签改为「补充资料（运营手动填写，优先级最高）」
- 新增规则：纯内容赛道达人 → 零产品/品牌展示

---

## 六、Word 文档生成服务

新建 `backend/app/services/persona_docx.py`

参考旧架构 `export-word/route.ts` 中的 `markdownToParagraphs` 和 `parseInlineRuns` 逻辑，用 `python-docx` 实现等价功能。

```python
async def generate_persona_docx(
    report_id: int,
    doc_type: str,           # "profile" 或 "plan"
    content: str,
    influencer_name: str
) -> str:
    """
    将 Markdown 内容转换为 Word 文档。
    返回文件路径 storage/persona_reports/{report_id}_{doc_type}.docx
    """
```

支持的 Markdown 格式（与旧架构一致）：
- `# ## ### ####` → 对应 HEADING 1-4
- `- ` / `* ` → 无序列表
- `1. ` → 有序列表
- `> ` → 引用（斜体，缩进）
- `**text**` → 粗体
- 空行 → 空段落

文档头部格式：
```
{influencer_name} · {人格档案|内容规划}
生成时间：2026-XX-XX XX:XX:XX
（正文内容）
```

存储路径：`backend/storage/persona_reports/`，启动时 `os.makedirs(..., exist_ok=True)`。

---

## 七、问卷模板下载接口

新建静态接口，供前端「下载问卷模板」按钮使用。

### GET `/api/persona/questionnaire-template` — 下载问卷模板 Word

逻辑：调用 `generate_questionnaire_template()` 生成问卷模板 docx 并直接返回。

问卷结构（与旧架构 `export-questionnaire/route.ts` 中的 SECTIONS 完全一致）：

```
一、基本信息（4题，均必填）
  1. 达人的名字 / 昵称是什么？（粉丝怎么称呼 ta）*必填
  2. 年龄、所在城市？*必填
  3. 职业背景和从业经历？（做过什么、多少年、怎么走到今天的）*必填
  4. 想做的内容赛道是什么？（如美妆、母婴、美食等）*必填

二、个人特色（3题，均必填）
  5. 有什么专业资质、成就或独特经历？*必填
  6. 性格特点是什么？朋友会怎么形容 ta？*必填
  7. 想要什么样的说话风格？*必填

三、内容方向（3题，选填）
  8. 目标受众是什么人群？
  9. 有没有想对标或喜欢的博主？喜欢 ta 什么？
  10. 还有什么想补充的？
```

文档样式参照旧架构 export-questionnaire/route.ts（紫色主题，有页眉页脚）。

---

## 八、路由注册

`backend/app/main.py`：

```python
from app.routers import persona

app.include_router(persona.router, prefix="/api/persona", tags=["persona"])
```

---

## 九、注意事项

1. **SSE 与数据库**：generate 接口流式返回期间，流完成后的存档操作（拆分结果、写 docx、更新 DB）需在后台异步执行，不阻塞 SSE 流关闭。推荐 `asyncio.create_task()` 或 FastAPI `BackgroundTasks`。

2. **TikHub adapter 复用**：直接复用已有的 `tikhub_adapter`，不重写。如果现有 adapter 没有 `resolve_sec_user_id` 方法，参考旧架构 `lib/tikhub.ts` 补充。

3. **AI 配置**：`persona_generation` 配置初始 `ai_model_id=NULL`，管理员在后台「AI 配置」中绑定模型。`system_prompt` 从旧架构 `app/api/generate/route.ts` 中的 `SYSTEM_PROMPT` 常量直接复制（约170行，完整保留）。

4. **文件截断**：`parse_uploaded_file` 截断至 8000 字符，与旧架构一致，防止 token 超限。

5. **存档字段**：`questionnaire_files` / `supplement_files` / `benchmark_*_files` 以 `[{filename: str, text: str}]` 格式存入 JSONB，便于历史回溯。

6. **kol_intake_configs 表复用**：`persona_generation` 配置复用 `kol_intake_configs` 表（config_key 唯一），无需新建配置表。

7. **KOL 导入数据来源**：旧架构从文件系统读取 `/opt/kol-intake/data/*.json`；新架构从 `kol_intake_submissions` 表读取（WHERE status='completed'）。

8. **优化对话 system prompt**：动态构建，包含当前文档内容 + 达人信息 + 对标资料，不存入数据库配置表。

9. **Adapter 扩展**：以下方法需在现有 adapter 中新增（不新建 adapter 文件）：
   - `yunwu_adapter.chat_stream(messages, db, model_id, provider, user_id, feature, ...)` — SSE 流式调用，复用 `_pick_and_lock` / `_release` 逻辑，流完成后写 `AiCallLog`
   - `tikhub_adapter.resolve_sec_user_id(input)` — 解析抖音号/链接 → `sec_user_id` + `nickname`，参考旧架构 `lib/tikhub.ts`
   - `tikhub_adapter.fetch_user_videos(sec_user_id, max_pages=10)` — 分页获取视频列表，返回 `VideoItem[]`

---

## 十-A、产出双写规则

人格定位报告生成完成后，**同时写入 `outputs` 表**，运营可在「产出中心 → AI 产出」tab 查看。

```python
# 在 generate 接口流完成后的后台任务中，PersonaReport 更新为 ready 之后
output = Output(
    title=f"{influencer_name} · 人格档案 + 内容规划",
    tool_code="persona-positioning",
    tool_name="人格定位",
    content=raw_output,              # 完整 AI 输出
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

**双写的字段映射：**

| Output 字段 | 来源 |
|-------------|------|
| `title` | `{influencer_name} · 人格档案 + 内容规划` |
| `tool_code` | `persona-positioning` |
| `tool_name` | `人格定位` |
| `content` | `raw_output`（完整 AI 输出含 ===SPLIT===） |
| `content_json` | `{"report_id", "influencer_name", "profile_result", "plan_result"}` |
| `word_count` | `len(raw_output)` |
| `created_by` | `current_user.id` |

**前端「AI 产出」tab 自动展示**：产出中心已有 `GET /api/outputs` 按 `tool_code` 过滤，无需新增前端代码，`persona-positioning` 工具的产出会自动出现在列表中。

---

## 十-B、日志要求

| 场景 | 日志表 | 写入位置 | 字段 |
|------|--------|---------|------|
| AI 生成（generate） | `ai_call_logs` | `yunwu.chat_stream()` 内部自动写 | feature=`persona_generation` |
| AI 优化对话（optimize） | `ai_call_logs` | `yunwu.chat_stream()` 内部自动写 | feature=`persona_optimize` |
| TikHub 抖音号解析 | `external_service_logs` | `fetch-douyin` 路由内手动写 | service=`tikhub`, action=`resolve_sec_user_id` |
| TikHub 视频列表 | `external_service_logs` | `fetch-douyin` 路由内手动写 | service=`tikhub`, action=`fetch_user_videos` |
| 生成报告完成 | `operation_logs` | generate 后台任务内写 | action=`generate_persona_report` |
| 导出 Word | `operation_logs` | export-word 路由内写 | action=`export_persona_word` |
| 删除报告 | `operation_logs` | delete 路由内写 | action=`delete_persona_report` |

> 参考 `kol_tikhub.py` 中写 `ExternalServiceLog` 的模式；参考 `operator_intake_direct.py` 中写 `OperationLog` 的 `_write_op_log()` 辅助函数。

---

## 十-C、验收标准

1. `POST /api/persona/fetch-douyin` 传入有效抖音号 → 返回 nickname、top10_text、recent30_text，`external_service_logs` 有 TikHub 调用记录
2. `POST /api/persona/parse-file` 上传 .docx / .pdf / .txt → 返回提取文本（截断至8000字符）
3. `GET /api/persona/questionnaire-template` → 返回可下载的问卷模板 Word 文件
4. `POST /api/persona/generate`：
   - 传入 influencer_info → SSE 流式返回 AI 生成内容
   - 响应 Header 包含 `X-Report-Id`
   - 流式内容包含 `===SPLIT===` 分隔符
   - 生成完成后 DB 中 status='ready'，profile_docx_path / plan_docx_path 有值
   - `outputs` 表有对应产出记录（tool_code='persona-positioning'），运营端「AI 产出」tab 可见
   - `ai_call_logs` 有 AI 调用记录（feature='persona_generation'）
   - `operation_logs` 有操作记录
5. `POST /api/persona/export-word` 传入有效 report_id + type → 返回对应 Word 文件，`operation_logs` 有导出记录
6. `GET /api/persona/reports` → 返回当前运营的历史列表
7. `GET /api/persona/kol-submissions` → 返回已完成的 KOL 入驻列表，带格式化答案和报告
8. `POST /api/persona/optimize` → SSE 流式返回优化结果，`ai_call_logs` 有记录
9. `GET /api/persona/reports/{id}` → 返回完整报告（含 profile_result / plan_result）
10. `DELETE /api/persona/reports/{id}` → 软删除成功，`operation_logs` 有删除记录
11. 所有接口 unauthorized 请求返回 401
12. 管理员在「功能配置」可绑定 AI 模型和编辑 Prompt → 绑定后 generate 正常工作
