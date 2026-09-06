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

### 1.9 外部只读 KOL API

| 分类 | 接口数 | 路由前缀 |
|------|--------|----------|
| 外部系统只读接口 | 2 | `/api/external/kols` |
| 外部录屏主播同步接口 | 1 | `/api/external/recording-anchors` |

---

## 2. 通用约定

与 M1 完全一致，参见 `MCN_M1_Base_API.md` §2。关键点：

- **响应格式**：`{ success, code, message, data }`
- **鉴权**：Bearer Token（JWT），公开接口除外；外部只读 KOL API / 外部录屏主播同步接口例外，使用 `X-API-Key`
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
| POST | `/api/operator/intake/direct/start` | 新建运营直发会话，可选绑定正式达人 |

---

### POST `/api/operator/intake/links` — 生成分享链接

Request：`kol_id` 可选；一旦传入，后端必须校验它指向未删除的正式 `kols` 记录。`kol_name` 只作展示，不参与任何自动匹配。
```json
{ "kol_id": 43, "kol_name": "张三", "expire_hours": 24 }
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
    "kol_id": 43,
    "kol_name": "张三",
    "expires_at": "2026-06-09T10:00:00+08:00",
    "share_url": "/intake/abc123"
  }
}
```

业务规则：
- `kol_id` 不传时保留为 `null`，历史和新建未绑定记录均不得按姓名自动关联。
- `kol_id` 传入时只按正式编号绑定，不使用 `kol_name` 猜测；操作日志仅记录对象编号，不记录档案正文。
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

### POST `/api/operator/intake/direct/start` — 新建运营直发会话

Request：`{ "kol_id": 43, "kol_name": "张三" }`。`kol_id` 可选；传入时必须指向未删除的正式达人，并原样写入 `kol_intake_operator_sessions.kol_id`。不传时保存 `null`，不得按姓名自动匹配。

Response.data：`{ "session_id": 21, "kol_id": 43, "kol_name": "张三" }`。后续对话、提交和报告生成沿用这条会话已保存的 `kol_id`，不得用会话编号冒充达人编号。

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

## 6A. 红人管理接口（admin/kols）

> 路由文件：`backend/app/routers/admin_kols.py`
>
> 路由前缀：`/api/admin/kols`
>
> 权限（2026-07-12 PR #25 起调整）：
> - **读路径**（GET 列表 / GET 详情）：`require_admin_or_operator` — admin + operator 可读
> - **写路径**（POST / PATCH / DELETE / fetch-tikhub）：`require_admin` — 仅 admin

### 6A.1 接口总览

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/api/admin/kols` | 红人列表（分页 + 关键词 + 状态筛选） | admin / operator |
| POST | `/api/admin/kols` | 新建红人 | admin |
| GET | `/api/admin/kols/{kol_id}` | 红人详情（含 tikhub_raw） | admin / operator |
| PATCH | `/api/admin/kols/{kol_id}` | 更新红人字段 | admin |
| DELETE | `/api/admin/kols/{kol_id}` | 软删红人（写 deleted_at） | admin |
| POST | `/api/admin/kols/{kol_id}/fetch-tikhub` | 手动触发 TikHub 拉取 | admin |

### 6A.2 GET `/api/admin/kols` — 红人列表

**Query 参数**：

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `page` | int | 1 | 页码（从 1 开始） |
| `page_size` | int | 20 | 每页条数（只接受 10/20/50；其他值回退到 20） |
| `keyword` | str | "" | 关键词，模糊匹配 name / account_name / douyin_id |
| `status` | str | "" | 计算状态筛选（4 种合法值，见 §6A.8；非法值静默忽略 = 不过滤） |

**Response**（标准信封）：
```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "items": [
      {
        "id": 1,
        "name": "测试红人",
        "account_name": "kol_a",
        "category": "美妆",
        "platform": "douyin",
        "douyin_id": "xxx",
        "sec_uid": "yyy",
        "avatar_url": "https://...",
        "followers_count": 12345,
        "works_count": 30,
        "persona": "...",
        "content_plan": "...",
        "style_note": "...",
        "owner": "张三",
        "owner_id": 2,
        "status": "onboarded",
        "tikhub_fetched": true,
        "created_by": 1,
        "created_at": "2026-07-12T08:00:00",
        "updated_at": "2026-07-12T08:00:00"
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 1,
      "total_pages": 1
    }
  }
}
```

> 列表接口不返回 `tikhub_raw`（仅在详情接口返回）。
> `status` 为计算字段（非 DB 列），见 §6A.8。

### 6A.3 POST `/api/admin/kols` — 新建红人

**Request Body**：`CreateKolRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `name` | str | 是 | — | 红人姓名 |
| `account_name` | str | 否 | null | 抖音账号名 |
| `category` | str | 否 | null | 分类 |
| `platform` | str | 否 | "douyin" | 平台 |
| `douyin_id` | str | 否 | null | 抖音号（在 `deleted_at IS NULL` 范围内唯一） |
| `sec_uid` | str | 否 | null | sec_uid（在 `deleted_at IS NULL` 范围内唯一） |
| `avatar_url` | str | 否 | null | 头像 URL |
| `follower_count` | int | 否 | null | 粉丝数 |
| `video_count` | int | 否 | null | 作品数 |
| `style_note` | str | 否 | null | 风格备注（**前端字段名**，映射到 DB `style_notes`） |
| `owner` | str | 否 | null | 负责人姓名 |
| `owner_id` | int | 否 | null | 负责人 user_id |

**Response**：`success_response(data=_kol_to_dict(kol), message="红人创建成功")`

**错误码**：
- `RESOURCE_ALREADY_EXISTS` — douyin_id 或 sec_uid 已存在（未软删）

**写 OperationLog**：action=`create_kol`，target_type=`kol`。

### 6A.4 GET `/api/admin/kols/{kol_id}` — 红人详情

返回单个红人完整字段，**含 `tikhub_raw` 原始数据**（列表接口不返回此字段）。

**错误码**：
- `RESOURCE_NOT_FOUND` — 红人不存在或已软删

### 6A.5 PATCH `/api/admin/kols/{kol_id}` — 更新红人

**Request Body**：`UpdateKolRequest`（所有字段均可选，与 CreateKolRequest 字段集相同）。Sprint 25 起不再接受 `persona` / `content_plan` 写入；红人管理只读展示这两项并跳转红人工作台维护。

> ⚠️ **2026-07-12 起**：`UpdateKolRequest` **删除了 `status` 字段**。`status` 改为根据 persona + content_plan 动态计算（见 §6A.8）。客户端若仍传 `status` 字段，会被 Pydantic 静默忽略（不报错但不生效）。

**写 OperationLog**：action=`update_kol`，target_type=`kol`，target_id=kol_id，detail=变更字段（除 `updated_at` 外）的 KV 字典；无变更时 detail=null。

**错误码**：
- `RESOURCE_NOT_FOUND` — 红人不存在或已软删

### 6A.6 DELETE `/api/admin/kols/{kol_id}` — 软删

设置 `deleted_at = now()`，**不物理删除**。GET 列表 / 详情均排除已软删记录。`douyin_id` / `sec_uid` 的唯一约束基于 `deleted_at IS NULL` 的部分唯一索引，软删后可重建同号红人。

**写 OperationLog**：action=`delete_kol`。

**错误码**：
- `RESOURCE_NOT_FOUND` — 红人不存在或已软删

### 6A.7 POST `/api/admin/kols/{kol_id}/fetch-tikhub` — TikHub 拉取

手动触发 TikHub 数据抓取：优先用 sec_uid，为空时用 douyin_id。无论成功失败都写 `external_service_logs`（详见 TikHub 章节日志约定）。返回拉取结果 + 更新后的 kol 字段。

**Response**：
```json
{
  "success": true,
  "data": {
    "tikhub": { "sec_uid": "...", "follower_count": 12345, ... },
    "kol": { "id": 1, ... }
  }
}
```

**错误码**：
- `RESOURCE_NOT_FOUND` — 红人不存在或已软删

### 6A.8 字段说明：`status` 计算字段（2026-07-12 重构）

**重要变更**：`status` 从手动管理的 DB 字段改为**计算字段**，基于 `persona` 和 `content_plan` 是否非空动态计算。原 DB 列 `kols.status` **已 deprecated**（仍保留，但代码不再读写；未来通过 migration 删除该列）。

4 种计算状态：

| status 值 | 触发条件 | 含义 |
|-----------|----------|------|
| `pending_onboarding` | persona 空 + content_plan 空 | 待入驻 |
| `persona_done` | persona 有 + content_plan 空 | 人格档案已填 |
| `content_done` | persona 空 + content_plan 有 | 内容规划已填 |
| `onboarded` | persona 有 + content_plan 有 | 入驻完成 |

**"空"判定逻辑**：`bool(value and value.strip())`（None、空字符串、纯空白字符串 — 含空格/Tab/换行 — 均视为空）。

**GET 列表的 `status` 查询参数**：传入上述 4 种合法值之一时，按相同的 persona / content_plan 组合条件过滤；传入其他值时静默忽略（不应用任何过滤）。

**代码位置**：`app/routers/admin_kols.py::_compute_status(persona, content_plan)`。

---

## 6B. 外部只读 KOL API

> 路由文件：`backend/app/routers/external_kols.py`
>
> 路由前缀：`/api/external/kols`
>
> 用途：给其它项目只读访问 `kols` 表中的红人资料。接口不开放数据库连接、不支持写入、不使用 JWT。
>
> 鉴权：请求头 `X-API-Key: <密钥>`；密钥从后端环境变量 `EXTERNAL_KOLS_API_KEY` 读取。
>
> 数据来源：复用 M1 `kols` 表，不新增业务表。字段定义见 `MCN_M1_Base_Database.md` §6；人物档案 5 分区字段见 M2 红人工作台数据库补充。

### 6B.1 接口总览

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| GET | `/api/external/kols` | 红人列表（分页 + 关键词 + 平台 + 计算状态筛选） | `X-API-Key` |
| GET | `/api/external/kols/{kol_id}` | 单个红人详情 | `X-API-Key` |

### 6B.2 GET `/api/external/kols` — 外部红人列表

**Query 参数**：

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `page` | int | 1 | 页码，从 1 开始 |
| `page_size` | int | 20 | 每页条数，范围 1~100 |
| `keyword` | str | "" | 模糊匹配 `name` / `account_name` / `douyin_id` / `sec_uid` |
| `platform` | str | "" | 平台精确筛选，例如 `douyin` |
| `status` | str | "" | 计算状态筛选：`pending_onboarding` / `persona_done` / `content_done` / `onboarded`；非法值静默忽略 |
| `include_raw` | bool | false | 是否返回 `tikhub_raw` 原始 JSON |

**Response**（标准信封）：
```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "items": [
      {
        "id": 1,
        "name": "测试红人",
        "account_name": "kol_a",
        "category": "美妆",
        "platform": "douyin",
        "external_id": "ext_001",
        "douyin_id": "douyin_001",
        "sec_uid": "MS4wLjABAAAA...",
        "avatar_url": "https://...",
        "signature": "个人简介",
        "follower_count": 12345,
        "video_count": 67,
        "owner": "运营A",
        "owner_id": 2,
        "persona": "人格档案",
        "content_plan": "内容规划",
        "style_notes": "风格说明",
        "status": "signed",
        "computed_status": "onboarded",
        "created_by": 1,
        "background": "基本身份",
        "experience": "真实经历",
        "relationships": "关系网",
        "unique_story": "独特故事",
        "extra_notes": "补充说明",
        "created_at": "2026-08-05T10:00:00+08:00",
        "updated_at": "2026-08-05T10:00:00+08:00",
        "deleted_at": null
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 1,
      "total_pages": 1
    }
  }
}
```

说明：
- 默认排除 `deleted_at IS NOT NULL` 的软删红人。
- `computed_status` 计算规则与 §6A.8 一致。
- `status` 为数据库保留字段，业务应优先使用 `computed_status`。
- `include_raw=false` 时不返回 `tikhub_raw`，避免默认响应过大。

### 6B.3 GET `/api/external/kols/{kol_id}` — 外部红人详情

**Query 参数**：

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `include_raw` | bool | true | 是否返回 `tikhub_raw` 原始 JSON |

**Response**：单个红人字段，字段集同 §6B.2；默认包含 `tikhub_raw`。

**错误码**：
- `401 EXTERNAL_API_KEY_INVALID` — 缺少或传错 `X-API-Key`
- `503 EXTERNAL_API_KEY_NOT_CONFIGURED` — 后端未配置 `EXTERNAL_KOLS_API_KEY`
- `404 RESOURCE_NOT_FOUND` — 红人不存在或已软删

### 6B.4 部署约定

- 本地测试：`http://localhost:8000/api/external/kols`
- 阿里云部署：由运维通过 Nginx / HTTPS 暴露公网域名，例如 `https://api.example.com/api/external/kols`
- 密钥只放在服务器环境变量或 `.env`，不得提交真实密钥到 GitHub
- 生产环境不建议直接裸露 `8000` 端口，推荐只开放 `80/443`

---

## 6C. 外部录屏主播同步 API

> 路由文件：`backend/app/routers/external_recording_anchors.py`
>
> 路由前缀：`/api/external/recording-anchors`
>
> 用途：给远程自动录屏 / 直播分析项目读取“需要进入录屏系统的主播清单”。接口合并读取 `kols` 与 `kol_benchmarks`，返回统一结构并通过 `source_type` 区分来源。
>
> 鉴权：请求头 `X-API-Key: <密钥>`；复用环境变量 `EXTERNAL_KOLS_API_KEY`。
>
> 数据来源：`kols` 全部未软删红人作为 `source_type=kol`；`kol_benchmarks` 仅返回 `account_type=livestream` 的直播对标账号作为 `source_type=live_benchmark`。`account_type=content` 的内容对标账号不返回、不进入远程录屏系统。

### 6C.1 接口总览

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| GET | `/api/external/recording-anchors` | 录屏主播统一列表（红人主播 + 直播对标主播） | `X-API-Key` |

### 6C.2 GET `/api/external/recording-anchors`

**Query 参数**：

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `page` | int | 1 | 页码，从 1 开始 |
| `page_size` | int | 50 | 每页条数，范围 1~200 |
| `keyword` | str | "" | 模糊匹配红人名称 / 账号昵称 / 抖音号 / sec_user_id / 对标原始输入 |
| `platform` | str | "" | 平台筛选；直播对标当前固定为 `douyin`，传其他平台时不会返回直播对标 |
| `source_type` | str | "" | 来源筛选：空 = 全部，`kol` = 红人主播，`live_benchmark` = 直播对标主播 |
| `ready_only` | bool | false | true 时只返回已具备抖音账号 ID 或 `sec_user_id` 的记录 |

**Response**（标准信封）：
```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "items": [
      {
        "source_key": "kol:1",
        "source_type": "kol",
        "source_label": "红人主播",
        "source_table": "kols",
        "source_id": 1,
        "parent_kol_id": 1,
        "parent_kol_name": "搭搭",
        "should_record": true,
        "platform": "douyin",
        "account_input": "dadahei",
        "douyin_id": "dadahei",
        "sec_user_id": "MS4wLjABAAAA...",
        "sec_uid": "MS4wLjABAAAA...",
        "nickname": "搭搭",
        "name": "搭搭",
        "avatar_url": "https://...",
        "signature": "个人简介",
        "follower_count": 12345,
        "video_count": 67,
        "description": "备注",
        "sync_ready": true,
        "sync_block_reason": null,
        "created_at": "2026-08-07T10:00:00+08:00",
        "updated_at": "2026-08-07T10:00:00+08:00"
      },
      {
        "source_key": "live_benchmark:9",
        "source_type": "live_benchmark",
        "source_label": "直播对标主播",
        "source_table": "kol_benchmarks",
        "source_id": 9,
        "parent_kol_id": 1,
        "parent_kol_name": "搭搭",
        "should_record": true,
        "platform": "douyin",
        "account_input": "live_douyin_id",
        "douyin_id": "live_douyin_id",
        "sec_user_id": "MS4wLjABAAAA...",
        "sec_uid": "MS4wLjABAAAA...",
        "nickname": "对标主播昵称",
        "name": "对标主播昵称",
        "avatar_url": "https://...",
        "signature": null,
        "follower_count": 8888,
        "video_count": null,
        "description": "直播对标说明",
        "sync_ready": true,
        "sync_block_reason": null,
        "created_at": "2026-08-07T10:00:00+08:00",
        "updated_at": "2026-08-07T10:00:00+08:00"
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 50,
      "total": 2,
      "total_pages": 1
    }
  }
}
```

说明：
- 远程项目可将 `source_type=kol` 写作“红人主播”，将 `source_type=live_benchmark` 写作“直播对标主播”。
- `sec_user_id` 与 `sec_uid` 返回同一值；前者对齐远程添加主播表单，后者对齐本平台既有字段名。
- `sync_ready=false` 表示该记录缺少抖音账号 ID 与 `sec_user_id`，远程应暂不入库或放入待补全队列。

**错误码**：
- `400 VALIDATION_ERROR` — `source_type` 非法
- `401 EXTERNAL_API_KEY_INVALID` — 缺少或传错 `X-API-Key`
- `503 EXTERNAL_API_KEY_NOT_CONFIGURED` — 后端未配置 `EXTERNAL_KOLS_API_KEY`

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
| GET  | `/api/persona/kols` | 正式达人列表（分页、搜索，值为 `kols.id`） |
| GET  | `/api/persona/kols/{kol_id}/intake` | 当前运营对该正式达人有权访问的最近完成入驻资料 |
| GET  | `/api/persona/reports` | 报告列表（当前用户最近 50 条） |
| GET  | `/api/persona/reports/{id}` | 报告详情 |
| POST | `/api/persona/reports/{id}/sync-decisions` | 对待覆盖定位字段提交覆盖或保留决定 |
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
  "kol_id": 43,
  "influencer_info": "已导入或上传的达人资料",
  "douyin_nickname": "然然",
  "top10_content": "...",
  "recent30_text": "...",
  "questionnaire_files": [],
  "supplement_text": "补充信息"
}
```

Response：`text/plain` 流式逐 chunk 输出 AI 生成内容，响应头 `X-Report-Id` 返回报告编号。

AI 输出必须且只能用一个 `===SPLIT===` 分隔两部分：人格档案 + 内容规划；分隔符缺失、任一侧为空或出现多段时，报告标记为 `failed`，不生成 Output、不写正式档案。

业务规则：
- `kol_id` 必填，必须是未删除的正式达人；报告创建、输出记录、正式档案同步和操作日志始终使用同一编号。
- `persona` / `content_plan` 为空时自动写入；非空且与新报告不同时进入待覆盖列表，默认保留。
- 五项人物事实从 `profile_result` 提取，只接受能在报告正文中找到原文证据的内容，且只写当前空字段；提取失败不把报告改为生成失败。
- 报告历史始终保留，即使运营拒绝覆盖已有正式档案。

### GET `/api/persona/kols` — 正式达人列表

Query：`page`（默认 1）、`page_size`（10/20/50，默认 20）、`keyword`（匹配 name / account_name / douyin_id）。只返回 `deleted_at IS NULL` 的 `kols`。

Response.data：
```json
{
  "items": [{
    "id": 43,
    "name": "mini兔兔",
    "account_name": "mini兔兔",
    "douyin_id": "mini2026",
    "profile_filled_count": 6,
    "profile_total": 7
  }],
  "pagination": { "page": 1, "page_size": 20, "total": 1, "total_pages": 1 }
}
```

不得读取入驻会话代替达人，不返回会话编号或未绑定历史会话。

### GET `/api/persona/kols/{kol_id}/intake` — 最近关联入驻资料

只在分享链接或运营直发会话明确保存相同 `kol_id`、报告状态为 `ready`、报告非空且 `operator_id=current_user.id` 时返回最近一条。Response.data 为 `null` 或：
```json
{
  "completed_at": "2026-08-03T10:00:00+08:00",
  "formatted_answers": "【达人回答】...",
  "report": "入驻报告正文"
}
```

历史 `kol_id IS NULL` 记录、其他运营记录和姓名相同但编号不同的记录均不得返回。

### GET `/api/persona/reports/{id}` — 报告详情与同步状态

除历史字段外返回 `kol_id`、`sync_result`、`pending_overwrites`、`failure_reason`、`positioning_sync_failed` 和 `fact_sync_failed`。`pending_overwrites` 每项包含字段名、现有摘要和新报告摘要；`failure_reason` 仅在生成失败时返回 `kol_deleted` 或 `generation_failed`，两个同步失败布尔值分别表示定位字段同步和五项事实补全失败。`fact_sync_failed` 以同一报告最新一次事实同步结果为准，成功重试后关闭旧失败；不返回其他运营的报告。

### POST `/api/persona/reports/{id}/sync-decisions` — 字段级覆盖决定

Request：
```json
{ "decisions": { "persona": "keep", "content_plan": "overwrite" } }
```

只接受详情接口当前返回的待覆盖字段，字段分别判断，未显式选择覆盖时按 `keep` 处理。重复提交按最新正式值重算；相同内容不重复写入或重复产生覆盖日志。Response.data 返回字段级 `auto_written` / `overwritten` / `kept` / `unchanged` 结果。

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
- 从 `kols` 表查询 `persona IS NOT NULL AND deleted_at IS NULL AND status IN ('signed', 'pending_renewal')`
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

Response：`text/event-stream`（SSE），Response Header 含 `X-Task-Id: {number}`。事件统一为：

```text
event: content
data: {"text":"报告片段"}

event: complete
data: {"task_id":1}

event: failed
data: {"task_id":1,"code":"GENERATION_FAILED","message":"AI 生成失败，请重新生成"}
```

业务规则：
- `scripts` 为空 → 400 INVALID_INPUT
- `scripts.length > 30` → 400 SCRIPTS_LIMIT_EXCEEDED（"不能超过30条"）
- 携带投放数据但匹配数为 0 → 400 VALIDATION_ERROR；`data` 返回 `matched_count`、`unmatched_scripts`（脚本序号和标题）及 `unmatched_excel_rows`（Excel 行号和素材名），且不创建任务、不调用 AI。
- 通过输入门禁后创建 `task_jobs(status=processing)`；任务记录只保存条数、是否含投放数据和匹配数，不保存完整脚本。
- 只有报告非空、无生成异常并发送 `complete` 事件后，任务才更新为 `success`。
- 空报告、生成异常或客户端中断分别更新为 `failed`，错误码为 `EMPTY_REPORT`、`GENERATION_FAILED` 或 `STREAM_INTERRUPTED`；错误通过 `failed` 事件返回，不把 `[ERROR]` 混入报告正文。

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

错误：
- report 为空 → 400 INVALID_INPUT
- report 含 `[ERROR]` → 400 INVALID_REPORT
- task 不属于当前用户/工具，或任务终态不是 success → 409 TASK_NOT_SUCCESS

保存成功后，`outputs.task_id` 与 `task_jobs.output_id` 双向关联。

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
  "max_tokens": 8000,
  "ai_model_id": null
}
```

字段说明：
- `model`：直接指定 model_id 字符串；当 `ai_model_id` 为空时使用此值，provider 默认 `yunwu`
- `ai_model_id`（可选）：有值则查 `ai_models` 表，用表中的 `model_id` 覆盖 `model` 字段，并用表中的 `provider` 决定走哪个服务商的凭证池（yunwu/siliconflow/glm）；表无此 id 或 status≠active 时回退到默认值。**调用方应优先传 `ai_model_id`**（如 qianchuan-edit-review 工具，admin 配的模型靠此字段生效）

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
| GET | `/api/tools/livestream-writer/kols/personas` | operator/admin | 达人列表（含 `id`，供独立页面提交 `kol_id`）|
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

SQL：`WHERE content_plan IS NOT NULL AND persona IS NOT NULL AND deleted_at IS NULL AND status IN ('signed', 'pending_renewal') ORDER BY name`

Response（200）：
```json
{
  "success": true, "code": "OK",
  "data": {
    "personas": [
      { "id": 123, "name": "达人名称", "soul": "persona字段内容", "contentPlan": "content_plan字段内容" }
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
  "workspace_mode": true,
  "kol_id": 123,
  "reference_script": "已确认的对标直播间文案",
  "reference_confirmed": true,
  "sp_order": "背书→机制→种草",
  "systemPrompt": "string（兼容旧调用；工作台生成以后台统一配置为准）",
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

业务规则：

- 仅工作台内嵌模式（`workspace_mode=true`）必须传入 `kol_id`、已确认的 `reference_script`、`reference_confirmed=true` 和卖点顺序；首次生成、后续修改和自动压缩均适用。
- 独立入口保留原有的人设、卖点卡、对标和前端提示词输入，不强制要求工作台红人或当前商品。
- 服务端按 `kol_id` 重新读取未删除红人的完整档案，以及该红人的唯一当前商品；不采信前端拼接的商品正文。
- 没有当前商品时返回 400 `CURRENT_PRODUCT_REQUIRED`；未确认对标文案时返回 400 `REFERENCE_SCRIPT_REQUIRED`。
- 写入任务上下文时记录红人、当前商品、对标文案字数、卖点顺序、功能、模型和产出标识，不写入完整对标文案。

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

Step 1 达人下拉列表。返回 `persona + content_plan` 均非空且未删除、状态为 `signed` 或 `pending_renewal` 的达人。

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
| `messages` | array<{role, content}> | 用户对话消息（含原版脚本、运营修改意见或逐轮最小修改指令）|
| `persona_id` | int | 达人 ID；兼容独立工具入口。工作台调用时必须与 `kol_id` 相同 |
| `kol_id` | int\|null | 红人工作台路由中的红人 ID；提供时后端以它为准读取完整红人档案 |
| `product_id` | int\|null | 当前共享商品 ID；提供时必须等于该红人的当前商品。留空时后端读取该红人的当前商品；无当前商品返回 400 CURRENT_PRODUCT_REQUIRED |
| `create_job` | bool | 是否创建 task_job 记录（默认 false）|
| `job_context` | object \| null | 任务上下文（original_script_length 等）；产品名称和商品字段由后端从数据库读取，不信任前端文本 |

Response：`text/plain; charset=utf-8`（裸文本流，流式 chunk）

错误：messages 为空 → 400 INVALID_INPUT；配置未激活 → 503 CONFIG_NOT_FOUND；persona 不存在 → 404 RESOURCE_NOT_FOUND。

流程：读 DB 配置（`default`，is_active=true）→ 读取完整红人档案与当前商品 → `render_system_prompt` 占位符替换并追加完整档案、商品全部非空字段及“只有我有”约束 → `yunwu_adapter.chat_stream` → StreamingResponse；`create_job=true` 时 BackgroundTask 写 TaskJob + OperationLog（action=`qianchuan_writer_chat`）。Adapter finally 自动写 AiCallLog。

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

---

## 22. persona-writer（Sprint 15）

基础路径：`/api/tools/persona-writer`（operator / admin 鉴权，需已改密）
管理端路径：`/api/admin/persona-writer`（admin 鉴权）

人设脚本仿写工具：3 步向导（加载风格 → 对标验证 → 仿写创作）。Step 2 含抖音链接解析 + 点赞门槛 + AI 开头评估；Step 3 含 AI 结构拆解 + 双选题（💡我有想法 / 🤖我没想法）+ 多轮追问 + 终稿编辑。4 个 Prompt 模板 + 2 个 AI 模型（light / heavy）由 admin 配置。

### 22.1 GET /kols/personas

Step 1 达人下拉列表（同 qianchuan-writer）。返回 `persona + content_plan` 均非空、未删除、状态为 `signed` 或 `pending_renewal` 的达人。

Response（200）：
```json
{
  "success": true, "code": "OK",
  "data": [
    { "id": 3, "name": "孙静", "soul_preview": "（前 400 字）", "creator_name": "系统预设" }
  ]
}
```

### 22.2 POST /fetch-video

Step 2.1 抖音分享链接解析（调 tikhub_adapter）。

Request（JSON）：`{ "share_url": "https://v.douyin.com/xxx/" }`

Response（200）：
```json
{
  "success": true,
  "data": {
    "title": "视频标题",
    "digg_count": 250000,
    "aweme_id": "7234...",
    "play_url": "https://...",
    "likes_pass": true
  }
}
```

`likes_pass = (digg_count >= 100000)` 硬编码（业务铁律：对标视频必须 ≥10 万赞）。

错误：share_url 空 → 400 INVALID_INPUT；TikHub 调用失败 → 502 EXTERNAL_SERVICE_ERROR。写 OperationLog（action=`persona_writer_fetch_video`）。TikHubCallLog 由 tikhub adapter finally 自动写。

### 22.3 POST /evaluate-opening

Step 2.4 AI 开头评估（裸文本流）。调 yunwu light 模型 + `evaluation_prompt` 模板。

Request（JSON）：`{ "transcript": "对标文案全文" }`

Response：`text/plain; charset=utf-8`（裸文本流，流式 chunk）

错误：transcript 空 → 400 INVALID_INPUT；配置未激活 → 503 CONFIG_NOT_FOUND。AiCallLog 由 yunwu adapter finally 自动写。

### 22.4 POST /analyze-structure

Step 3.1 AI 结构拆解（裸文本流）。调 yunwu light 模型 + `analysis_prompt` 模板。

Request（JSON）：`{ "transcript": "对标文案全文" }`

Response：`text/plain; charset=utf-8`（裸文本流）

错误：transcript 空 → 400 INVALID_INPUT；配置未激活 → 503 CONFIG_NOT_FOUND。

### 22.5 POST /chat

Step 3.3/3.4 AI 写作 + 多轮追问（裸文本流）。调 yunwu heavy 模型，根据 scene 选 `writing_prompt` 或 `iteration_prompt`。

Request（JSON）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `scene` | string | `writing`（默认）\| `iteration` |
| `topic_mode` | string | `default`（默认）\| `custom`（仅 writing 场景有效；custom 时用户必须传 topic）|
| `persona_id` | int | 达人 ID（必填）|
| `transcript` | string | 对标文案全文 |
| `structure_analysis` | string | Step 3.1 拆解结果（writing/iteration 用）|
| `topic` | string | 选题（writing 场景：custom 模式下用户输入；default 模式下空）|
| `messages` | array<{role, content}> | 用户对话消息（iteration 场景含图片 image_url）|
| `create_job` | bool | 是否创建 task_job 记录（默认 false）|
| `job_context` | object \| null | 任务上下文（可选）|

Response：`text/plain; charset=utf-8`（裸文本流）

错误：messages 空 / scene 不合法 / persona_id 空 → 400 INVALID_INPUT；persona 不存在 → 404 RESOURCE_NOT_FOUND；配置未激活 → 503 CONFIG_NOT_FOUND。

流程：读 DB 配置（`default`，is_active=true）→ 读 kols（name/persona/content_plan）→ `render_prompt` 占位符替换（7 个 + `{{is_custom}}...{{/is_custom}}` 块语法）→ yunwu_adapter.chat_stream → StreamingResponse；`create_job=true` 时 BackgroundTask 写 TaskJob + OperationLog（action=`persona_writer_chat`）。

### 22.6 POST /save-output

保存仿写产出至 outputs 表（账号绑定）。

Request（JSON）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `content` | string | 产出正文（必填）|
| `title` | string | 标题（可选，留空自动生成 "人设脚本仿写 · YYYY-MM-DD"）|
| `task_id` | int \| null | 关联任务 ID（可选）|
| `topic` | string \| null | 选题（仅入 OperationLog）|
| `transcript_digest` | string \| null | 对标文案摘要（仅入 OperationLog）|

Response（200）：`{ "success": true, "data": { "output_id": 789 } }`

错误：content 空 → 400 INVALID_INPUT。写 OperationLog（action=`persona_writer_save_output`）。

### 22.7 POST /export-word

导出 Word 文档（.docx 二进制流，不走标准信封）。

Request（JSON）：`{ "content": "...", "filename": "人设脚本" }`

Response：`application/vnd.openxmlformats-officedocument.wordprocessingml.document`

Header：`Content-Disposition: attachment; filename*=UTF-8''<URL-encoded>_<YYYY-MM-DD>.docx`

错误：content 空 → 400 INVALID_INPUT。

### 22.8 GET /outputs

历史记录（按账号隔离，只返回当前用户的 outputs）。同 qianchuan-writer §21.6。

Query 参数：`page`（默认 1，ge 1）、`page_size`（默认 20，仅允许 10 / 20 / 50）

Response（200）：
```json
{
  "success": true,
  "data": {
    "items": [
      { "id": 1, "title": "人设脚本仿写 · 2026-06-23", "content": "...", "word_count": 800, "task_id": null, "created_at": "2026-06-23T10:00:00+08:00" }
    ],
    "pagination": { "page": 1, "page_size": 20, "total": 5, "total_pages": 1 }
  }
}
```

SQL 过滤：`WHERE tool_code='persona-writer' AND created_by=current_user.id AND deleted_at IS NULL`。

### 22.9 GET /admin/configs

获取配置列表（admin）。

Response（200）：
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "config_key": "default",
      "evaluation_prompt": "...",
      "analysis_prompt": "...",
      "writing_prompt": "...（含 {{is_custom}}...{{/is_custom}} 块语法）",
      "iteration_prompt": "...",
      "light_model_id": 2,
      "heavy_model_id": 4,
      "is_active": true,
      "updated_at": "2026-06-23T..."
    }
  ]
}
```

通常仅返回 1 条 `config_key='default'`。

### 22.10 PUT /admin/configs/{config_key}

更新配置（admin）。

Request（JSON）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `evaluation_prompt` | string \| null | 开头评估 Prompt 模板 |
| `analysis_prompt` | string \| null | 结构拆解 Prompt 模板 |
| `writing_prompt` | string \| null | 写作 Prompt 模板（含 `{{is_custom}}...{{/is_custom}}` 块语法）|
| `iteration_prompt` | string \| null | 追问 Prompt 模板 |
| `light_model_id` | int \| null | 评估/拆解用 AI 模型（留空默认 `claude-haiku-4-5-20251001`）|
| `heavy_model_id` | int \| null | 写作/追问用 AI 模型（留空默认 `claude-opus-4-6`）|
| `is_active` | bool | 配置启用开关（默认 true）|

Response（200）：`{ "success": true, "data": { "config_key": "default" } }`

错误：config_key 不存在 → 404 RESOURCE_NOT_FOUND。写 OperationLog（action=`admin_update_persona_writer_config`）。

---

## 23. seeding-writer（Sprint 16）

种草内容仿写工具：4 步向导（选达人+素材库 → 产品信息 → 对标验证 → 种草仿写）。
基础路径：`/api/tools/seeding-writer`（operator / admin 鉴权，需已改密）。

### 23.1 运营端接口（20 个）

| # | 方法 | 路径 | 用途 | 信封 | OperationLog |
|---|------|------|------|------|-------------|
| 1 | GET | `/kols/personas` | 达人下拉（同 persona-writer）| 标准 | 否 |
| 2 | GET | `/references?kol_id=X` | 素材列表（达人维度共享）| 标准 | 否 |
| 3 | POST | `/references` | 新增素材（粘贴文本）| 标准 | 是 |
| 4 | POST | `/references/import-from-douyin` | 抖音链接导入（阻塞）| 标准 | 是 |
| 5 | DELETE | `/references/{id}` | 软删素材 | 标准 | 是 |
| 6 | GET | `/products` | 产品库列表（公司共享，分页）| 标准 | 否 |
| 7 | POST | `/products` | 新建产品 | 标准 | 是 |
| 8 | PUT | `/products/{id}` | 更新产品 | 标准 | 是 |
| 9 | DELETE | `/products/{id}` | 软删产品 | 标准 | 是 |
| 10 | POST | `/products/parse-document` | 文档解析（multipart）| 标准 | 是 |
| 11 | POST | `/products/extract-selling-points` | AI 卖点讨论（流式）| 流式（裸文本）| 否 |
| 12 | POST | `/fetch-video` | 抖音链接解析 | 标准 | 是 |
| 13 | POST | `/transcribe/submit` | 提交 ASR | 标准 | 是 |
| 14 | POST | `/transcribe/poll` | 轮询 ASR（高频）| 标准 | 否 |
| 15 | POST | `/analyze-structure` | 结构拆解（流式，light）| 流式 | 否 |
| 16 | POST | `/ai-recommend` | AI 推荐角度（流式，light）| 流式 | 否 |
| 17 | POST | `/chat` | 写作+迭代（流式，heavy）| 流式 | create_job 时写 |
| 18 | POST | `/save-output` | 保存产出 | 标准 | 是 |
| 19 | POST | `/export-word` | 导出 Word | StreamingResponse | 否 |
| 20 | GET | `/outputs` | 历史记录（账号隔离）| 标准 | 否 |

### 23.2 关键接口

#### POST /references（粘贴文本）

Request：`{ "kol_id": 3, "title": "...", "content": "...", "type": "种草爆款", "likes": 120000, "source": "抖音" }`
Response：`{ "success": true, "data": { "id": 456 } }`

#### POST /references/import-from-douyin（同步阻塞）

Request：`{ "kol_id": 3, "share_url": "https://v.douyin.com/xxx/", "type": "种草爆款" }`
流程：fetch-video → download → OSS upload → sign → ASR transcribe（阻塞，max 600s）→ 写表
Response：`{ "success": true, "data": { "id": 456, "title": "...", "content": "..." } }`

#### POST /products/parse-document（multipart）

Request：`multipart/form-data`，files 字段支持 PDF/DOCX/XLSX/PPTX/TXT
流程：解析文本 → AI（heavy 模型 + parse_product_prompt）→ JSON 提取
Response：`{ "success": true, "data": { "name": "...", "category": "...", "price": "...", "sellingPoints": "...", "targetAudience": "...", "scenario": "...", "medicalAestheticAnchor": "...", "_rawText": "..." } }`

#### POST /products/extract-selling-points（流式）

Request：`{ "raw_text": "产品资料原文", "preliminary_info": {...} }`
调 yunwu（heavy 模型）+ sp_system_prompt → 裸文本流（AI 讨论 3 个核心卖点）

#### POST /transcribe/submit

Request：`{ "play_url": "https://..." }`
Response：`{ "success": true, "data": { "task_id": "abc123", "expected_max_seconds": 600 } }`

#### POST /transcribe/poll

Request：`{ "task_id": "abc123" }`
Response（processing）：`{ "success": true, "data": { "status": "processing" } }`
Response（done）：`{ "success": true, "data": { "status": "done", "text": "..." } }`

#### POST /chat

Request：`{ "scene": "writing|iteration", "persona_id": 3, "product_id": 7, "reference_ids": [], "transcript": "...", "structure_analysis": "...", "topic": "...", "messages": [...], "create_job": false }`

占位符（14 个）：`{{name}} {{soul}} {{content_plan}} {{product_name}} {{product_category}} {{product_price}} {{product_selling_points}} {{product_target_audience}} {{product_scenario}} {{references}} {{transcript}} {{structure_analysis}} {{topic}} {{raw_text}}`

### 23.3 管理端接口（2 个）

基础路径：`/api/admin/seeding-writer`（admin 鉴权）

| # | 方法 | 路径 | 用途 |
|---|------|------|------|
| 1 | GET | `/configs` | 配置列表 |
| 2 | PUT | `/configs/{config_key}` | 更新 6 Prompt + 2 模型 + 启用 |

#### PUT /configs/{config_key}

Request Body：
| 字段 | 类型 | 说明 |
|------|------|------|
| `sp_system_prompt` | string \| null | 卖点提取 Prompt |
| `parse_product_prompt` | string \| null | 文档解析 Prompt |
| `structure_analysis_prompt` | string \| null | 结构拆解 Prompt |
| `ai_recommend_prompt` | string \| null | AI 推荐角度 Prompt |
| `writing_prompt` | string \| null | 写作 Prompt |
| `iteration_prompt` | string \| null | 迭代 Prompt |
| `light_model_id` | int \| null | 结构拆解/AI推荐用模型 |
| `heavy_model_id` | int \| null | 写作/迭代/卖点讨论用模型 |
| `is_active` | bool | 配置启用开关 |

写 OperationLog（action=`admin_update_seeding_writer_config`）。

---

## 24. material-library 素材库（Sprint 18 — 迁移自旧架构）

红人素材中枢：管理每位红人的人格档案（soul.md）、内容规划（content-plan.md）、参考素材（6 类），
并支持 AI 从入驻问卷数据生成 soul.md 初稿。
基础路径：`/api/tools/material-library`（运营端）与 `/api/admin/material-library`（管理端）。
迁移自旧架构 `Ai_Toolbox/material-library-web/`。

### 24.1 数据存储说明

- 人格档案、内容规划**复用 `kols.persona` 与 `kols.content_plan` 字段**（不新建 profile 表）。
- 参考素材存于新表 `kol_references`（详见 `MCN_M2_Base_Database.md` §28）。
- AI 配置存于新表 `material_library_configs`（详见 §29）。

### 24.2 运营端接口（10 个）

基础路径：`/api/tools/material-library`（operator / admin 鉴权，需已改密）

| # | 方法 | 路径 | 用途 | 信封 | OperationLog |
|---|------|------|------|------|-------------|
| 1 | GET | `/kols?search=&page=&page_size=` | 红人列表（搜索+聚合+分页）| 标准 | 否 |
| 2 | GET | `/kols/{kol_id}` | 红人详情（persona + plan + references 按类型分组）| 标准 | 否 |
| 3 | POST | `/kols/{kol_id}/references` | 新增参考素材 | 标准 | 是 |
| 4 | DELETE | `/kols/{kol_id}/references/{ref_id}` | 软删参考素材 | 标准 | 是 |
| 5 | GET | `/kols/{kol_id}/intake` | 红人最新入驻问卷数据 | 标准 | 否 |
| 6 | POST | `/kols/{kol_id}/generate-soul` | AI 生成只读草稿（不写正式档案）| 标准 | 是 |
| 7 | PUT | `/kols/{kol_id}/references/{ref_id}` | 编辑标题、数据说明和正文 | 标准 | 是 |
| 8 | POST | `/kols/{kol_id}/references/parse-document` | 解析脚本文档，返回可编辑正文和文档元数据 | 标准 | 是 |
| 9 | POST | `/kols/{kol_id}/references/{ref_id}/video` | 上传或明确替换视频原片 | 标准 | 是 + OSS 调用日志 |
| 10 | GET | `/kols/{kol_id}/references/{ref_id}/video/playback` | 鉴权后返回短时视频播放地址 | 标准 | OSS 调用日志 |

#### GET /kols?search=&page=&page_size=
`page` 默认 1，`page_size` 默认 20，最大 100。Response.data：`{ items: KolListItem[], pagination }`
```json
{
  "items": [{
    "id": 3, "name": "孙静", "account_name": "sunjing", "category": "美妆",
    "follower_count": 1200000,
    "has_persona": true, "has_content_plan": false,
    "reference_count": 3, "has_intake": true,
    "updated_at": "2026-06-20T10:00:00+08:00"
  }],
  "pagination": { "page": 1, "page_size": 20, "total": 1 }
}
```

#### GET /kols/{kol_id}
Response.data：`KolDetail`
```json
{
  "id": 3, "name": "孙静", "account_name": "sunjing",
  "category": "美妆", "follower_count": 1200000,
  "persona": "我是孙静...",
  "content_plan": "",
  "references": {
    "红人爆款文案": [{ "id": 10, "title": "...", "likes": 50000, "source": "抖音", "content": "...", "created_at": "..." }],
    "风格参考": [],
    "红人喜欢的内容": [],
    "千川爆款文案": [],
    "千川喜欢的内容": [],
    "千川风格参考": []
  }
}
```

Sprint 25 起移除 `PUT /kols/{kol_id}/profile`。素材库仅返回 `persona` / `content_plan` 只读摘要，正式编辑统一跳转 `/kol-workspace/{kol_id}` 的“人物档案”页签。

#### POST /kols/{kol_id}/references
Request Body：
```json
{
  "type": "红人爆款文案",
  "title": "夏季护肤心得",
  "likes": 50000,
  "source": "抖音",
  "content": "正文..."
}
```
`type` 必须是 6 类之一：`红人爆款文案 / 红人喜欢的内容 / 风格参考 / 千川爆款文案 / 千川喜欢的内容 / 千川风格参考`
Response.data：完整素材对象（包含 `id`、标题、正文、文档元数据和视频状态；不含私有对象键或播放地址）。
写 OperationLog（action=`material_library_create_reference`）。

`data_description`、`document_name`、`document_type`、`document_size` 均为可选字段。文档内容解析后由前端在此接口提交，服务端只保存解析结果与元数据，不保存文档的本地永久路径。

#### PUT /kols/{kol_id}/references/{ref_id}
Request Body 可更新 `title`、`data_description`、`content`；不传的视频字段保持原视频不变。`ref_id` 必须属于路径中的 `kol_id`，否则按不存在处理。
写 OperationLog（action=`material_library_update_reference`）。

#### POST /kols/{kol_id}/references/parse-document
`multipart/form-data`，字段名 `file`。支持平台既有文档解析格式，最大 20MB；服务端仅限大小读取一次后解析，返回 `{ text, document_name, document_type, document_size }`，用于运营在保存素材前修改正文。红人不存在或已删除时不可解析。写 OperationLog（action=`material_library_parse_document`）。

#### POST /kols/{kol_id}/references/{ref_id}/video
`multipart/form-data`，字段名 `file`。仅接受 `video/*` 文件，最大 500MB；服务端按块写入系统临时文件并在超限时停止读取，再通过对象存储的文件流接口上传。临时文件在成功、失败和替换路径均会清理，不长期保存。上传对象强制设置为私有，再替换素材的视频元数据，成功后删除旧对象。数据库只保存私有对象键与文件元数据，不返回或保存长期公开地址。写 OperationLog（action=`material_library_upload_video` 或 `material_library_replace_video`）；对象存储调用另写服务调用日志。

#### GET /kols/{kol_id}/references/{ref_id}/video/playback
仅当素材属于该红人且未软删、存在视频对象键时返回短时签名地址：`{ "url": "...", "expires_in": 900 }`。地址由后端生成，不写入素材详情或数据库。

#### DELETE /kols/{kol_id}/references/{ref_id}
软删（`deleted_at = NOW()`）；若有关联视频对象，软删后调用平台对象存储适配层删除对象并自动写服务调用日志。Response.data 为空，删除结果在标准信封的 `message` 返回。
写 OperationLog（action=`material_library_delete_reference`）；若视频对象清理失败，额外写 `material_library_delete_video_cleanup_failed`。

#### GET /kols/{kol_id}/intake
查询 kol 最新入驻问卷数据（先查 KolIntakeSubmission，再查 KolIntakeOperatorSession）。
Response.data：`IntakeData | null`
```json
{
  "source": "submission",
  "messages": [{ "role": "user", "content": "..." }, ...],
  "ai_report": "AI 分析报告全文",
  "report_status": "completed",
  "created_at": "..."
}
```

#### POST /kols/{kol_id}/generate-soul
读取 `material_library_configs` 中 `soul_generator` 配置，渲染占位符（`{{kol_name}} {{intake_answers}} {{intake_report}}`），
调用 yunwu_adapter.chat() 生成初稿。**不自动保存**，仅返回文本供前端预览编辑。
Response.data：`{ "soul_md": "AI 生成的人格档案初稿..." }`
写 OperationLog（action=`material_library_generate_soul`）。

### 24.3 管理端接口（2 个）

基础路径：`/api/admin/material-library`（admin 鉴权）

| # | 方法 | 路径 | 用途 | OperationLog |
|---|------|------|------|-------------|
| 1 | GET | `/configs` | 获取 soul_generator 配置 | 否 |
| 2 | PUT | `/configs` | 更新配置 | 是 |

#### PUT /configs
Request Body：
| 字段 | 类型 | 说明 |
|------|------|------|
| `ai_model_id` | int \| null | AI 模型 ID |
| `system_prompt` | string \| null | soul_generator 系统提示词 |
| `is_active` | bool | 启用开关 |

写 OperationLog（action=`admin_update_material_library_config`）。

---

## 25. subtitle 字幕提取（Sprint 19 — 迁移自旧架构）

抖音视频字幕提取（单条 / 批量）+ AI 思维导图 + 多格式导出。
基础路径：`/api/tools/subtitle`（运营端）与 `/api/admin/subtitle`（管理端）。
迁移自旧架构 `Ai_Toolbox/subtitle-extractor-web/`。
公共服务走 adapter：tikhub（视频解析）/ asr（阿里云 ASR）/ yunwu（思维导图）。

### 25.1 数据存储说明

- 批量任务存于新表 `subtitle_jobs` + `subtitle_items`（详见 `MCN_M2_Base_Database.md` §30）。
- AI 配置（思维导图 Prompt + 模型）存于新表 `subtitle_configs`（§30）。
- 产出接入共享 `outputs` 表（tool_code='subtitle'），无需新表。

### 25.2 运营端接口（8 个）

基础路径：`/api/tools/subtitle`（operator / admin 鉴权，需已改密）

| # | 方法 | 路径 | 用途 | 信封 | OperationLog |
|---|------|------|------|------|-------------|
| 1 | POST | `/extract` | 单条：share_text 或 file_url → 异步任务 → 返回 job_code（前端轮询）| 标准 | 是 |
| 2 | POST | `/batch` | 批量：多 share_text → 创建 job + 后台执行 | 标准 | 是 |
| 3 | GET | `/batch/{job_code}` | 查询任务详情（含 items，绑定 created_by；含软删除过滤）| 标准 | 否 |
| 4 | GET | `/batches` | 历史记录列表（单条 + 批量统一，分页，绑定 created_by，过滤软删除）| 标准 | 否 |
| 5 | DELETE | `/batch/{job_code}` | 软删除一条历史记录（设置 deleted_at）| 标准 | 是 |
| 6 | POST | `/mindmap` | 字幕 → AI 思维导图（JSON）| 标准 | 是 |
| 7 | POST | `/save-output` | 保存字幕到产出中心（写共享 outputs 表）| 标准 | 是 |
| 8 | GET | `/outputs`（**复用全局 `/api/outputs?tool_code=subtitle`**）| 我的字幕产出列表 | 标准 | 否 |

> 任务通过 `created_by` 绑定用户身份（JWT 鉴权），无需额外查询码。
> **Sprint 21 起**：`/extract` 改为异步任务模式（`kind='single'`），返回 `job_code` 后前端轮询 `/batch/{job_code}` 获取结果。单条 + 批量统一在 `/batches` 展示。

#### POST /extract（异步任务化 — Sprint 21）
Request Body（二选一）：
```json
{ "share_text": "7.69 复制打开抖音... https://v.douyin.com/xxx/" }
```
或
```json
{ "file_url": "https://oss.example.com/audio/uploaded.mp3" }
```
流程（异步）：
1. 生成 job_code → INSERT subtitle_jobs（kind='single', total=1, status='processing'）+ 1 subtitle_item
2. `asyncio.create_task(_run_single_extract(job_id, user_id))` 后台执行
3. 立即返回 job_code

**`_run_single_extract` 后台执行**：
- share_text 模式：tikhub.fetch_video_by_share_url() → audio_url + 视频元信息（play_url/cover_url/nickname/digg_count/aweme_id）→ asr.transcribe() → 字幕
- file_url 模式：跳过 tikhub，直接 ASR；视频元信息字段全部为空
- 完成后：将视频元信息以 JSON 形式存入 `subtitle_items.meta_json`，item.status='success' / 'failed'，job.status='completed' / 'failed'

Response.data：
```json
{
  "job_code": "sub_single_xxxxxxxx",
  "status": "processing"
}
```
前端拿到 job_code 后轮询 `GET /batch/{job_code}`，直到 `status === 'completed'` 取 `items[0]`（已扁平化 meta_json 字段到顶层）。

错误码：400（输入为空）/ 502（tikhub 或 ASR 失败，`EXTERNAL_SERVICE_ERROR`）。
写 OperationLog（action=`subtitle_extract`）。
ASR 调用日志由 `asr_adapter` 自动写 `asr_call_logs`（router 不重复）。

#### POST /batch
Request Body：
```json
{ "items": [{ "share_text": "https://v.douyin.com/aaa/" }, { "share_text": "https://v.douyin.com/bbb/" }] }
```
流程：生成 job_code → INSERT subtitle_jobs（created_by=current_user.id）+ N subtitle_items → `asyncio.create_task(_run_batch(job_id, user_id))`。
Response.data：
```json
{ "job_code": "sub_20260625_xxxxxxxx", "total": 2 }
```
错误码：400（items 为空）。
写 OperationLog（action=`subtitle_batch_create`，target_type=`subtitle_job`）。

**`_run_batch(job_id, user_id)` 后台执行（使用 AsyncSessionLocal，脱离请求生命周期）**：
1. 锁定 job，phase='running'
2. 遍历 subtitle_items：item.status='processing' → tikhub.fetch + asr.transcribe → status='success' / 'failed'（含 error）
3. 聚合统计：job.status='completed' / 'failed'，job.success/failed 计数
4. tikhub / asr 异常捕获写入 item.error；ASR 调用日志由 adapter 自动写。

#### GET /batch/{job_code}
查询条件：`job_code == :job_code AND created_by == current_user.id AND deleted_at IS NULL`（仅能查到自己创建且未软删除的任务；他人 job_code → 404，软删除 → 404）。
Response.data：`SubtitleJob`（含 items 数组，单条任务 item 含扁平化的视频元信息）
```json
{
  "id": 12, "job_code": "sub_...", "kind": "single|batch",
  "status": "processing", "phase": "running",
  "total": 2, "success": 1, "failed": 0, "created_by": 7,
  "created_at": "...", "updated_at": "...",
  "items": [{
    "id": 23, "row_number": 1, "original_url": "https://v.douyin.com/aaa/",
    "title": "视频标题", "transcript": "字幕文本（success 时非空）",
    "status": "success", "error": "",
    "play_url": "https://...（单条 success 时从 meta_json 扁平化）",
    "audio_url": "https://...",
    "cover_url": "https://p3-sign.douyinpic.com/...jpg",
    "nickname": "作者昵称",
    "digg_count": 12345,
    "aweme_id": "7xxxxxxxxxxxxxx"
  }]
}
```
错误码：404（任务不存在 / 无权限访问 / 已软删除）。

#### DELETE /batch/{job_code}（软删除 — Sprint 21）
软删除一条历史记录（设置 `deleted_at = now()`）。后续 GET /batches 和 GET /batch/{job_code} 均过滤该记录。
仅能删除自己创建的任务（`created_by == current_user.id`），他人 job_code → 404。
Response.data：
```json
{ "job_code": "sub_...", "deleted": true }
```
错误码：404（任务不存在 / 无权限 / 已删除）。
写 OperationLog（action=`subtitle_delete`，target_type=`subtitle_job`）。

#### GET /batches
查询当前用户的历史记录列表（单条 + 批量统一展示，分页，按 created_at 倒序，过滤软删除 `deleted_at IS NULL`，不含 items）。
Query 参数：`page`（默认 1）、`page_size`（默认 20，1-50）。
Response.data：
```json
{
  "items": [{
    "id": 12, "job_code": "sub_...", "kind": "single|batch",
    "status": "completed", "phase": "done",
    "total": 5, "success": 4, "failed": 1, "created_by": 7,
    "created_by_username": "alice（可选，管理端列表用）",
    "created_at": "...", "updated_at": "..."
  }],
  "pagination": { "page": 1, "page_size": 20, "total": 3, "total_pages": 1 }
}
```

#### POST /mindmap
Request Body：
```json
{ "transcript": "字幕全文" }
```
流程：读 `subtitle_configs` default 配置 → 渲染 `{{transcript}}` 占位符 → yunwu_adapter.chat() → 清理 markdown fence → JSON 解析。
Response.data：
```json
{
  "rootTitle": "核心主题",
  "summary": "一句话总结",
  "branches": [{ "title": "分支 1", "children": ["要点 1", "要点 2"] }]
}
```
错误码：400（transcript 为空）/ 502（AI 调用失败或 JSON 解析失败）/ 503（无激活配置）。
写 OperationLog（action=`subtitle_mindmap`）。
AI 调用日志由 `yunwu_adapter` 自动写 `ai_call_logs`（router 不重复）。
默认模型：`claude-haiku-4-5-20251001`（配置缺失或失效时回退）。

#### POST /save-output
Request Body：
```json
{
  "title": "字幕标题（可空，缺省为'未命名字幕'）",
  "transcript": "字幕全文",
  "mindmap": { "rootTitle": "...", "summary": "...", "branches": [...] }
}
```
写入共享 `outputs` 表（tool_code='subtitle'，content=transcript，content_json.mindmap 可选）。
Response.data：
```json
{ "id": 456, "title": "...", "tool_code": "subtitle", "word_count": 1234, "created_at": "..." }
```
错误码：400（transcript 为空）。
写 OperationLog（action=`subtitle_save_output`，target_type=`output`）。

### 25.3 管理端接口（3 个）

基础路径：`/api/admin/subtitle`（admin 鉴权）

| # | 方法 | 路径 | 用途 | OperationLog |
|---|------|------|------|-------------|
| 1 | GET | `/configs` | 获取思维导图 Prompt + 模型配置 | 否 |
| 2 | PUT | `/configs` | 更新配置 | 是 |
| 3 | GET | `/batches` | 全部批量任务列表（跨用户，支持 user_id 过滤）| 否 |

#### GET /configs
Response.data：`SubtitleConfig[]`
```json
[{
  "id": 1, "config_key": "default",
  "mindmap_prompt": "你是思维导图生成器。输入：{{transcript}}",
  "mindmap_model_id": 2, "is_active": true, "updated_at": "..."
}]
```

#### PUT /configs
Request Body（所有字段可选）：
| 字段 | 类型 | 说明 |
|------|------|------|
| `mindmap_model_id` | int \| null | 思维导图 AI 模型 ID（绑 ai_models.id）|
| `mindmap_prompt` | string \| null | 思维导图系统提示词（支持 `{{transcript}}` 占位符）|
| `is_active` | bool | 启用开关 |

写 OperationLog（action=`admin_subtitle_config_update`，target_type=`subtitle_config`）。

#### GET /batches
查询全部批量任务（跨用户，可选 user_id 过滤），按 created_at 倒序。响应含 `created_by_username`（前端展示创建人）。
Query 参数：`page`（默认 1）、`page_size`（默认 20，1-50）、`user_id`（可选，>0 时按用户过滤）。
Response.data：
```json
{
  "items": [{
    "id": 12, "job_code": "sub_...", "status": "completed", "phase": "done",
    "total": 5, "success": 4, "failed": 1, "created_by": 7, "created_by_username": "operatorA",
    "created_at": "...", "updated_at": "..."
  }],
  "pagination": { "page": 1, "page_size": 20, "total": 3, "total_pages": 1 }
}
```

---

## 26. values-writer（Sprint 20）

> 路由前缀：`/api/operator/values-writer`（运营端）+ `/api/admin/values-writer`（管理端）
> 所有接口需 JWT 鉴权。运营端需 operator/admin 角色。
> § 编号说明：原 feature 分支为 §25，与 main 的 §25 subtitle 冲突，合并后改为 §26。

### 26.1 接口总览

| 方向 | 接口数 |
|------|--------|
| 运营端 | 5（4 工具接口 + 1 save-output） |
| 管理端 | 2 |
| 小计 | 7 |

### 26.2 管理端接口

#### GET `/api/admin/values-writer/config`

读取 `config_key='default'` 配置。

Response `data`：
```json
{
  "id": 1,
  "config_key": "default",
  "extract_values_prompt": "...",
  "emotion_direction_prompt": "...",
  "writing_prompt": "...",
  "iteration_prompt": "...",
  "model_id": null,
  "is_active": true,
  "updated_at": "2026-06-26T00:00:00Z"
}
```

#### PUT `/api/admin/values-writer/config`

Request Body（所有字段可选，未传字段不变）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `extract_values_prompt` | string\|null | 价值观提炼 Prompt |
| `emotion_direction_prompt` | string\|null | 情绪方向 Prompt |
| `writing_prompt` | string\|null | 内容生成 Prompt |
| `iteration_prompt` | string\|null | 迭代优化 Prompt |
| `model_id` | int\|null | AI 模型 ID |
| `is_active` | bool | 启用开关 |

写 OperationLog（action=`admin_update_values_writer_config`）。

### 26.3 运营端接口

#### POST `/api/operator/values-writer/derive-directions`

旧版四步流程的第三步。服务端固定读取 `kol_id` 的完整人物档案和唯一当前商品；前端传入的商品正文不会被采用。根据锁定开头、爆款全文和当前商品返回 2 至 3 个可选情绪方向。解析或模型调用失败时，服务端最多尝试 3 次；三次仍失败返回明确错误。

Request Body：
```json
{ "kol_id": 1, "opening_line": "锁定的第一句", "original_script": "爆款全文" }
```

Response `data`：
```json
{ "directions": [{ "type": "焦虑型", "title": "错失机会", "description": "放大缺失的代价", "anchor": "再拖下去会错过" }] }
```

没有当前商品时返回 `400`，错误信息为“请先在产品库选择当前商品”。

#### POST stream `/api/operator/values-writer/generate`

旧版四步流程的第四步。服务端读取当前商品和完整人物档案，要求模型输出 `<analysis>`、`<rewrite>`、`<report>` 三个结构化片段；改写稿必须逐字保留 `opening_line`，并且不得出现当前商品名称或直接商品信息。

Request Body：
```json
{
  "kol_id": 1,
  "opening_line": "锁定的第一句",
  "original_script": "爆款全文",
  "direction": { "type": "诱惑型", "title": "人生开挂", "description": "放大获得后的生活优势", "anchor": "被看见的轻松感" }
}
```

Response：`Content-Type: text/event-stream`，格式：`data: {"delta": "..."}`。模型输出缺少任一结构化片段时，前端必须展示解析失败，不能将原始标签文本作为成功脚本。

`extract-values`、`emotion-direction`、`write` 和 `iterate` 为兼容既有独立入口保留；红人工作台入口只使用以上两个旧版四步流程接口。

#### POST stream `/api/operator/values-writer/iterate`

根据用户指令迭代优化（SSE 流式）。

Request Body：
```json
{ "kol_id": 1, "content": "现有内容...", "instruction": "开头更有冲击力" }
```

Response：`Content-Type: text/event-stream`

#### POST `/api/operator/values-writer/save-output`

保存生成内容到历史（手动触发，复用全局 `outputs` 表，`tool_code='values-writer'`）。

Request Body：
```json
{
  "content": "仿写出的完整内容",
  "title": "可选标题",
  "topic": "可选主题，如「真实、治愈」"
}
```

Response `data`：
```json
{ "output_id": 123 }
```

写 OperationLog（action=`values_writer_save_output`, target_type=`output`）。

历史查询走全局接口：`GET /api/outputs?tool_code=values-writer`（用户隔离）；删除走 `DELETE /api/outputs/{id}`（软删）。

---

## 27. qianchuan-script-review 千川脚本预审（Sprint 21）

### 27.1 说明

对千川脚本进行 AI 预审，支持「千川直销模式」和「价值观模式」两种类型，返回结构化审核结论（rating / must_fix / suggestions / passed）。

### 27.2 管理端接口

#### GET `/api/admin/qianchuan-script-review/config`

读取 `config_key='default'` 配置。鉴权：admin 角色。

Response `data`：
```json
{
  "id": 1,
  "config_key": "default",
  "direct_prompt": "...",
  "value_prompt": "...",
  "ai_model_id": null,
  "is_active": true,
  "updated_at": "2026-06-27T00:00:00Z"
}
```

#### PUT `/api/admin/qianchuan-script-review/config`

更新 default 配置（PATCH 语义）。鉴权：admin 角色。写 OperationLog（action=`admin_update_script_review_config`）。

Request Body（所有字段可选）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `direct_prompt` | string\|null | 千川直销模式 Prompt（含 `{original_script}`/`{adapted_script}`/`{product_info}` 占位符） |
| `value_prompt` | string\|null | 价值观模式 Prompt（含 `{original_script}`/`{adapted_script}` 占位符） |
| `ai_model_id` | int\|null | AI 模型 ID（null 时默认 claude-sonnet-4-6） |
| `is_active` | bool | 启用开关 |

### 27.3 运营端接口

#### POST `/api/operator/qianchuan-script-review/review`

非流式脚本预审，等待 AI 返回完整 JSON 结论。鉴权：operator/admin 角色。

Request Body：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `script_type` | `"direct"\|"value"` | 是 | 预审模式 |
| `original_script` | string | 是 | 原版脚本 |
| `adapted_script` | string | 是 | 仿写脚本 |
| `product` | object\|null | 否 | 兼容独立预审页的产品信息；工作台闭环不得依赖此字段 |
| `kol_id` | int\|null | 否 | 工作台红人 ID；与 `product_id` 同时提供时，后端校验商品是该红人的当前商品 |
| `product_id` | int\|null | 否 | 当前共享商品 ID；后端读取最新商品字段，优先于 `product`，防止前端伪造旧卖点 |

Response `data`：
```json
{
  "task_id": 1,
  "rating": "pass",
  "must_fix": [{ "type": "价格替换", "quote": "原文引用", "fix": "修改建议" }],
  "suggestions": ["可选优化建议"],
  "passed": ["通过项说明"]
}
```

`rating` 取值：`pass`（可上线）/ `minor`（小改可上线）/ `fail`（需大改）。

结果结构与任务规则：
- `rating` 必须是上述三种值；`must_fix` 必须是数组且每项都有非空 `type`、`quote`、`fix`；`suggestions`、`passed` 必须是字符串数组；不接受额外字段。
- 首次结果不合法时最多再做 2 次受控 JSON 格式修复；修复提示不得改变审核结论或补充审核内容。
- 调用前创建 `task_jobs(status=processing)`，只记录脚本类型、两份脚本长度、达人/商品编号和模型编号，不记录脚本正文。
- 严格校验通过后才把任务记为 `success`、写成功操作日志并返回 `task_id`；连续 3 次不合法或 AI 调用异常则任务为 `failed`，返回 `EXTERNAL_SERVICE_ERROR`，且不写成功日志。

#### POST `/api/operator/qianchuan-script-review/save-output`

保存预审结果到历史（手动触发，复用全局 `outputs` 表，`tool_code='qianchuan-script-review'`）。

Request Body：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_id` | int | 是 | review 接口成功返回的任务编号；必须属于当前用户且终态为 success |
| `content` | string | 是 | 仿写脚本原文（便于还原上下文） |
| `content_json` | object | 是 | 结构化评分（同 review 接口返回的 ReviewResult：rating/must_fix/suggestions/passed） |
| `title` | string | 否 | 标题，默认自动生成（含 rating） |

Response `data`：
```json
{ "output_id": 124 }
```

写 OperationLog（action=`script_review_save_output`, target_type=`output`）。

保存前再次按 review 的严格结构校验 `content_json`；无效结构返回 400 INVALID_REVIEW_RESULT，任务不存在、不属于当前用户或终态不是 success 返回 409 TASK_NOT_SUCCESS。保存成功后关联 `outputs.task_id` 和 `task_jobs.output_id`。

历史查询走全局接口：`GET /api/outputs?tool_code=qianchuan-script-review`；删除走 `DELETE /api/outputs/{id}`（软删）。

---

## 28. retrospective 复盘（Sprint 22）

### 28.1 说明

红人工作台复盘模块。支持多维度材料录入（直播数据/素材数据/评价文字/直播脚本/素材脚本），AI 流式生成复盘报告，支持保存/历史管理/导出 Word。

接口前缀：`/api/operator/workspace/{kol_id}/retrospective`（运营端）、`/api/admin/retrospective`（管理端）。

### 28.2 管理端接口

#### GET `/api/admin/retrospective/config`

读取复盘 AI 配置（config_key='default'）。鉴权：admin 角色。

Response `data`：
```json
{
  "id": 1,
  "config_key": "default",
  "system_prompt": null,
  "ai_model_id": null,
  "is_active": true,
  "updated_at": null
}
```

#### PUT `/api/admin/retrospective/config`

更新复盘 AI 配置。鉴权：admin 角色。写 OperationLog（action=`admin_update_retrospective_config`）。

Request Body（所有字段可选）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `system_prompt` | string\|null | AI System Prompt（null 时用内置默认） |
| `ai_model_id` | int\|null | AI 模型 ID（null 时默认 claude-sonnet-4-6） |
| `is_active` | bool | 启用开关 |

### 28.3 运营端接口

#### GET `/api/operator/workspace/{kol_id}/retrospective`

分页查询该红人的复盘列表。鉴权：operator/admin；资源按红人编号隔离，不额外引入未定义的红人授权映射。

Query：`page`（默认1）、`page_size`（10/20/50，默认10）。

Response `data`：
```json
{
  "total": 5,
  "page": 1,
  "page_size": 10,
  "items": [{ "id": 1, "title": "6月复盘", "status": "done", "updated_at": "..." }]
}
```

#### POST `/api/operator/workspace/{kol_id}/retrospective`

新建或更新复盘记录（upsert by id）。鉴权：operator/admin。写 OperationLog（action=`upsert_retrospective_session`）。

Request Body：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | int\|null | 否 | 有则更新，无则新建 |
| `title` | string | 是 | 复盘标题 |
| `live_data` | string\|null | 否 | 直播数据（文本） |
| `material_data` | string\|null | 否 | 素材数据（文本） |
| `review_text` | string\|null | 否 | 评价文字 |
| `live_script` | string\|null | 否 | 直播脚本 |
| `material_scripts` | array\|null | 否 | 素材脚本列表（`[{name, text}]`） |

Response `data`：完整 RetrospectiveSession 对象。

#### DELETE `/api/operator/workspace/{kol_id}/retrospective/{id}`

物理删除复盘记录。写 OperationLog（action=`delete_retrospective_session`）。

Response `data`：`{ "id": 1 }`

#### POST `/api/operator/workspace/{kol_id}/retrospective/parse-files`

逐份解析上传文件（multipart/form-data）。支持 PDF/DOCX/TXT/XLSX/PPTX/MD 格式；响应中的文件名与正文严格一一对应，前端可分别编辑后保存。

Response `data`：`{ "files": [{ "name": "脚本一.docx", "text": "解析出的正文..." }] }`

#### POST stream `/api/operator/workspace/{kol_id}/retrospective/{id}/analyze`

流式生成复盘报告（SSE）。至少需填写直播汇总数据或素材明细数据之一；分析会读取完整红人档案，空字段跳过。生成完成后自动保存 `result`，更新 `status='done'`，写 OperationLog（action=`retrospective_analyze`）。

Response：`Content-Type: text/event-stream`，格式：`data: {"delta": "..."}\n\ndata: [DONE]\n\n`

#### GET `/api/operator/workspace/{kol_id}/retrospective/{id}/export-word`

导出复盘报告为 Word 文件。

Response：`application/vnd.openxmlformats-officedocument.wordprocessingml.document`

---

## 29. 红人工作台当前商品（M2 核心工作流）

接口前缀：`/api/operator/workspace/{kol_id}`。鉴权：operator/admin。所有响应使用标准信封。

### GET `/api/operator/workspace/{kol_id}/active-products`

为兼容现有调用保留数组响应，但数组最多包含一个当前商品。商品详情来自平台共享产品库，软删除商品不会返回。

### PUT `/api/operator/workspace/{kol_id}/active-products`

设置或解除当前商品。写入 OperationLog（`action=update_kol_active_products`）。

Request Body：

| 字段 | 类型 | 说明 |
|------|------|------|
| `product_ids` | int[] | 允许空数组解除关联，或只含一个产品 ID；传入多个 ID 返回 422 |

Response `data`：`{ "active_product_ids": [] }` 或 `{"active_product_ids": [123]}`。

业务规则：写入时整体替换旧关联；商品 ID 必须存在且未软删除；删除当前商品前必须先解除或替换关联，删除接口会返回 400 和明确提示。

---

## 30. qianchuan-preview 完整视频成片预审（M2 红人工作台还原）

> 路由前缀：`/api/tools/qianchuan-preview`。保留原有文案预审接口；以下接口仅用于红人工作台的完整视频分析，不会退化为关键帧分析。

### POST stream `/api/tools/qianchuan-preview/analyze-video`

`multipart/form-data`，字段 `kol_id`（当前工作台红人编号）、`original` 和 `edited` 均必填。服务端先验证 `kol_id` 对应的未删除红人存在；两个文件只接受 `.mp4`、`.mov` 和对应 `video/mp4`、`video/quicktime` MIME 类型；每个文件服务端实际限制为 **500MB**。服务端按块写入临时目录，临时上传到私有对象存储，再将两条完整视频上传至 Gemini Files API，轮询到 `ACTIVE` 后才发起流式分析。

Response：`Content-Type: text/event-stream`。流事件为 `status`（上传、处理进度）、`report`（每个 Gemini 正文分片，`data.text` 可立即追加）以及供应商失败时的 `error`、`failed`；前端收到 `error` 或 `failed` 后保留已选视频但禁止保存或导出部分报告。响应头 `X-Task-Id` 可用于保存。

分析所用 Prompt、模型和 Gemini 凭证均由管理端既有 `qianchuan_preview_configs`、`ai_models`、`credentials` 统一管理。完整视频固定读取独立的 `full_video` 配置键，既有 `default` 配置键仍只用于文案预审；绑定模型必须是状态为 `active`、provider 为 `gemini` 的模型；无配置、供应商处理失败或超时会返回明确错误，绝不改为关键帧分析。`task_jobs.input_payload` 只记录临时对象键和文件元数据，处理结束后删除对象存储和 Gemini 临时文件；Gemini 清理失败会单独写入关联任务的外部服务日志。只有任务状态为 `success` 的完整报告可保存。

工作台页签代码为 `film-review`、显示名为“千川成片预审”。`kol_workspace_configs.enabled_tabs` 的默认值和 `052_enable_qianchuan_full_video_workspace_tab.sql` 都会包含此页签；迁移只补充系统页签，不改变历史红人、商品、素材或产出数据。

### POST `/api/tools/qianchuan-preview/save-video-report`

将完整视频预审报告写入全局 `outputs`，不迁移旧数据。红人归属只从 `task_id` 对应任务的 `input_payload.kol_id` 读取并写进 `outputs.content_json`，前端不能另传或覆盖。

Request Body：
```json
{ "task_id": 123, "report": "完整 Markdown 报告", "original_filename": "original.mp4", "edited_filename": "edited.mov" }
```

Response `data`：`{ "output_id": 456 }`。仅允许任务创建者或管理员保存；空报告会按平台统一响应信封返回 `success=false` 与 `VALIDATION_ERROR`（校验失败），HTTP 状态码为 `200`。

`POST /export-word` 可复用，传入上述保存前或保存后的报告文本即可导出 `.docx` 办公文档。

---

## 31. Sprint 25 — 红人工作台统一人物档案

基础路径：`/api/operator/kols/{kol_id}/persona-details`。鉴权：已改密的 `operator` / `admin`。正式数据始终写入同一条 `kols` 记录。

### GET `/api/operator/kols/{kol_id}/persona-details`

返回 `persona`、`content_plan`、`background`、`experience`、`relationships`、`unique_story`、`extra_notes` 共七项正式字段，以及 `filled_count`、`total_count=7`、`updated_at`。空白字符串按空值计算。

### PUT `/api/operator/kols/{kol_id}/persona-details`

一次请求必须且只能提交七项字段中的一个；允许提交空字符串以便运营清空。任一字段保存失败不影响其他字段。写 OperationLog：`action=update_kol_persona_field`，detail 只含 `field`，不得记录正文。

Request 示例：`{ "persona": "完整人格档案" }`。

### POST `/api/operator/kols/{kol_id}/persona-details/fill-empty`

读取当前运营自己创建、同一 `kol_id`、状态为 `ready` 的最新人格报告，重新执行有原文证据约束的五项人物事实提取，只写当前为空的事实字段，不触碰 `persona` / `content_plan`，不覆盖任何非空内容。

Response.data：
```json
{
  "kol_id": 43,
  "report_id": 88,
  "filled_fields": ["extra_notes"],
  "preserved_fields": ["background", "experience", "relationships", "unique_story"]
}
```

没有可用报告时返回 `RESOURCE_NOT_FOUND`；提取无可用事实时成功返回空 `filled_fields`。提取成功后即写 OperationLog：`action=fill_kol_persona_facts`，包括没有新字段可填的成功重试；detail 只含达人编号、报告编号和字段名，不记录正文。提取失败写同一报告编号的 `persona_fact_sync_failed`，供详情按最新结果展示当前状态。

---

## 32. 智能体任务配置 V1.6 阶段二（内容分析）

> 基础路径：`/api/admin/agent-tasks/content-analysis`。鉴权：仅已完成改密的 `admin`；`operator` 一律返回 `PERMISSION_DENIED`。全部非流式响应使用标准信封。阶段二通过进程内注入的执行器调用内容分析能力，任务配置模块不读取飞书表、不复制飞书行，也不使用模块 HTTP 回调。

### 32.1 固定任务与状态合同

页面仍只有两个固定任务：

| `task_code` | 名称 | 固定触发说明 | 分析窗口 |
|---|---|---|---|
| `daily` | 每日项目对标内容分析 | 每日北京时间 00:00 | 刚结束业务日及其前 2 日，右端排他的 3 个完整自然日，项目级 |
| `weekly` | 账号人设内容基准更新 | 每周一北京时间 01:00 | 刚结束业务日及其前 29 日，右端排他的 30 个完整自然日，按内容对标账号去重 |

接口统一返回 `not_run`、`queued`、`running`、`success`、`failed`、`cancelled`。其中数据库 `pending` 映射为 `queued`，`processing` 映射为 `running`；`not_run` 独立表示必要配置缺失，不能映射为失败或取消。

每个真正启动的运行有独立 `deadline_at = triggered_at + 12 小时`；`not_run` 未运行记录不生成 `deadline_at`。监控查询会同时校验专属 `tool_code` 与 `input_payload.agent_code='content-analysis'`，只把已超过截止时间且仍为 `pending/processing` 的本智能体记录收敛为 `failed` 并追加 `task_logs` 超时记录；该收敛不触发任何真实 Agent。晚到结果不得把超时失败改回成功。

### GET `/api/admin/agent-tasks/content-analysis/overview`

返回智能体信息、固定任务、当前项目范围统计与最近运行摘要。

Response `data`：

```json
{
  "agent_code": "content-analysis",
  "agent_name": "内容分析",
  "selected_project_count": 2,
  "scope_counts": {"selected_ready": 1, "selected_missing": 1, "unselected": 3},
  "status_summary": {"today_completed": 0, "current_running": 0, "failed_last_7_days": 0},
  "config_updated_by": 1,
  "config_updated_by_name": "管理员",
  "config_updated_at": "2026-09-03T10:00:00+08:00",
  "report_root_ref": "folder-reference",
  "tasks": [
    {"task_code": "daily", "name": "每日项目对标内容分析", "schedule": "每日 00:00", "window_days": 3, "latest_formal_run": null, "next_fixed_run": "2026-09-04T00:00:00+08:00"},
    {"task_code": "weekly", "name": "账号人设内容基准更新", "schedule": "每周一 01:00", "window_days": 30, "latest_formal_run": null, "next_fixed_run": "2026-09-07T01:00:00+08:00"}
  ],
  "report_root_ref_configured": true,
  "delivery_target": "feishu_document"
}
```

### GET `/api/admin/agent-tasks/content-analysis/projects`

分页返回全部入驻成功项目的选择与可运行状态。入驻成功沿用现有全局口径：`persona`、`content_plan` 均非空。查询参数：`page`、`page_size`、`keyword`、`scope_status`；`page_size` 最大 100。

每项包含 `project_id`、`project_name`、`project`（项目与红人展示摘要）、`selected`、`scope_status`、内容对标账号总数/可识别数/关系状态、项目上下文完整性、`missing_required`、`optional_context_missing`、`updated_at`。`scope_status` 仅允许：

- `selected_ready`：已选且必要配置通过；非必需上下文缺失时仍可运行，并在 `optional_context_missing` 说明。
- `selected_missing`：已选但内容对标账号等当前任务必要配置缺失。
- `unselected`：未选择。

内容对标账号只有 `account_type='content'` 且去除首尾空白后的 `sec_uid` 非空才算可识别。数据库关系只用于运行前预检，不代表飞书运行时关系有效。

### GET `/api/admin/agent-tasks/content-analysis/projects/{project_id}/input`

只读返回单个入驻成功项目的输入上下文。`modules` 中每项包含 `key`、`label`、`required`、`status`、`source`、`updated_at`、`value`、`missing_reason`；`status` 为 `ready`、`missing` 或 `input_limited`。其他非必需上下文缺失时还返回具体的 `missing_reasons` 数组，便于逐项说明缺失但不阻断运行。至少覆盖项目基础信息、人格、内容规划、内容对标账号、其他非必需上下文、内容数据、历史分析和正式结果位置。

### GET `/api/admin/agent-tasks/content-analysis/weekly-accounts`

分页返回周任务测试可选择的有效内容对标账号。查询参数：`page`、`page_size`、`keyword`、`project_id`；`page_size` 最大 100。测试候选来自全部入驻成功且必要数据库预检通过的项目，不要求项目已加入持续自动运行范围；可选 `project_id` 只把候选限制到该合格项目。关系必须满足 `account_type='content'` 且去除首尾空白后 `sec_uid` 非空，再按精确、区分大小写的规范化 `sec_uid` 跨项目去重并确定性排序。每项返回 `account_key`、可空展示名和升序去重的 `project_ids`；不得混入未入驻、非内容关系、空账号或其他项目上下文正文。正式自动周调度不调用本接口，仍只汇总已勾选且预检通过的项目。

### PUT `/api/admin/agent-tasks/content-analysis/config`

Request：`{"selected_project_ids": [1, 2], "report_root_ref": "folder-reference"}`。整体替换 `content-analysis` 的当前项目范围，数组去重；`report_root_ref` 是内容分析智能体级共享飞书报告根目录引用，可暂不配置，不按项目保存，也不允许测试运行临时覆盖。全空白引用必须去空白后保存为 `null`，不能视为已配置。任一项目不存在、已软删或未达到现有入驻成功标准时整次请求失败，不做部分保存。首次保存与并发更新按 `agent_code` 原子写入。Response `data` 返回项目 ID 数组、`report_root_ref`、`updated_by`、`updated_by_name`、`updated_at`。成功写 OperationLog：`action=update_agent_task_config`，detail 仅含智能体编码、项目 ID 和 `report_root_ref_configured` 布尔值，严禁记录目录引用原文。

### GET `/api/admin/agent-tasks/content-analysis/runs`

分页返回明确属于 `content-analysis` 的执行记录；查询同时校验专属 `tool_code` 与 `input_payload.agent_code`。查询参数：`page`、`page_size`、`task_code`、`status`、`project_id`、`account_key`、`run_type`、`started_from`、`started_to`；`page_size` 最大 100。每日记录按单项目执行对象，周记录包括账号执行对象及内部的 `weekly_batch_finalize`（周批次收尾）对象；账号对象带本次范围内的 `project_ids`，收尾对象带批次编号、批次数量、已选项目范围和收尾版本。每项至少包含 `execution`、四层结果 `database_precheck` / `feishu_relation` / `internal_result` / `delivery`、`failure_stage`、重试关联及时间字段；`internal_result.internal_result_id` 存在时作为只读内部结构化结果编号返回，`delivery.document_url` 存在且为合法 HTTP/HTTPS 地址时作为飞书结果文档链接返回。当前没有内部结果详情页接口，不得为编号伪造可点击链接。筛选、计数与分页在数据库完成。历史响应中的账号执行对象只返回稳定哈希 `account_key_hash`，不返回原始 `account_key`；原值只允许周账号候选接口用于管理员选择。收尾对象不能冒充账号对象，其失败不改写账号任务状态。

### GET `/api/admin/agent-tasks/content-analysis/runs/{run_id}`

返回单条内容分析记录、`execution` 执行对象、四层结果、脱敏输入快照、原任务/后续重试任务双向关联和按时间升序的 `task_logs`。列表与详情都按相同规则展示只读内部结构化结果编号和飞书文档链接。顶层执行对象、输入快照和结果摘要中的账号标识都只返回同一规则生成的 `account_key_hash`。日志与接口不得暴露完整 `sec_uid`、报告目录引用、项目上下文正文或飞书行。非内容分析任务或载荷智能体归属不匹配时返回 `RESOURCE_NOT_FOUND`。

### POST `/api/admin/agent-tasks/content-analysis/test-runs`

每日测试 Request：`{"task_code": "daily", "project_id": 1, "request_id": "..."}`；周测试 Request：`{"task_code": "weekly", "account_key": "...", "request_id": "..."}`。一次只允许一个执行对象；每日项目和周账号都不要求已加入持续自动运行范围，但必须来自入驻成功且必要数据库预检通过的项目。周测试由全部合格项目关系派生该账号的升序去重 `project_ids`，不得接受客户端传项目列表。`request_id` 去除首尾空白后必须为 1 至 128 个字符；同一 `task_code + run_type=test + request_id` 的串行或并发重复请求必须返回同一 `TaskJob`，且执行器只调用一次，不同请求编号仍创建不同任务。重复请求可各记一条脱敏审计，但不得记录完整账号或目录引用。

测试信封 `run_type='test'`，允许保存带测试隔离标识的平台结构化结果（包括测试域 `Output`），并写入共享报告根目录下确定性的“测试报告”子目录；不得写正式业务投影或正式目录，包括正式日报、项目内容库、跨项目机会和账号基准。测试目录失败不得回退正式目录。测试使用注入的执行器，仓库测试必须使用 fake，禁止真实飞书、模型和生产数据库调用。

共享报告根目录未配置时，周账号候选仍可浏览，但日/周测试均只创建 `not_run` 记录，`database_precheck.reason_code='REPORT_ROOT_REF_MISSING'`，后三层为 `skipped`，不调用执行器。页面必须提前说明该阻断条件。

成功写 OperationLog：`action=create_agent_task_test_run`。

### POST `/api/admin/agent-tasks/content-analysis/runs/{run_id}/retry`

Request：`{"request_id": "..."}`，去除首尾空白后必须为 1 至 128 个字符。只允许对单条 `failed` 内容分析记录手动重试；同一原任务、同一 `request_id` 在并发请求下也幂等返回同一条新任务。新任务继承原执行对象、业务日期、分析窗口、测试/正式投递范围、`internal_result_key` 和 `document_key`，以重试触发时间生成新的 12 小时截止时间。投递失败，或 `failure_stage='timeout'` 且已有内部结果编号和投递身份时，`retry.mode='delivery_only'` 并调用 `redeliver(envelope, internal_result_id, delivery_identity)`；其他失败为 `retry.mode='full'` 并调用 `execute(envelope)`。仅投递调用抛异常、运行资源不可用或返回非法合同结果时，仍保持输入和内部执行层 `skipped`、`failed/delivery` 与两项重试身份，后续不得升级为完整重跑。原记录没有非空报告根目录时拒绝重试，不使用当前新配置替换旧投递上下文；管理员需先配置根目录，再等待新自动任务或另行发起新测试。原记录保持失败。成功写 OperationLog：`action=retry_agent_task_run`，日志不得记录完整账号标识或目录引用。

### 32.2 任务信封 2.0、自动触发与四层结果

进程内执行器协议固定为两个异步方法：`execute(envelope)` 与 `redeliver(envelope, internal_result_id, delivery_identity)`；两者都必须是真正的异步方法，不得增加模块 HTTP 回调。信封 `contract_version='2.0'`，包含：`task_identity`、`task_code`、`run_type`、刚结束的 `business_date`、`analysis_window={start,end,timezone:'Asia/Shanghai',end_exclusive:true}`、`triggered_at`、`deadline_at`、`retry`、`database_precheck`、`delivery_target`、`execution` 与 `idempotency={run_key,internal_result_key,document_key}`。标准构造层必须在序列化前将所有入口的 `triggered_at` 与派生或显式 `deadline_at` 统一转换为 `Asia/Shanghai`；转换不改变时间点、业务日期、3/30 日窗口或 12 小时时长。执行器缺失或不符合完整合同，测试和重试接口统一返回 HTTP 503 标准信封，调度不创建后台任务，禁止回退为阶段一伪执行。

- 日任务 `execution={object_type:'project',project_id}`。
- 周任务 `execution={object_type:'account',account_key,project_ids,weekly_batch_id,batch_size,batch_position}`；正式自动批次只使用已勾选且预检通过项目，同批账号按去除首尾空白后的精确 `sec_uid` 去重并确定性排序，逐个顺序执行，共享一个 `document_key`，单账号失败不阻断后续账号。
- 正式周批全部账号进入终态后，必须再通过同一 `execute(envelope)` 创建并执行一个 `execution={object_type:'weekly_batch_finalize',weekly_batch_id,batch_size,project_ids,finalize_version}` 的周批次收尾任务；`batch_size` 为非负整数，`project_ids` 必须是非空的已选项目编号数组。存在至少一个已选项目但无可计算账号时仍创建 `batch_size=0` 的空批收尾；完全没有已选项目时不创建账号任务、收尾任务或周报。最后一个或全部账号失败时也不能跳过收尾。收尾信封不得携带账号、内容、关系明细或项目长文本；测试运行一次只测一个账号，不创建收尾任务。创建任意正式自动收尾任务前，任务配置服务必须以完整锁名 `content-analysis:weekly-batch:{weekly_batch_id}` 和 PostgreSQL 键 `hashtextextended(:lock_name, 0)` 取得事务级咨询锁；同一事务内重新读取终态快照、确定最新 `finalize_version`、执行幂等检查、创建 `TaskJob` 并提交，提交后释放锁，再调用执行器。该锁与内容分析执行收尾时持有的同键会话级锁共享锁空间，保证旧版执行完成后才允许新版本建账。
- 正式自动任务只有部署开关开启且配置的系统账号存在、启用、未软删且角色为 `admin` 时才运行；否则 tick 关闭失败并记系统配置错误，禁止回退使用其他管理员创建任务。导入应用且开关关闭时不得启动该调度工作。
- 正式日/周自动任务的非空 `run_key` 受数据库部分唯一索引保护；测试与手动重试不占用该唯一范围。
- 正式自动任务的 `internal_result_key` 与默认 `document_key` 保持既有业务日/执行对象逻辑键。测试任务的三键进入确定性测试命名空间，`internal_result_key` 与 `document_key` 均包含规范化 `request_id`，保证同一请求重送稳定、不同请求分离，且不与同对象同业务日的正式任务冲突。手动重试与内部重试继承原任务的内部结果键和文档键。
- 平台内部重试沿用同一 `TaskJob` 与原截止时间；手动重试新建 `TaskJob` 与新截止时间。
- 自动触发先在同一短事务中持久化本批全部账号 `TaskJob`、完整信封与运行键；项目必要配置或共享报告根目录缺失的执行对象直接落为 `not_run`，根目录缺失时不得调用执行器。未勾选项目仍不创建正式自动任务；周固定时点完全没有已选项目时也不得创建空收尾。补偿扫描使用固定到期时点计算业务日期和窗口，但以实际恢复时刻记录触发时间并生成新的 12 小时截止时间，不能补建即过期；进程恢复还须先领取已持久化的正式自动 `pending` 任务，不因当前项目或账号范围变化丢弃原队列。事务提交后，日任务由彼此隔离的受管理后台工作协程领取，周账号任务按 `batch_position` 由单个受管理批次协程顺序领取。全部声明账号进入终态后，再创建并领取收尾任务；有已选项目但零账号时直接按非空项目范围创建零批量收尾。收尾读取同一数据库时必须严格限定内容分析周任务、正式域、批次和账号对象，多次尝试按账号确定性采用最新有效终态；零账号快照必须保持空集合，不得误读其他批次或测试域，最终统计只有成功、无内容、失败且 `pending=0`。领取使用 `pending -> processing` 条件更新；长执行不阻塞调度循环扫描下一固定时点或执行超时收敛。应用关闭时必须取消并等待本模块调度与执行协程，测试和手动重试仍在请求内执行。

周批次收尾不读取飞书输入表、项目上下文或模型，不重跑账号分析，也不重复写项目内容库、跨项目机会或账号基准。它只根据严格限定的终态快照生成新的不可变内部汇总结果，并用该业务窗口既有 `document_key` 创建或更新唯一公司账号基准周报；失败账号只允许携带账号哈希和脱敏原因码。收尾使用包含终态版本的独立 `internal_result_key`，相同终态快照的并发或重复收尾幂等返回同一任务。收尾内部成功但投递失败时，手动重试仍调用 `redeliver` 且复用原结果与文档身份；某账号后续重试改变最终状态时，创建新收尾版本并复用同一周报文档，不重跑其他账号。

`result_summary` 固定保存四层：`database_precheck`、`feishu_relation`、`internal_result`、`delivery`，另有 `failure_stage`。映射必须为：项目必要配置缺失或报告根目录未配置为 `not_run`，对应原因分别保存且后三层跳过；飞书完整读取后无有效关系也为 `not_run`；关系/内容表鉴权、字段或分页失败为 `failed/data_source`；无视频但内部空结果与日报投递成功为 `success`；内部成功但投递失败为 `failed/delivery` 并保留 `internal_result_id`、`delivery_identity`；分析或内部持久化失败分别为 `failed/analysis`、`failed/internal_result`；12 小时超时为 `failed/timeout`。收尾对象的数据库预检通过、飞书关系层固定 `skipped`，内部结果和投递仍按同一严格合同映射。超时后的迟到结果不得覆盖终态或写入正式业务位置。

执行器回传必须通过禁止额外字段的严格四层校验，包括状态闭集、每种状态允许的精确字段、必需身份字段及层间一致性；普通日报或账号任务不得以输入 `skipped` 配合内部和投递成功形成假成功。仅在任务侧已经绑定原内部结果和文档身份的仅投递重试中，才允许保持输入与内部执行层 `skipped`，同时携带两项身份供连续补投。非法、缺字段、额外字段或互相矛盾的回传安全收敛为 `failed/analysis` 与 `EXECUTOR_CONTRACT_INVALID`，不得保存外来额外数据或形成假成功。测试与手动重试在调用长耗时执行器前先提交任务、`processing` 状态、开始日志和管理员 `OperationLog`；自动任务则先整批提交为持久队列，再在独立短事务中条件领取并提交 `processing` 与开始日志。执行结果统一在后续事务中按旧状态条件更新，使任务可被其他会话观察和超时收敛。自动调度不写管理员 `OperationLog`。
---

## 33. 内容分析项目库（M2 Sprint28）

接口前缀：`/api/tools/content-analysis/library`。鉴权：已改密的 `operator` / `admin`。所有响应使用标准信封。

### GET `/api/tools/content-analysis/library`

按项目、主分类和可用状态分页读取内容分析项目库。`project_id`、`category`（`persona` / `qianchuan`）必填；`availability` 为 `enabled` / `disabled`，默认 `enabled`；`page` 默认 1，`page_size` 默认 20、最大 100。不得跨项目返回记录。

Response `data`：

```json
{
  "items": [{
    "id": 1,
    "project_id": 1001,
    "kol_reference_id": 9,
    "title": "候选标题",
    "category": "qianchuan",
    "ingestion_source": "analysis",
    "platform": "unknown",
    "source_platform_note": "来源平台未知",
    "account_id": "匿名账号编号",
    "platform_content_id": "匿名作品编号",
    "external_url": null,
    "analysis": {},
    "project_assessment": {},
    "latest_metrics": {},
    "confidence": "medium",
    "priority": 1,
    "opening_status": "unannotated",
    "opening_fragment": null,
    "opening_unavailable_reason": null,
    "availability": "enabled"
  }],
  "pagination": {"page": 1, "page_size": 20, "total": 1}
}
```

### POST `/api/tools/content-analysis/library`

运营把一条千川正文人工加入明确项目。Request：

```json
{
  "project_id": 1001,
  "title": "人工候选标题",
  "transcript": "人工候选正文",
  "platform_content_id": null,
  "external_url": null
}
```

`transcript` 必填且必须是可用正文；`title` 可选，缺失时使用“人工千川正文”作为展示标题；两个稳定身份可选。新记录保存为
`ingestion_source=manual`、`opening_status=unannotated`，等待后续日报补标。两个外部稳定身份都缺失时，系统使用已持久化项目库记录编号形成仅供内部历史关联的稳定键，不改变接口返回，也不得阻断当前项目或其他项目日报。
同项目已有相同作品编号或外部链接时合并到原记录，只补齐缺失身份并把当前来源标为人工，
不覆盖原标题、正文或开头标注。稳定身份去重查询在项目库事务锁内执行，并发的人工/自动写入合并到同一条记录且保持人工来源。写 `OperationLog`；框架参数校验错误也使用标准响应信封。

### PATCH `/api/tools/content-analysis/library/{item_id}/availability`

Request：`{"project_id": 1001, "availability": "disabled"}`。只能操作同一 `project_id` 的候选；写 `OperationLog`，不物理删除内容。停用/恢复路径在首次读取候选前取得与自动项目库刷新相同的事务锁，重建跨项目机会时必须使用最新分析快照。停用记录继续占用作品编号/外部链接稳定身份，避免自动重复新建；后续日报再次采集到同一内容时可刷新分析与互动快照，但不得自动恢复可用状态、标记为在库可复用/跨项目或进入跨项目机会，即使其他可用内容共享同一方法键也不能提升该停用记录；必须由人工恢复后才重新参与复用。

### PATCH `/api/tools/content-analysis/library/{item_id}/opening`

只允许人工补标千川候选。可用时提交 `status=available` 与能在原转写中逐字定位的 `fragment`；不可用时提交 `status=unavailable` 与非空 `unavailable_reason`。开头结果与正文候选保存在同一项目记录，并写 `OperationLog`。人工路径与日报自动刷新/自动补标使用同一事务锁，自动结果不得在旧快照上覆盖已提交的人工标注。

### 进程内执行合同

任务配置模块不通过 HTTP 调用内容分析，而只调用同一后端进程内的 `execute(envelope)` 与 `redeliver(envelope, internal_result_id, delivery_identity)`。调用方不直接操作内容分析领域仓库。`execute` 可完整运行或完整重试；`redeliver` 只读取已保存结果并重试飞书投递，不重复模型分析或业务入库。每日项目和周度账号的人工仅投递重试必须先核验本次重试任务保存的 `request_id`、来源失败任务、既有内部结果、原投递目标与正式/测试域；测试域还必须精确绑定原 `test_subdirectory`。一次人工补投再次投递失败时，后续补投沿任务配置保存的来源链逐跳核验上述身份并定位同一个不可变内部结果，不生成新分析结果；周账号补投后的周批收尾同样读取该原结果。仅投递调用即使在信封/参数解析、运行资源创建或原任务来源校验阶段失败，四层结果也必须保持 `failure_stage=delivery`、飞书关系/内容层 `skipped`、内部结果 `skipped`、投递 `failed`，不得伪装成内部分析失败并诱导完整重试。完整执行在信封解析、运行资源、系统配置或重试来源核验阶段尚未读取飞书就失败时，飞书关系/内容层也必须为 `skipped`，不得报成已就绪。

信封运行类型只接受 `auto`、`test`、`manual_retry`、`retry` 和任务配置内部调度使用的 `internal_retry`。重试必须保留并校验 `retry.mode`，只接受 `full`（完整重试）或 `delivery_only`（仅投递重试）；后者只能调用 `redeliver`，不得进入 `execute`。`internal_retry` 映射为内部重试并保留原任务编号、业务窗口和截止时间，触发来源记为系统；执行侧还必须以当前 `TaskJob` 已保存输入核对任务类型、执行对象、正式/测试域、测试子目录和三层幂等键，任一漂移按 `EXECUTOR_CONTRACT_INVALID` 失败关闭。`manual_retry` 与 `retry` 是同义的用户触发类型；每日项目与周度账号的 `full` 人工重试必须同时绑定当前重试 `TaskJob` 和失败原任务，继承原执行对象、业务窗口、正式/测试域、测试子目录、内部结果键和文档键，禁止把测试结果提升到正式域或移到另一测试目录。`retry_of_task_id`、`mode` 和 `request_id` 按运行类型严格闭合：自动任务三项均为空；测试任务只带非空 `request_id`；内部重试只带当前任务编号和合法模式；人工重试必须带正整数来源任务编号、合法模式和非空文本 `request_id`。其他运行类型一律按合同错误拒绝。根对象、任务身份、分析窗口、数据库预检、交付目标、重试、幂等键和三种执行对象均使用精确字段闭集；任一未知字段，或把其他执行分支的字段、内容明细、关系明细、项目长文本混入信封，均失败关闭。

任务配置最终注册长生命周期的内容分析运行入口时，必须使用资源提供器：应用通过统一 `Settings` 从标准 `.env` 或进程环境读取内容分析配置并显式注入提供器；每次 `execute` 或 `redeliver` 调用独占一个数据库会话和一个有明确关闭责任的飞书网络客户端，调用结束统一回滚未提交事务并关闭资源。单次调用内的数据读取、模型日志、持久化和投递共享同一个数据库会话；不同并发任务不得共享会话。配置或资源创建失败返回脱敏的四层失败结果，不在构造或导入阶段联网。

正式日报目录由内容分析执行侧使用数据库项目名称和稳定项目编号派生为
`项目日报/{project_id}-{project_name}`；测试运行固定进入 `测试报告`，不得回退正式目录。
周任务有两种执行对象：账号实例 `account` 只更新 `account:{sec_uid}` 区块；全部账号实例进入终态后，`weekly_batch_finalize` 收尾实例通过同一个 `execute(envelope)` 入口读取本批次最新账号终态，只更新唯一 `batch-summary` 公司汇总区块。飞书文档键和业务区块键分别使用哈希派生的稳定标记，并且只把正文第一、第二行的专用标记视为文档与区块身份；任务信封中的 `document_key` 禁止换行。账号文本或业务键即使包含类似标记也不能冒充其他文档/公司汇总区块。收尾不读取飞书输入、项目上下文或模型，不写项目库、跨项目机会和账号基准。账号重试改变终态后使用新的分析/结果幂等键再次收尾，生成新不可变汇总结果，并复用同一个周报 `document_key` 更新原文档；相同收尾请求保持幂等。收尾投递失败仍只调用 `redeliver`。

收尾信封使用 `task_code=weekly`、`execution.object_type=weekly_batch_finalize`，携带 `weekly_batch_id`、非负整数 `batch_size`、非空且排序去重的 `project_ids`，以及非空的终态快照版本 `finalize_version`；不得携带内容、关系明细或项目长文本。该版本必须进入不可变结果和任务来源回执，完整内部重试也必须与原任务精确一致。至少有一个已选项目、但本周没有账号实例时，`batch_size=0`，仍生成待处理/成功/无内容/失败/可计算账号均为 0 的空周报；没有已选项目时，任务配置侧不创建账号任务、收尾任务或正式周报。收尾实例只允许正式隔离域；测试运行仍只能执行一个账号实例，不能构造测试域收尾。投递失败必须使用 `delivery_only + redeliver`，并核验原任务确为同批次、同 `finalize_version` 的投递失败收尾且内部结果编号一致；来源或版本无效按 `EXECUTOR_CONTRACT_INVALID` 失败关闭，使调用侧保持仅投递重试语义。非投递阶段失败的已有收尾任务可使用 `manual_retry + full + execute` 完整重试，但执行侧必须同时绑定本次人工重试 `TaskJob` 和来源失败任务，并显式拒绝把既有 `delivery_only` 失败升级为完整执行。自动收尾执行、系统内部或人工触发的完整收尾重试以及补投，均先取得周批次锁，再在任何结果读取或投递前以同批次最新自动收尾任务的 `finalize_version` 为权威版本，不按重试编号或版本字符串大小判断；过期自动任务不得读取旧结果或覆盖新周报。人工重试使用新的运行键，但继续绑定原内部结果键和文档键；仅投递可复用已保存结果，不因运行键变化误拒绝。收尾四层结果必须把 `feishu_relation` 标为 `skipped`，内部结果和投递仍使用既有封闭状态。执行侧对同一分析键先使用受截止时间约束的进程内单飞锁，再与同一周批次、报告目录各级前缀和文档键一样使用 PostgreSQL 会话级 advisory lock；同一任务的嵌套分析/投递锁复用一个独立连接，非阻塞轮询受任务截止时间约束，并按连接池容量预留业务连接。锁持续到完整分析/收尾投递结束，不会被业务会话中途提交释放，从而避免连接池饥饿、多进程重复分析、过期汇总覆盖、重复建目录或重复建文档。正式项目库的自动刷新、跨项目机会首次查询/写入以及人工开头补标在读取候选前取同一公司级事务锁，保证全局方法键唯一且人工开头不与最新自动分析字段互相覆盖。日报模型分析结束后必须在同一项目库事务锁内重新读取当前可用状态与待补标集合，再冻结结构化结果并持久化；模型运行期间新增后又停用的同身份内容不得留在当次新增候选，待自动补标内容若被停用只跳过该条，不得回滚整份日报。

收尾仅依据每个最新账号终态所绑定的内部结果编号，读取并校验对应 `content_analysis_results` 与 `outputs.content_json`：任务、账号、项目范围、业务窗口、正式/测试域和结果状态必须一致。公司汇总保留成功、无内容、失败三类任务计数，另以已保存基准 `status=available` 且样本数大于 0 计算“可计算账号数”。成功或无内容账号栏目展示稳定账号号、终态、关联项目、样本数、平均点赞、中位数、最高/最低点赞、基准更新时间和不可计算原因；失败账号只展示 `sha256` 账号哈希、关联项目、终态时间和脱敏原因码，不把原始稳定账号号写入结构化周批结果或飞书周报。成功任务若没有可计算的人设样本，仍计入成功或无内容任务计数，但不计入可计算账号。任一内部结果身份或基准结构不一致时收尾失败关闭，不重读飞书或调用模型。
