# MCN Information System Platform · M2 Base API 说明

> 文档定位：本文件定义 M2 阶段新增的所有 API 接口。M1 接口见 `docs/base/M1/MCN_M1_Base_API.md`。
> M2 包含 Sprint 1（kol-intake 红人入驻问卷）、Sprint 2（运营首页重设计）、Sprint 3（人格定位 + TikHub 管理）、Sprint 4（tiktok-writer）、Sprint 5（selling-point-extractor）、Sprint 6（qianchuan-review）、Sprint 7（qianchuan-edit-review）。

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

### 1.3 Sprint 3 — 人格定位

| 分类 | 接口数 | 路由前缀 |
|------|--------|----------|
| 人格定位运营端 | 10 | `/api/persona` |

### 1.4 Sprint 3 — TikHub 管理

| 分类 | 接口数 | 路由前缀 |
|------|--------|----------|
| TikHub 管理端 | 10 | `/api/admin/tikhub` |

### 1.5 Sprint 4 — TikTok 脚本仿写

| 分类 | 接口数 | 路由前缀 |
|------|--------|----------|
| 运营端 | 3 | `/api/tools/tiktok-writer` |

### 1.6 Sprint 5 — 产品卖点提取器

| 分类 | 接口数 | 路由前缀 |
|------|--------|----------|
| 运营端 | 5 | `/api/tools/selling-point-extractor` |
| 管理端 | 2 | `/api/admin/selling-point` |

### 1.7 Sprint 6 — 千川脚本复盘

| 分类 | 接口数 | 路由前缀 |
|------|--------|----------|
| 运营端 | 4 | `/api/tools/qianchuan-review` |

### 1.8 Sprint 7 — 千川剪辑预审

| 分类 | 接口数 | 路由前缀 |
|------|--------|----------|
| 工具接口（截帧/转录/流式/Word导出/保存报告） | 5 | `/api/tools/` |

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

## 8. AI 开发硬性要求

1. 公开接口 `/api/intake/*` 不得加 JWT 鉴权中间件。
2. 运营接口数据隔离：operator 只能查 `operator_id = 当前用户` 的记录。
3. 报告生成必须走 `BackgroundTasks`，不允许在请求响应链内同步生成。
4. 文件存本地 `backend/storage/intake_reports/`，M2 不走 OSS。
5. 每次 AI 调用均须写 `ai_call_logs`。
6. API 修改必须先修改本文档，再改代码。

---

## 9. Sprint 3 — 人格定位接口（persona-positioning）

> 路由文件：`backend/app/routers/persona.py`
>
> 权限：`operator` 或 `admin`（`require_operator`）。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/persona/fetch-douyin` | 解析抖音账号（分享文本→昵称+视频列表） |
| POST | `/api/persona/parse-file` | 解析上传文件（docx/txt） |
| POST | `/api/persona/generate` | SSE 流式生成人格档案+内容规划 |
| POST | `/api/persona/optimize` | SSE 流式优化对话 |
| POST | `/api/persona/export-word` | 导出 Word 文档 |
| GET  | `/api/persona/questionnaire-template` | 下载问卷模板 |
| GET  | `/api/persona/kol-submissions` | KOL 入驻列表（供导入达人资料） |
| GET  | `/api/persona/reports` | 报告列表（当前用户最近 50 条） |
| GET  | `/api/persona/reports/{id}` | 报告详情 |
| DELETE | `/api/persona/reports/{id}` | 软删除报告 |

### POST `/api/persona/fetch-douyin` — 解析抖音账号

Request:
```json
{ "douyin_text": "长按复制此条消息... https://v.douyin.com/xxx/" }
```

Response:
```json
{
  "nickname": "然然",
  "sec_user_id": "MS4w...",
  "video_count": 10,
  "top_videos": [
    { "desc": "视频描述", "stats": { "digg_count": 1234, "comment_count": 56 } }
  ]
}
```

### POST `/api/persona/generate` — SSE 流式生成

Request:
```json
{
  "douyin_text": "...",
  "douyin_nickname": "然然",
  "sec_user_id": "MS4w...",
  "top_videos": [...],
  "file_content": "上传文件解析后的文本",
  "kol_submission_id": null,
  "additional_info": "补充信息"
}
```

Response：SSE `text/event-stream`，逐 chunk 输出 AI 生成内容。

AI 输出用 `===SPLIT===` 分隔两部分：人格档案 + 内容规划。

### POST `/api/persona/optimize` — SSE 流式优化对话

Request:
```json
{
  "report_id": 4,
  "type": "profile",
  "messages": [
    { "role": "user", "content": "让语气更活泼一点" }
  ]
}
```

Response：SSE 流式输出优化后的完整内容。

### POST `/api/persona/export-word` — 导出 Word

Request:
```json
{ "report_id": 4, "type": "profile" }
```

Response：文件流 `Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document`

---

## 10. Sprint 3 — TikHub 管理接口

> 路由文件：`backend/app/routers/admin_tikhub.py`
>
> 权限：`admin`（`require_admin`）。

### 10.1 统计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/tikhub/stats` | 调用统计（总量/今日/平均延迟/活跃 Key 数） |

### 10.2 Key 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/tikhub/keys` | Key 列表（分页） |
| POST | `/api/admin/tikhub/keys` | 新增 Key |
| PUT | `/api/admin/tikhub/keys/{id}` | 编辑 Key（标签/备注） |
| DELETE | `/api/admin/tikhub/keys/{id}` | 删除 Key |
| POST | `/api/admin/tikhub/keys/{id}/test` | 测试 Key 连通性 |
| POST | `/api/admin/tikhub/keys/{id}/enable` | 启用 Key |
| POST | `/api/admin/tikhub/keys/{id}/disable` | 停用 Key |

### 10.3 端点统计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/tikhub/endpoints` | 各端点调用次数统计 |

### 10.4 用户排行

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/tikhub/users` | 用户调用排行（分页） |

---

## 10A. OSS 凭证与调用统计接口（Sprint 4+）

> 路由文件：`backend/app/routers/admin_oss.py`（统计）+ `backend/app/routers/admin_credentials.py`（凭证 CRUD，通用）
>
> 权限：`admin`（`require_admin`）。
>
> 说明：OSS 复用通用 `service_credentials` 表（provider='oss'），不单独建凭证表。
> OSS 调用日志由 adapter（`app/adapters/oss.py`）在 finally 块写入 `oss_call_logs` 表。

### 10A.1 统计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/oss/stats` | 三维统计：overview（总调用/今日/平均延迟/活跃凭证数）+ operations[]（按 upload/download/delete 聚合）+ users[]（TOP10）+ trend[]（近 7 天） |

Response data 结构：
```json
{
  "overview": {
    "total_calls": 1234,
    "today_calls": 56,
    "avg_latency_ms": 120.5,
    "active_keys": 2,
    "total_keys": 3
  },
  "operations": [
    { "operation": "upload", "calls": 1000, "percentage": 81.0 }
  ],
  "users": [
    { "user_id": 1, "username": "admin", "calls": 50 }
  ],
  "trend": [
    { "date": "06-15", "calls": 10 }
  ]
}
```

### 10A.2 操作统计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/oss/operations` | 按 operation 聚合：calls / percentage / avg_latency_ms / success_rate |

### 10A.3 用户排行

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/oss/users` | 按用户聚合：user_id / username / role / calls / last_called_at（支持 start_date / end_date / limit 参数） |

### 10A.4 OSS 凭证 CRUD（复用通用凭证接口）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/config/credentials?provider=oss` | 凭证列表（分页） |
| POST | `/api/admin/config/credentials` | 新增 OSS 凭证（provider='oss', config={access_key_id, bucket, endpoint}) |
| PATCH | `/api/admin/config/credentials/{id}` | 编辑凭证（含密钥轮换） |
| DELETE | `/api/admin/config/credentials/{id}` | 删除凭证（物理删除） |
| POST | `/api/admin/config/credentials/{id}/test` | 测试连通性（调 OSS get_bucket_info，保存 last_tested_at + last_latency_ms） |
| POST | `/api/admin/config/credentials/{id}/enable` | 启用 |
| POST | `/api/admin/config/credentials/{id}/disable` | 停用 |

### 10A.5 文件上传/下载/删除（造 OSS 调用场景）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/files` | 上传文件到 OSS（operator 权限）。对象键：`uploads/{user_id}/{yyyymmdd}/{uuid}.{ext}`，大小限制 50MB |
| GET | `/api/files/{file_id}/download-url` | 生成 OSS 签名下载 URL（1 小时有效） |
| DELETE | `/api/files/{file_id}` | 软删数据库 + 调 OSS delete_file（失败不阻塞软删） |

---

## 10B. ASR 凭证与调用统计接口（Sprint 4+）

> 路由文件：`backend/app/routers/admin_asr.py`（统计）+ `backend/app/routers/admin_credentials.py`（凭证 CRUD，通用）
>
> 权限：`admin`（`require_admin`）。
>
> 说明：ASR（阿里云智能语音交互 — 录音文件识别）复用通用 `service_credentials` 表（provider='asr'）。
> ASR 调用日志由 adapter（`app/adapters/asr.py`）在 finally 块写入 `asr_call_logs` 表。

### 10B.1 统计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/asr/stats` | 三维统计：overview（总调用/今日/平均延迟/活跃凭证数）+ operations[]（按 submit/query 聚合）+ users[]（TOP10）+ trend[]（近 7 天） |

Response data 结构：
```json
{
  "overview": {
    "total_calls": 2345,
    "today_calls": 78,
    "avg_latency_ms": 210.5,
    "active_keys": 2,
    "total_keys": 4
  },
  "operations": [
    { "operation": "submit", "calls": 1800, "percentage": 76.8 }
  ],
  "users": [
    { "user_id": 1, "username": "admin", "calls": 120 }
  ],
  "trend": [
    { "date": "06-15", "calls": 40 }
  ]
}
```

### 10B.2 操作统计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/asr/operations` | 按 operation 聚合：calls / percentage / avg_latency_ms / success_rate |

### 10B.3 用户排行

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/asr/users` | 按用户聚合：user_id / username / role / calls / last_called_at（支持 start_date / end_date / limit 参数） |

### 10B.4 ASR 凭证 CRUD（复用通用凭证接口）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/config/credentials?provider=asr` | 凭证列表（分页） |
| POST | `/api/admin/config/credentials` | 新增 ASR 凭证（provider='asr', config={app_key, region}, api_key="access_key_id\naccess_key_secret"） |
| PATCH | `/api/admin/config/credentials/{id}` | 编辑凭证（含密钥轮换：同时填 AccessKey ID + Secret 才生效） |
| DELETE | `/api/admin/config/credentials/{id}` | 删除凭证（物理删除） |
| POST | `/api/admin/config/credentials/{id}/test` | 测试连通性（调 GetTaskResult 用 probe TaskId，不依赖测试音频；保存 last_tested_at + last_latency_ms） |
| POST | `/api/admin/config/credentials/{id}/enable` | 启用 |
| POST | `/api/admin/config/credentials/{id}/disable` | 停用 |

### 10B.5 凭证 config / api_key 字段格式

```json
{
  "provider": "asr",
  "label": "上海生产环境",
  "api_key": "LTAIabcd1234\nsecret5678",
  "weight": 10,
  "config": {
    "app_key": "阿里云 ISI 项目 AppKey",
    "region": "cn-shanghai"
  }
}
```

`api_key` 用 `\n` 分隔 AccessKey ID 和 Secret（与 OSS 单一 secret 不同）。region 支持：`cn-shanghai`（默认）/ `cn-beijing` / `cn-shenzhen`。

### 10B.6 测试端点行为

为避免依赖测试音频文件，ASR 测试端点调用 `GetTaskResult` 用一个固定 probe TaskId（`test-connectivity-probe-task-id`），阿里云必返回业务错误（如 `41050010 TASK_EXPIRED`）。只要不抛认证/签名异常，就认为连通性 OK：

```json
// 成功
{ "status": "ok", "latency_ms": 120, "status_text": "FILE_TRANS_TASK_EXPIRED", "status_code": 41050010 }

// 失败（凭证/签名错误）
{ "status": "error", "latency_ms": 80, "error": "InvalidAccessKeyId..." }
```

---

## 11. M2 错误码补充（Sprint 3）

| HTTP 状态 | code | 含义 |
|-----------|------|------|
| 400 | `AI_MODEL_NOT_CONFIGURED` | 人格定位 AI 模型未配置 |
| 400 | `REPORT_NOT_READY` | 报告未生成完成 |
| 400 | `OPTIMIZATION_FAILED` | AI 优化失败 |
| 404 | `REPORT_NOT_FOUND` | 报告不存在 |

---

## 12. Sprint 5 — 产品卖点提取器（selling-point-extractor）

> 路由文件：`backend/app/routers/operator_selling_point.py`（运营端）、`backend/app/routers/admin_selling_point.py`（管理端）
> 权限：JWT 鉴权。运营端：operator / admin；管理端：admin 专属

### 12.1 接口总览

| 方法 | 路径 | 角色 | 说明 |
|------|------|------|------|
| GET | `/api/admin/selling-point/configs` | admin | 配置列表 |
| PUT | `/api/admin/selling-point/configs/{key}` | admin | 更新 Prompt / 模型 / 激活状态 |
| POST | `/api/tools/selling-point-extractor/chat` | operator/admin | AI 流式对话（raw text stream）|
| POST | `/api/tools/selling-point-extractor/parse-file` | operator/admin | 文件解析 |
| GET | `/api/tools/selling-point-extractor/history` | operator/admin | 历史列表 / 单条 |
| POST | `/api/tools/selling-point-extractor/history` | operator/admin | 保存历史记录 |
| DELETE | `/api/tools/selling-point-extractor/history` | operator/admin | 软删除 |

### 12.2 GET `/api/admin/selling-point/configs`

返回所有配置（目前只有 `config_key='extract'` 一条）：
```json
{
  "success": true,
  "data": [{
    "id": 1, "config_key": "extract",
    "ai_model_id": null, "system_prompt": "...",
    "is_active": true, "updated_at": "ISO 8601"
  }]
}
```

### 12.3 PUT `/api/admin/selling-point/configs/{config_key}`

Request：`{ "ai_model_id": int|null, "system_prompt": "string", "is_active": bool }`
Response：`{ "success": true, "data": { "config_key": "extract" } }`
404 + code=`RESOURCE_NOT_FOUND` 当 key 不存在。

### 12.4 POST `/api/tools/selling-point-extractor/chat`

Request：`{ "messages": [{"role": "user"|"assistant", "content": "string"}] }`
（**无 systemPrompt 字段**，后端从 `selling_point_configs` 表读取）

Response：`text/plain` 流式文本（raw text stream，非 SSE）

503 + code=`CONFIG_NOT_FOUND` 当配置未激活。

### 12.5 POST `/api/tools/selling-point-extractor/parse-file`

Request：`multipart/form-data`，字段名 `file`

Response：
```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": { "text": "string", "filename": "string" }
}
```

支持格式：`.txt` / `.md` / `.docx` / `.pdf`（pdfplumber）/ `.pages`（zipfile+snappy）/ `.doc`（返回提示）/ 其他（UTF-8）

### 12.6 GET `/api/tools/selling-point-extractor/history`

不带 id：返回列表 `data: { "records": [{ "id", "productName", "createdAt", "summary" }] }`（全员共享）
带 `?id={id}`：返回单条 `data: { "record": { "id", "productName", "result", "chatHistory", "briefFiles", "scriptFiles", "createdAt" } }`

### 12.7 POST `/api/tools/selling-point-extractor/history`

Request：`{ "productName": "string", "result": "string", "chatHistory": [...], "briefFiles": [...], "scriptFiles": [...] }`
Response：`{ "success": true, "code": "OK", "data": { "id": "string" } }`

### 12.8 DELETE `/api/tools/selling-point-extractor/history?id={id}`

软删除（设 `deleted_at`）。Response：`{ "success": true, "code": "OK", "data": { "id": id } }`

### 12.9 错误码

| HTTP | code | 含义 |
|------|------|------|
| 400 | `INVALID_INPUT` | messages/result 为空 |
| 404 | `NOT_FOUND` | 历史记录不存在或已删除 |
| 404 | `RESOURCE_NOT_FOUND` | 配置 key 不存在 |
| 422 | `PARSE_ERROR` | 文件格式不支持（ValueError）|
| 500 | `PARSE_ERROR` | 文件解析内部错误 |
| 503 | `CONFIG_NOT_FOUND` | 配置未激活 |

---

## 13. Sprint 4 — TikTok 脚本仿写（tiktok-writer）

> 路由文件：`backend/app/routers/operator_tiktok_writer.py`
> 权限：JWT 鉴权，operator / admin（`require_operator`）
> 无独立配置表：Prompt 由前端传入（`systemPrompt` 字段），不存 DB

### 13.1 接口总览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tools/tiktok-writer/chat` | AI 流式对话（raw text stream） |
| POST | `/api/tools/tiktok-writer/export-word` | 导出 Word 文档（docx 二进制流） |
| GET | `/api/tools/tiktok-writer/kols/personas` | 达人人设列表（从 kols 表读取） |

### 13.2 POST `/api/tools/tiktok-writer/chat`

Request:
```json
{
  "messages": [{"role": "user", "content": "string"}],
  "systemPrompt": "string（必填）",
  "model": "claude-opus-4-6-thinking",
  "createJob": false,
  "jobContext": { "tiktokUrl": "", "likesCount": "", "selectedPersonaName": "" }
}
```

Response：`text/plain` 流式文本（raw text stream，非 SSE）

业务规则：
- `systemPrompt` 为空时返回 400
- 内置 429 限流重试（间隔 2/4/6 秒，最多 3 次）
- `createJob=true` 时后台写 `task_jobs` 记录
- 后台写 OperationLog（action=`tiktok_writer_chat`）
- AI 调用明细由 yunwu adapter 写 `ai_call_logs`

### 13.3 POST `/api/tools/tiktok-writer/export-word`

Request:
```json
{
  "personaName": "string",
  "topic": "string",
  "content": "string（必填，Markdown 正文）",
  "taskJobId": null
}
```

Response：文件流
- `Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- `Content-Disposition: attachment; filename="TikTok_Script_{personaName}_{date}.docx"`

业务规则：
- 写入 `outputs` 表（tool_code=`tiktok-writer`）
- 写 OperationLog（action=`tiktok_export_word`，target_type=`output`）

### 13.4 GET `/api/tools/tiktok-writer/kols/personas`

Response:
```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "personas": [
      { "name": "string", "soul": "string", "contentPlan": "string" }
    ]
  }
}
```

业务规则：
- 从 `kols` 表查询 `persona IS NOT NULL AND deleted_at IS NULL`
- 按 `name` ASC 排序

### 13.5 错误码

| HTTP | code | 含义 |
|------|------|------|
| 400 | `INVALID_INPUT` | messages 为空 / systemPrompt 为空 / content 为空 |

---

## 14. Sprint 6 — 千川脚本复盘接口（qianchuan-review）

> 路由文件：`backend/app/routers/operator_qianchuan_review.py`
> 权限：operator / admin，需 JWT + `password_changed_at IS NOT NULL`

### POST `/api/tools/qianchuan-review/parse-file` — 解析脚本文件

Request：multipart，`file` 字段（.txt/.md/.docx/.pages，不支持 .pdf）

Response（200）：
```json
{ "success": true, "code": "OK", "data": { "text": "string", "filename": "string" } }
```

错误：不支持格式 → 400 UNSUPPORTED_FORMAT

---

### POST `/api/tools/qianchuan-review/generate` — 流式生成复盘报告

Request（JSON）：
```json
{
  "scripts": [{ "title": "string", "content": "string" }],
  "excel_data": [{ "video_theme": "string", "spend": 1234.5, "roi": 2.1, ... }],
  "has_excel": false
}
```

Response：`text/event-stream`（SSE），Response Header 含 `X-Task-Id: {number}`

业务规则：
- `scripts` 为空 → 400 INVALID_INPUT
- `scripts.length > 30` → 400 SCRIPTS_LIMIT_EXCEEDED（"不能超过30条"）
- 流开始前创建 task_jobs(status=processing)；流结束后更新 status=success

---

### POST `/api/tools/qianchuan-review/save` — 保存报告

Request（JSON）：
```json
{ "task_id": 1, "report": "string" }
```

Response（200）：
```json
{ "success": true, "code": "OK", "data": { "output_id": 1 } }
```

错误：report 为空 → 400 INVALID_INPUT

---

### GET `/api/tools/qianchuan-review/outputs` — 历史列表

Query：`page`（默认1）、`size`（默认20）

Response（200）：
```json
{
  "success": true, "code": "OK",
  "data": {
    "items": [{ "id": 1, "title": "string", "created_at": "ISO8601", "word_count": 100 }],
    "total": 10, "page": 1, "size": 20
  }
}
```

业务规则：operator 只看自己（created_by 过滤），admin 看全部

---

## 15. Sprint 7 — 千川剪辑预审接口（qianchuan-edit-review）

> 路由文件：`backend/app/routers/tool_extract_frames.py` / `tool_transcribe.py` / `tool_chat_stream.py` / `tool_export_word.py` / `tool_qianchuan_edit_review.py`
> 权限：operator / admin，需 JWT + `password_changed_at IS NOT NULL`

### POST `/api/tools/extract-frames` — 截帧

Request：multipart，`file` 字段（视频文件），`count` 字段（默认8，截帧数量）

Response（200）：
```json
{
  "success": true, "code": "OK",
  "data": {
    "frames": [{ "time": 0.0, "base64": "data:image/jpeg;base64,..." }],
    "duration": 32.5
  }
}
```

错误：无文件字段 → 422；ffprobe 读取失败 → 400 EXTRACT_FAILED；超时（60s）→ 400

---

### POST `/api/tools/transcribe` — 转录

Request：multipart，`file` 字段（视频/音频文件），`language` 字段（默认 zh）

Response（200）：
```json
{ "success": true, "code": "OK", "data": { "text": "string" } }
```

错误：文件 > 25MB → 400 FILE_TOO_LARGE；上游 API 失败 → 502 UPSTREAM_ERROR

业务规则：429 时重试，`_RETRY_DELAYS=[3,6]`，共 3 次

---

### POST `/api/tools/chat-stream` — 多模态 SSE 流式对话

Request（JSON）：
```json
{
  "messages": [{ "role": "user", "content": [{ "type": "text", "text": "..." }, { "type": "image_url", "image_url": { "url": "data:image/..." } }] }],
  "system_prompt": "string",
  "model": "gpt-4o",
  "max_tokens": 8000
}
```

Response：`text/plain; charset=utf-8`（raw text stream，非 SSE event 格式）

错误：messages 为空 → 400 INVALID_INPUT；system_prompt 为空 → 400 INVALID_INPUT

---

### POST `/api/tools/export-word` — 导出 Word

Request（JSON）：
```json
{ "content": "# 标题\n\n内容...", "title": "千川剪辑预审报告" }
```

Response：`application/vnd.openxmlformats-officedocument.wordprocessingml.document`（文件流，非标准信封）
- Header：`Content-Disposition: attachment; filename*=UTF-8''%E5%8D%83...docx`（RFC5987 编码）
- 文件名格式：`千川预审报告_{YYYYMMDD}.docx`

错误：content 为空 → 400 INVALID_INPUT

---

### POST `/api/tools/qianchuan-edit-review/outputs` — 保存报告

Request（JSON）：
```json
{
  "title": "千川剪辑预审_2026-06-14",
  "report": "string",
  "original_duration": 32.5,
  "ours_duration": 28.0,
  "original_frame_count": 8,
  "ours_frame_count": 8
}
```

Response（200）：
```json
{ "success": true, "code": "OK", "data": { "id": 1, "created_at": "ISO8601" } }
```

错误：report 为空 → 400 INVALID_INPUT

---

## 16. Sprint 8 — 直播脚本仿写接口（livestream-writer）

### 16.1 接口列表

| 方法 | 路径 | 角色 | 功能 |
|------|------|------|------|
| GET | `/api/tools/livestream-writer/config` | operator/admin | 获取激活的 Prompt + 模型（实时拉取，管理端可配置）|
| GET | `/api/tools/livestream-writer/kols/personas` | operator/admin | 达人列表（content_plan 和 persona 均非空）|
| POST | `/api/tools/livestream-writer/parse-file` | operator/admin | 文件解析（.txt/.md/.docx/.pages，不支持 .pdf）|
| POST | `/api/tools/livestream-writer/chat` | operator/admin | AI 流式对话（raw text stream）|
| GET | `/api/admin/livestream-writer/configs` | admin | 配置列表 |
| PUT | `/api/admin/livestream-writer/configs/{key}` | admin | 更新配置（Prompt / 模型 / 激活状态）|

### 16.2 GET `/api/tools/livestream-writer/config`

Response（200）：
```json
{
  "success": true, "code": "OK",
  "data": {
    "generate_prompt": "string（首次生成 Prompt 模板，含 {变量}）",
    "iterate_prompt": "string（多轮迭代 Prompt 模板，含 {变量}）",
    "model_id": "string（如 claude-opus-4-6-thinking）"
  }
}
```

配置未激活时返回 503 CONFIG_NOT_FOUND。

### 16.3 GET `/api/tools/livestream-writer/kols/personas`

SQL：`WHERE content_plan IS NOT NULL AND persona IS NOT NULL AND deleted_at IS NULL ORDER BY name`

Response（200）：
```json
{
  "success": true, "code": "OK",
  "data": {
    "personas": [
      { "name": "达人名称", "soul": "persona字段内容", "contentPlan": "content_plan字段内容" }
    ]
  }
}
```

### 16.4 POST `/api/tools/livestream-writer/parse-file`

Request：`multipart/form-data`，字段名 `file`

支持格式：`.txt / .md / .docx / .pages`，**不支持 .pdf**（返回提示字符串而非报错）

Response（200）：
```json
{ "success": true, "code": "OK", "data": { "text": "string", "filename": "string" } }
```

错误：不支持格式 → 400 UNSUPPORTED_FILE_TYPE

### 16.5 POST `/api/tools/livestream-writer/chat`

Request（JSON）：
```json
{
  "messages": [{ "role": "user|assistant", "content": "string" }],
  "systemPrompt": "string（前端动态构建，已注入变量）",
  "model": "string（可选，默认 claude-opus-4-6-thinking）",
  "createJob": true,
  "jobContext": {
    "productName": "string",
    "personaName": "string",
    "spOrder": "string（如：背书→机制→种草）",
    "refLength": 1234
  }
}
```

Response：`text/plain; charset=utf-8`（raw text stream，非 SSE）

重试策略：429 时最多 5 次，退避 5/10/15/20/25s。

BackgroundTask（createJob=true 时）：生成结束后写 `task_jobs` + `outputs`。

错误：messages 为空 → 400 INVALID_INPUT；systemPrompt 为空 → 400 INVALID_INPUT

---

## 17. 人设脚本复盘（persona-review）— Sprint 10

### 17.1 POST `/api/tools/persona-review/generate`

流式生成复盘报告（SSE）。

Request（JSON）：
```json
{
  "scripts": [{ "title": "string", "content": "string" }],
  "excel_data": [
    {
      "video_theme": "string",
      "date": "string（可选）",
      "video_type": "string（可选）",
      "total_plays": "string（可选）",
      "completion_rate": "string（可选）",
      "five_sec_rate": "string（可选）",
      "likes": "string（可选）",
      "comments": "string（可选）",
      "ad_spend": "string（可选）"
    }
  ]
}
```

Response：`text/event-stream`（SSE）

Response Headers：`X-Task-Id: <task_job_id>`

前置校验：`scripts` 不能为空 → 400 SCRIPTS_REQUIRED

hasExcel 判断：merged 结果中任意一条含 `completion_rate` / `ad_spend` / `likes` 即为 true。

合并规则：
- 按 `video_theme` 模糊匹配（双向6字前缀）
- 匹配时 title 使用 Excel 的 `video_theme`；有脚本内容的行按点赞数降序排列
- 未匹配的 Excel 行（有 video_theme）**追加到末尾**，`content=""`，不参与排序
- 内容截断：2000 字

Prompt 来源：从 `persona_review_configs` 表读取（`with_excel` / `without_excel`），fallback 到 `prompts.py` 常量。

### 17.2 POST `/api/tools/persona-review/save`

保存报告到 outputs 表。

Request（JSON）：
```json
{
  "task_id": 1,
  "report": "string",
  "script_count": 3,
  "has_excel": true
}
```

Response（200）：
```json
{ "success": true, "code": "OK", "data": { "output_id": 1 } }
```

错误：report 为空 → 400 REPORT_EMPTY

### 17.3 GET `/api/tools/persona-review/outputs`

历史列表（当前用户，分页）。

Query：`page=1&page_size=10`

Response（200）：
```json
{
  "success": true, "code": "OK",
  "data": {
    "items": [{ "id": 1, "title": "string", "content": "string", "created_at": "string" }],
    "total": 5, "page": 1, "page_size": 10
  }
}
```

### 17.4 GET `/api/admin/persona-review/configs`

管理端读取 Prompt 配置（仅 admin）。

Response（200）：
```json
{
  "success": true, "code": "OK",
  "data": [
    { "id": 1, "config_key": "with_excel", "system_prompt": "string", "ai_model_id": null, "is_active": true }
  ]
}
```

### 17.5 PUT `/api/admin/persona-review/configs/{config_key}`

管理端更新 Prompt 配置（仅 admin）。

Request（JSON）：`{ "system_prompt": "string", "ai_model_id": 1 }`

Response（200）：`{ "success": true, "code": "OK", "data": { "config_key": "with_excel" } }`

错误：config_key 不存在 → 404 CONFIG_NOT_FOUND

---

## 19. Sprint 12 — 千川爆文合集（qianchuan-collection）

**前缀**：`/api/tools/qianchuan-collection`  
**鉴权**：所有接口要求 `role in ('operator','admin')` 且 `password_changed_at IS NOT NULL`  
**特点**：纯手工收集库，无 AI 调用，无 SSE，无文件下载流

### 19.1 GET /personas

获取达人列表（排除软删除，含每位达人的脚本数量）。

Response（200）：
```json
{ "success": true, "code": "OK", "data": { "personas": [{ "name": "达人A", "script_count": 5 }] } }
```

### 19.2 POST /personas

新建达人分组。

Request（JSON）：`{ "name": "达人A" }`

Response（200）：`{ "success": true, "code": "OK", "data": { "name": "达人A" } }`

错误：名称重复 → 409 PERSONA_EXISTS；名称为空 → 422

### 19.3 DELETE /personas/{persona_name}

软删除达人（同时级联软删该达人下所有脚本）。

Response（200）：`{ "success": true, "code": "OK", "data": { "ok": true } }`

错误：达人不存在 → 404 PERSONA_NOT_FOUND

### 19.4 GET /scripts

获取脚本列表，支持分页和筛选。

Query 参数：

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `pool` | string | 必填 | `global` 或 `persona` |
| `persona_name` | string | — | pool=persona 时必填 |
| `q` | string | — | 关键词搜索（title + content ILIKE） |
| `page` | int | 1 | 页码 |
| `page_size` | int | 20 | 每页条数（最大 100） |

Response（200）：
```json
{
  "success": true, "code": "OK",
  "data": {
    "scripts": [{ "id": 1, "pool": "global", "persona_name": null, "title": "...", "content": "...",
                  "likes": 50000, "source": "抖音", "source_account": null,
                  "script_date": "2026-05-19", "created_at": "2026-06-18T10:00:00Z" }],
    "total": 41, "page": 1, "page_size": 20
  }
}
```

错误：pool 无效 → 400；pool=persona 但未传 persona_name → 400

### 19.5 POST /scripts

新增脚本。

Request（JSON）：
```json
{ "pool": "global", "persona_name": null, "title": "脚本标题", "content": "正文...",
  "likes": 50000, "source": "抖音", "source_account": "某账号", "script_date": "2026-06-18" }
```

Response（200）：`{ "success": true, "code": "OK", "data": { "id": 123 } }`

错误：title/content 为空 → 422；pool=persona 时 persona_name 为空 → 400；达人不存在 → 400 PERSONA_NOT_FOUND；script_date 格式错误 → 400

### 19.6 DELETE /scripts/{script_id}

软删除脚本。

Response（200）：`{ "success": true, "code": "OK", "data": { "ok": true } }`

错误：脚本不存在或已删除 → 404 SCRIPT_NOT_FOUND

### 19.7 POST /parse-file

上传文件解析返回文本（multipart/form-data，字段名 `file`）。

支持格式：`.txt` / `.md` / `.docx` / `.pdf`

Response（200）：`{ "success": true, "code": "OK", "data": { "text": "...", "filename": "原文件名" } }`

错误：不支持的格式 → 400 UNSUPPORTED_FORMAT

---

## 20. tiktok-review（Sprint 13）

基础路径：`/api/tools/tiktok-review`（operator/admin 鉴权）
管理端路径：`/api/admin/tiktok-review`（admin 鉴权）

### 20.1 POST /generate

SSE 流式生成复盘报告。

Request（JSON）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `original_transcript` | string | 原版爆款文案（与 copycat_transcript 至少一个非空） |
| `original_likes` | string | 原版点赞数（可选，如"1万"） |
| `copycat_transcript` | string | 仿写版文案 |
| `copycat_likes` | string | 仿写版点赞数 |

Response：`text/plain; charset=utf-8`（裸文本流）

Response Header：`X-Task-Id: <task_id>`（供保存时使用）

错误：两侧文案均为空 → 400 INVALID_INPUT；配置未激活 → 503 CONFIG_NOT_FOUND

### 20.2 POST /save

保存报告到 outputs 表。

Request（JSON）：`{ "content": "报告正文", "title": "TT复盘报告_2026-06-18", "task_id": 123 }`

Response（200）：`{ "success": true, "code": "OK", "data": { "output_id": 456 } }`

错误：content 为空 → 400 INVALID_INPUT

### 20.3 GET /outputs

历史报告列表。

Query 参数：`page`（默认1）、`size`（默认10，最大100）

Response（200）：
```json
{
  "success": true, "code": "OK",
  "data": {
    "items": [{ "id": 1, "title": "TT复盘报告_2026-06-18", "created_at": "...", "preview": "...", "word_count": 800 }],
    "total": 5
  }
}
```

operator 只看自己的；admin 看全部。

### 20.4 POST /export-word

导出 Word。

Request（JSON）：`{ "content": "报告正文", "title": "TT复盘报告" }`

Response：`application/vnd.openxmlformats-officedocument.wordprocessingml.document`（docx 二进制）

错误：content 为空 → 400 INVALID_INPUT

### 20.5 GET /admin/configs

获取配置列表（admin）。

Response（200）：`{ "success": true, "data": [{ "id": 1, "config_key": "default", "ai_model_id": null, "system_prompt": "...", "is_active": true, "updated_at": "..." }] }`

### 20.6 PUT /admin/configs/{config_key}

更新配置（admin）。

Request（JSON）：`{ "ai_model_id": 2, "system_prompt": "新 Prompt", "is_active": true }`

Response（200）：`{ "success": true, "data": { "config_key": "default" } }`

错误：config_key 不存在 → 404 RESOURCE_NOT_FOUND

## 21. qianchuan-writer（Sprint 14）

基础路径：`/api/tools/qianchuan-writer`（operator / admin 鉴权，需已改密）
管理端路径：`/api/admin/qianchuan-writer`（admin 鉴权）

千川脚本仿写工具：选达人人设 + 加载产品卖点 + 粘贴原版脚本，AI 保留原结构 100% 产出仿写版本。

### 21.1 GET /kols/personas

Step 1 达人下拉列表。返回 `persona + content_plan` 均非空且未删除、状态为 active 的达人。

Response（200）：
```json
{
  "success": true, "code": "OK",
  "data": [
    { "id": 1, "name": "孙知羽", "soul_preview": "（前 400 字）", "creator_name": "系统预设" },
    { "id": 5, "name": "用户自建达人", "soul_preview": "...", "creator_name": "张三" }
  ]
}
```

说明：`soul_preview` 为 persona 前 400 字；`creator_name` 为创建者用户名，系统预设时为 `"系统预设"`。

### 21.2 POST /parse-file

Step 2 产品卖点卡文件解析（FormData）。

Request（multipart/form-data）：`file: UploadFile`（.txt / .md / .docx / .pdf / .xlsx / .pptx）

Response（200）：
```json
{ "success": true, "data": { "text": "解析后的纯文本", "word_count": 1234 } }
```

错误：不支持格式 → 400 UNSUPPORTED_FILE_TYPE；解析失败 → 500 FILE_PARSE_ERROR。写 OperationLog（action=`qianchuan_parse_file`）。

### 21.3 POST /chat

Step 4 AI 流式仿写（raw text stream）。

Request（JSON）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `messages` | array<{role, content}> | 用户对话消息（含原版脚本 + 产品卖点 + 多轮追问）|
| `persona_id` | int | 达人 ID（必填，从 /kols/personas 选）|
| `create_job` | bool | 是否创建 task_job 记录（默认 false）|
| `job_context` | object \| null | 任务上下文（product_name / original_script_length 等）|

Response：`text/plain; charset=utf-8`（裸文本流，流式 chunk）

错误：messages 为空 → 400 INVALID_INPUT；配置未激活 → 503 CONFIG_NOT_FOUND；persona 不存在 → 404 RESOURCE_NOT_FOUND。

流程：读 DB 配置（`default`，is_active=true）→ 读 kols（persona/content_plan）→ `render_system_prompt` 占位符替换 → `yunwu_adapter.chat_stream` → StreamingResponse；`create_job=true` 时 BackgroundTask 写 TaskJob + OperationLog（action=`qianchuan_writer_chat`）。Adapter finally 自动写 AiCallLog。

### 21.4 POST /save-output

保存仿写产出至 outputs 表（账号绑定）。

Request（JSON）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `content` | string | 产出正文（必填，不能为空）|
| `title` | string | 标题（可选，留空自动生成 "千川文案写作 · YYYY-MM-DD"）|
| `task_id` | int \| null | 关联任务 ID（可选）|
| `product_name` | string \| null | 产品名（可选，仅入 OperationLog）|

Response（200）：`{ "success": true, "data": { "output_id": 789 } }`

错误：content 为空 → 400 INVALID_INPUT。写 OperationLog（action=`qianchuan_writer_save_output`）。

### 21.5 POST /export-word

导出 Word 文档（.docx 二进制流，不走标准信封）。

Request（JSON）：`{ "content": "...", "filename": "千川仿写" }`

Response：`application/vnd.openxmlformats-officedocument.wordprocessingml.document`

Header：`Content-Disposition: attachment; filename*=UTF-8''<URL-encoded>_<YYYY-MM-DD>.docx`

错误：content 为空 → 400 INVALID_INPUT。

### 21.6 GET /outputs

历史记录（按账号隔离，只返回当前用户的 outputs）。

Query 参数：`page`（默认 1，ge 1）、`page_size`（默认 20，仅允许 10 / 20 / 50，其他值 fallback 到 20）

Response（200）：
```json
{
  "success": true, "code": "OK",
  "data": {
    "items": [
      { "id": 1, "title": "千川仿写_孙知羽_产品A", "content": "...", "word_count": 800, "task_id": 123, "created_at": "2026-06-22T10:00:00+08:00" }
    ],
    "pagination": { "page": 1, "page_size": 20, "total": 5, "total_pages": 1 }
  }
}
```

SQL 过滤：`WHERE tool_code='qianchuan-writer' AND created_by=current_user.id AND deleted_at IS NULL`。

### 21.7 GET /admin/configs

获取配置列表（admin）。

Response（200）：
```json
{
  "success": true,
  "data": [
    { "id": 1, "config_key": "default", "ai_model_id": null, "system_prompt": "...", "is_active": true, "updated_at": "2026-06-22T..." }
  ]
}
```

通常仅返回 1 条 `config_key='default'`。

### 21.8 PUT /admin/configs/{config_key}

更新配置（admin）。

Request（JSON）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `ai_model_id` | int \| null | 关联 ai_models.id（留空走默认 `claude-opus-4-6-thinking`）|
| `system_prompt` | string \| null | Prompt 模板（含 `{{name}}`/`{{soul}}`/`{{content_plan}}` 占位符）|
| `is_active` | bool | 配置启用开关（默认 true）|

Response（200）：`{ "success": true, "data": { "config_key": "default" } }`

错误：config_key 不存在 → 404 RESOURCE_NOT_FOUND。写 OperationLog（action=`admin_update_qianchuan_writer_config`）。
