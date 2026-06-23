# MCN Information System Platform · M1 Base Database 说明

> 文档定位：本文件定义 M1 系统底座数据库表、字段含义、写入时机、权限过滤和删除策略。本文不展开 persona-writer 的业务 Prompt 和迁移逻辑。

---

## 1. 数据库选型

M1 阶段使用 PostgreSQL。

```text
开发环境：本地 PostgreSQL
测试环境：测试服务器 PostgreSQL
正式环境：后续上线前再评估 RDS
```

M1 不使用 MongoDB、不使用 MySQL、不使用独立数据仓库。

---

## 2. 表清单

### 2.1 M1 核心表

| 表名 | 用途 |
|---|---|
| `users` | 用户账号、角色、密码、状态、强制改密、在线状态、软删 |
| `workspace_tools` | 内容工作台工具配置、工具状态、工具阈值配置 |
| `kols` | 红人基础信息 + 人格档案 + 签约人员；M1 地基期可先建表预留 |
| `task_jobs` | 工具任务主表，一次工具使用会话对应一个任务 |
| `task_logs` | 任务执行日志，记录每个步骤的状态和错误 |
| `outputs` | 工具最终产出，例如生成的脚本、报告、文案 |
| `files` | 文件记录，例如 Word 导出文件、附件、OSS key |
| `operation_logs` | 用户操作日志，例如登录、创建账号、导出、上下线工具 |
| `external_service_logs` | 外部服务调用日志，例如 AI / TikHub / OSS / ASR |

### 2.2 M1 地基支撑表

| 表名 | 用途 |
|---|---|
| `tool_sessions` | 工具会话 / 草稿持久化；M1 基层阶段先建表预留 |
| `service_credentials` | 外部服务密钥池；AI / TikHub / ASR 多 key 轮换，OSS 可单独配置 |
| `credentials` | AI Key 池（Sprint 4 新增）；yunwu / siliconflow / glm 并发调度 |
| `ai_models` | 可用 AI 模型配置（Sprint 4 新增） |
| `ai_call_logs` | AI 调用明细日志（Sprint 4 新增） |

---

## 3. 通用字段规范

所有业务表建议包含：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | BIGSERIAL / UUID | 主键 |
| `created_at` | TIMESTAMPTZ | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 更新时间 |
| `deleted_at` | TIMESTAMPTZ NULL | 软删除时间，非所有表必需 |

时间统一使用 `TIMESTAMPTZ`。

---

## 4. users 用户表

### 4.1 用途

用于系统账号、角色、密码、状态、首次改密、在线判定和软删除。

### 4.2 建议字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `id` | BIGSERIAL | 是 | 用户 ID |
| `username` | VARCHAR(64) | 是 | 登录账号，唯一 |
| `real_name` | VARCHAR(64) | 是 | 真实姓名 / 显示名称 |
| `password_hash` | TEXT | 是 | 加密后的密码 |
| `role` | VARCHAR(32) | 是 | `admin` / `operator` |
| `status` | VARCHAR(32) | 是 | `enabled` / `disabled` |
| `password_changed_at` | TIMESTAMPTZ | 否 | 为空表示首次登录必须改密 |
| `token_version` | INT | 是 | Token 版本，用于登出或重置密码后失效 |
| `last_login_at` | TIMESTAMPTZ | 否 | 最近登录时间 |
| `last_active_at` | TIMESTAMPTZ | 否 | 最近活跃时间，用于在线判定 |
| `created_by` | BIGINT | 否 | 创建人，管理员 ID |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 否 | 软删除时间 |

### 4.3 枚举

```text
role: admin / operator
status: enabled / disabled
```

### 4.4 写入时机

| 场景 | 写入 / 更新 |
|---|---|
| 管理员创建账号 | 新增用户，`password_changed_at = null` |
| 用户首次改密 | 更新 `password_hash`、`password_changed_at`、`token_version` |
| 登录成功 | 更新 `last_login_at`、`last_active_at` |
| 用户发起请求 | 可定期更新 `last_active_at` |
| 重置密码 | 更新 `password_hash`、`password_changed_at = null`、`token_version + 1` |
| 停用账号 | 更新 `status = disabled` |
| 删除账号 | 写入 `deleted_at`，不物理删除 |

---

## 5. workspace_tools 工具表

### 5.1 用途

用于内容工作台工具卡片、工具状态、工具说明、工具阈值配置。

### 5.2 建议字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `id` | BIGSERIAL | 是 | 工具 ID |
| `tool_code` | VARCHAR(64) | 是 | 工具唯一编码，例如 `persona-writer` |
| `tool_name` | VARCHAR(128) | 是 | 工具名称 |
| `category` | VARCHAR(64) | 否 | 工具分类 |
| `description` | TEXT | 否 | 工具说明 |
| `status` | VARCHAR(32) | 是 | `online` / `dev` / `offline` / `disabled` |
| `tags` | JSONB | 否 | 标签数组 |
| `config` | JSONB | 否 | 工具配置，例如点赞阈值、超时时间 |
| `sort_order` | INT | 是 | 排序 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间 |

### 5.3 推荐初始数据

```json
[
  {
    "tool_code": "persona-writer",
    "tool_name": "人设脚本仿写",
    "category": "脚本创作",
    "status": "online"
  },
  {
    "tool_code": "benchmark",
    "tool_name": "对标分析助手",
    "category": "选题分析",
    "status": "dev"
  },
  {
    "tool_code": "qianchuan",
    "tool_name": "千川工具组",
    "category": "投放",
    "status": "dev"
  },
  {
    "tool_code": "review",
    "tool_name": "复盘工具组",
    "category": "数据复盘",
    "status": "dev"
  },
  {
    "tool_code": "subtitle",
    "tool_name": "字幕提取",
    "category": "素材处理",
    "status": "dev"
  }
]
```

---

## 6. kols 红人表

### 6.1 用途

M1 基层阶段先建表预留，供后续 persona-writer 选择达人使用。

### 6.2 建议字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `id` | BIGSERIAL | 是 | 红人 ID |
| `name` | VARCHAR(128) | 是 | 红人名称 |
| `category` | VARCHAR(64) | 否 | 所属类目 |
| `platform` | VARCHAR(32) | 否 | 平台，例如 `douyin` |
| `external_id` | VARCHAR(128) | 否 | 平台外部 ID |
| `douyin_id` | VARCHAR(128) | 否 | 抖音号 |
| `avatar_url` | TEXT | 否 | 头像地址 |
| `persona` | TEXT | 否 | 人设描述 |
| `content_plan` | TEXT | 否 | 内容规划 |
| `style_notes` | TEXT | 否 | 风格说明 |
| `owner_id` | BIGINT | 否 | 签约 / 负责运营人员，关联 `users.id` |
| `status` | VARCHAR(32) | 是 | `signed` / `pending_renewal` / `terminated`；新建时 ORM 默认 `signed`（kol.py:27）。各 writer 下拉只展示 `signed` 和 `pending_renewal` |
| `created_by` | BIGINT | 否 | 创建人 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 否 | 软删除时间 |

### 6.3 索引

| 索引名 | 类型 | 说明 |
|---|---|---|
| `idx_kols_douyin_id_unique` | UNIQUE（部分） | `WHERE deleted_at IS NULL AND douyin_id IS NOT NULL AND douyin_id <> ''`，防止重复添加红人（migration 032） |
| `idx_kols_sec_uid_unique` | UNIQUE（部分） | `WHERE deleted_at IS NULL AND sec_uid IS NOT NULL AND sec_uid <> ''`，同上（migration 032） |

> 参照 `idx_users_username`（001_init.sql）的部分唯一索引模式；软删记录不参与唯一性约束。

---

## 7. task_jobs 任务主表

### 7.1 用途

记录一次工具调用或一次工具会话。无论同步还是异步，均先创建 `task_jobs`。

### 7.2 建议字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `id` | BIGSERIAL | 是 | 任务 ID |
| `task_no` | VARCHAR(64) | 是 | 展示编号，例如 `#20844` |
| `tool_code` | VARCHAR(64) | 是 | 工具编码 |
| `tool_name` | VARCHAR(128) | 是 | 工具名称冗余字段 |
| `status` | VARCHAR(32) | 是 | `pending` / `processing` / `success` / `failed` / `cancelled` |
| `input_payload` | JSONB | 否 | 输入参数脱敏后记录 |
| `result_summary` | JSONB | 否 | 结果摘要 |
| `error_code` | VARCHAR(128) | 否 | 错误码 |
| `error_message` | TEXT | 否 | 错误信息 |
| `session_id` | BIGINT | 否 | 关联 `tool_sessions.id` |
| `output_id` | BIGINT | 否 | 关联 `outputs.id` |
| `created_by` | BIGINT | 是 | 发起人 |
| `started_at` | TIMESTAMPTZ | 否 | 开始时间 |
| `finished_at` | TIMESTAMPTZ | 否 | 完成时间 |
| `duration_ms` | INT | 否 | 执行耗时 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间 |

### 7.3 状态流转

```text
pending → processing → success
pending → processing → failed
pending → cancelled
processing → cancelled
```

不允许：

```text
success → processing
failed → processing
cancelled → success
```

### 7.4 权限过滤

| 角色 | 可见范围 |
|---|---|
| `admin` | 全部任务 |
| `operator` | `created_by = 当前用户` |

---

## 8. task_logs 任务日志表

### 8.1 用途

记录任务执行过程中的关键节点和错误，方便任务详情页展示与排查。

### 8.2 建议字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `id` | BIGSERIAL | 是 | 日志 ID |
| `task_id` | BIGINT | 是 | 关联 `task_jobs.id` |
| `step_code` | VARCHAR(64) | 是 | 步骤编码，例如 `create_task`、`call_ai` |
| `step_name` | VARCHAR(128) | 是 | 步骤名称 |
| `status` | VARCHAR(32) | 是 | `success` / `failed` / `skipped` |
| `message` | TEXT | 否 | 展示信息 |
| `payload` | JSONB | 否 | 扩展数据，敏感信息必须脱敏 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |

---

## 9. outputs 产出表

### 9.1 用途

记录工具最终产出。M1 中无论哪个工具产生可复用结果，都必须写入 `outputs`。

### 9.2 建议字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `id` | BIGSERIAL | 是 | 产出 ID |
| `title` | VARCHAR(255) | 是 | 产出标题 |
| `tool_code` | VARCHAR(64) | 是 | 工具编码 |
| `tool_name` | VARCHAR(128) | 是 | 工具名称冗余字段 |
| `task_id` | BIGINT | 否 | 关联任务 |
| `content` | TEXT | 否 | 产出正文 |
| `content_json` | JSONB | 否 | 结构化产出 |
| `word_count` | INT | 否 | 字数 |
| `file_id` | BIGINT | 否 | 默认导出文件 ID |
| `created_by` | BIGINT | 是 | 创建人 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 否 | 软删除时间 |

### 9.3 权限过滤

| 角色 | 可见范围 |
|---|---|
| `admin` | 全部产出 |
| `operator` | `created_by = 当前用户` |

---

## 10. files 文件表

### 10.1 用途

记录导出文件、附件、OSS key、文件大小、过期策略。文件不落应用服务器本地盘。

### 10.2 建议字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `id` | BIGSERIAL | 是 | 文件 ID |
| `file_name` | VARCHAR(255) | 是 | 文件名 |
| `file_type` | VARCHAR(64) | 是 | `docx` / `pdf` / `image` / `video` / `attachment` |
| `mime_type` | VARCHAR(128) | 否 | MIME 类型 |
| `size_bytes` | BIGINT | 否 | 文件大小 |
| `storage_provider` | VARCHAR(32) | 是 | 默认 `oss` |
| `bucket` | VARCHAR(128) | 否 | OSS bucket |
| `object_key` | TEXT | 是 | OSS key |
| `url_expires_policy` | VARCHAR(64) | 否 | 下载 URL 过期策略 |
| `retention_policy` | VARCHAR(64) | 否 | 文件生命周期策略 |
| `tool_code` | VARCHAR(64) | 否 | 来源工具 |
| `task_id` | BIGINT | 否 | 关联任务 |
| `output_id` | BIGINT | 否 | 关联产出 |
| `created_by` | BIGINT | 是 | 创建人 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `deleted_at` | TIMESTAMPTZ | 否 | 软删除时间 |

### 10.3 存储规则

1. Word、图片、视频、附件均使用 OSS。
2. 后端只保存 `object_key`，下载时生成临时签名 URL。
3. 视频禁止落应用服务器本地盘。
4. 测试桶建议 30 天自动删除。
5. 生产桶后续按低频 / 归档策略分层。

---

## 11. operation_logs 操作日志表

### 11.1 用途

记录用户关键操作，支撑管理员审计。

### 11.2 建议字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `id` | BIGSERIAL | 是 | 日志 ID |
| `user_id` | BIGINT | 否 | 操作人 |
| `user_name` | VARCHAR(128) | 否 | 操作人名称冗余 |
| `action` | VARCHAR(128) | 是 | 行为编码 |
| `target_type` | VARCHAR(64) | 否 | 对象类型 |
| `target_id` | VARCHAR(128) | 否 | 对象 ID |
| `detail` | JSONB | 否 | 操作详情，敏感信息脱敏 |
| `ip_address` | VARCHAR(64) | 否 | 来源 IP |
| `user_agent` | TEXT | 否 | 浏览器信息 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |

### 11.3 必须记录的操作

```text
login
logout
change_password
create_user
update_user
reset_password
disable_user
enable_user
delete_user
update_tool_config
create_task
save_output
download_file
create_credential
disable_credential
enable_credential
```

---

## 12. external_service_logs 外部调用日志表

### 12.1 用途

记录 AI / TikHub / OSS / ASR 等外部服务调用情况，用于排查、成本核算、配额分析。

### 12.2 建议字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `id` | BIGSERIAL | 是 | 日志 ID |
| `service` | VARCHAR(64) | 是 | `ai` / `tikhub` / `oss` / `asr` |
| `provider` | VARCHAR(64) | 否 | 供应商，例如 `openai`、`aliyun` |
| `endpoint` | VARCHAR(255) | 否 | 调用端点 |
| `model` | VARCHAR(128) | 否 | AI 模型 |
| `tool_code` | VARCHAR(64) | 否 | 来源工具 |
| `task_id` | BIGINT | 否 | 关联任务 |
| `credential_id` | BIGINT | 否 | 使用的密钥 ID |
| `tokens_in` | INT | 否 | 输入 Token |
| `tokens_out` | INT | 否 | 输出 Token |
| `credits` | NUMERIC | 否 | TikHub 等积分消耗 |
| `audio_seconds` | INT | 否 | ASR 音频秒数 |
| `duration_ms` | INT | 否 | 调用耗时 |
| `status` | VARCHAR(32) | 是 | `success` / `failed` / `timeout` / `skipped` |
| `error_code` | VARCHAR(128) | 否 | 错误码 |
| `error_message` | TEXT | 否 | 错误信息 |
| `request_hash` | VARCHAR(128) | 否 | 请求摘要，不保存敏感明文 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |

---

## 13. tool_sessions 工具会话表

### 13.1 用途

保存工具使用过程中的 step、上下文、草稿和多轮消息，防止刷新页面丢失状态。

### 13.2 M1 基层阶段要求

基层阶段只需要建表和预留 API 结构，不需要实现 persona-writer 的完整会话逻辑。

### 13.3 建议字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `id` | BIGSERIAL | 是 | 会话 ID |
| `tool_code` | VARCHAR(64) | 是 | 工具编码 |
| `current_step` | VARCHAR(64) | 否 | 当前步骤 |
| `context` | JSONB | 否 | 会话上下文 |
| `drafts` | JSONB | 否 | 草稿版本 |
| `messages` | JSONB | 否 | 多轮修改消息 |
| `status` | VARCHAR(32) | 是 | `draft` / `processing` / `completed` / `cancelled` |
| `created_by` | BIGINT | 是 | 创建人 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间 |

---

## 14. service_credentials 密钥池表

### 14.1 用途

用于 AI / TikHub / ASR 多密钥轮换和冷却管理。禁止明文回显密钥。

### 14.2 建议字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `id` | BIGSERIAL | 是 | 密钥 ID |
| `provider` | VARCHAR(64) | 是 | `ai` / `tikhub` / `asr` |
| `label` | VARCHAR(128) | 是 | 密钥名称 |
| `secret_enc` | TEXT | 是 | 加密后的密钥 |
| `secret_tail` | VARCHAR(16) | 是 | 密钥后四位，用于展示 |
| `status` | VARCHAR(32) | 是 | `enabled` / `disabled` / `cooldown` |
| `weight` | INT | 是 | 调度权重 |
| `quota_limit` | BIGINT | 否 | 配额上限 |
| `quota_used` | BIGINT | 否 | 已用配额 |
| `fail_count` | INT | 是 | 连续失败次数 |
| `cooldown_until` | TIMESTAMPTZ | 否 | 冷却结束时间 |
| `created_by` | BIGINT | 否 | 创建人 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间 |

---

## 15. 索引建议

```sql
CREATE UNIQUE INDEX idx_users_username ON users(username) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_role_status ON users(role, status);

CREATE UNIQUE INDEX idx_workspace_tools_code ON workspace_tools(tool_code);
CREATE INDEX idx_workspace_tools_status ON workspace_tools(status);

CREATE INDEX idx_task_jobs_created_by ON task_jobs(created_by);
CREATE INDEX idx_task_jobs_tool_status ON task_jobs(tool_code, status);
CREATE INDEX idx_task_jobs_created_at ON task_jobs(created_at DESC);

CREATE INDEX idx_task_logs_task_id ON task_logs(task_id);

CREATE INDEX idx_outputs_created_by ON outputs(created_by);
CREATE INDEX idx_outputs_tool_code ON outputs(tool_code);
CREATE INDEX idx_outputs_created_at ON outputs(created_at DESC);

CREATE INDEX idx_files_output_id ON files(output_id);
CREATE INDEX idx_files_task_id ON files(task_id);
CREATE INDEX idx_files_created_by ON files(created_by);

CREATE INDEX idx_operation_logs_user_id ON operation_logs(user_id);
CREATE INDEX idx_operation_logs_action ON operation_logs(action);
CREATE INDEX idx_operation_logs_created_at ON operation_logs(created_at DESC);

CREATE INDEX idx_external_logs_service ON external_service_logs(service);
CREATE INDEX idx_external_logs_task_id ON external_service_logs(task_id);
CREATE INDEX idx_external_logs_created_at ON external_service_logs(created_at DESC);
```

---

## 15. credentials AI Key 池表

### 15.1 用途

Sprint 4 新增。存储云雾 / 硅基流动 / GLM 等 AI 服务商的 API Key，支持多 Key 并发调度与排队管理。与 `service_credentials` 不同，本表面向 AI 并发控制场景，通过 `active_requests` / `max_concurrent` 实现 DB 级原子锁定（`FOR UPDATE SKIP LOCKED`）。

### 15.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `id` | BIGSERIAL | 是 | Key ID |
| `provider` | VARCHAR(64) | 是 | 服务商：`yunwu` / `siliconflow` / `glm` |
| `label` | VARCHAR(128) | 否 | 名称标签 |
| `api_key` | TEXT | 是 | 明文 API Key（管理端内部使用，不对外暴露） |
| `base_url` | VARCHAR(512) | 否 | 接口地址，为空时使用服务商默认地址 |
| `status` | VARCHAR(32) | 是 | `active` / `disabled` |
| `active_requests` | INT | 是 | 当前并发请求数，默认 0 |
| `max_concurrent` | INT | 是 | 最大并发上限，默认 5 |
| `max_users` | INT | 是 | 最大用户数，默认 10 |
| `last_tested_at` | TIMESTAMPTZ | 否 | 最近一次连通性测试时间 |
| `last_latency_ms` | INT | 否 | 最近一次测试延迟（ms） |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间 |

### 15.3 并发控制逻辑

```sql
-- 原子锁定：选取并发未满的 Key
UPDATE credentials
SET active_requests = active_requests + 1, updated_at = NOW()
WHERE id = (
    SELECT id FROM credentials
    WHERE provider = :provider
      AND status = 'active'
      AND active_requests < max_concurrent
    ORDER BY active_requests ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
RETURNING id, api_key, COALESCE(base_url, :fallback);

-- 请求结束后释放
UPDATE credentials
SET active_requests = GREATEST(active_requests - 1, 0), updated_at = NOW()
WHERE id = :id;
```

无可用槽位时，请求进入 `asyncio.Queue` 等待，超过 30 秒抛出 `RuntimeError`。

### 15.4 写入时机

| 场景 | 写入 / 更新 |
|---|---|
| 管理员添加 Key | 新增记录 |
| 请求开始 | `active_requests + 1` |
| 请求结束（成功/失败） | `active_requests - 1` |
| Key 连通性测试 | 更新 `last_tested_at` / `last_latency_ms` |

---

## 16. ai_models 模型配置表

### 16.1 用途

Sprint 4 新增。管理可调用的 AI 模型配置。`model_id` 与 `ai_call_logs.model_id` 关联，用于统计各模型调用量。

### 16.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `id` | BIGSERIAL | 是 | 模型 ID |
| `name` | VARCHAR(128) | 是 | 模型名称（展示用） |
| `provider` | VARCHAR(64) | 是 | 服务商：`yunwu` / `siliconflow` / `glm` |
| `model_id` | VARCHAR(128) | 是 | 模型 ID（传给 API），全局唯一 |
| `status` | VARCHAR(32) | 是 | `active` / `disabled` |
| `last_tested_at` | TIMESTAMPTZ | 否 | 最近一次测试时间 |
| `last_latency_ms` | INT | 否 | 最近一次测试延迟（ms） |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间 |

### 16.3 枚举

```text
provider: yunwu / siliconflow / glm
status: active / disabled
```

---

## 17. ai_call_logs AI 调用明细表

### 17.1 用途

Sprint 4 新增。记录每次 AI 调用的完整明细，用于统计分析、成本核算和故障排查。每次调用 `yunwu_adapter.chat()` 均写入，无论成功与否。

### 17.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `id` | BIGSERIAL | 是 | 日志 ID |
| `user_id` | BIGINT | 否 | 调用用户，关联 `users.id` |
| `feature` | VARCHAR(128) | 否 | 功能标识，如 `persona-writer` / `model_test` |
| `model_id` | VARCHAR(128) | 否 | 使用的模型 ID（冗余存储，模型删除后日志仍可查） |
| `credential_id` | BIGINT | 否 | 使用的 Key，关联 `credentials.id` |
| `input_tokens` | INT | 否 | 输入 Token 数 |
| `output_tokens` | INT | 否 | 输出 Token 数 |
| `latency_ms` | INT | 否 | 调用耗时（ms） |
| `status` | VARCHAR(32) | 是 | `success` / `error` |
| `error_message` | TEXT | 否 | 错误信息（最多 500 字符） |
| `created_at` | TIMESTAMPTZ | 是 | 调用时间 |

### 17.3 索引

```sql
CREATE INDEX idx_ai_call_logs_created_at   ON ai_call_logs(created_at DESC);
CREATE INDEX idx_ai_call_logs_credential   ON ai_call_logs(credential_id);
CREATE INDEX idx_ai_call_logs_model_id     ON ai_call_logs(model_id);
CREATE INDEX idx_ai_call_logs_user_feature ON ai_call_logs(user_id, feature);
```

### 17.4 写入时机

每次 `yunwu_adapter.chat()` 调用结束后（`finally` 块），无论成功或失败均写入，确保日志完整性。

---

---

## 18. AI 开发硬性要求

1. 不允许直接修改数据库结构而不更新本文档。
2. 不允许明文保存密码、Token、外部服务密钥。
3. 不允许物理删除用户、产出、文件等关键数据。
4. 不允许 operator 查询其他用户任务和产出。
5. 不允许文件落应用服务器本地盘。
6. 不允许外部服务调用不写 `external_service_logs`。
7. 不允许关键操作不写 `operation_logs`。
8. 不允许任务型操作跳过 `task_jobs`。
9. 不允许最终产出不写 `outputs`。
10. 不允许导出文件不写 `files`。

