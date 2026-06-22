# MCN Information System Platform · M1 Base API 接口规范

> 文档定位：本文件只定义 M1 系统底座 API，不展开 `persona-writer` 的具体业务生成、AI Prompt、TikHub 解析、Word 导出实现。所有前端、后端、测试、代码审核均以本文件作为接口契约。

---

## 1. 基本原则

### 1.1 API 前缀

所有后端接口统一以 `/api` 开头。

```text
/api/health
/api/auth/login
/api/admin/users
/api/workspace/tools
/api/tasks
/api/outputs
/api/files
/api/admin/logs
```

禁止出现未登记的临时路径，例如：

```text
/persona/generate
/api/user/list
/api/admin/userList
/api/tool/getAll
```

### 1.2 字段命名

接口请求与响应字段统一使用 `snake_case`。

```json
{
  "user_id": 1,
  "tool_code": "persona-writer",
  "created_at": "2026-06-05T10:00:00+08:00"
}
```

前端页面内部如需使用 `camelCase`，必须在 API 层统一转换，不能污染接口契约。

### 1.3 时间格式

所有时间字段统一使用 ISO 8601 字符串。

```text
2026-06-05T10:00:00+08:00
```

### 1.4 鉴权方式

除 `/api/health`、`/api/version`、`/api/auth/login` 外，所有接口默认需要 JWT。

```http
Authorization: Bearer <access_token>
```

### 1.5 角色

M1 只定义两个角色：

| 角色 | 说明 |
|---|---|
| `admin` | 管理员，可进入 `/admin/*`，可管理用户、工具、任务、产出、日志、服务配置 |
| `operator` | 运营人员，可进入运营端，使用内容工作台，只能查看自己的任务和产出 |

---

## 2. 统一响应结构

### 2.1 成功响应

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {}
}
```

### 2.2 失败响应

```json
{
  "success": false,
  "code": "AUTH_INVALID_PASSWORD",
  "message": "账号或密码错误",
  "data": null
}
```

### 2.3 分页响应

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "items": [],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 86,
      "total_pages": 5
    }
  }
}
```

### 2.4 分页参数

| 参数 | 类型 | 默认值 | 说明 |
|---|---:|---:|---|
| `page` | number | 1 | 当前页，从 1 开始 |
| `page_size` | number | 20 | 每页数量，只允许 10 / 20 / 50 |
| `keyword` | string | 空 | 搜索关键词 |
| `status` | string | 空 | 状态筛选 |

---

## 3. 统一错误码

| 错误码 | HTTP 状态码 | 说明 |
|---|---:|---|
| `OK` | 200 | 成功 |
| `VALIDATION_ERROR` | 400 | 参数校验失败 |
| `AUTH_INVALID_PASSWORD` | 401 | 账号或密码错误 |
| `AUTH_TOKEN_MISSING` | 401 | 缺少 Token |
| `AUTH_TOKEN_EXPIRED` | 401 | Token 已过期 |
| `AUTH_USER_DISABLED` | 403 | 账号已停用 |
| `AUTH_FORCE_CHANGE_PASSWORD` | 403 | 需要先修改初始密码 |
| `PERMISSION_DENIED` | 403 | 无权限访问 |
| `RESOURCE_NOT_FOUND` | 404 | 资源不存在 |
| `USER_NOT_FOUND` | 404 | 用户不存在 |
| `USERNAME_ALREADY_EXISTS` | 409 | 用户名已存在 |
| `TOOL_NOT_FOUND` | 404 | 工具不存在 |
| `TOOL_NOT_ONLINE` | 403 | 工具未上线 |
| `TASK_NOT_FOUND` | 404 | 任务不存在 |
| `OUTPUT_NOT_FOUND` | 404 | 产出不存在 |
| `FILE_NOT_FOUND` | 404 | 文件不存在 |
| `EXTERNAL_SERVICE_ERROR` | 502 | 外部服务调用失败 |
| `INTERNAL_ERROR` | 500 | 服务内部错误 |

---

## 4. 系统 API

### 4.1 健康检查

```http
GET /api/health
```

权限：公开。

Response:

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "status": "ok",
    "service": "mcn-api",
    "database": "ok",
    "time": "2026-06-05T10:00:00+08:00"
  }
}
```

### 4.2 版本信息

```http
GET /api/version
```

权限：公开。

Response:

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "service": "mcn-api",
    "version": "0.1.0",
    "stage": "m1-base"
  }
}
```

---

## 5. 认证 API

### 5.1 登录

```http
POST /api/auth/login
```

权限：公开。

Request:

```json
{
  "username": "admin",
  "password": "Admin@123456"
}
```

Response:

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "access_token": "jwt_token_here",
    "token_type": "bearer",
    "expires_in": 86400,
    "must_change_password": false,
    "user": {
      "id": 1,
      "username": "admin",
      "real_name": "陈管理",
      "role": "admin",
      "status": "enabled"
    }
  }
}
```

写入规则：

| 表 | 写入动作 |
|---|---|
| `users` | 更新 `last_login_at`、`last_active_at` |
| `operation_logs` | 写入 `login` 行为 |

### 5.2 当前用户信息

```http
GET /api/auth/me
```

权限：登录用户。

Response:

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "id": 2,
    "username": "li.yun",
    "real_name": "李运营",
    "role": "operator",
    "status": "enabled",
    "must_change_password": false,
    "last_login_at": "2026-06-05T09:30:00+08:00"
  }
}
```

### 5.3 修改密码

```http
POST /api/auth/change-password
```

权限：登录用户。首次登录用户必须先完成该接口。

Request:

```json
{
  "old_password": "Init@123456",
  "new_password": "New@123456",
  "confirm_password": "New@123456"
}
```

Response:

```json
{
  "success": true,
  "code": "OK",
  "message": "密码修改成功，请重新登录",
  "data": null
}
```

写入规则：

| 表 | 写入动作 |
|---|---|
| `users` | 更新 `password_hash`、`password_changed_at`、`token_version` |
| `operation_logs` | 写入 `change_password` 行为 |

### 5.4 退出登录

```http
POST /api/auth/logout
```

权限：登录用户。

Response:

```json
{
  "success": true,
  "code": "OK",
  "message": "已退出登录",
  "data": null
}
```

写入规则：

| 表 | 写入动作 |
|---|---|
| `users` | 可选：递增 `token_version`，使当前 Token 失效 |
| `operation_logs` | 写入 `logout` 行为 |

---

## 6. 管理员用户 API

### 6.1 用户列表

```http
GET /api/admin/users?page=1&page_size=20&keyword=&status=&role=
```

权限：`admin`。

Response:

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "items": [
      {
        "id": 1,
        "username": "admin",
        "real_name": "陈管理",
        "role": "admin",
        "status": "enabled",
        "last_login_at": "2026-06-05T09:30:00+08:00",
        "last_active_at": "2026-06-05T09:45:00+08:00",
        "created_at": "2026-06-01T10:00:00+08:00"
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

### 6.2 创建用户

```http
POST /api/admin/users
```

权限：`admin`。

Request:

```json
{
  "username": "li.yun",
  "real_name": "李运营",
  "role": "operator"
}
```

Response:

```json
{
  "success": true,
  "code": "OK",
  "message": "账号创建成功",
  "data": {
    "id": 2,
    "username": "li.yun",
    "real_name": "李运营",
    "role": "operator",
    "status": "enabled",
    "initial_password": "X7mA9q2L"
  }
}
```

规则：

- 初始密码由后端随机生成。
- `password_changed_at = null`，用于首次登录强制改密。
- `initial_password` 只在创建成功响应中返回一次，不入库明文。

写入规则：

| 表 | 写入动作 |
|---|---|
| `users` | 创建用户记录 |
| `operation_logs` | 写入 `create_user` 行为 |

### 6.3 用户详情

```http
GET /api/admin/users/{user_id}
```

权限：`admin`。

### 6.4 更新用户

```http
PATCH /api/admin/users/{user_id}
```

权限：`admin`。

Request:

```json
{
  "real_name": "李运营",
  "role": "operator",
  "status": "enabled"
}
```

### 6.5 重置密码

```http
POST /api/admin/users/{user_id}/reset-password
```

权限：`admin`。

Response:

```json
{
  "success": true,
  "code": "OK",
  "message": "密码已重置",
  "data": {
    "initial_password": "P8qX2m7A"
  }
}
```

规则：

- 重置后 `password_changed_at = null`。
- 用户再次登录必须修改密码。
- 随机密码只返回一次。

### 6.6 启用用户

```http
POST /api/admin/users/{user_id}/enable
```

权限：`admin`。

### 6.7 停用用户

```http
POST /api/admin/users/{user_id}/disable
```

权限：`admin`。

### 6.8 删除用户

```http
DELETE /api/admin/users/{user_id}
```

权限：`admin`。

规则：软删除，写入 `deleted_at`，不物理删除。

---

## 7. 内容工作台 API

### 7.1 工具列表

```http
GET /api/workspace/tools
```

权限：登录用户。

Response:

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "items": [
      {
        "tool_code": "persona-writer",
        "tool_name": "人设脚本仿写",
        "category": "脚本创作",
        "status": "online",
        "description": "选择达人 → 对标验证 → 智能仿写 → 导出文档",
        "tags": ["智能生成", "视频解析", "文档导出"]
      },
      {
        "tool_code": "benchmark",
        "tool_name": "对标分析助手",
        "category": "选题分析",
        "status": "dev",
        "description": "拆解对标视频结构与爆点节奏",
        "tags": ["智能生成"]
      }
    ]
  }
}
```

### 7.2 工具详情

```http
GET /api/workspace/tools/{tool_code}
```

权限：登录用户。

规则：

- `online` 工具允许进入。
- `dev` / `offline` / `disabled` 工具前端展示但不可进入。

### 7.3 管理员更新工具配置

```http
PATCH /api/admin/workspace/tools/{tool_code}
```

权限：`admin`。

Request:

```json
{
  "status": "online",
  "description": "选择达人 → 对标验证 → 智能仿写 → 导出文档",
  "config": {
    "like_threshold": 100000,
    "opening_eval_timeout_seconds": 15
  }
}
```

写入规则：

| 表 | 写入动作 |
|---|---|
| `workspace_tools` | 更新工具状态和配置 |
| `operation_logs` | 写入 `update_tool_config` 行为 |

---

## 8. 任务 API

### 8.1 我的任务

```http
GET /api/tasks?page=1&page_size=20&status=&tool_code=&keyword=
```

权限：登录用户。

规则：

- `operator` 只能返回 `created_by = 当前用户` 的任务。
- `admin` 调用该接口也默认返回自己的任务；查看全部任务使用 `/api/admin/tasks`。

Response:

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "items": [
      {
        "id": 20844,
        "task_no": "#20844",
        "tool_code": "persona-writer",
        "tool_name": "人设脚本仿写",
        "status": "success",
        "created_by": 2,
        "created_by_name": "李运营",
        "started_at": "2026-06-05T09:30:00+08:00",
        "finished_at": "2026-06-05T09:31:00+08:00",
        "duration_ms": 42000,
        "output_id": 5521,
        "error_message": null
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

### 8.2 任务详情

```http
GET /api/tasks/{task_id}
```

权限：登录用户。

规则：

- `operator` 只能查看自己的任务。
- `admin` 可查看任意任务。

Response 必须包含 `task_logs`。

### 8.3 管理员全部任务

```http
GET /api/admin/tasks?page=1&page_size=20&status=&tool_code=&user_id=&keyword=
```

权限：`admin`。

### 8.4 管理员任务详情

```http
GET /api/admin/tasks/{task_id}
```

权限：`admin`。

---

## 9. 产出 API

### 9.1 我的产出

```http
GET /api/outputs?page=1&page_size=20&tool_code=&keyword=
```

权限：登录用户。

规则：

- `operator` 只能返回自己的产出。
- `admin` 调用该接口也默认返回自己的产出；查看全部产出使用 `/api/admin/outputs`。

Response:

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "items": [
      {
        "id": 5521,
        "title": "夏小棠 · 早C晚A避坑指南",
        "tool_code": "persona-writer",
        "tool_name": "人设脚本仿写",
        "task_id": 20844,
        "created_by": 2,
        "created_by_name": "李运营",
        "word_count": 612,
        "file_id": 9001,
        "created_at": "2026-06-05T09:31:00+08:00"
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

### 9.2 产出详情

```http
GET /api/outputs/{output_id}
```

权限：登录用户。

规则：

- `operator` 只能查看自己的产出。
- `admin` 可查看任意产出。

### 9.3 管理员全部产出

```http
GET /api/admin/outputs?page=1&page_size=20&tool_code=&user_id=&keyword=
```

权限：`admin`。

### 9.4 管理员产出详情

```http
GET /api/admin/outputs/{output_id}
```

权限：`admin`。

---

## 10. 文件 API

### 10.1 文件详情

```http
GET /api/files/{file_id}
```

权限：登录用户。

规则：

- `operator` 只能查看自己产出关联的文件。
- `admin` 可查看全部文件。

### 10.2 获取下载地址

```http
POST /api/files/{file_id}/download-url
```

权限：登录用户。

Response:

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "file_id": 9001,
    "file_name": "夏小棠_早C晚A避坑指南.docx",
    "download_url": "https://oss-signed-url.example.com/xxx",
    "expires_in": 600
  }
}
```

写入规则：

| 表 | 写入动作 |
|---|---|
| `operation_logs` | 写入 `download_file` 行为 |

### 10.3 管理员文件列表

```http
GET /api/admin/files?page=1&page_size=20&file_type=&tool_code=&user_id=
```

权限：`admin`。

---

## 11. 日志 API

### 11.1 外部调用日志

```http
GET /api/admin/logs/external?page=1&page_size=20&service=&status=&tool_code=&keyword=
```

权限：`admin`。

Response 字段必须包含：

```json
{
  "id": 1,
  "service": "ai",
  "endpoint": "chat.completions",
  "model": "gpt-4o",
  "tool_code": "persona-writer",
  "task_id": 20844,
  "tokens_in": 1200,
  "tokens_out": 800,
  "credits": null,
  "audio_seconds": null,
  "duration_ms": 1800,
  "status": "success",
  "error_message": null,
  "created_at": "2026-06-05T09:30:00+08:00"
}
```

### 11.2 操作日志

```http
GET /api/admin/logs/operation?page=1&page_size=20&action=&user_id=&keyword=
```

权限：`admin`。

Response 字段必须包含：

```json
{
  "id": 1,
  "user_id": 1,
  "user_name": "陈管理",
  "action": "create_user",
  "target_type": "user",
  "target_id": "2",
  "ip_address": "127.0.0.1",
  "user_agent": "Chrome",
  "created_at": "2026-06-05T09:30:00+08:00"
}
```

---

## 12. 服务配置 API

### 12.1 密钥池列表

```http
GET /api/admin/config/credentials?provider=
```

权限：`admin`。

返回时禁止返回明文密钥，只允许返回 `secret_tail`。

### 12.2 新增密钥

```http
POST /api/admin/config/credentials
```

权限：`admin`。

Request:

```json
{
  "provider": "ai",
  "label": "openai-main",
  "secret": "sk-xxxx",
  "weight": 1,
  "quota_limit": 1000000
}
```

写入规则：

| 表 | 写入动作 |
|---|---|
| `service_credentials` | 加密存储密钥 |
| `operation_logs` | 写入 `create_credential` 行为 |

### 12.3 启用 / 停用密钥

```http
POST /api/admin/config/credentials/{credential_id}/enable
POST /api/admin/config/credentials/{credential_id}/disable
```

权限：`admin`。

### 12.4 更新密钥

```http
PATCH /api/admin/config/credentials/{credential_id}
```

权限：`admin`。

Request（所有字段可选，提供 `api_key` 时同步轮换 `secret_enc` + `secret_tail`）：

```json
{
  "label": "new-label",
  "status": "enabled|disabled",
  "weight": 10,
  "quota_limit": 1000000,
  "config": { "access_key_id": "LTAI...", "bucket": "...", "endpoint": "..." },
  "api_key": "new-secret"
}
```

写入规则：

| 表 | 写入动作 |
|---|---|
| `service_credentials` | 更新指定字段；提供 `api_key` 时覆盖 `secret_enc` 和 `secret_tail` |
| `operation_logs` | 写入 `update_credential` 行为 |

### 12.5 删除密钥

```http
DELETE /api/admin/config/credentials/{credential_id}
```

权限：`admin`。

> 当前为**物理删除**（一票否决级债务，计划后续改为软删）。

写入规则：`operation_logs` 写入 `delete_credential` 行为。

### 12.6 测试密钥连通性

```http
POST /api/admin/config/credentials/{credential_id}/test
```

权限：`admin`。当前仅支持 `provider="oss"`。

业务校验：

- 凭证不存在 → `RESOURCE_NOT_FOUND`
- `provider != "oss"` → `VALIDATION_ERROR`
- `config` 缺 `access_key_id` / `bucket` / `endpoint` → `VALIDATION_ERROR`

Response `data`（业务失败也走 `success` 信封，状态在 `data.status`）：

```json
// 成功
{
  "status": "ok",
  "latency_ms": 123,
  "bucket": "xxx",
  "location": "oss-cn-hangzhou",
  "creation_date": "2024-01-01"
}
// 失败
{
  "status": "error",
  "latency_ms": 123,
  "error": "<异常信息前 200 字符>"
}
```

实现：复用 `app.adapters.oss._make_bucket` 构造 bucket，调用 `bucket.get_bucket_info()` 做最轻量验证。不持久化测试结果（只写 `operation_logs`）。

写入规则：`operation_logs` 写入 `test_credential` 行为（无论成功失败都记，detail 含 status + latency_ms）。

---

## 13. AI 管理 API

> 权限：所有接口均需 `admin` 角色。

### 13.1 Key 列表

```http
GET /api/admin/ai/keys
```

Response `data.items[]` 字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | number | Key ID |
| `provider` | string | 服务商：`yunwu` / `siliconflow` / `glm` |
| `label` | string\|null | 名称标签 |
| `api_key` | string | 完整 Key（管理端不脱敏） |
| `base_url` | string\|null | 接口地址 |
| `status` | string | `active` / `disabled` |
| `active_requests` | number | 当前并发请求数 |
| `max_concurrent` | number | 最大并发上限 |
| `max_users` | number | 最大用户数 |
| `last_tested_at` | string\|null | 最近测试时间（ISO 8601） |
| `last_latency_ms` | number\|null | 最近测试延迟（ms） |
| `today_calls` | number | 今日调用次数 |
| `total_calls` | number | 历史总调用次数 |
| `created_at` | string | 创建时间 |
| `updated_at` | string | 更新时间 |

### 13.2 添加 Key

```http
POST /api/admin/ai/keys
```

Request:

```json
{
  "provider": "yunwu",
  "label": "云雾主账号",
  "api_key": "sk-xxxx",
  "base_url": null,
  "max_concurrent": 5,
  "max_users": 10
}
```

规则：`base_url` 为 `null` 时自动填充各服务商默认地址。

### 13.3 编辑 Key

```http
PATCH /api/admin/ai/keys/{id}
```

Request（所有字段可选）：

```json
{
  "label": "新名称",
  "api_key": "sk-new",
  "base_url": "https://yunwu.ai/v1",
  "status": "disabled",
  "max_concurrent": 10,
  "max_users": 20
}
```

### 13.4 删除 Key

```http
DELETE /api/admin/ai/keys/{id}
```

物理删除，不可恢复。

### 13.5 Key 连通性测试

```http
POST /api/admin/ai/keys/{id}/test
```

真实调用服务商 `GET /v1/models`，15 秒超时，不消耗 Token。测试成功后写回 `last_tested_at` 和 `last_latency_ms`。

Response:

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "status": "ok",
    "latency_ms": 320
  }
}
```

失败时：

```json
{
  "data": {
    "status": "error",
    "latency_ms": 15012,
    "error": "401 Unauthorized"
  }
}
```

---

### 13.6 模型列表

```http
GET /api/admin/ai/models
```

Response `data.items[]` 字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | number | 模型 ID |
| `name` | string | 模型名称（展示用） |
| `provider` | string | 服务商：`yunwu` / `siliconflow` / `glm` |
| `model_id` | string | 模型 ID（传给 API 使用） |
| `status` | string | `active` / `disabled` |
| `last_tested_at` | string\|null | 最近测试时间 |
| `last_latency_ms` | number\|null | 最近测试延迟（ms） |
| `total_calls` | number | 历史总调用次数 |
| `total_tokens` | number | 历史总 Token 数 |
| `created_at` | string | 创建时间 |
| `updated_at` | string | 更新时间 |

### 13.7 添加模型

```http
POST /api/admin/ai/models
```

Request:

```json
{
  "name": "Claude Haiku 4.5",
  "provider": "yunwu",
  "model_id": "claude-haiku-4-5-20251001"
}
```

规则：`model_id` 全局唯一，重复时返回 `VALIDATION_ERROR`。

### 13.8 编辑模型

```http
PATCH /api/admin/ai/models/{id}
```

Request（所有字段可选）：

```json
{
  "name": "新名称",
  "provider": "siliconflow",
  "status": "disabled"
}
```

### 13.9 删除模型

```http
DELETE /api/admin/ai/models/{id}
```

物理删除。已有 `ai_call_logs` 记录中的 `model_id` 字段不受影响（字符串冗余存储）。

### 13.10 模型可用性测试

```http
POST /api/admin/ai/models/{id}/test
```

按模型的 `provider` 自动选取对应服务商的可用 Key，发送 `"hi"` + `max_tokens=1` 验证链路可用性。成功和失败均写回 `last_tested_at` / `last_latency_ms`。

Response 格式同 13.5。

---

### 13.11 AI 使用统计

```http
GET /api/admin/ai/stats?start_date=&end_date=&provider=&status=
```

参数：

| 参数 | 类型 | 说明 |
|---|---|---|
| `start_date` | string | 起始日期 `YYYYMMDD`，不传默认今日 |
| `end_date` | string | 结束日期 `YYYYMMDD`，不传默认明日 |
| `provider` | string | 服务商筛选（过滤 Key 汇总） |
| `status` | string | Key 状态筛选 |

Response:

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "summary": {
      "total_keys": 3,
      "healthy_keys": 2,
      "model_count": 5,
      "total_tokens": 128000,
      "avg_latency_ms": 820.5,
      "service_status": "healthy",
      "queue_length": 0,
      "current_active": 1,
      "total_capacity": 15
    },
    "by_model": [
      {
        "model_id": "claude-haiku-4-5-20251001",
        "name": "Claude Haiku 4.5",
        "provider": "yunwu",
        "requests": 240,
        "tokens": 96000,
        "percentage": 0.75
      }
    ],
    "token_trend": [
      {
        "date": "2026-06-07",
        "input_tokens": 80000,
        "output_tokens": 48000
      }
    ]
  }
}
```

`service_status` 枚举：

| 值 | 说明 |
|---|---|
| `healthy` | 正常 |
| `degraded` | 降级（可用 Key 不足 50%） |
| `overloaded` | 超负载（有请求排队或已达满载） |
| `unavailable` | 不可用（无 active Key 或容量为 0） |

---

## 14. 状态枚举

### 13.1 用户状态

```text
enabled   启用
disabled  停用
deleted   已删除
```

### 13.2 工具状态

```text
online    已上线
dev       开发中
offline   已下线
disabled  已停用
```

### 13.3 任务状态

```text
pending     待开始
processing  进行中
success     成功
failed      失败
cancelled   已取消
```

### 13.4 外部服务状态

```text
success   成功
failed    失败
timeout   超时
skipped   跳过
```

### 13.5 密钥状态

```text
enabled   启用
disabled  停用
cooldown  冷却中
```


---

## 15. AI 开发硬性要求

1. 不允许前端自行假设接口路径。
2. 不允许后端临时新增未登记接口。
3. 不允许混用 `camelCase` 与 `snake_case`。
4. 不允许返回结构脱离 `success / code / message / data`。
5. 不允许只返回字符串错误。
6. 不允许前端直接调用 AI / TikHub / OSS / ASR。
7. 不允许 operator 查询全部任务、全部产出。
8. 不允许真实删除用户、任务、产出和文件记录，M1 默认软删除或归档。
9. 不允许在 API 响应中返回明文密钥。
10. API 修改必须先修改本文档，再改代码。

