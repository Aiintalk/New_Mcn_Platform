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
> 迁移文件清单见 §11（M2 数据迁移脚本，完整 006~029）。

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
| `016_qianchuan_review.sql` | workspace_tools 注册（tool_code=`qianchuan-review`） | Sprint 6 |
| `017_tiktok_writer_configs.sql` | tiktok_writer_configs 表（Prompt + 模型配置） | Sprint 4 |
| `018_qianchuan_review_configs.sql` | qianchuan_review_configs 表（Prompt + 模型配置） | Sprint 6 |
| `019_qianchuan_edit_review.sql` | workspace_tools 注册（tool_code=`qianchuan-edit-review`） | Sprint 7 |
| `020_qianchuan_edit_review_configs.sql` | qianchuan_edit_review_configs 表（Prompt + 模型配置） | Sprint 7 |
| `021_livestream_writer.sql` | livestream_writer_configs 表 + workspace_tools 注册（tool_code=`livestream-writer`） | Sprint 8 |
| `022_livestream_review.sql` | livestream_review_configs 表 + workspace_tools 注册（tool_code=`livestream-review`） | Sprint 9 |
| `023_persona_review.sql` | persona_review_configs 表 + workspace_tools 注册（tool_code=`persona-review`） | Sprint 10 |
| `024_qianchuan_preview.sql` | qianchuan_preview_configs 表 + workspace_tools 注册（tool_code=`qianchuan-preview`） | Sprint 11 |
| `025_qianchuan_collection.sql` | qianchuan_collection_groups + qianchuan_collection_scripts 表 + 种子数据 + workspace_tools 注册 | Sprint 12 |
| `026_tiktok_review.sql` | tiktok_review_configs 表 + workspace_tools 注册（tool_code=`tiktok-review`） | Sprint 13 |
| `027_oss_call_logs.sql` | oss_call_logs 表（OSS 调用日志） | Sprint 4+ |
| `028_service_credentials_test_fields.sql` | service_credentials 加 last_tested_at / last_latency_ms 字段 | Sprint 4+ |
| `029_asr_call_logs.sql` | asr_call_logs 表（ASR 调用日志） | Sprint 4+ |

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

---

## 19. qianchuan_collection_personas 达人分组表（Sprint 12）

**迁移文件**：`025_qianchuan_collection.sql`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | SERIAL | 是 | 主键 |
| `name` | VARCHAR(100) UNIQUE | 是 | 达人名称（唯一） |
| `is_deleted` | BOOLEAN | 是 | 软删除标志，默认 false |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间（触发器自动） |

---

## 20. qianchuan_collection_scripts 脚本表（Sprint 12）

**迁移文件**：`025_qianchuan_collection.sql`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | SERIAL | 是 | 主键 |
| `pool` | VARCHAR(20) | 是 | 脚本池：`global`（全网爆款）/ `persona`（达人爆款） |
| `persona_name` | VARCHAR(100) | 否 | 达人名称（pool=persona 时有值） |
| `title` | VARCHAR(200) | 是 | 脚本标题 |
| `content` | TEXT | 是 | 脚本正文 |
| `likes` | INTEGER | 否 | 点赞数 |
| `source` | VARCHAR(100) | 否 | 来源平台 |
| `source_account` | VARCHAR(100) | 否 | 来源账号 |
| `script_date` | DATE | 否 | 脚本日期（默认写入当天） |
| `is_deleted` | BOOLEAN | 是 | 软删除标志，默认 false |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间（触发器自动） |

**索引**：
- `(pool, is_deleted)` — 列表查询主路径
- `(persona_name, is_deleted)` — 按达人查脚本

**种子数据**：迁移 025 写入 41 条全网爆款脚本（从旧工具 `data/global/scripts/` 迁入）

### 20.1 workspace_tools 注册

| tool_code | tool_name | category | status | sort_order |
|-----------|-----------|----------|--------|------------|
| `qianchuan-collection` | 千川爆文合集 | 千川 | `online` | 自动计算 |

---

## 21. tiktok_review_configs（Sprint 13）

**迁移文件**：`026_tiktok_review.sql`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | SERIAL | 是 | 主键 |
| `config_key` | VARCHAR(50) UNIQUE | 是 | 配置标识，当前只有 `default` |
| `ai_model_id` | INTEGER | 否 | 关联 ai_models.id，NULL 时使用默认模型 |
| `system_prompt` | TEXT | 否 | 系统 Prompt |
| `is_active` | BOOLEAN | 是 | 是否激活，默认 true |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间（触发器自动） |

**触发器**：`trg_tiktok_review_configs_updated`（自动更新 updated_at）

### 21.1 workspace_tools 注册

| tool_code | tool_name | category | status | sort_order |
|-----------|-----------|----------|--------|------------|
| `tiktok-review` | TT内容复盘 | 内容创作 | `dev` | 16 |

---

## 22. oss_call_logs OSS 调用日志（Sprint 4+）

### 22.1 用途

记录每次 OSS（阿里云对象存储）调用的详细信息，用于统计分析和用户排行。由 `app/adapters/oss.py` 在 `finally` 块写入（仿 yunwu AiCallLog 模式）。

### 22.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | BIGSERIAL | 是 | 日志 ID |
| `credential_id` | BIGINT | 否 | 关联 `service_credentials.id`（ON DELETE SET NULL） |
| `user_id` | BIGINT | 否 | 调用用户（系统调用时为 NULL，ON DELETE SET NULL） |
| `operation` | VARCHAR(16) | 是 | 操作类型：`upload` / `download` / `delete` |
| `status` | VARCHAR(32) | 是 | 调用状态：`success` / `fail` |
| `latency_ms` | INTEGER | 否 | 响应延迟（ms） |
| `oss_key` | TEXT | 否 | OSS 对象键（如 `uploads/1/20260101/abc.txt`） |
| `error_message` | TEXT | 否 | 失败时的错误信息（前 500 字符） |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间（默认 NOW()） |

### 22.3 索引

```sql
CREATE INDEX idx_oss_call_logs_credential ON oss_call_logs(credential_id);
CREATE INDEX idx_oss_call_logs_user       ON oss_call_logs(user_id);
CREATE INDEX idx_oss_call_logs_operation  ON oss_call_logs(operation);
CREATE INDEX idx_oss_call_logs_status     ON oss_call_logs(status);
CREATE INDEX idx_oss_call_logs_created_at ON oss_call_logs(created_at DESC);
```

### 22.4 写入位置

- `app/adapters/oss.py::upload_file` — operation='upload'
- `app/adapters/oss.py::get_download_url` — operation='download'
- `app/adapters/oss.py::delete_file` — operation='delete'

三个函数都在 `finally` 块写日志 + commit，确保成功/失败都留痕。

### 22.5 迁移文件

`027_oss_call_logs.sql`

---

## 23. service_credentials 扩展字段（OSS 测试结果）

### 23.1 新增字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `last_tested_at` | TIMESTAMPTZ | 否 | 上次测试时间（凭证测试端点保存） |
| `last_latency_ms` | INTEGER | 否 | 上次测试延迟（ms） |

### 23.2 写入位置

`app/routers/admin_credentials.py::test_credential` — 测试成功/失败都会更新这两个字段（admin 调用测试端点时）。

### 23.3 通用性

字段是通用的（不限定 provider='oss'），将来 ASR / AI 等其他 provider 的测试端点也可复用。

### 23.4 迁移文件

`028_service_credentials_test_fields.sql`：
```sql
ALTER TABLE service_credentials ADD COLUMN IF NOT EXISTS last_tested_at  TIMESTAMPTZ;
ALTER TABLE service_credentials ADD COLUMN IF NOT EXISTS last_latency_ms INTEGER;
```

---

## 24. asr_call_logs ASR 调用日志（Sprint 4+）

### 24.1 用途

记录每次 ASR（阿里云智能语音交互 — 录音文件识别）调用的详细信息。由 `app/adapters/asr.py` 在 `finally` 块写入（与 `oss_call_logs` / `yunwu.AiCallLog` 同模式）。

### 24.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | BIGSERIAL | 是 | 日志 ID |
| `credential_id` | BIGINT | 否 | 关联 `service_credentials.id`（ON DELETE SET NULL） |
| `user_id` | BIGINT | 否 | 调用用户（系统调用时为 NULL，ON DELETE SET NULL） |
| `operation` | VARCHAR(16) | 是 | 操作类型：`submit`（提交任务）/ `query`（查询结果） |
| `status` | VARCHAR(32) | 是 | 调用状态：`success` / `fail` |
| `latency_ms` | INTEGER | 否 | 响应延迟（ms） |
| `task_id` | TEXT | 否 | 阿里云 ASR 任务 ID（SubmitTask 返回） |
| `audio_url` | TEXT | 否 | 输入音频 URL（仅 submit 记录，query 无） |
| `error_message` | TEXT | 否 | 失败时的错误信息（前 500 字符） |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间（默认 NOW()） |

### 24.3 索引

```sql
CREATE INDEX idx_asr_call_logs_credential ON asr_call_logs(credential_id);
CREATE INDEX idx_asr_call_logs_user       ON asr_call_logs(user_id);
CREATE INDEX idx_asr_call_logs_operation  ON asr_call_logs(operation);
CREATE INDEX idx_asr_call_logs_status     ON asr_call_logs(status);
CREATE INDEX idx_asr_call_logs_created_at ON asr_call_logs(created_at DESC);
```

### 24.4 写入位置

- `app/adapters/asr.py::submit_transcription` — operation='submit'（带 audio_url）
- `app/adapters/asr.py::query_transcription` — operation='query'（带 task_id，无 audio_url）
- `app/adapters/asr.py::transcribe` — 不直接写日志（由 submit + query 两次子调用各自记录）

两个函数都在 `finally` 块写日志 + commit，确保成功/失败都留痕。

### 24.5 凭证字段约定

`service_credentials` 中 provider='asr' 的凭证：
- `config`：`{"app_key": "项目AppKey", "region": "cn-shanghai|cn-beijing|cn-shenzhen"}`
- `secret_enc`：`"access_key_id\naccess_key_secret"`（两行，与 OSS 单一 secret 不同）

### 24.6 迁移文件

`029_asr_call_logs.sql`

## 25. qianchuan_writer_configs 千川文案写作配置表（Sprint 14）

### 25.1 用途

千川脚本仿写工具（`qianchuan-writer`）的配置表：存储 Prompt 模板 + 绑定的 AI 模型 + 启用开关。由管理端 `功能配置` Tab 维护（参照 `TiktokWriterConfig` 模式）。

### 25.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | BIGSERIAL | 是 | 主键 |
| `config_key` | VARCHAR(64) | 是 | 配置键（UNIQUE，默认 `'default'`）|
| `system_prompt` | TEXT | 否 | Prompt 模板（含 `{{name}}` / `{{soul}}` / `{{content_plan}}` 占位符）|
| `ai_model_id` | BIGINT | 否 | 关联 `ai_models.id`（ON DELETE SET NULL）；留空走默认 `claude-opus-4-6-thinking` |
| `is_active` | BOOLEAN | 是 | 启用开关（默认 TRUE）|
| `created_at` | TIMESTAMPTZ | 是 | 创建时间（默认 NOW()）|
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间（默认 NOW()，管理端 PUT 时刷新）|

### 25.3 种子 Prompt 模板（migration 030 内置）

```
你是一个千川脚本仿写专家。任务：把原版脚本改写成「{{name}}」视角的仿写版本。

## {{name}} 人物档案
{{soul}}

## {{name}} 内容规划参考
{{content_plan}}

## 仿写铁律（必须严格执行）
1. 结构完全不变：句式结构、段落顺序、整体框架100%保留
2. 字数只能相同或更少，绝对不能更多
3. 开头99%原封不动：只有当原版开头出现的人物/产品与{{name}}身份直接冲突时，才最多换一两个字
4. 产品全部替换：把原版中所有产品信息、卖点，替换成用户提供的「{{name}}产品卖点」里对应的卖点
5. 人物视角换成{{name}}：原版里的其他网红/人物换成{{name}}本人的第一人称视角

直接输出仿写后的完整脚本，不要解释，不要加任何注释或标注。
```

**占位符**（后端 `app/services/qianchuan_writer_prompt.py::render_system_prompt` 用正则一次性替换，避免 soul 内含 `{{name}}` 文本时二次替换）：
- `{{name}}` → `kols.name`
- `{{soul}}` → `kols.persona`
- `{{content_plan}}` → `kols.content_plan`

### 25.4 workspace_tools 注册

migration 030 同时在 `workspace_tools` 表注册工具：
- `tool_code='qianchuan-writer'`, `tool_name='千川文案写作'`
- `category='脚本创作'`, `status='dev'`（测试通过后管理端改 `online`）
- `sort_order=100`

### 25.5 迁移文件

`030_qianchuan_writer.sql`

---

## 26. persona_writer_configs 人设脚本仿写配置表（Sprint 15）

### 26.1 用途

人设脚本仿写工具（`persona-writer`）的配置表：存储 4 个 Prompt 模板 + 2 个 AI 模型绑定（light / heavy）+ 启用开关。由管理端 `功能配置` Tab 维护。

### 26.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | BIGSERIAL | 是 | 主键 |
| `config_key` | VARCHAR(64) | 是 | 配置键（UNIQUE，默认 `'default'`）|
| `evaluation_prompt` | TEXT | 否 | Step 2.4 开头评估 Prompt 模板（含 `{{transcript}}`）|
| `analysis_prompt` | TEXT | 否 | Step 3.1 结构拆解 Prompt 模板（含 `{{transcript}}`）|
| `writing_prompt` | TEXT | 否 | Step 3.3 写作 Prompt 模板（含 `{{is_custom}}...{{/is_custom}}` 块语法区分双模式）|
| `iteration_prompt` | TEXT | 否 | Step 3.4 多轮追问 Prompt 模板 |
| `light_model_id` | BIGINT | 否 | 评估/拆解用 AI 模型（`ai_models.id`，ON DELETE SET NULL）；留空走默认 `claude-haiku-4-5-20251001` |
| `heavy_model_id` | BIGINT | 否 | 写作/追问用 AI 模型（`ai_models.id`，ON DELETE SET NULL）；留空走默认 `claude-opus-4-6` |
| `is_active` | BOOLEAN | 是 | 启用开关（默认 TRUE）|
| `created_at` | TIMESTAMPTZ | 是 | 创建时间（默认 NOW()）|
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间（默认 NOW()，管理端 PUT 时刷新）|

### 26.3 Prompt 占位符（7 个 + 1 个块语法）

后端 `app/services/persona_writer_prompt.py::render_prompt` 渲染：

| 占位符 | 渲染值 | 用于 |
|--------|--------|------|
| `{{name}}` | `kols.name` | writing / iteration |
| `{{soul}}` | `kols.persona` 全文 | writing / iteration |
| `{{content_plan}}` | `kols.content_plan` | writing / iteration |
| `{{transcript}}` | 对标文案全文 | evaluate / analyze / writing / iteration |
| `{{structure_analysis}}` | Step 3.1 拆解结果 | writing / iteration |
| `{{topic}}` | 选题 | writing |
| `{{is_custom}}...{{/is_custom}}` | `is_custom=true` 时保留块内容，否则移除 | writing（双模式分支）|
| `{{!is_custom}}...{{/!is_custom}}` | `is_custom=false` 时保留块内容，否则移除 | writing（双模式分支）|

**渲染规则**：先处理 `{{is_custom}}` 块语法（按 `topic_mode='custom'|'default'` 保留/移除），再用 `re.compile(r"\{\{\s*(name|soul|content_plan|transcript|structure_analysis|topic)\s*\}\}")` 一次性 `re.sub` 替换其余占位符（避免 soul 内容含 `{{name}}` 文本时二次替换）。

### 26.4 双模式逻辑（writing_prompt 内部）

`POST /chat` body 传 `topic_mode`：
- `topic_mode='custom'`（💡我有想法）：保留 `{{is_custom}}...{{/is_custom}}` 块，移除 `{{!is_custom}}...{{/!is_custom}}` 块；员工选题 > 对标结构 > 达人风格
- `topic_mode='default'`（🤖我没想法）：保留 `{{!is_custom}}...{{/!is_custom}}` 块，移除 `{{is_custom}}...{{/is_custom}}` 块；原文结构 > 分析 > 人格档案

### 26.5 种子 Prompt（migration 031 内置）

4 个 Prompt 全部从旧架构 `persona-writer-web/src/app/page.tsx` 提取并改造：
- `${var}` 前端拼字符串 → `{{var}}` 后端模板
- 移除硬编码模型名（`qwen-flash` / `claude-opus-4-6-thinking`）→ 用 `light_model_id` / `heavy_model_id` 字段
- 双选题 Prompt 合并到 1 个 `writing_prompt`，用 `{{is_custom}}` 块语法区分

种子值：`config_key='default'`, `light_model_id=2`（claude-haiku-4-5-20251001）, `heavy_model_id=4`（claude-opus-4-6）, `is_active=TRUE`。

### 26.6 workspace_tools 注册

migration 031 同时 UPSERT `workspace_tools` 表（旧表已有 `persona-writer` 记录 status='disabled'）：
- `tool_code='persona-writer'`, `tool_name='人设脚本仿写'`
- `category='脚本创作'`, `status='online'`（直接上线，已通过 E2E）
- `sort_order=110`

### 26.7 迁移文件

`031_persona_writer.sql`

---

## 27. seeding-writer 种草内容仿写（Sprint 16）

3 张新表 + 6 种子 Prompt + workspace_tools 上线。

### 27.1 seeding_writer_configs 配置表

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | BIGSERIAL | 是 | 主键 |
| `config_key` | VARCHAR(64) | 是 | UNIQUE，默认 'default' |
| `sp_system_prompt` | TEXT | 否 | Step 2 卖点提取系统 Prompt |
| `parse_product_prompt` | TEXT | 否 | Step 2 文档解析 Prompt（JSON 输出）|
| `structure_analysis_prompt` | TEXT | 否 | Step 3 结构拆解 Prompt |
| `ai_recommend_prompt` | TEXT | 否 | Step 4.1 AI 推荐角度 Prompt |
| `writing_prompt` | TEXT | 否 | Step 4.2 写作 Prompt |
| `iteration_prompt` | TEXT | 否 | Step 4.4 迭代 Prompt |
| `light_model_id` | BIGINT FK→ai_models | 否 | 轻量模型（结构拆解/AI推荐），默认 claude-haiku-4-5 |
| `heavy_model_id` | BIGINT FK→ai_models | 否 | 重型模型（写作/迭代/卖点），默认 claude-opus-4-6 |
| `is_active` | BOOLEAN | 是 | 默认 TRUE |
| `created_at` | TIMESTAMPTZ | 是 | 默认 NOW() |
| `updated_at` | TIMESTAMPTZ | 是 | 默认 NOW() |

种子：6 Prompt 从旧版 page.tsx / parse-product/route.ts 提取，`${var}` 改 `{{var}}`。

### 27.2 seeding_writer_products 产品库表（公司共享）

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
| `created_by` | BIGINT FK→users | 否 | 审计用（**不隔离查询**）|
| `created_at` | TIMESTAMPTZ | 是 | 默认 NOW() |
| `updated_at` | TIMESTAMPTZ | 是 | 默认 NOW() |
| `deleted_at` | TIMESTAMPTZ | 否 | 软删 |

索引：`idx_seeding_writer_products_name`（name 模糊查询，WHERE deleted_at IS NULL）+ `idx_seeding_writer_products_created_by`

### 27.3 seeding_writer_references 素材库表（达人维度共享）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | BIGSERIAL | 是 | 主键 |
| `kol_id` | BIGINT FK→kols | 否 | ON DELETE SET NULL |
| `title` | TEXT | 是 | 标题 |
| `content` | TEXT | 是 | 正文 |
| `type` | VARCHAR(32) | 否 | 种草爆款 / 对标种草 / 风格参考 |
| `source` | VARCHAR(32) | 否 | 抖音 / 小红书 / 手写 |
| `likes` | INT | 否 | 点赞数 |
| `douyin_url` | TEXT | 否 | 抖音源链接（导入时填）|
| `created_by` | BIGINT FK→users | 否 | 审计用（**不隔离查询**）|
| `created_at` | TIMESTAMPTZ | 是 | 默认 NOW() |
| `updated_at` | TIMESTAMPTZ | 是 | 默认 NOW() |
| `deleted_at` | TIMESTAMPTZ | 否 | 软删 |

索引：`idx_seeding_writer_references_kol_id`（WHERE deleted_at IS NULL）+ `idx_seeding_writer_references_created_by`

### 27.4 workspace_tools 注册

migration 033 UPSERT `workspace_tools` 表：
- `tool_code='seeding-writer'`, `tool_name='种草内容仿写'`
- `category='脚本创作'`, `status='online'`
- `sort_order=120`

### 27.5 Prompt 占位符（14 个）

| 占位符 | 渲染值 | 用于哪个 Prompt |
|--------|--------|---------------|
| `{{name}}` | kols.name | writing / iteration |
| `{{soul}}` | kols.persona | writing / iteration / ai_recommend |
| `{{content_plan}}` | kols.content_plan | writing / iteration / ai_recommend |
| `{{product_name}}` | products.name | writing / iteration |
| `{{product_category}}` | products.category | writing / iteration |
| `{{product_price}}` | products.price | writing / iteration |
| `{{product_selling_points}}` | products.selling_points | writing / iteration / ai_recommend |
| `{{product_target_audience}}` | products.target_audience | writing / iteration / ai_recommend |
| `{{product_scenario}}` | products.scenario | writing / iteration |
| `{{references}}` | references 拼接 | writing / iteration / ai_recommend |
| `{{transcript}}` | 对标文案 | structure_analysis / writing / iteration / ai_recommend |
| `{{structure_analysis}}` | 拆解结果 | writing / iteration |
| `{{topic}}` | 选题 | writing |
| `{{raw_text}}` | 产品资料原文 | sp_system_prompt |

### 27.6 迁移文件

`033_seeding_writer.sql`

---

## 28. kol_references 素材库参考素材（Sprint 18 — material-library）

红人素材库的参考素材表。每位红人可有多条参考素材，按 `type` 字段分 6 类管理。
软删策略：`deleted_at IS NULL` 视为有效；FK CASCADE（kol 删除时连带素材一并删除）。

### 28.1 字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | BIGSERIAL | 是 | 主键 |
| `kol_id` | BIGINT FK→kols | 是 | ON DELETE CASCADE |
| `title` | VARCHAR(500) | 是 | 素材标题 |
| `likes` | INT | 否 | 点赞数 |
| `source` | VARCHAR(100) | 否 | 来源，默认 '抖音' |
| `type` | VARCHAR(50) | 是 | 6 类之一（见下） |
| `content` | TEXT | 是 | 正文内容 |
| `created_by` | BIGINT FK→users | 否 | 审计用 |
| `created_at` | TIMESTAMPTZ | 是 | 默认 NOW() |
| `updated_at` | TIMESTAMPTZ | 是 | 默认 NOW() |
| `deleted_at` | TIMESTAMPTZ | 否 | 软删 |

`type` 枚举：`红人爆款文案 / 红人喜欢的内容 / 风格参考 / 千川爆款文案 / 千川喜欢的内容 / 千川风格参考`

### 28.2 索引

- `idx_kol_references_kol_type`：`(kol_id, type) WHERE deleted_at IS NULL` — 列表分组查询主索引
- `idx_kol_references_kol_recent`：`(kol_id, created_at DESC)` — 最新素材排序

### 28.3 迁移文件

`034_material_library.sql`

---

## 29. material_library_configs 素材库 AI 配置（Sprint 18）

存放 soul_generator（从入驻问卷生成人格档案初稿）的系统提示词与模型选择。

### 29.1 字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | BIGSERIAL | 是 | 主键 |
| `config_key` | VARCHAR(64) | 是 | UNIQUE，目前固定 'soul_generator' |
| `ai_model_id` | BIGINT FK→ai_models | 否 | AI 模型 ID |
| `system_prompt` | TEXT | 否 | 系统提示词，占位符 `{{kol_name}} {{intake_answers}} {{intake_report}}` |
| `is_active` | BOOLEAN | 是 | 默认 TRUE |
| `created_at` | TIMESTAMPTZ | 是 | 默认 NOW() |
| `updated_at` | TIMESTAMPTZ | 是 | 默认 NOW() |

### 29.2 种子数据

migration 034 INSERT soul_generator 默认配置：
- `ai_model_id=3`（claude-sonnet-4-6）
- `is_active=true`
- `system_prompt` 含 3 个占位符 + 中文撰写要求（745 字符）

### 29.3 workspace_tools 注册

migration 034 UPSERT：
- `tool_code='material-library'`, `tool_name='素材库'`
- `category='素材管理'`, `status='dev'`（先以开发中状态上线）
- `sort_order=130`

### 29.4 迁移文件

`034_material_library.sql`

---

## 30. subtitle 字幕提取（Sprint 19 — 迁移自旧架构）

批量字幕任务、任务条目、思维导图配置 3 表。迁移自旧架构 `Ai_Toolbox/subtitle-extractor-web/lib/db.ts`（SQLite）→ PostgreSQL。
产出接入共享 `outputs` 表（不新建产出表）。

### 30.1 subtitle_jobs 批量任务表

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | BIGSERIAL | 是 | 主键 |
| `job_code` | VARCHAR(32) UNIQUE | 是 | 服务端任务码 `sub_yyyymmdd_xxxxxxxx` |
| `status` | VARCHAR(16) | 是 | `processing` / `completed` / `failed`（默认 `processing`）|
| `phase` | VARCHAR(64) | 是 | 执行阶段：`queued` / `running` / `done` |
| `total` | INT | 是 | 总条数 |
| `success` | INT | 是 | 成功条数 |
| `failed` | INT | 是 | 失败条数 |
| `created_by` | BIGINT FK → users(id) ON DELETE SET NULL | 否 | 创建者（任务通过此字段绑定用户身份，无 access_code）|
| `created_at` / `updated_at` | TIMESTAMPTZ | 是 | 默认 NOW() |

索引：`idx_subtitle_jobs_created_by`、`idx_subtitle_jobs_status`。

### 30.2 subtitle_items 批量任务条目表

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | BIGSERIAL | 是 | 主键 |
| `job_id` | BIGINT FK → subtitle_jobs(id) ON DELETE CASCADE | 是 | 所属任务 |
| `row_number` | INT | 是 | 行号（从 1 开始）|
| `original_url` | TEXT | 是 | 原始抖音分享文本 |
| `title` | TEXT | 是 | 视频标题（成功后填充）|
| `transcript` | TEXT | 是 | 字幕文本（成功后填充）|
| `status` | VARCHAR(16) | 是 | `pending` / `processing` / `success` / `failed`（默认 `pending`）|
| `error` | TEXT | 是 | 失败原因（失败时填充）|
| `created_at` / `updated_at` | TIMESTAMPTZ | 是 | 默认 NOW() |

约束：`UNIQUE (job_id, row_number)`。
索引：`idx_subtitle_items_job`。

### 30.3 subtitle_configs 思维导图配置表

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | BIGSERIAL | 是 | 主键 |
| `config_key` | VARCHAR(64) UNIQUE | 是 | 配置键（当前只用 `default`）|
| `mindmap_prompt` | TEXT | 否 | 思维导图系统提示词（支持 `{{transcript}}` 占位符）|
| `mindmap_model_id` | BIGINT FK → ai_models(id) ON DELETE SET NULL | 否 | AI 模型 ID |
| `is_active` | BOOLEAN | 是 | 启用开关（默认 TRUE）|
| `created_at` / `updated_at` | TIMESTAMPTZ | 是 | 默认 NOW() |

### 30.4 Seed 默认数据

migration 035 INSERT：
- `config_key='default'`
- `mindmap_model_id=2`（claude-haiku-4-5-20251001）
- `is_active=true`
- `mindmap_prompt` 含 `{{transcript}}` 占位符 + JSON 输出规范（348 字符）

### 30.5 workspace_tools 注册

migration 035 UPDATE：
- `tool_code='subtitle'`, `tool_name='字幕提取'`
- `category='内容工作台'`, `status='online'`（直接上线）
- `sort_order=140`

### 30.6 迁移文件

`035_subtitle.sql`

---

## 32. values_writer_configs 价值观仿写配置表（Sprint 20）

### 32.1 用途

存储价值观仿写工具的 AI 配置（4 个 Prompt + 模型绑定）。管理员在后台「价值观仿写」ConfigTab 中维护。

### 32.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | BIGSERIAL | 是 | PK |
| `config_key` | VARCHAR(64) | 是 | UNIQUE，目前只有 `default` |
| `extract_values_prompt` | TEXT | 否 | Step 1：从人物档案提炼价值观 |
| `emotion_direction_prompt` | TEXT | 否 | Step 2：推导情绪方向 |
| `writing_prompt` | TEXT | 否 | Step 3：生成内容 |
| `iteration_prompt` | TEXT | 否 | Step 4：迭代优化 |
| `model_id` | BIGINT FK ai_models | 否 | AI 模型（NULL 时用默认） |
| `is_active` | BOOLEAN | 是 | 启用开关 |
| `created_at` | TIMESTAMPTZ | 是 | |
| `updated_at` | TIMESTAMPTZ | 是 | 触发器自动更新 |

### 32.3 迁移文件

`043_values_writer.sql`
