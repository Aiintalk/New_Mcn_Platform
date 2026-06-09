# MCN_Backend_Agent — M2 Sprint 3 任务指令（人格定位迁移）

> 角色：MCN_Backend_Agent（后端开发 Claude）  
> 工作目录：`backend/`  
> PM 生成时间：2026-06-09  
> 前置条件：M2 Sprint 1 kol-intake 全部验收通过，TikHub adapter 可用，AI Key Pool 可用  
> 完成后：回传 PM，等待前端联调

---

## M2 Sprint 3 目标

将旧架构 `persona-positioning` 功能 **1:1 迁移**到新架构。  
功能逻辑与交互完全保留，替换底层服务调用（TikHub / AI / 文件处理），补充鉴权、AI 调用日志、结果存档。

旧架构路径（仅供参考，不修改）：  
`D:\2026年工作\AI相关\AI工具箱新架构方案\AI工具箱网站\Ai_Toolbox\persona-positioning\`

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
6. 调用 `yunwu_adapter.chat_stream(messages, system_prompt)` → SSE 流式返回
7. 在 SSE Header 中添加 `X-Report-Id: {report_id}`（前端存储，用于后续下载）
8. 流式完成后（后台）：
   - 拆分 raw_output：`===SPLIT===` 前为 `profile_result`，后为 `plan_result`
   - 从 `profile_result` 第一行提取 influencer_name（格式：`# {名字} · 人格档案 v1.0`）
   - 调用 `generate_persona_docx(report_id, "profile", profile_result, influencer_name)`
   - 调用 `generate_persona_docx(report_id, "plan", plan_result, influencer_name)`
   - 更新 PersonaReport：status='ready'，generated_at=NOW()，docx_path 等
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

---

## 五、Word 文档生成服务

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

## 六、问卷模板下载接口

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

## 七、路由注册

`backend/app/main.py`：

```python
from app.routers import persona

app.include_router(persona.router, prefix="/api/persona", tags=["persona"])
```

---

## 八、注意事项

1. **SSE 与数据库**：generate 接口流式返回期间，流完成后的存档操作（拆分结果、写 docx、更新 DB）需在后台异步执行，不阻塞 SSE 流关闭。推荐 `asyncio.create_task()` 或 FastAPI `BackgroundTasks`。

2. **TikHub adapter 复用**：直接复用已有的 `tikhub_adapter`，不重写。如果现有 adapter 没有 `resolve_sec_user_id` 方法，参考旧架构 `lib/tikhub.ts` 补充。

3. **AI 配置**：`persona_generation` 配置初始 `ai_model_id=NULL`，管理员在后台「AI 配置」中绑定模型。`system_prompt` 从旧架构 `app/api/generate/route.ts` 中的 `SYSTEM_PROMPT` 常量直接复制（约170行，完整保留）。

4. **文件截断**：`parse_uploaded_file` 截断至 8000 字符，与旧架构一致，防止 token 超限。

5. **存档字段**：`questionnaire_files` / `supplement_files` / `benchmark_*_files` 以 `[{filename: str, text: str}]` 格式存入 JSONB，便于历史回溯。

6. **kol_intake_configs 表复用**：`persona_generation` 配置复用 `kol_intake_configs` 表（config_key 唯一），无需新建配置表。

---

## 九、验收标准

1. `POST /api/persona/fetch-douyin` 传入有效抖音号 → 返回 nickname、top10_text、recent30_text
2. `POST /api/persona/parse-file` 上传 .docx / .pdf / .txt → 返回提取文本（截断至8000字符）
3. `GET /api/persona/questionnaire-template` → 返回可下载的问卷模板 Word 文件
4. `POST /api/persona/generate`：
   - 传入 influencer_info → SSE 流式返回 AI 生成内容
   - 响应 Header 包含 `X-Report-Id`
   - 流式内容包含 `===SPLIT===` 分隔符
   - 生成完成后 DB 中 status='ready'，profile_docx_path / plan_docx_path 有值
5. `POST /api/persona/export-word` 传入有效 report_id + type → 返回对应 Word 文件
6. `GET /api/persona/reports` → 返回当前运营的历史列表
7. 所有接口 unauthorized 请求返回 401
