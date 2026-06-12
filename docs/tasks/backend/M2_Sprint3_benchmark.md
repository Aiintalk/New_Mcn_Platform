# MCN_Backend_Agent — M2 Sprint 3 任务指令（对标分析助手）

> **角色**：后端开发  
> **工作目录**：`backend/`  
> **PM 生成日期**：2026-06-10  
> **前置依赖**：M2 Sprint 1（kol-intake）已完成，TikHub 适配器已就绪  
> **完成后**：回传 PM，等待前端联调

---

## M2 Sprint 3 目标

将旧架构 `benchmark-analyzer`（对标分析助手）迁移至新平台，实现：

```
运营输入抖音号/粘贴文案 → TikHub 拉取视频 → AI 分析生成人格档案+内容规划 → 导出 Word → 写入产出中心
```

管理员可配置 Prompt 和模型，所有操作产生日志。

---

## 一、数据库迁移

新建迁移文件 `backend/migrations/007_benchmark.sql`：

```sql
-- =====================================================================
-- M2 Sprint 3 — 对标分析助手
-- =====================================================================

-- 1. benchmark_configs（管理员配置：Prompt + 模型）
CREATE TABLE benchmark_configs (
  id            SERIAL PRIMARY KEY,
  config_key    VARCHAR(50)   NOT NULL UNIQUE,
  ai_model_id   INT           REFERENCES ai_models(id) ON DELETE SET NULL,
  system_prompt TEXT,
  is_active     BOOLEAN       NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_benchmark_configs_updated BEFORE UPDATE ON benchmark_configs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 初始配置：两个 Prompt（人格档案 + 内容规划合并为一个 config_key = 'analyze'）
INSERT INTO benchmark_configs (config_key, system_prompt, is_active) VALUES
('analyze', '你是一个专业的抖音账号对标分析师。用户会提供一个抖音账号的内容数据，你需要根据这些数据生成两份分析文档。

用户会提供两组数据：
1. 全账号点赞TOP10的视频文案（代表这个账号历史上最能打的内容）
2. 最近30天的全部视频文案（代表当前内容策略和方向）

你需要输出两份文档，用 ===SPLIT=== 分隔符分开：

第一份：【人格档案】
严格按照以下模板结构输出。每个板块都要填，数据不足的标注"待补充"。

# {账号名} · 人格档案 v1.0

> 用于以{账号名}第一人称口吻创作内容时加载。

---

## 一、一句话定位

> 格式：「{身份/经历} + {独特视角} + {服务谁}」

{一句话定位}

---

## 二、基本信息

| 字段 | 内容 |
|------|------|
| 年龄 | （从内容推断） |
| 城市 | |
| 家庭 | |
| 教育背景 | |
| 职业经历 | （简要，3句以内） |
| 账号名 | |
| 粉丝量级 | |
| 粉丝称呼 | |
| 公司/品牌 | |
| 内容赛道 | |
| 商业模式 | （带货/自有品牌/知识付费/广告等） |
| 客单价 | |

---

## 三、人设内核

### 3.1 权威来源

> 这个人凭什么让别人听她的？拆解为 2-3 个具体维度，每个维度必须能对应到经历素材库中的真实故事。

**维度一：{名称}**
说明：……
对应素材：→ 见 4.1

**维度二：{名称}**
说明：……
对应素材：→ 见 4.2

**维度三：{名称}**（可选）

### 3.2 与用户的关系

> 她站在什么位置跟用户说话？

{一句话定义}

### 3.3 差异化锚点

> 同赛道博主几百个，她跟别人最本质的区别是什么？

{差异化描述}

---

## 四、经历素材库

> 从视频内容中提取的真实故事，按权威维度分组。每条标注适用内容类型。

### 4.1 {对应维度一的素材}

- **{素材标题}**：{具体故事}（适用：{纯内容/带货/通用}）
- ……

### 4.2 {对应维度二的素材}

- ……

### 4.3 个人成长线（通用素材）

- ……

---

## 五、受众画像

### 5.1 核心人群

| 字段 | 描述 |
|------|------|
| 年龄段 | |
| 性别 | |
| 收入水平 | |
| 城市层级 | |
| 人生阶段 | |

### 5.2 核心痛点

1. **{痛点}**：{为什么痛}
2. ……

### 5.3 她们在哪些场景下会看这个人的内容

- {具体场景}
- ……

---

## 六、内容矩阵

### 6.1 双线逻辑

| 线 | 目的 | 是否带货 | 内容方向 |
|----|------|----------|----------|
| 信任线（纯内容） | 建立认知权威、积累信任 | 否 | {具体方向} |
| 商业线（带货/转化） | GMV / 品牌转化 | 是 | {具体方向} |

### 6.2 信任线内容系列

> 设计 4 个可以反复出的内容系列。每个系列有固定格式，换素材就能持续产出。

**系列一：「{系列名}」**
- 格式：{开头怎么起 → 中间怎么展开 → 结尾怎么收}
- 调性：{一句话}
- 可出内容：
  - {4条示例}

**系列二：「{系列名}」**
（同上格式）

**系列三：「{系列名}」**
（同上格式）

**系列四：「{系列名}」**
（同上格式）

### 6.3 货盘规划

> 直播间和带货视频的核心产品，按品类列出。

| 品类 | 品牌/产品名 | 备注 |
|------|------------|------|
| | | |

---

## 七、说话风格

### 7.1 语气特征

> 每条用「关键词 + 一句话解释 + 正例」的格式。从文案中提炼，带具体例句。

- **{关键词}**：{解释}。如："……"
- ……

### 7.2 常用句式

> 从文案中高频出现的句式，直接引用原文。

- "……"
- ……

### 7.3 禁用表达

> 从内容风格反推：这个人明显不会说的话。每条说清为什么禁。

- 不说"……"——因为{原因}
- ……

---

## 八、内容品味

### 8.1 她喜欢的内容特质

- **{特质}**：{一句话说明}
- ……

### 8.2 她不喜欢的内容

- ……

---

## 九、视觉与呈现风格

> 从视频内容推断出镜状态、拍摄场景、封面风格、剪辑节奏。数据不足的标注"待补充"。

### 9.1 出镜状态
### 9.2 拍摄场景
### 9.3 封面与字幕风格
### 9.4 剪辑节奏

---

## 十、写文案时的注意事项

> 给撰稿人/AI 的执行清单。

1. ……
2. ……

===SPLIT===

第二份：【内容规划】
这是一份更详细的内容操作方案，结构如下：

# {账号名} · 内容规划方案

## 一、人设定位

### 一句话
{同人格档案中的一句话定位}

### 凭什么听她/他的——核心支撑点
{从人格档案中的权威来源展开，写成叙事体}

---

## 二、内容体系

### 总览
用树状图展示：
- 纯内容各系列（与人格档案6.2对应）
- 带货内容类型
- 各类内容占比

### 每个系列详细说明
对每个纯内容系列给出：
- 定位和作用
- 内容公式（结构拆解）
- 选题库（每系列至少10条具体选题，从实际文案中提取或根据风格延展）

---

## 三、爆款规律
- TOP10内容的共性分析
- 开头钩子的常用模式
- 什么类型的选题容易爆

## 四、更新频率
- 每周大概更新几条
- 各类型内容的更新节奏

注意事项：
- 所有分析必须基于用户提供的实际文案，不要编造
- 引用具体文案作为证据
- 如果某个维度数据不足无法分析，坦诚说明，不要强行填充
- 语气客观专业，像一个资深内容策划在做竞品分析报告
- 人格档案和内容规划的信息要一致，不能自相矛盾', true);

-- 2. benchmark_analyses（分析记录）
CREATE TABLE benchmark_analyses (
  id              SERIAL PRIMARY KEY,
  account_name    VARCHAR(200),
  sec_user_id     VARCHAR(200),
  top10_content   TEXT,
  recent30_content TEXT,
  profile_result  TEXT,
  plan_result     TEXT,
  model_used      VARCHAR(100),
  tokens_used     INT,
  duration_ms     INT,
  status          VARCHAR(20)   NOT NULL DEFAULT 'pending',
  created_by      INT           NOT NULL REFERENCES users(id),
  created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX idx_benchmark_analyses_user ON benchmark_analyses(created_by);
CREATE INDEX idx_benchmark_analyses_created ON benchmark_analyses(created_at DESC);
CREATE TRIGGER trg_benchmark_analyses_updated BEFORE UPDATE ON benchmark_analyses
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 3. 注册 workspace_tools
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, tags, sort_order) VALUES
  ('benchmark', '对标分析助手', '选题分析', '拆解对标账号，输出人格档案与内容规划', 'online', '["智能生成","文档导出"]'::jsonb, 2)
ON CONFLICT (tool_code) DO UPDATE SET status = 'online', tags = EXCLUDED.tags;
```

---

## 二、ORM 模型

新建 `backend/app/models/benchmark.py`：

```python
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, TIMESTAMP, func
from app.core.database import Base


class BenchmarkConfig(Base):
    """管理员配置（Prompt + 模型）"""
    __tablename__ = "benchmark_configs"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    config_key    = Column(String(50), nullable=False, unique=True)
    ai_model_id   = Column(Integer, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    system_prompt = Column(Text, nullable=True)
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class BenchmarkAnalysis(Base):
    """分析记录"""
    __tablename__ = "benchmark_analyses"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    account_name     = Column(String(200), nullable=True)
    sec_user_id      = Column(String(200), nullable=True)
    top10_content    = Column(Text, nullable=True)
    recent30_content = Column(Text, nullable=True)
    profile_result   = Column(Text, nullable=True)
    plan_result      = Column(Text, nullable=True)
    model_used       = Column(String(100), nullable=True)
    tokens_used      = Column(Integer, nullable=True)
    duration_ms      = Column(Integer, nullable=True)
    status           = Column(String(20), nullable=False, default="pending")
    created_by       = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at       = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at       = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
```

---

## 三、TikHub 适配器扩展

在 `backend/app/adapters/tikhub.py` 中新增 3 个函数：

### 3.1 resolve_sec_user_id

```python
async def resolve_sec_user_id(input_str: str, db: AsyncSession) -> dict:
    """
    智能解析输入：支持抖音号（unique_id）、主页链接、分享链接。
    返回: {"sec_user_id": str, "nickname": str | None}
    """
```

**逻辑：**
- 输入包含 `http` → 调用 `GET /api/v1/douyin/web/get_sec_user_id?url=...`
- 否则 → 调用 `GET /api/v1/douyin/app/v3/handler_user_profile_v2?unique_id=...`
- 返回 sec_user_id 和 nickname

### 3.2 fetch_user_videos

```python
async def fetch_user_videos(sec_user_id: str, db: AsyncSession, max_pages: int = 10) -> list[dict]:
    """
    拉取用户全部作品（翻页，最多 max_pages 页）。
    返回: [{"desc": str, "digg_count": int, "create_time": int, "aweme_id": str}, ...]
    """
```

**逻辑：**
- 调用 `GET /api/v1/douyin/web/fetch_user_post_videos?sec_user_id=...&max_cursor=...&count=20`
- 翻页直到 has_more=false 或达到 max_pages
- 每次请求写 external_service_logs

### 3.3 辅助函数（纯逻辑，不需要 API 调用）

```python
def get_top10(videos: list[dict]) -> list[dict]:
    """按点赞排序取 TOP10"""

def get_recent30days(videos: list[dict]) -> list[dict]:
    """过滤最近 30 天的视频"""

def format_videos(videos: list[dict], label: str) -> str:
    """格式化视频列表为文本（用于 AI Prompt）"""
```

---

## 四、API 路由

### 4.1 运营端接口

新建 `backend/app/routers/operator_benchmark.py`：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/operator/benchmark/fetch` | 输入抖音号/链接，拉取视频数据 |
| POST | `/api/operator/benchmark/analyze` | 提交分析（流式 SSE） |
| GET | `/api/operator/benchmark/history` | 自己的分析历史列表 |
| GET | `/api/operator/benchmark/history/{id}` | 单条历史详情 |
| POST | `/api/operator/benchmark/export-word` | 导出 Word（人格档案/内容规划） |

#### POST /api/operator/benchmark/fetch

**请求体：**
```json
{"input": "DNX833 或 https://..."}
```

**响应：**
```json
{
  "success": true,
  "data": {
    "sec_user_id": "...",
    "nickname": "陶然",
    "total_videos": 156,
    "top10_count": 10,
    "recent30_count": 23,
    "top10_text": "---\n第1条 | 2026-05-01 | 点赞 3.2万\n...",
    "recent30_text": "---\n第1条 | ...\n..."
  }
}
```

**业务逻辑：**
1. 调用 `tikhub_adapter.resolve_sec_user_id(input, db)`
2. 调用 `tikhub_adapter.fetch_user_videos(sec_user_id, db)`
3. 调用 `get_top10()` + `get_recent30days()` + `format_videos()`
4. 返回格式化文本

#### POST /api/operator/benchmark/analyze

**请求体：**
```json
{
  "account_name": "陶然",
  "sec_user_id": "...",
  "top10_content": "...",
  "recent30_content": "..."
}
```

**响应：** SSE 流式返回，格式为纯文本（与旧架构一致）

**业务逻辑：**
1. 从 `benchmark_configs` 读取 config_key='analyze' 的 system_prompt 和 ai_model_id
2. 构造 user message：`"请分析以下抖音账号：{account_name}\n\n## 全账号点赞TOP10视频文案\n\n{top10_content}\n\n## 最近30天全部视频文案\n\n{recent30_content}"`
3. 调用 `yunwu_adapter.chat_stream()` 流式返回
4. 同时创建 `benchmark_analyses` 记录（status='generating'）
5. 流式完成后更新记录：status='completed', profile_result, plan_result, model_used, tokens_used, duration_ms
6. 写入 `outputs` 表（tool_code='benchmark', title='「{account_name}」对标分析'）
7. 写入 `task_jobs` + `task_logs`
8. 写入 `external_service_logs`

**注意：** 需要在 `app/adapters/yunwu.py` 中新增 `chat_stream()` 函数，支持 SSE 流式返回。参考旧架构 `lib/yunwu.ts` 的实现。

#### GET /api/operator/benchmark/history

**响应：**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "account_name": "陶然",
      "total_videos": 156,
      "status": "completed",
      "created_at": "2026-06-10T12:00:00Z"
    }
  ]
}
```

#### GET /api/operator/benchmark/history/{id}

**响应：** 完整记录含 profile_result + plan_result

#### POST /api/operator/benchmark/export-word

**请求体：**
```json
{
  "analysis_id": 1,
  "type": "profile"
}
```

**响应：** FileResponse（docx 文件）

**业务逻辑：**
1. 读取分析记录
2. 调用 `benchmark_report.generate_docx()` （复用 intake_report.py 的模式）
3. 返回文件

---

### 4.2 管理员接口

新建 `backend/app/routers/admin_benchmark.py`：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/benchmark/configs` | 配置列表 |
| PUT | `/api/admin/benchmark/configs/{key}` | 更新配置（Prompt + 模型） |
| GET | `/api/admin/benchmark/analyses` | 全部分析记录 |
| GET | `/api/admin/benchmark/analyses/{id}` | 分析详情 |
| POST | `/api/admin/benchmark/analyses/{id}/regenerate` | 重新生成 |

#### PUT /api/admin/benchmark/configs/{key}

**请求体：**
```json
{
  "ai_model_id": 1,
  "system_prompt": "...",
  "is_active": true
}
```

---

## 五、报告文件生成

新建 `backend/app/services/benchmark_report.py`：

```python
def generate_docx(analysis_id: int, content: str, account_name: str, doc_type: str) -> str:
    """
    生成 Word 文档，返回文件路径。
    doc_type: 'profile' 或 'plan'
    文件名: 人格档案_{account_name}_{date}.docx 或 内容规划_{account_name}_{date}.docx
    """
```

**复用 `intake_report.py` 的 Markdown → docx 转换逻辑。**

存储路径：`storage/benchmark_reports/{analysis_id}_{type}.docx`

---

## 六、SSE 流式支持

在 `backend/app/adapters/yunwu.py` 中新增：

```python
async def chat_stream(
    messages: list[dict],
    db: AsyncSession,
    model_id: str,
    provider: str = "yunwu",
    user_id: int | None = None,
    feature: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
):
    """
    流式调用 AI，yield 每个 chunk 的文本。
    使用 httpx.AsyncClient.stream() + SSE 解析。
    """
```

---

## 七、路由注册

在 `backend/app/main.py` 中添加：

```python
from app.routers.operator_benchmark import router as operator_benchmark_router
from app.routers.admin_benchmark import router as admin_benchmark_router

app.include_router(operator_benchmark_router, prefix="/api")
app.include_router(admin_benchmark_router, prefix="/api")
```

---

## 八、注意事项

1. **TikHub 视频拉取接口**：使用 `/api/v1/douyin/web/fetch_user_post_videos`，需要 sec_user_id。输入为抖音号时需先调 resolve 接口。
2. **流式返回**：SSE 格式需与前端 StreamingTextResponse 对齐，前端通过 ReadableStream 逐 chunk 读取并按 `===SPLIT===` 分割。
3. **outputs 写入时机**：流式完成后立即写入，content_json 存储 `{profile: ..., plan: ...}`。
4. **模型选择**：默认使用 `claude-sonnet-4-6`，管理员可在后台切换。
5. **错误处理**：TikHub 拉取失败返回 400，AI 生成失败更新 analysis.status='failed'。

---

## 九、联调修复记录（2026-06-10）

| # | 问题 | 根因 | 修复 |
|---|------|------|------|
| 1 | `PUT /api/admin/benchmark/configs/analyze` 返回 500 | `BenchmarkConfig.is_active` 模型定义为 `Column(Integer)`，但数据库列为 `BOOLEAN`。asyncpg 对类型严格，发送整数给布尔列导致报错 | 改为 `Column(Boolean)`，路由中 `is_active=1 if body.is_active else 0` → `is_active=body.is_active`，查询条件 `== 1` → `== True` |
| 2 | `POST /api/operator/benchmark/fetch` 返回 400 `'str' object has no attribute 'get'` | TikHub `get_sec_user_id` 接口的 `data` 字段直接返回 sec_user_id 字符串，而非 `{"sec_user_id": "..."}` 字典 | `resolve_sec_user_id` 中 `(raw.get("data") or {}).get("sec_user_id")` → `raw.get("data")`，增加 `isinstance(sec_uid, str)` 校验 |
| 3 | `POST /api/operator/benchmark/analyze` 返回 500 | SSE 流式生成器 `generate()` 复用了请求级 `db` 会话，请求上下文结束后会话关闭导致后续数据库操作失败 | 生成器内部改用 `async with AsyncSessionLocal() as stream_db` 创建独立会话 |

**涉及文件：**
- `backend/app/models/benchmark.py` — is_active 字段类型
- `backend/app/adapters/tikhub.py` — resolve_sec_user_id 解析逻辑
- `backend/app/routers/operator_benchmark.py` — is_active 查询条件 + 流式会话生命周期

---

## 十、验收标准

| # | 验收项 | 验证方法 |
|---|--------|----------|
| 1 | 数据库迁移成功 | `benchmark_configs` 有 1 条初始 Prompt，`benchmark_analyses` 表存在 |
| 2 | workspace_tools 注册 | `SELECT * FROM workspace_tools WHERE tool_code='benchmark'` 返回 status='online' |
| 3 | 抖音号解析 | `POST /api/operator/benchmark/fetch` 输入抖音号返回 sec_user_id + 视频数据 |
| 4 | 链接解析 | `POST /api/operator/benchmark/fetch` 输入主页链接返回 sec_user_id + 视频数据 |
| 5 | AI 分析流式 | `POST /api/operator/benchmark/analyze` 返回 SSE 流，包含 ===SPLIT=== 分隔的两份文档 |
| 6 | 历史记录 | 分析完成后 `GET /api/operator/benchmark/history` 可见新记录 |
| 7 | 产出中心 | 分析完成后 `GET /api/outputs` 可见 tool_code='benchmark' 的产出 |
| 8 | Word 导出 | `POST /api/operator/benchmark/export-word` 返回 docx 文件 |
| 9 | 管理员配置 | `PUT /api/admin/benchmark/configs/analyze` 可更新 Prompt 和模型 |
| 10 | 日志完整 | `task_jobs`、`external_service_logs`、`operation_logs` 均有记录 |
