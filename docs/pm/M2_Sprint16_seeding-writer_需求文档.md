# M2 Sprint 16 — seeding-writer（种草内容仿写）需求文档

> 状态：**待 PM 写完 → 用户签收 → 进入节点 B**
> 创建日期：2026-06-23
> 对应旧架构模块：`Ai_Toolbox/seeding-writer-web`（Next.js 14 + Tailwind，4 步向导）
> 对应分支：`migrate/seeding-writer`（已从 main 拉出）
> 前序任务：Sprint 15 persona-writer（最接近的样板，4 步向导 + 4 Prompt + 2 模型）

---

## 一、工具概述

**名称**：seeding-writer（种草内容仿写）
**定位**：基于达人风格 + 产品信息 + 对标视频的种草短视频脚本仿写工具。4 步向导：选达人 → 产品信息 → 对标验证 → 种草仿写。
**业务铁律**：4 步业务逻辑 100% 忠实旧版，Prompt + AI 模型全部模板化（admin 可配）。
**关键差异 vs persona-writer**：
- 多了 Step 1 末尾的 **素材库管理**（达人维度共享，A 粘贴文本 + B 抖音链接导入）
- 多了 Step 2 **产品信息表单**（公司共享"团队产品库"）+ **文档解析**（PDF/Word/Excel/PPT）+ **AI 卖点讨论**
- 多了 Step 3 的 **ASR 转写**（抖音视频 → OSS → 阿里云 ASR → 文案，submit + poll 分离）
- 多了 Step 4 的 **字数校验**（超字自动 trim 重生成）
- 共 **5 Prompt + 2 模型**：sp_system_prompt（卖点提取）/ structure_analysis_prompt（结构拆解）/ ai_recommend_prompt（AI 推荐角度）/ writing_prompt（写作）/ iteration_prompt（迭代）+ light（claude-haiku-4-5）/ heavy（claude-opus-4-6）

---

## 二、需求澄清记录

| # | 问题 | 决策 |
|---|------|------|
| 1 | 产品信息怎么存？ | **B 新建 `seeding_writer_products` 表**（持久化"团队产品库"）|
| 2 | ASR 调用模式？ | **B submit + poll 分离**（前端轮询，避免长连接超时）|
| 3 | 文档解析放哪？ | **A 后端 Python**（加 pypdf / openpyxl / python-pptx）|
| 4 | 素材库 references 怎么存？ | **A 新建 `seeding_writer_references` 表**（达人维度共享）|
| 5 | 迁移范围？ | **完整迁移**（建表 + adapter + API + 前端 Tab + 测试 + 文档）|
| 6 | 素材上传方式？ | **A+B**（粘贴文本 + 抖音链接自动导入）|
| 7 | 产品库共享维度？ | **公司共享**（与素材库、kols 语义一致；仅 created_by 审计，不隔离查询）|
| 8 | ASR 依赖是否齐备？ | ✅ 已完整实现 `backend/app/adapters/asr.py` 267 行（Sprint 15 完成）|
| 9 | OSS 依赖是否齐备？ | ✅ 已接通（PR #3 Sprint 14）|
| 10 | TikHub 依赖是否齐备？ | ✅ 已接通（Sprint 15 persona-writer 用过 fetch_video_by_share_url）|

---

## 三、变与不变

### 不变（业务铁律）
- 4 步向导业务流：选达人 → 产品信息 → 对标验证 → 种草仿写
- Step 4 写作 Prompt 4 条铁律：不写开头 / 结构一致 / 字数只少不多 / 已确认卖点逐条覆盖
- Step 2 卖点讨论独立 chat 流（独立 spSystemPrompt）
- Step 3 抖音链接 → ASR 转写文案流程
- Step 4 字数校验（超字自动 trim）
- 3 种选题模式：沿用原文角度 / 自定义角度 / AI 推荐角度
- 终稿复制到剪贴板（clipboard）
- 卖点提取的 JSON 格式（name/category/price/sellingPoints/targetAudience/scenario/medicalAestheticAnchor）

### 变（新架构改造）
- 旧版 `${var}` 前端拼字符串 → 新版 `{{var}}` 后端 DB 模板渲染（同 persona-writer）
- 旧版 5 个 Prompt 硬编码 → DB 模板化（admin 可配）
- 旧版固定云雾默认模型 → admin 可配 2 个 AI 模型（light/heavy）
- 旧版本地文件 `data/personas/{name}/` → 新版 3 张表（configs/products/references）
- 旧版产品信息前端 state（不持久化）→ 新版 `seeding_writer_products` 表（公司共享，CRUD）
- 旧版 references 本地 markdown 文件 → 新版 `seeding_writer_references` 表（达人维度共享）
- 旧版无账号系统 → 新版 outputs 账号绑定（同 persona-writer）
- 旧版无 workspace_tools → 新架构 workspace_tools 注册 status='online'
- 旧版 Node.js 库（mammoth/xlsx/jszip/unpdf）→ 新版 Python 库（openpyxl/python-pptx/pypdf）

---

## 四、4 步业务流

### Step 1 选达人 + 素材库管理

| 子环节 | 用户操作 | 系统 |
|--------|---------|------|
| 1.1 选达人 | 下拉选达人（必选，filter persona+content_plan 非空）| 显示达人 content_plan 前 8 行作为预览（同 persona-writer）|
| 1.2 素材库（可选）| 维护当前达人的优质内容参考 | **GET /references?kol_id=X** 列表 |
| 1.2a 粘贴文本 | 点"上传种草爆款/对标种草/风格参考"按钮 → 填 title/likes/content | **POST /references**（type 区分 3 种）|
| 1.2b 抖音链接导入 | 粘贴抖音链接 → 自动 fetch-video + ASR 转文案 → 自动填 title/content/likes | **POST /references/import-from-douyin**（复用 fetch-video + ASR）|
| 1.2c 删除 | 点素材卡片删除 | **DELETE /references/{id}** |
| 1.3 点"下一步" | 进 Step 2 | — |

数据源：
- 达人列表：`kols` 表（filter `persona+content_plan 非空 AND status IN ('signed','pending_renewal') AND deleted_at IS NULL`，JOIN users 拿 creator_name）— 同 persona-writer
- 素材：`seeding_writer_references` 表（filter `kol_id=X AND deleted_at IS NULL`，**不按 created_by 隔离**）

### Step 2 产品信息

| 子环节 | 用户操作 | 系统 |
|--------|---------|------|
| 2.1 选产品 | 从产品库选已有产品 / 新建产品 | **GET /products**（公司共享列表）|
| 2.1a 手填 | 填 6 字段表单（name*/category/price/targetAudience/sellingPoints*/scenario）+ 保存到产品库 | **POST /products**（公司共享，所有人可见）|
| 2.1b 文档解析 | 上传 PDF/Word/Excel/PPT → AI 自动提取 | **POST /products/parse-document**（多文件合并，AI 提取 JSON）|
| 2.2 AI 卖点讨论 | 自动触发：基于产品资料原文讨论 3 个核心卖点 | **POST /products/extract-selling-points**（流式，spSystemPrompt）|
| 2.2a 迭代讨论 | 用户输入"第 2 个卖点换成 XX 方向"等指令 | 同上接口，多轮 chat |
| 2.2b 采用卖点到表单 | 点"采用卖点到表单"按钮，从 AI 输出提取【最终卖点】| 纯前端正则提取 + setState |
| 2.3 点"下一步" | 进 Step 3（需 productValid = name+sellingPoints 非空 + spApplied=true）| — |

### Step 3 对标验证

| 子环节 | 用户操作 | 系统 |
|--------|---------|------|
| 3.1 粘贴视频链接 | 粘贴抖音分享链接 | **POST /fetch-video**（TikHub 解析）|
| 3.2 ASR 转写 | 等 5-15 分钟（前端轮询）| **POST /transcribe/submit**（download → upload OSS → submit ASR → 返回 task_id）→ 前端每 5s **POST /transcribe/poll** |
| 3.3 文案确认 | 用户检查/修改转写文案 → 确认 | 纯前端 textarea |
| 3.4 进入 Step 4 | 自动触发结构拆解 | **POST /analyze-structure**（流式，light 模型）|

**ASR 数据流**：
```
抖音 play_url → 后端下载视频 → 上传 OSS → 生成 1 小时签名 URL → 提交 ASR → task_id
                                                                          ↓
                                                       前端每 5s 轮询 → 拿文案
```

### Step 4 种草仿写

| 子环节 | 用户操作 | 系统 |
|--------|---------|------|
| 4.1 选种草角度 | 3 种模式：沿用原文 / 自定义 / AI 推荐 | **POST /ai-recommend**（流式，仅 AI 模式触发）|
| 4.2 AI 写脚本 | 等流式输出 | **POST /chat**（scene=writing，heavy 模型，writing_prompt）|
| 4.3 字数校验 | 超字时自动触发 trim | 同 /chat 接口，多一轮 user message 要求压缩 |
| 4.4 多轮迭代 | 文本输入修改指令 | **POST /chat**（scene=iteration，heavy 模型，iteration_prompt）|
| 4.5 导出终稿 | 点"导出终稿"复制到剪贴板 | 纯前端 clipboard |
| 4.6 保存历史 | 点保存（可选）| **POST /save-output**（写 outputs + OperationLog）|

**3 个动作按钮**（同 persona-writer）：
- 保存历史 → POST /save-output
- 导出 .txt → 前端 Blob
- 导出 .docx → POST /export-word

---

## 五、运营端 API（19 接口）

基础路径：`/api/tools/seeding-writer`（operator / admin 鉴权，需已改密）

### 5.1 达人 + 素材库（Step 1）

| # | 接口 | 用途 | 信封 |
|---|------|------|------|
| 1 | GET `/kols/personas` | 达人下拉（同 persona-writer）| 标准 |
| 2 | GET `/references?kol_id=X` | 某达人的素材列表（达人维度共享）| 标准 |
| 3 | POST `/references` | 新增素材（粘贴文本）| 标准 + OperationLog |
| 4 | POST `/references/import-from-douyin` | 抖音链接导入素材（fetch-video + ASR）| 标准 + OperationLog |
| 5 | DELETE `/references/{id}` | 删除素材 | 标准 + OperationLog |

### 5.2 产品信息（Step 2）

| # | 接口 | 用途 | 信封 |
|---|------|------|------|
| 6 | GET `/products` | 产品库列表（公司共享，分页）| 标准 |
| 7 | POST `/products` | 新建产品 | 标准 + OperationLog |
| 8 | PUT `/products/{id}` | 更新产品 | 标准 + OperationLog |
| 9 | DELETE `/products/{id}` | 软删产品 | 标准 + OperationLog |
| 10 | POST `/products/parse-document` | 上传文档 AI 解析（multipart/form-data）| 标准（不走信封的 multipart 部分）|
| 11 | POST `/products/extract-selling-points` | AI 卖点讨论（流式）| 流式（裸文本例外）|

### 5.3 对标验证（Step 3）

| # | 接口 | 用途 | 信封 |
|---|------|------|------|
| 12 | POST `/fetch-video` | 抖音链接解析（复用 tikhub_adapter）| 标准 + OperationLog |
| 13 | POST `/transcribe/submit` | 提交 ASR 任务（download → OSS → submit）| 标准 + OperationLog |
| 14 | POST `/transcribe/poll` | 轮询 ASR 结果 | 标准（不写 OperationLog，高频）|
| 15 | POST `/analyze-structure` | 结构拆解（流式，light 模型）| 流式 |

### 5.4 种草仿写（Step 4）

| # | 接口 | 用途 | 信封 |
|---|------|------|------|
| 16 | POST `/ai-recommend` | AI 推荐种草角度（流式，light 模型）| 流式 |
| 17 | POST `/chat` | 写作 + 迭代（流式，heavy 模型）+ scene 字段 | 流式 + BackgroundTask（create_job=true 时）|
| 18 | POST `/save-output` | 保存产出 | 标准 + OperationLog |
| 19 | POST `/export-word` | 导出 .docx | StreamingResponse（例外）|
| — | GET `/outputs` | 历史记录（账号隔离，分页）| 标准 |

> **接口总数 19+1=20**：达人+素材库 5 + 产品 6 + 对标 4 + 仿写 4 + 历史 1 = 20。

### 5.5 接口细节

#### POST /references（粘贴文本）

Request：
```json
{
  "kol_id": 3,
  "title": "敏感肌精华种草爆款",
  "content": "全文...",
  "type": "种草爆款",       // 种草爆款 / 对标种草 / 风格参考
  "likes": 120000,           // 可选
  "source": "抖音"            // 可选
}
```

Response：`{ "success": true, "data": { "id": 456 } }`

#### POST /references/import-from-douyin

Request：`{ "kol_id": 3, "share_url": "https://v.douyin.com/xxx/", "type": "种草爆款" }`

后端流程：
1. tikhub_adapter.fetch_video_by_share_url → title/play_url/digg_count
2. httpx 下载 play_url → upload OSS → signed URL
3. asr_adapter.transcribe(signed_url) → 文案文本（阻塞，5-15 分钟）
4. 写 seeding_writer_references：title=视频标题 / content=ASR 文案 / likes=digg_count / source=抖音 / douyin_url=share_url

Response：`{ "success": true, "data": { "id": 456, "title": "...", "content": "..." } }`

> 决策：import-from-douyin **同步阻塞**（一次调用拿结果），因为这个接口是素材库管理员低频操作；不像 Step 3 transcribe 是用户向导核心环节需要轮询 UX。

#### POST /products/parse-document

Request：`multipart/form-data`（files 字段，支持多文件）

后端流程：
1. 按扩展名分流解析：PDF（pypdf）/ DOCX（python-docx）/ XLSX/XLS（openpyxl）/ PPTX（python-pptx）/ TXT（utf-8）
2. 合并所有文件文本（截断 8000 字符）
3. 调 yunwu（heavy 模型）+ sp_system_prompt（固定）→ JSON 提取
4. 返回结构化 ProductInfo

Response：
```json
{
  "success": true,
  "data": {
    "name": "...", "category": "...", "price": "...",
    "sellingPoints": "...", "targetAudience": "...", "scenario": "...",
    "medicalAestheticAnchor": "...", "_rawText": "..."
  }
}
```

#### POST /products/extract-selling-points（流式）

Request：`{ "raw_text": "产品资料原文", "preliminary_info": {...} }`

调 yunwu（heavy 模型）+ sp_system_prompt（DB 可配）→ 裸文本流（AI 讨论 3 个核心卖点）。

#### POST /transcribe/submit

Request：`{ "play_url": "https://..." }`

后端流程：
1. httpx 下载 play_url
2. oss_adapter.upload(buffer, object_key="seeding-writer/transcribe/{ts}.mp4")
3. oss_adapter.sign(object_key, expire=3600)
4. asr_adapter.submit_transcription(signed_url) → task_id
5. 返回 task_id

Response：`{ "success": true, "data": { "task_id": "abc123" } }`

#### POST /transcribe/poll

Request：`{ "task_id": "abc123" }`

调 asr_adapter.query_transcription(task_id) → 解析 StatusText：
- RUNNING / QUEUEING → `{ "status": "processing" }`
- SUCCESS → `{ "status": "done", "text": "拼接的文案" }`
- 其他 → 抛错

Response：`{ "success": true, "data": { "status": "done", "text": "..." } }`

#### POST /chat（scene 字段复用，同 persona-writer）

Request：
```json
{
  "scene": "writing",       // writing | iteration
  "persona_id": 3,
  "product_id": 7,
  "reference_ids": [456, 789],
  "transcript": "对标文案",
  "structure_analysis": "...",
  "topic": "...",
  "messages": [...],
  "create_job": false
}
```

调 yunwu（heavy 模型）+ writing_prompt 或 iteration_prompt（根据 scene）。

占位符 `{{name}} {{soul}} {{content_plan}} {{product_name}} {{product_category}} {{product_price}} {{product_selling_points}} {{product_target_audience}} {{product_scenario}} {{references}} {{transcript}} {{structure_analysis}} {{topic}}`。

---

## 六、管理端 API（2 接口）

基础路径：`/api/admin/seeding-writer`（admin 鉴权）

| # | 接口 | 用途 |
|---|------|------|
| 1 | GET `/configs` | 配置列表（通常仅 default 1 条）|
| 2 | PUT `/configs/{config_key}` | 更新 5 Prompt + 2 模型 + 启用 |

---

## 七、数据模型

### 7.1 `seeding_writer_configs` 表（新建）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | BIGSERIAL | 是 | 主键 |
| `config_key` | VARCHAR(64) | 是 | UNIQUE，默认 'default' |
| `sp_system_prompt` | TEXT | 否 | Step 2 卖点提取系统 Prompt（固定结构）|
| `parse_product_prompt` | TEXT | 否 | Step 2 文档解析系统 Prompt（JSON 输出）|
| `structure_analysis_prompt` | TEXT | 否 | Step 3 结构拆解 Prompt |
| `ai_recommend_prompt` | TEXT | 否 | Step 4.1 AI 推荐种草角度 Prompt |
| `writing_prompt` | TEXT | 否 | Step 4.2 写作 Prompt（铁律 + 模板）|
| `iteration_prompt` | TEXT | 否 | Step 4.4 迭代 Prompt |
| `light_model_id` | BIGINT | 否 | 轻量模型（结构拆解用），默认 `claude-haiku-4-5-20251001` |
| `heavy_model_id` | BIGINT | 否 | 重型模型（卖点/写作/迭代用），默认 `claude-opus-4-6` |
| `is_active` | BOOLEAN | 是 | 默认 TRUE |
| `created_at` | TIMESTAMPTZ | 是 | 默认 NOW() |
| `updated_at` | TIMESTAMPTZ | 是 | 默认 NOW() |

> 共 **6 Prompt + 2 模型**（比 persona-writer 多 2 个 Prompt）。

### 7.2 `seeding_writer_products` 表（新建）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | BIGSERIAL | 是 | 主键 |
| `name` | TEXT | 是 | 产品名称 |
| `category` | TEXT | 否 | 品类 |
| `price` | TEXT | 否 | 价格区间 |
| `selling_points` | TEXT | 否 | 核心卖点 |
| `target_audience` | TEXT | 否 | 目标人群 |
| `scenario` | TEXT | 否 | 使用场景 |
| `medical_aesthetic_anchor` | TEXT | 否 | 医美锚定建议 |
| `created_by` | BIGINT | 是 | 审计用 users.id（**不隔离查询**）|
| `created_at` | TIMESTAMPTZ | 是 | 默认 NOW() |
| `updated_at` | TIMESTAMPTZ | 是 | 默认 NOW() |
| `deleted_at` | TIMESTAMPTZ | 否 | 软删 |

索引：`idx_seeding_writer_products_name`（name 模糊查询）+ `idx_seeding_writer_products_created_by`

### 7.3 `seeding_writer_references` 表（新建）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | BIGSERIAL | 是 | 主键 |
| `kol_id` | BIGINT | 是 | REFERENCES kols(id) ON DELETE SET NULL |
| `title` | TEXT | 是 | 标题 |
| `content` | TEXT | 是 | 正文 |
| `type` | VARCHAR(32) | 否 | 种草爆款 / 对标种草 / 风格参考 |
| `source` | VARCHAR(32) | 否 | 抖音 / 小红书 / 手写 |
| `likes` | INT | 否 | 点赞数 |
| `douyin_url` | TEXT | 否 | 抖音源链接（导入时填）|
| `created_by` | BIGINT | 是 | 审计用（**不隔离查询**）|
| `created_at` | TIMESTAMPTZ | 是 | 默认 NOW() |
| `updated_at` | TIMESTAMPTZ | 是 | 默认 NOW() |
| `deleted_at` | TIMESTAMPTZ | 否 | 软删 |

索引：`idx_seeding_writer_references_kol_id` + `idx_seeding_writer_references_created_by`

### 7.4 Prompt 占位符

| 占位符 | 渲染值 | 用于哪个 Prompt |
|--------|--------|---------------|
| `{{name}}` | kols.name | writing / iteration |
| `{{soul}}` | kols.persona | writing / iteration |
| `{{content_plan}}` | kols.content_plan | writing / iteration |
| `{{product_name}}` | seeding_writer_products.name | writing / iteration |
| `{{product_category}}` | products.category | writing / iteration |
| `{{product_price}}` | products.price | writing / iteration |
| `{{product_selling_points}}` | products.selling_points | writing / iteration / ai_recommend |
| `{{product_target_audience}}` | products.target_audience | writing / iteration / ai_recommend |
| `{{product_scenario}}` | products.scenario | writing / iteration |
| `{{references}}` | references 拼接 | writing / iteration / ai_recommend |
| `{{transcript}}` | 对标文案 | structure_analysis / writing / iteration |
| `{{structure_analysis}}` | 拆解结果 | writing / iteration |
| `{{topic}}` | 选题 | writing |
| `{{raw_text}}` | 产品资料原文 | extract_selling_points |

### 7.5 workspace_tools 更新

新增（或 UPDATE 已有 'seeding-writer' disabled 记录）：
```sql
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, sort_order)
VALUES ('seeding-writer', '种草内容仿写', 'writer', '基于达人 + 产品 + 对标视频的种草脚本仿写', 'online', 5)
ON CONFLICT (tool_code) DO UPDATE SET status='online';
```

### 7.6 迁移文件

`backend/migrations/033_seeding_writer.sql`：
1. 建 3 张表（configs + products + references）
2. 种子 6 个 Prompt（从旧版 page.tsx 提取）
3. workspace_tools UPSERT（status='online'）

---

## 八、前端契约

### 8.1 文件清单（新建/修改）

| 操作 | 文件 |
|------|------|
| 新建 | `frontend/src/types/seedingWriter.ts` |
| 新建 | `frontend/src/api/seedingWriter.ts`（22 函数：20 operator + 2 admin）|
| 新建 | `frontend/src/pages/operator/SeedingWriterPage.tsx`（4 步向导主页）|
| 新建 | `frontend/src/pages/admin/SeedingWriterConfigTab.tsx` |
| 修改 | `frontend/src/App.tsx`（加 `/workspace/seeding-writer` 路由）|
| 修改 | `frontend/src/pages/operator/HomePage.tsx`（创作中心入口加 seeding-writer 卡片）|
| 修改 | `frontend/src/pages/admin/WorkspaceConfigPage.tsx`（增加 SeedingWriterConfigTab）|
| 新建 | `frontend/src/__tests__/components/pages/SeedingWriterPage.test.tsx` |

### 8.2 ConfigTab 字段（6 Prompt + 2 模型 + 启用）

| 字段 | 组件 | 说明 |
|------|------|------|
| `sp_system_prompt` | TextArea rows=10 | 卖点提取系统 Prompt |
| `parse_product_prompt` | TextArea rows=8 | 文档解析 Prompt |
| `structure_analysis_prompt` | TextArea rows=8 | 结构拆解 Prompt |
| `ai_recommend_prompt` | TextArea rows=8 | AI 推荐角度 Prompt |
| `writing_prompt` | TextArea rows=16 | 写作 Prompt（铁律）|
| `iteration_prompt` | TextArea rows=12 | 迭代 Prompt |
| `light_model_id` | Select allowClear | 默认 claude-haiku-4-5（id=2）|
| `heavy_model_id` | Select allowClear | 默认 claude-opus-4-6（id=4）|
| `is_active` | Switch | 启用 |

### 8.3 SeedingWriterPage 4 步向导结构

参照 persona-writer 3 步向导，扩展为 4 步：
- Step 1 选达人（同 persona-writer）+ 素材库管理面板（references CRUD）
- Step 2 产品信息（产品库选择/新建 + 6 字段表单 + 文档上传 + AI 卖点讨论）
- Step 3 对标验证（fetch-video + ASR submit/poll + 文案确认 + 结构拆解流式）
- Step 4 种草仿写（3 种选题 + AI 写作流式 + 字数校验 + 多轮迭代 + 保存 + 导出）

### 8.4 ASR 轮询实现（前端）

```typescript
// 提交 ASR
const { task_id } = await post('/tools/seeding-writer/transcribe/submit', { play_url })

// 轮询
let attempts = 0
while (attempts < 60) {
  await sleep(5000); attempts++
  setLoading(`转录中...（已等待 ${attempts * 5} 秒）`)
  const { status, text } = await post('/tools/seeding-writer/transcribe/poll', { task_id })
  if (status === 'done') { setTranscript(text); break }
  if (status !== 'processing') throw new Error('转录失败')
}
```

### 8.5 文档上传（multipart）

前端 FormData（不走 request.ts 标准 JSON 包装，例外）：
```typescript
const fd = new FormData()
files.forEach(f => fd.append('files', f))
const res = await fetch('/api/tools/seeding-writer/products/parse-document', {
  method: 'POST',
  headers: { Authorization: `Bearer ${token}` },  // 不设 Content-Type，让浏览器自动 multipart
  body: fd,
})
```

### 8.6 导出文件命名

```
种草脚本_${persona.name}_${product.name}_${topic || '终稿'}.txt
种草脚本_${persona.name}_${product.name}_${topic || '终稿'}.docx
```

---

## 九、测试要求

### 9.1 后端测试

| 类型 | 文件 | 用例数 |
|------|------|--------|
| 单测 prompt 渲染 | `tests/unit/services/test_seeding_writer_prompt.py` | 12+（14 占位符 + 缺失 fallback + 真实模板）|
| 单测文档解析 | `tests/unit/services/test_document_parser.py` | 8+（PDF/DOCX/XLSX/PPTX/TXT + 多文件合并 + 截断 + 异常）|
| 集测 operator | `tests/integration/routers/test_operator_seeding_writer.py` | 35+（鉴权 4 + personas 3 + references 5 + products 8 + parse-document 3 + extract-sp 3 + fetch-video 4 + transcribe 4 + analyze 3 + ai-recommend 3 + chat 5 + save 3 + export 2 + outputs 2）|
| 集测 admin | `tests/integration/routers/test_admin_seeding_writer.py` | 9+（鉴权 4 + GET 1 + PUT 4）|

### 9.2 前端测试

| 文件 | 用例数 |
|------|--------|
| `SeedingWriterPage.test.tsx` | 20+（4 步向导 + 素材库 CRUD + 产品库 CRUD + 文档上传 mock + ASR 轮询 mock + 卖点讨论 + 写作 + 迭代 + 保存 + 导出）|

### 9.3 红线自检（6/6 必过）

- convention_guard 全过
- 标准信封（流式 / export-word / multipart / poll 例外）
- OperationLog：references/products/fetch-video/save-output/PUT configs/chat(create_job=true) 都写
- request.ts：全部 JSON 调用（SSE 4 + multipart 1 + Blob 1 例外）
- AiCallLog 由 yunwu.py finally 写（router 不重复）
- AsyncSessionLocal 注册：流式接口（extract-sp/analyze/ai-recommend/chat）用，conftest patch 列表加

---

## 十、不在本次范围

- ❌ 旧版 transcribe/upload + poll（已被新版 submit/poll 两接口替代）
- ❌ 旧版 `data/personas/{name}/` 文件数据迁移（沿用新架构 kols 表 + 手工录素材）
- ❌ 产品库批量导入（Excel 上传多条产品）— 后续独立任务
- ❌ 素材库分类筛选 / 分页 — 当前数据量小，后续按需迭代
- ❌ 医美锚定（medicalAestheticAnchor）独立功能模块 — 仅作 product 字段存储
- ❌ tool_transcribe 改造（Sprint 3 债务，独立任务）

---

## 十一、验收标准 DoD

1. ✅ 管理端可配 6 Prompt + 2 AI 模型 + 启用开关
2. ✅ 运营端 4 步向导全走通
3. ✅ 素材库支持 A 粘贴文本 + B 抖音链接导入
4. ✅ 产品库公司共享（所有运营/管理员可见，可 CRUD）
5. ✅ 文档解析支持 PDF/Word/Excel/PPT/TXT 5 种格式
6. ✅ AI 卖点讨论可流式输出 + 采用到表单
7. ✅ ASR 转写：submit + poll 前端轮询 5-15 分钟拿结果
8. ✅ 3 种选题模式 + AI 写作 + 字数校验
9. ✅ outputs 账号绑定 + 历史可查
10. ✅ 5 张日志表全部留痕（ai_call_logs / tikhub_call_logs / oss_call_logs / asr_call_logs / operation_logs）
11. ✅ 所有测试通过（后端 pytest + 前端 vitest + convention_guard）
12. ✅ 契约文档同步（Base_API §23 + Base_Database §27）+ 前后端 README + PM 记忆
13. ✅ workspace_tools 中 seeding-writer status='online'

---

## 十二、关键技术决策

| # | 决策 | 理由 |
|---|------|------|
| 1 | 3 张新表（configs/products/references）| 完整迁移；products 公司共享；references 达人维度共享 |
| 2 | ASR 走 submit + poll 分离 | 避免长连接超时（5-15 分钟）；与旧版 UX 一致 |
| 3 | 文档解析后端 Python（pypdf/openpyxl/python-pptx）| 新架构后端是 Python，必须用 Python 库；与 OSS 已接通配合 |
| 4 | 抖音链接导入素材同步阻塞 | 素材库是低频管理员操作，不需要轮询 UX；接口数少 |
| 5 | Step 3 ASR 转写走轮询 | 用户高频向导操作，需要"已等待 N 秒"进度反馈 |
| 6 | extract_selling_points 走流式 chat | 与旧版一致；用户能看到 AI 实时讨论 |
| 7 | sp_system_prompt 也 DB 可配 | 即使旧版硬编码，DB 可配让运营尝试不同 Prompt；预留灵活性 |
| 8 | medical_aesthetic_anchor 仅存字段 | 旧版有此字段但不强需求；存下来供未来用 |
| 9 | 6 Prompt 合并到 1 张表 configs | 避免 6 张表 JOIN；DB 种子提供初值；admin 可改 |
| 10 | writing_prompt 14 个占位符 | 复用 persona-writer 模式；种子从旧版 page.tsx 提取 |
| 11 | 产品库 / 素材库不按 created_by 隔离 | 公司资产；与 kols 表语义一致；仅审计 |
| 12 | outputs 仍按 created_by 隔离 | 个人产出；与 persona-writer 一致；CLAUDE.md 红线「不能看他人数据」|

---

## 十三、CLAUDE.md 红线自检

| 红线 | 状态 | 说明 |
|------|------|------|
| 标准信封 | ✅ | 20 接口中 13 个用 success_response；extract-sp/analyze/ai-recommend/chat 流式（裸文本，例外）；export-word StreamingResponse（例外）；parse-document multipart（例外）|
| OperationLog | ✅ | references 3 + products 4 + fetch-video 1 + save-output 1 + PUT configs 1 + chat(create_job=true) 1 全写；poll 不写（高频）|
| 前端走 request.ts | ✅ | api/seedingWriter.ts 用 get/post；例外：SSE 4 + multipart 1 + Blob 1 |
| 契约同步 | ✅ | Base_API §23 + Base_Database §27 |
| README 更新 | ✅ | 前后端 README 同步 |
| AiCallLog 由 adapter 写 | ✅ | yunwu.py finally 自动写；OSS / ASR / TikHub adapter 各自 finally 写 |
| AsyncSessionLocal 注册 | ✅ | operator_seeding_writer 流式接口用 AsyncSessionLocal，conftest patch 列表加 |

**9 条一票否决项**：无新增触发。

---

## 十四、实施顺序（节点 B 拆解参考）

1. **分支**：`migrate/seeding-writer`（已创建）
2. **后端 Part A**（数据库 + ORM）：migration 033 + 3 个 ORM 模型（SeedingWriterConfig/Product/Reference）+ 注册 __init__
3. **后端 Part B**（Prompt + 解析 service）：
   - `services/seeding_writer_prompt.py`（render_prompt with 14 占位符）
   - `services/document_parser.py`（PDF/DOCX/XLSX/PPTX/TXT 解析）
   - requirements.txt 加 pypdf/python-docx/openpyxl/python-pptx
4. **后端 Part C**（operator + admin router）：
   - `routers/operator_seeding_writer.py`（20 接口）
   - `routers/admin_seeding_writer.py`（2 接口）
   - main.py 注册 + conftest patch 加 AsyncSessionLocal
5. **后端 Part D**（测试）：单测 prompt + 单测文档解析 + 集测 operator + 集测 admin
6. **前端 Part E**（types + api）：seedingWriter.ts
7. **前端 Part F**（页面）：SeedingWriterPage + SeedingWriterConfigTab
8. **前端 Part G**（路由 + 入口 + 测试）：App.tsx + HomePage + WorkspaceConfigPage + vitest
9. **回归**：后端 pytest 全量 + 前端 vitest 全量 + convention_guard
10. **节点 B++**：文档收尾 + commit + push + PR #7

---

## 十五、风险与预案

| 风险 | 概率 | 预案 |
|------|------|------|
| ASR 轮询超时（5-15 分钟）| 中 | 前端 max 60 次 × 5s = 5 分钟；超时提示"请重试或手动粘贴文案" |
| 文档解析格式多样（PDF 表格/图片）| 中 | pypdf 提取失败时返回 raw_text 截断；提示用户手填 |
| 抖音链接导入素材阻塞太久 | 中 | 单接口 max_wait=600s（同 transcribe），超时返 504 |
| AI 卖点讨论 JSON 解析失败 | 低 | 沿用旧版正则兜底（`/【最终卖点】/` 或 `/^\d+[\.\、]/`）|
| 产品库重复录入 | 低 | 公司共享；admin 可见所有人产品，重复可手动合并 |
| references 表 kol_id 软删后孤立 | 低 | ON DELETE SET NULL，references 保留但 kol_id 变 NULL |
| 14 占位符遗漏 | 低 | 单测覆盖全部占位符 + 缺失 fallback |

---

> **下一步**：PM 签收本文档 → 进入节点 B（拆解前后端任务 + 派 subagent）。
