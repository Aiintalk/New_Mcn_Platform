# MCN Information System Platform · M2 Base API 说明

> 文档定位：本文件定义 M2 阶段新增的所有 API 接口。M1 接口见 `docs/base/M1/MCN_M1_Base_API.md`。
> M2 目前包含 Sprint 1（kol-intake 红人入驻问卷）和 Sprint 2（运营首页重设计）。

---

## 1. M2 接口总览

### 1.1 Sprint 1 — kol-intake 入驻问卷

| 分类 | 接口数 | 路由前缀 |
|------|--------|----------|
| 公开接口（博主端） | 5 | `/api/intake` |
| 运营端接口 | 5 | `/api/operator/intake` |
| 管理员接口 | 13 | `/api/admin/intake` |
| **小计** | **23** | |

### 1.2 Sprint 2 — 运营首页

| 分类 | 接口数 | 路由前缀 |
|------|--------|----------|
| 运营首页统计 | 2 | `/api/operator/homepage` |

---

## 2. 通用约定

与 M1 完全一致，参见 `MCN_M1_Base_API.md` §2。关键点：

- **响应格式**：`{ success, code, message, data }`
- **鉴权**：Bearer Token（JWT），公开接口除外
- **字段命名**：响应全部使用 `snake_case`
- **时间格式**：ISO 8601 with timezone（`+08:00`）

---

## 3. kol-intake 公开接口（博主端）

> 路由文件：`backend/app/routers/intake_public.py`
>
> 权限：**无需鉴权**，通过 URL token 标识身份。

---

### GET `/api/intake/{token}` — 校验链接，返回初始状态

Response（200）：
```json
{
  "valid": true,
  "kol_name": "张三",
  "already_submitted": false,
  "existing_messages": []
}
```

业务规则：
- 首次访问写入 `kol_intake_links.used_at`
- 已提交时：`already_submitted: true`，`existing_messages` 返回历史对话（只读展示）
- 链接过期 → `410`
- 链接不存在 → `404`

---

### POST `/api/intake/{token}/chat` — AI 多轮对话（核心接口）

Request:
```json
{
  "messages": [
    {"role": "assistant", "content": "你好！我是…"},
    {"role": "user",      "content": "我叫小红"}
  ]
}
```

说明：
- 首次调用：`messages` 传空数组 `[]`，后端让 AI 生成开场白
- 后续调用：传完整对话历史（由前端维护）

Response（200）：
```json
{
  "reply": "太好了！那请问你的抖音账号名叫什么？",
  "role": "assistant"
}
```

- AI 未配置时 → `{"reply": null, "error": "AI对话暂未配置"}`

AI 配置：`kol_intake_configs` 中 `conversation_bridge` 记录，使用 haiku 模型，`max_tokens=300`。

---

### POST `/api/intake/{token}/submit` — 提交对话，触发报告生成

Request:
```json
{
  "messages": [...]
}
```

Response（200）：
```json
{
  "submission_id": 5,
  "report_status": "generating"
}
```

业务规则：
- 写入 `kol_intake_submissions`
- 后台通过 `BackgroundTasks` 异步生成报告（docx + PDF）
- 重复提交 → `409`
- 链接已过期 → `410`

报告生成：使用 `kol_intake_configs` 中 `report_generation` 记录配置的模型（opus，extended thinking budget=6000）。

---

### GET `/api/intake/{token}/status` — 轮询报告生成状态

Response（200）：
```json
{
  "report_status": "ready",
  "download_ready": true
}
```

`report_status` 枚举：`pending` / `generating` / `ready` / `failed`

---

### GET `/api/intake/{token}/download` — 博主下载报告

Query 参数：`?format=docx`（默认）或 `?format=pdf`

条件：token 未过期 + `report_status='ready'`

Response：文件流

- 首次下载写入 `kol_intake_submissions.kol_downloaded_at`
- `Content-Disposition: attachment; filename="MCN红人入驻评估报告.docx"`
- 文件存于 `backend/storage/intake_reports/{id}.docx`（不走 OSS）

---

## 4. kol-intake 运营端接口

> 路由文件：`backend/app/routers/intake_operator.py`
>
> 权限：`operator` 或 `admin`，operator 只能看自己创建的数据。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/operator/intake/links` | 生成分享链接 |
| GET  | `/api/operator/intake/links` | 我的链接列表 |
| GET  | `/api/operator/intake/submissions` | 我的提交列表 |
| GET  | `/api/operator/intake/submissions/{id}` | 提交详情（含 messages + ai_report） |
| GET  | `/api/operator/intake/submissions/{id}/download` | 运营下载报告 |

---

### POST `/api/operator/intake/links` — 生成分享链接

Request:
```json
{ "kol_name": "张三", "expires_hours": 24 }
```

Response:
```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "id": 1,
    "token": "abc123",
    "kol_name": "张三",
    "expires_at": "2026-06-09T10:00:00+08:00",
    "share_url": "/intake/abc123"
  }
}
```

业务规则：
- 工具 `kol-intake` 状态不为 `online` 时，返回 `403`
- `expires_hours` 范围：1 ~ 720（30天）

---

### GET `/api/operator/intake/links` — 我的链接列表

Response `data` 数组，每条包含：`id`、`token`、`kol_name`、`expires_at`、`used_at`、`submitted_at`、`is_active`。

---

### GET `/api/operator/intake/submissions` — 我的提交列表

Response `data` 数组，每条包含：`id`、`link_id`、`kol_name`、`report_status`、`created_at`。

---

### GET `/api/operator/intake/submissions/{id}` — 提交详情

Response `data`：完整字段，含 `messages` 对话历史和 `ai_report` 报告正文。

---

### GET `/api/operator/intake/submissions/{id}/download` — 运营下载报告

Query 参数：`?format=docx`（默认）或 `?format=pdf`

**运营下载条件**（满足其一才允许下载）：
1. `link.expires_at < NOW()`（链接已过期）
2. `submission.kol_downloaded_at IS NOT NULL`（博主已下载过）

不满足时 → `403: 链接仍在有效期内，请等待博主下载或链接到期后再操作`

首次下载写入 `operator_downloaded_at`。

---

## 5. kol-intake 管理员接口

> 路由文件：`backend/app/routers/intake_admin.py`
>
> 权限：`admin`。

### 5.1 题目管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET    | `/api/admin/intake/questions` | 题目列表（按 order_num，含 category） |
| POST   | `/api/admin/intake/questions` | 新增题目 |
| PATCH  | `/api/admin/intake/questions/{id}` | 编辑题目 |
| DELETE | `/api/admin/intake/questions/{id}` | 软删除（`is_active=false`） |
| PUT    | `/api/admin/intake/questions/reorder` | 批量更新 `order_num` |

### 5.2 AI 配置管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/intake/configs` | 获取两条配置 |
| PUT | `/api/admin/intake/configs/{key}` | 更新配置 |

`key` 枚举：`conversation_bridge` / `report_generation`

PUT Request:
```json
{ "ai_model_id": 3, "system_prompt": "你是一名专业的MCN机构运营顾问…" }
```

### 5.3 链接管理（admin 可看全部）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/intake/links` | 全部链接（含 operator 信息） |

### 5.4 提交记录（admin 可看全部）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/intake/submissions` | 全部提交（含 operator 信息） |
| GET | `/api/admin/intake/submissions/{id}` | 详情（含 messages + ai_report） |
| POST | `/api/admin/intake/submissions/{id}/regenerate` | 重新生成报告 |

---

## 6. 运营首页接口

> 路由前缀：`/api/operator/homepage`
>
> 权限：`operator`（仅看自己数据）或 `admin`（看全部）。

### GET `/api/operator/homepage/stats` — 统计卡片数据

Response:
```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "tasks_today": 12,
    "outputs_total": 356,
    "active_kols": 28,
    "tools_online": 3
  }
}
```

### GET `/api/operator/homepage/trend` — 图表数据（折线图趋势）

Query 参数：`?days=7`（默认）或 `?days=30`

Response:
```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "line_chart": [
      { "date": "06-01", "tasks": 8, "outputs": 6 }
    ],
    "tool_distribution": [
      { "name": "人设脚本仿写", "value": 45 },
      { "name": "对标分析", "value": 30 }
    ]
  }
}
```

---

## 7. M2 错误码补充

| HTTP 状态 | code | 含义 |
|-----------|------|------|
| 404 | `LINK_NOT_FOUND` | 链接不存在 |
| 409 | `ALREADY_SUBMITTED` | 该链接已提交过 |
| 410 | `LINK_EXPIRED` | 链接已过期 |
| 403 | `DOWNLOAD_NOT_ALLOWED` | 运营下载条件不满足 |
| 503 | `AI_NOT_CONFIGURED` | AI 模型未配置 |

---

## §18. Sprint 11 — 千川文案预审（qianchuan-preview）

> 路由前缀：`/api/tools/qianchuan-preview`（operator/admin 鉴权）  
> 管理端前缀：`/api/admin/qianchuan-preview`（admin 鉴权）  
> 数据库迁移：`024_qianchuan_preview.sql`

### 18.1 operator 接口

#### POST /api/tools/qianchuan-preview/parse-file

上传文案文件，解析返回文本。

请求：`multipart/form-data`，`file` 字段（`.txt` / `.md` / `.docx` / `.pages`）

响应（标准信封）：
```json
{
  "success": true,
  "data": {
    "text": "解析出的文本内容",
    "filename": "原文件名.txt"
  }
}
```

错误：400 `UNSUPPORTED_FORMAT`（不支持的文件格式）/ 400 `PARSE_ERROR`

---

#### POST /api/tools/qianchuan-preview/generate

SSE 流式生成文案预审报告。

请求 body：
```json
{
  "script_a": "原版爆款文案内容",
  "script_b": "我方文案内容"
}
```

响应：`StreamingResponse`（`text/plain; charset=utf-8`），流式输出 AI 报告文本。  
System Prompt 和 AI 模型从 `qianchuan_preview_configs` 表的 `default` 配置读取。

错误：400 `INVALID_INPUT`（script_a 或 script_b 为空）

---

#### POST /api/tools/qianchuan-preview/export-word

将预审报告导出为 Word 文件。

请求 body：
```json
{
  "content": "报告 Markdown 内容",
  "title": "千川文案预审报告"
}
```

响应：`StreamingResponse`（`.docx` 二进制），`Content-Disposition: attachment; filename*=UTF-8''...`

错误：400 `INVALID_INPUT`（内容为空）

---

### 18.2 admin 接口

#### GET /api/admin/qianchuan-preview/configs

获取预审配置列表。

响应（标准信封）：
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "config_key": "default",
      "ai_model_id": null,
      "system_prompt": "...",
      "is_active": true,
      "updated_at": "2026-06-18T..."
    }
  ]
}
```

---

#### PUT /api/admin/qianchuan-preview/configs/{config_key}

更新指定 config_key 的配置。

请求 body：
```json
{
  "system_prompt": "新的 Prompt 内容",
  "ai_model_id": null
}
```

响应（标准信封）：更新后的配置对象。

错误：404 `CONFIG_NOT_FOUND`（config_key 不存在）

---

## 19. 红人工作台复盘文件解析补充

#### POST /api/operator/workspace/{kol_id}/retrospective/parse-files

复盘材料解析接口保持现有 multipart 请求和标准信封响应不变。`files` 可上传 `.xlsx`、`.xls`、`.csv`；旧版 Excel `.xls` 由后端解析为每个工作表的文本，返回的每项继续保留原文件名与解析正文的一一对应关系。

错误：400 `INVALID_INPUT`（文件为空、旧版 Excel 损坏或无法提取有效内容）。

---

## 8. AI 开发硬性要求

1. 公开接口 `/api/intake/*` 不得加 JWT 鉴权中间件。
2. 运营接口数据隔离：operator 只能查 `operator_id = 当前用户` 的记录。
3. 报告生成必须走 `BackgroundTasks`，不允许在请求响应链内同步生成。
4. 文件存本地 `backend/storage/intake_reports/`，M2 不走 OSS。
5. 每次 AI 调用均须写 `ai_call_logs`。
6. API 修改必须先修改本文档，再改代码。
