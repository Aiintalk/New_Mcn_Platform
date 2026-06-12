# MCN Information System Platform · M2 Base Database 说明

> 文档定位：本文件定义 M2 阶段新增的数据库表。M1 表定义见 `docs/base/M1/MCN_M1_Base_Database.md`。
> M2 包含 Sprint 1（kol-intake 4 张表）、Sprint 3（persona 1 张表 + TikHub 2 张表），运营首页复用 M1 已有表，无新增。

---

## 1. M2 新增表清单

| 表名 | 用途 | Sprint |
|------|------|--------|
| `kol_intake_questions` | 24 道题目配置（AI 对话引导提纲） | Sprint 1 |
| `kol_intake_configs` | AI 配置（对话 bridge + 报告生成两条记录） | Sprint 1 |
| `kol_intake_links` | 运营生成的一次性分享链接 | Sprint 1 |
| `kol_intake_submissions` | 博主对话记录 + 生成报告 | Sprint 1 |
| `persona_reports` | 人格定位报告（AI 生成的人格档案+内容规划） | Sprint 3 |
| `tikhub_credentials` | TikHub 独立 Key 池 | Sprint 3 |
| `tikhub_call_logs` | TikHub 调用日志 | Sprint 3 |

---

## 2. kol_intake_questions 题目表

### 2.1 用途

存储 24 道 AI 对话引导题目，作为 AI 面试官的访谈提纲。每次 `/chat` 调用时后端实时从此表读取并注入 `system_prompt`。

### 2.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | SERIAL | 是 | 题目 ID |
| `order_num` | INTEGER | 是 | 排序序号（1-24） |
| `category` | VARCHAR(50) | 是 | 分组标题（基本信息/生活与家庭/野心评估等） |
| `question_text` | TEXT | 是 | 题目内容 |
| `question_type` | VARCHAR(20) | 是 | `text`（单条回答）/ `multi_collect`（需收集多条） |
| `max_items` | INTEGER | 否 | `multi_collect` 时有效，最多收集条数 |
| `is_required` | BOOLEAN | 是 | 必填题（AI 必须覆盖） |
| `is_active` | BOOLEAN | 是 | 是否启用，软删除用 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间 |

### 2.3 枚举

```text
question_type: text / multi_collect
```

### 2.4 说明

- 初始 24 道题目通过 migration seed 写入
- 管理员可在后台调整 `order_num`、`is_active` 和内容
- 不支持物理删除，通过 `is_active=false` 软删

---

## 3. kol_intake_configs AI 配置表

### 3.1 用途

存储两条 AI 配置：对话模型配置（`conversation_bridge`）和报告生成模型配置（`report_generation`）。管理员在后台「入驻问卷 → AI 配置」中维护。

### 3.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | SERIAL | 是 | 配置 ID |
| `config_key` | VARCHAR(50) | 是 | 唯一键：`conversation_bridge` / `report_generation` |
| `ai_model_id` | INTEGER | 否 | 关联 `ai_models.id`，NULL 表示未配置 |
| `system_prompt` | TEXT | 否 | AI 角色设定提示词 |
| `is_active` | BOOLEAN | 是 | 是否启用 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间 |

### 3.3 枚举

```text
config_key: conversation_bridge / report_generation
```

### 3.4 初始数据

两条记录在 migration 时插入，`system_prompt` 初始为 NULL，由管理员在后台填写。

| config_key | 推荐模型 | 说明 |
|------------|----------|------|
| `conversation_bridge` | haiku | 对话引导，`max_tokens=300`，低延迟 |
| `report_generation` | opus | 报告生成，extended thinking budget=6000 |

---

## 4. kol_intake_links 分享链接表

### 4.1 用途

运营为每个博主生成一次性链接，链接含有效期。公开接口通过 token 校验链接状态。

### 4.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | SERIAL | 是 | 链接 ID |
| `token` | VARCHAR(64) | 是 | URL token（`secrets.token_urlsafe(32)`），全局唯一 |
| `operator_id` | INTEGER | 是 | 生成链接的运营，关联 `users.id` |
| `kol_name` | VARCHAR(200) | 否 | 运营预填的博主姓名 |
| `expires_at` | TIMESTAMPTZ | 是 | 链接有效期 |
| `used_at` | TIMESTAMPTZ | 否 | 博主首次访问时间 |
| `submitted_at` | TIMESTAMPTZ | 否 | 博主提交（生成报告）时间 |
| `is_active` | BOOLEAN | 是 | 是否可用（下架只影响新建，不影响已有链接） |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |

### 4.3 写入时机

| 场景 | 写入 / 更新 |
|------|------------|
| 运营生成链接 | 新增记录 |
| 博主首次打开链接 | 写入 `used_at` |
| 博主提交对话 | 写入 `submitted_at` |

### 4.4 索引建议

```sql
CREATE UNIQUE INDEX idx_kol_intake_links_token ON kol_intake_links(token);
CREATE INDEX idx_kol_intake_links_operator ON kol_intake_links(operator_id);
CREATE INDEX idx_kol_intake_links_expires ON kol_intake_links(expires_at);
```

---

## 5. kol_intake_submissions 提交记录表

### 5.1 用途

存储博主的完整对话历史和 AI 生成的评估报告。一个链接只能提交一次（UNIQUE link_id）。

### 5.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | SERIAL | 是 | 提交 ID |
| `link_id` | INTEGER | 是 | 关联 `kol_intake_links.id`，唯一约束 |
| `messages` | JSONB | 是 | 完整对话历史，格式：`[{role, content, ts}]` |
| `ai_report` | TEXT | 否 | AI 生成的报告正文（Markdown） |
| `ai_report_raw` | JSONB | 否 | AI 原始响应（含 usage 等元数据） |
| `report_status` | VARCHAR(20) | 是 | `pending` / `generating` / `ready` / `failed` |
| `report_generated_at` | TIMESTAMPTZ | 否 | 报告生成完成时间 |
| `docx_path` | VARCHAR(500) | 否 | 本地存储路径：`storage/intake_reports/{id}.docx` |
| `pdf_path` | VARCHAR(500) | 否 | 本地存储路径：`storage/intake_reports/{id}.pdf` |
| `kol_downloaded_at` | TIMESTAMPTZ | 否 | 博主首次下载时间 |
| `operator_downloaded_at` | TIMESTAMPTZ | 否 | 运营首次下载时间 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间 |

### 5.3 report_status 状态流转

```text
pending → generating → ready
pending → generating → failed
```

不允许：
```text
ready → generating
failed → generating（需重新提交链接）
```

### 5.4 文件存储说明

- M2 阶段文件存本地，不走 OSS
- 路径：`backend/storage/intake_reports/{id}.docx` / `{id}.pdf`
- 目录需在部署时预创建，权限 755
- M3+ 迁移 OSS 时需更新本字段为 object_key

### 5.5 索引建议

```sql
CREATE UNIQUE INDEX idx_kol_intake_submissions_link ON kol_intake_submissions(link_id);
CREATE INDEX idx_kol_intake_submissions_status ON kol_intake_submissions(report_status);
CREATE INDEX idx_kol_intake_submissions_created ON kol_intake_submissions(created_at DESC);
```

---

## 6. M2 数据迁移脚本

Migration 文件位于 `backend/alembic/versions/` 或 `backend/migrations/`，Sprint 1 需包含：

1. 创建 4 张表
2. 插入 `kol_intake_configs` 初始两条记录
3. 插入 24 道 `kol_intake_questions` 初始题目
4. 创建索引

---

## 7. AI 开发硬性要求

1. 不允许直接修改数据库结构而不更新本文档。
2. `kol_intake_submissions.link_id` 有唯一约束，重复提交需在应用层拦截，返回 409。
3. 不允许物理删除 `kol_intake_submissions` 记录。
4. `messages` 字段保存完整对话，前端维护，后端只追加/覆盖，不截断。
5. 报告文件只存路径，不存文件内容至数据库。
6. 不允许 operator 查看其他 operator 的 links 和 submissions。

---

## 8. persona_reports 人格定位报告表（Sprint 3）

### 8.1 用途

存储人格定位功能生成的完整报告，包括人格档案和内容规划两部分内容，以及 AI 原始输出、导出文件路径等。

### 8.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | BIGSERIAL | 是 | 报告 ID |
| `operator_id` | BIGINT | 是 | 创建者，关联 `users.id` |
| `douyin_text` | TEXT | 否 | 用户输入的抖音分享文本 |
| `douyin_nickname` | VARCHAR(200) | 否 | TikHub 解析出的昵称 |
| `douyin_id` | TEXT | 否 | 抖音号或分享链接 |
| `sec_user_id` | VARCHAR(200) | 否 | TikHub sec_user_id |
| `top_videos` | JSONB | 否 | TikHub 拉取的 TOP 视频数据 |
| `file_content` | TEXT | 否 | 上传文件解析后的文本 |
| `kol_submission_id` | BIGINT | 否 | 关联 `kol_intake_submissions.id`（KOL 导入时） |
| `additional_info` | TEXT | 否 | 用户补充的额外信息 |
| `benchmark_input` | JSONB | 否 | 对标达人输入（profile + plan） |
| `status` | VARCHAR(20) | 是 | `generating` / `ready` / `failed` |
| `raw_output` | TEXT | 否 | AI 原始输出（===SPLIT=== 分隔） |
| `profile_result` | TEXT | 否 | 人格档案部分 |
| `plan_result` | TEXT | 否 | 内容规划部分 |
| `influencer_name` | VARCHAR(200) | 否 | 从 AI 输出提取的达人名字 |
| `profile_docx_path` | VARCHAR(500) | 否 | 人格档案 Word 文件路径 |
| `plan_docx_path` | VARCHAR(500) | 否 | 内容规划 Word 文件路径 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 否 | 软删除时间 |

### 8.3 status 状态流转

```text
generating → ready
generating → failed
```

### 8.4 索引建议

```sql
CREATE INDEX idx_persona_reports_operator ON persona_reports(operator_id);
CREATE INDEX idx_persona_reports_status ON persona_reports(status);
CREATE INDEX idx_persona_reports_created ON persona_reports(created_at DESC);
```

---

## 9. tikhub_credentials TikHub 独立 Key 池（Sprint 3）

### 9.1 用途

存储 TikHub API 的独立 Key 池，与 AI 的 `credentials` 表分离，支持多 Key 轮询、测试、启用/停用。

### 9.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | BIGSERIAL | 是 | 凭证 ID |
| `provider` | VARCHAR(64) | 是 | 固定 `tikhub` |
| `label` | VARCHAR(128) | 否 | 标签（如 tikhub-main） |
| `api_key` | TEXT | 是 | TikHub API Key |
| `base_url` | VARCHAR(500) | 否 | TikHub API 地址 |
| `status` | VARCHAR(20) | 是 | `active` / `disabled` |
| `weight` | INTEGER | 是 | 权重（默认 10） |
| `max_concurrent` | INTEGER | 是 | 最大并发（默认 5） |
| `active_requests` | INTEGER | 是 | 当前活跃请求数 |
| `last_tested_at` | TIMESTAMPTZ | 否 | 最后测试时间 |
| `last_latency_ms` | INTEGER | 否 | 最后测试延迟（ms） |
| `last_error` | TEXT | 否 | 最后测试错误信息 |
| `remark` | TEXT | 否 | 备注 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间 |

---

## 10. tikhub_call_logs TikHub 调用日志（Sprint 3）

### 10.1 用途

记录每次 TikHub API 调用的详细信息，用于统计分析和用户排行。

### 10.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | BIGSERIAL | 是 | 日志 ID |
| `credential_id` | BIGINT | 否 | 关联 `tikhub_credentials.id` |
| `user_id` | BIGINT | 否 | 调用用户（系统调用时为 NULL） |
| `endpoint` | VARCHAR(200) | 是 | TikHub 端点路径 |
| `params_summary` | TEXT | 否 | 请求参数摘要 |
| `latency_ms` | INTEGER | 否 | 响应延迟（ms） |
| `status` | VARCHAR(20) | 是 | `success` / `error` |
| `error_message` | TEXT | 否 | 错误信息 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |

### 10.3 索引建议

```sql
CREATE INDEX idx_tikhub_call_logs_credential ON tikhub_call_logs(credential_id);
CREATE INDEX idx_tikhub_call_logs_user ON tikhub_call_logs(user_id);
CREATE INDEX idx_tikhub_call_logs_endpoint ON tikhub_call_logs(endpoint);
CREATE INDEX idx_tikhub_call_logs_created ON tikhub_call_logs(created_at DESC);
```

---

## 11. M2 数据迁移脚本

| 迁移文件 | 内容 | Sprint |
|----------|------|--------|
| `006_kol_intake.sql` | kol-intake 4 张表 + 初始数据 | Sprint 1 |
| `007_kol_intake_operator_sessions.sql` | 运营直发会话表 | Sprint 1 |
| `008_schema_catchup.sql` | 补全 001~007 缺失的表和字段 | 补丁 |
| `009_persona_positioning.sql` | persona_reports 表 | Sprint 3 |
| `010_tikhub_credentials.sql` | tikhub_credentials 表 | Sprint 3 |
| `011_tikhub_call_logs.sql` | tikhub_call_logs 表 | Sprint 3 |
| `012_migrate_tikhub_to_dedicated_pool.sql` | 迁移 TikHub Key 到独立池 | Sprint 3 |
