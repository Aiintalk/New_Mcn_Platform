# MCN Information System Platform · M2 Base Database 说明

> 文档定位：本文件定义 M2 阶段新增的数据库表。M1 表定义见 `docs/base/M1/MCN_M1_Base_Database.md`。
> M2 包含 Sprint 1（kol-intake 4 张表）、Sprint 3（persona 1 张表 + TikHub 2 张表 + benchmark 2 张表）、Sprint 4（tiktok_writer_configs 1 张表）、Sprint 5（selling_point_configs 1 张表）、Sprint 6（qianchuan_review_configs 1 张表）、Sprint 7（qianchuan_edit_review_configs 1 张表），运营首页复用 M1 已有表，无新增。各工具的产出记录复用 `outputs` + `task_jobs`。

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
| `benchmark_configs` | 对标分析 AI 配置（Prompt + 模型） | Sprint 3 |
| `benchmark_analyses` | 对标分析记录（账号分析结果） | Sprint 3 |
| `selling_point_configs` | 卖点提取 AI 配置（Prompt + 模型） | Sprint 5 |
| `tiktok_writer_configs` | TikTok 脚本仿写 AI 配置（Prompt + 模型） | Sprint 4 |
| `qianchuan_review_configs` | 千川脚本复盘 AI 配置（Prompt + 模型） | Sprint 6 |
| `qianchuan_edit_review_configs` | 千川剪辑预审 AI 配置（Prompt + 模型） | Sprint 7 |

> 各工具的产出记录统一复用 `outputs` 和 `task_jobs`，不单独建产出表。

---

## 1a. M2 迁移文件清单

| 迁移文件 | Sprint | 操作说明 |
|---------|--------|---------|
| `007_benchmark.sql` | Sprint 3 | 新建 benchmark_configs、benchmark_analyses 表 |
| `008_tikhub_credentials.sql` | Sprint 3 | 新建 tikhub_credentials 表 |
| `009_persona_reports.sql` | Sprint 3 | 新建 persona_reports 表 |
| `010_tikhub_call_logs.sql` | Sprint 3 | 新建 tikhub_call_logs 表 |
| `011_workspace_tools.sql` | Sprint 3 | 初始化 workspace_tools 表及各工具入口 |
| `014_tiktok_writer_workspace.sql` | Sprint 4 | workspace_tools 注册 tiktok-writer |
| `015_selling_point_configs.sql` | Sprint 5 | 新建 selling_point_configs 表，注册 selling-point-extractor |
| `016_qianchuan_review.sql` | Sprint 6 | workspace_tools 注册 qianchuan-review，status=online |
| `017_tiktok_writer_configs.sql` | Sprint 4 | 新建 tiktok_writer_configs 表（TikTok 脚本仿写 Prompt 配置）|
| `018_qianchuan_review_configs.sql` | Sprint 6 | 新建 qianchuan_review_configs 表（管理端 Prompt 配置）|
| `019_qianchuan_edit_review.sql` | Sprint 7 | workspace_tools 注册 qianchuan-edit-review，status=online |
| `020_qianchuan_edit_review_configs.sql` | Sprint 7 | 新建 qianchuan_edit_review_configs 表（千川剪辑预审 Prompt 配置）|

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
| `013_benchmark.sql` | benchmark_configs + benchmark_analyses 表 + 初始 Prompt + workspace_tools 注册（tool_code=`benchmark`） | Sprint 3 |
| `014_tiktok_writer.sql` | workspace_tools 注册（tool_code=`tiktok-writer`，status=`dev`） | Sprint 4 |
| `015_selling_point_extractor.sql` | selling_point_configs 表 + 初始 Prompt + workspace_tools 注册（tool_code=`selling-point-extractor`） | Sprint 5 |

---

## 12. benchmark_configs 对标分析配置表（Sprint 3）

### 12.1 用途

存储对标分析功能的 AI 配置（Prompt + 模型绑定）。管理员在后台维护。

### 12.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | SERIAL | 是 | 配置 ID |
| `config_key` | VARCHAR(50) | 是 | 唯一键（目前只有 `analyze`） |
| `ai_model_id` | INTEGER | 否 | 关联 `ai_models.id`，NULL 时用默认模型 |
| `system_prompt` | TEXT | 否 | AI 分析提示词 |
| `is_active` | BOOLEAN | 是 | 是否启用 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间（触发器自动更新） |

---

## 13. benchmark_analyses 对标分析记录表（Sprint 3）

### 13.1 用途

存储每次对标分析的输入数据和 AI 生成结果。

### 13.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | SERIAL | 是 | 记录 ID |
| `account_name` | VARCHAR(200) | 否 | 对标账号名 |
| `sec_user_id` | VARCHAR(200) | 否 | TikHub sec_user_id |
| `top10_content` | TEXT | 否 | TOP10 视频文案 |
| `recent30_content` | TEXT | 否 | 近 30 天视频文案 |
| `profile_result` | TEXT | 否 | AI 生成的人格档案 |
| `plan_result` | TEXT | 否 | AI 生成的内容规划 |
| `model_used` | VARCHAR(100) | 否 | 使用的模型 ID |
| `tokens_used` | INTEGER | 否 | token 用量 |
| `duration_ms` | INTEGER | 否 | 生成耗时（ms） |
| `status` | VARCHAR(20) | 是 | `pending` / `ready` / `failed` |
| `created_by` | INTEGER | 是 | 创建者，关联 `users.id` |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间（触发器自动更新） |

### 13.3 索引

```sql
CREATE INDEX idx_benchmark_analyses_user ON benchmark_analyses(created_by);
CREATE INDEX idx_benchmark_analyses_created ON benchmark_analyses(created_at DESC);
```

---

## 14. selling_point_configs 卖点提取配置表（Sprint 5）

### 14.1 用途

存储卖点提取器的 AI 配置（Prompt + 模型绑定）。管理员在后台「工具配置 → 功能配置」中维护。

### 14.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | SERIAL | 是 | 配置 ID |
| `config_key` | VARCHAR(50) | 是 | 唯一键（目前只有 `extract`） |
| `ai_model_id` | INTEGER | 否 | 关联 `ai_models.id`，NULL 时用默认模型 `claude-sonnet-4-6` |
| `system_prompt` | TEXT | 否 | AI 卖点提取提示词 |
| `is_active` | BOOLEAN | 是 | 是否启用 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间（触发器自动更新） |

### 14.3 初始数据

迁移 015 插入一条 `config_key='extract'` 记录，`system_prompt` 为完整的极致卖点卡提取提示词（机制/背书/口碑/产品力四板块）。

### 14.4 workspace_tools 注册

| tool_code | tool_name | category | status | sort_order |
|-----------|-----------|----------|--------|------------|
| `selling-point-extractor` | 产品卖点提取器 | 选题分析 | `online` | 3 |

---

## 15. tiktok_writer_configs TikTok 脚本仿写配置表（Sprint 4）

### 15.1 用途

存储 TikTok 脚本仿写的 AI 配置（Prompt + 模型绑定）。管理员在后台「工具配置 → 功能配置」中维护。

### 15.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | SERIAL | 是 | 配置 ID |
| `config_key` | VARCHAR(50) | 是 | 唯一键（`hook_eval` / `structure`） |
| `ai_model_id` | INT | 否 | 关联 `ai_models.id`，NULL 时用默认模型 |
| `system_prompt` | TEXT | 否 | AI 提示词 |
| `is_active` | BOOLEAN | 是 | 是否启用 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间（触发器自动更新） |

### 15.3 初始数据

迁移 017 插入两条记录：`config_key='hook_eval'`（开头评估）和 `config_key='structure'`（结构分析）。

### 15.4 workspace_tools 注册

| tool_code | tool_name | category | status | sort_order |
|-----------|-----------|----------|--------|------------|
| `tiktok-writer` | TikTok 脚本仿写 | 选题分析 | `online` | 1 |

---

## 16. qianchuan_review_configs 千川脚本复盘配置表（Sprint 6）

### 16.1 用途

存储千川脚本复盘的 AI 配置（Prompt + 模型绑定）。管理员在后台「工具配置 → 功能配置」中维护。

### 16.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | SERIAL | 是 | 配置 ID |
| `config_key` | VARCHAR(50) | 是 | 唯一键（`with_excel` / `without_excel`） |
| `ai_model_id` | INT | 否 | 关联 `ai_models.id`，NULL 时用默认模型 |
| `system_prompt` | TEXT | 否 | AI 提示词 |
| `is_active` | BOOLEAN | 是 | 是否启用 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间（触发器自动更新） |

### 16.3 初始数据

迁移 018 插入两条记录：`config_key='with_excel'`（有数据表）和 `config_key='without_excel'`（无数据表）。

### 16.4 workspace_tools 注册

| tool_code | tool_name | category | status | sort_order |
|-----------|-----------|----------|--------|------------|
| `qianchuan-review` | 千川脚本复盘 | 选题分析 | `online` | 4 |

---

## 17. qianchuan_edit_review_configs 千川剪辑预审配置表（Sprint 7）

### 17.1 用途

存储千川剪辑预审的 AI 配置（Prompt + 模型绑定）。管理员在后台「工具配置 → 功能配置」中维护。

### 17.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | SERIAL | 是 | 配置 ID |
| `config_key` | VARCHAR(50) | 是 | 唯一键（`review`） |
| `ai_model_id` | INT | 否 | 关联 `ai_models.id`，NULL 时用默认模型 |
| `system_prompt` | TEXT | 否 | AI 提示词 |
| `is_active` | BOOLEAN | 是 | 是否启用 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间（触发器自动更新） |

### 17.3 初始数据

迁移 020 插入一条 `config_key='review'` 记录，`system_prompt` 为剪辑预审提示词。

### 17.4 workspace_tools 注册

| tool_code | tool_name | category | status | sort_order |
|-----------|-----------|----------|--------|------------|
| `qianchuan-edit-review` | 千川剪辑预审 | 选题分析 | `online` | 5 |

---

## 18. livestream_writer_configs 直播脚本仿写配置表（Sprint 8）

**迁移文件**：`021_livestream_writer.sql`

### 18.1 表结构

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | SERIAL | 是 | 配置 ID |
| `config_key` | VARCHAR(50) | 是 | 唯一键（`generate` / `iterate`） |
| `ai_model_id` | INTEGER | 否 | 关联 `ai_models.id`，NULL 时用默认模型 `claude-opus-4-6-thinking` |
| `system_prompt` | TEXT | 否 | AI 系统提示词（含模板变量，由前端注入）|
| `is_active` | BOOLEAN | 是 | 是否启用 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间（触发器自动更新）|

### 18.2 初始数据

迁移 021 插入两条记录：

| config_key | 用途 |
|------------|------|
| `generate` | 首次生成开播方案的 System Prompt |
| `iterate` | 多轮迭代修改的 System Prompt |

两条 Prompt 含动态变量（`{orderLabels}` / `{refLength}` / `{sellingPoints}` / `{refScript}` / `{personaSoul}`），由前端在调用 `/chat` 前完成字符串替换后传入后端。

### 18.3 workspace_tools 注册

| tool_code | tool_name | category | status | sort_order |
|-----------|-----------|----------|--------|------------|
| `livestream-writer` | 直播脚本仿写 | 内容创作 | `online` | 自动计算 |
