# M2 Sprint 15 — persona-writer（人设脚本仿写）需求文档

> 状态：**待 PM 写完 → 用户签收 → 进入节点 B**
> 创建日期：2026-06-23
> 对应旧架构模块：`Ai_Toolbox/persona-writer-web`（Next.js 14 + Tailwind）
> 对应分支：`migrate/persona-writer`（待创建，从 main 拉）
> 前序任务：Sprint 14 qianchuan-writer（同分支模式参照样板）

---

## 一、工具概述

**名称**：persona-writer（人设脚本仿写）
**定位**：基于达人风格 + 对标视频的脚本仿写工具。3 步向导：加载风格 → 对标验证 → 仿写创作。
**业务铁律**：3 步业务逻辑 100% 忠实旧版，Prompt + AI 模型全部模板化（admin 可配）。
**关键差异 vs qianchuan-writer**：
- 多了 Step 2 对标验证（TikHub 抓视频 + 点赞门槛 + AI 开头评估）
- 多了 Step 3 结构拆解 + 双选题模式 + 图片追问 + 终稿编辑
- 4 个 Prompt（评估/拆解/写作/追问）+ 2 个 AI 模型（轻/重）

---

## 二、需求澄清记录

| # | 问题 | 决策 |
|---|------|------|
| 1 | Step 2 对标验证（TikHub + 点赞 + AI 评估）是否保留？ | **全保留**（业务铁律，不能简化）|
| 2 | 4 Prompt + 2 模型策略 | **4 Prompt + 2 AI 模型全部 admin 可配**（评估/拆解=qwen-flash 默认，写作/追问=claude-opus 默认）|
| 3 | 多轮追问的图片上传 | **保留**（前端 → OSS → URL → yunwu image_url）|
| 4 | 双选题模式（💡我有想法 / 🤖我没想法）| **保留**（两种 Prompt 不同，合并到 1 个 writing_prompt + is_custom 标记）|
| 5 | 开头锁定（手动复制对标原文前 2-3 句）| **保留手动替换**（终稿编辑页提示用户操作）|
| 6 | 历史记录 | **账号绑定**（outputs.created_by），每次生成都保存一条 |
| 7 | 导出格式 | **.docx + .txt 两个按钮**（同 qianchuan-writer）|
| 8 | 日志可见性 | 运营端只看自己的 outputs；管理端 5 张表 + 6 个查看入口（ExternalLogs/OperationLogs/Ai/TikHub Tab/OSS Tab/Outputs）全覆盖 |
| 9 | workspace_tools 注册 | 旧表已有 `persona-writer` status='disabled'，改 status='online' |
| 10 | 旧版 transcribe/upload + poll | **不迁移**（旧版 UI 实际未用，死代码）|
| 11 | 旧版 references（达人优质内容参考）| **不迁移**（旧版 UI 实际未渲染该表单，死代码）|
| 12 | 旧版 Soul.md / content-plan.md 文件数据 | **不迁移**（沿用新架构 kols 表，admin 手工录入或迁移到 persona 数据补全作为独立任务）|
| 13 | 并行推进 qianchuan-writer | **是**（qianchuan-writer E2E 用户抽空验收，不阻塞 persona-writer）|
| 14 | 默认 light 模型（ai_models 表无 qwen-flash）| **改用 `claude-haiku-4-5-20251001`**（yunwu 已注册 id=2；旧版 qwen-flash 在新架构 ai_models 表不存在）|
| 15 | 分支策略 | **先合并 qianchuan-writer PR #5 → 再从 main 拉 `migrate/persona-writer`**（避免两分支改 ServiceConfigPage/README 等共享文件冲突）|

---

## 三、变与不变

### 不变（业务铁律）
- 3 步向导业务流：加载风格 → 对标验证 → 仿写创作
- Prompt 3 条铁律：完整脚本 / 结构一致 / 字数只少不多
- 双选题模式优先级：💡custom（员工想法 > 对标结构 > 达人风格）/ 🤖default（原文结构 > 分析 > 人格档案）
- 点赞门槛 `digg_count >= 100000` 硬编码
- 开头手动替换（用户在终稿编辑页操作）
- AI 评估开头吸引力 + 质量门判定逻辑
- 多轮追问支持图片

### 变（新架构改造）
- 旧版 `${var}` 前端拼字符串 → 新版 `{{var}}` 后端 DB 模板渲染
- 旧版 4 个 Prompt 硬编码字符串 → DB 模板化（admin 可配）
- 旧版固定 qwen-flash / 默认模型 → admin 可配 2 个 AI 模型（light/heavy）
- 旧版无日志 → 新增 5 张日志表写入（ai_call_logs / tikhub_call_logs / oss_call_logs / operation_logs / outputs）
- 旧版账号无隔离 → 新版 outputs.created_by 账号绑定
- 旧版无 workspace_tools → 新架构 workspace_tools 注册 status='online'

---

## 四、3 步业务流

### Step 1 加载风格

| 用户操作 | UI 反馈 |
|---------|---------|
| 下拉选达人（必选）| 显示达人 content_plan 前 8 行作为预览 |
| 点"下一步" | 进 Step 2 |

数据源：`kols` 表，过滤 `persona IS NOT NULL AND content_plan IS NOT NULL AND deleted_at IS NULL AND status='active'`，JOIN users 拿 creator_name 标签（同 qianchuan-writer）。

### Step 2 对标验证（4 子环节）

| 子环节 | 用户操作 | 系统 |
|--------|---------|------|
| 2.1 粘贴抖音链接 | 粘贴分享链接（含短链和分享文本）| **POST /fetch-video**：tikhub_adapter → 返回 {title, digg_count, aweme_id, play_url} |
| 2.2 点赞门槛 | 显示点赞数 + ✅/❌ | `digg_count >= 100000` 才能继续，否则提示"换点赞更高的对标" |
| 2.3 粘贴文案 | 粘贴对标视频口播文案（外部工具如 AI 好记转好）| 确认文案准确后进入评估 |
| 2.4 AI 开头评估 | 等 AI 流式输出 | **POST /evaluate-opening**：调 yunwu（默认 light 模型 claude-haiku-4-5-20251001）→ "判断：通过/不通过 + 理由" |
| 2.5 质量门判定 | 用户同意/不同意评估结果 | 点赞✅ + 评估✅ → 进 Step 3；任意❌ → 留在 Step 2 |

**质量门通过条件**：`digg_count >= 100000 AND (评估含"通过"且不含"不通过") AND user_agree=true`

### Step 3 仿写创作

| 子环节 | 用户操作 | 系统 |
|--------|---------|------|
| 3.1 AI 结构拆解 | 等 AI 流式输出 | **POST /analyze-structure**：调 yunwu（light 模型）→ 拆解对标骨架 |
| 3.2 选方向 | 💡我有想法 / 🤖我没想法 二选一 | 两种 Prompt 不同 |
| 3.2a custom（💡我有想法）| 用户输入选题想法（必填）| 写作 Prompt 优先级：员工想法 > 对标结构 > 达人风格 |
| 3.2b default（🤖我没想法）| 系统自动生成默认选题 | 写作 Prompt 优先级：原文结构 > 分析 > 人格档案 |
| 3.3 AI 写脚本 | 等 AI 流式输出 | **POST /chat**（场景=writing）→ 3 条铁律 + 完整脚本 + 自检表 |
| 3.4 多轮追问 | 文本输入 + 可贴图 | **POST /chat**（场景=iteration）→ 改哪哪，不动没问题的部分 |
| 3.5 终稿编辑 | 用户手动改 + 手动复制对标原文前 2-3 句替换开头 | 纯前端 textarea 操作，无后端 |
| 3.6 导出 | 点 .docx 或 .txt | .docx 走后端 word_export；.txt 走前端 Blob |

**3 个动作按钮**（同 qianchuan-writer）：
- 保存历史 → POST /save-output
- 导出 .txt → 前端 Blob 下载
- 导出 .docx → POST /export-word

---

## 五、运营端 API（8 接口）

基础路径：`/api/tools/persona-writer`（operator / admin 鉴权，需已改密）

| # | 接口 | 用途 | 备注 |
|---|------|------|------|
| 1 | GET `/kols/personas` | Step 1 达人下拉 | 同 qianchuan-writer（JOIN users 拿 creator_name）|
| 2 | POST `/fetch-video` | Step 2.1 抖音链接解析 | **新接口**，调 tikhub_adapter.fetch_video_by_share_url |
| 3 | POST `/evaluate-opening` | Step 2.4 AI 开头评估 | 调 yunwu（light 模型，默认 claude-haiku-4-5）|
| 4 | POST `/analyze-structure` | Step 3.1 对标结构拆解 | 调 yunwu（light 模型）|
| 5 | POST `/chat` | Step 3.3/3.4 写作 + 追问 | 调 yunwu（heavy 模型，默认 claude-opus-4-6）；body 含 `scene: 'writing'\|'iteration'` + `topic_mode: 'custom'\|'default'` |
| 6 | POST `/save-output` | 保存产出 | 写 outputs（账号绑定）+ OperationLog |
| 7 | POST `/export-word` | 导出 .docx | StreamingResponse，不走信封 |
| 8 | GET `/outputs` | 历史记录（账号隔离）| WHERE created_by=current_user.id |

### 接口细节

#### POST /fetch-video（新接口）

Request：`{ "share_url": "https://v.douyin.com/xxx/" }`

Response：
```json
{
  "success": true, "data": {
    "title": "视频标题",
    "digg_count": 250000,
    "aweme_id": "7234...",
    "play_url": "https://...",
    "likes_pass": true
  }
}
```

写 TikHubCallLog（tikhub_adapter finally）。写 OperationLog（action=`persona_writer_fetch_video`）。

#### POST /evaluate-opening

Request：`{ "transcript": "对标文案全文" }`

Response：`text/plain`（裸文本流）

调 yunwu（light 模型，默认 claude-haiku-4-5-20251001）+ evaluation_prompt 模板。

#### POST /analyze-structure

Request：`{ "transcript": "对标文案全文" }`

Response：`text/plain`（裸文本流）

调 yunwu（light 模型，默认 claude-haiku-4-5-20251001）+ analysis_prompt 模板。

#### POST /chat

Request：
```json
{
  "scene": "writing",            // writing | iteration
  "topic_mode": "custom",         // custom | default（仅 writing 场景有效）
  "persona_id": 3,
  "transcript": "对标文案",
  "structure_analysis": "Step 3.1 的拆解结果",
  "topic": "用户的选题想法或默认选题",
  "messages": [{"role":"user","content":"..."}],  // iteration 场景用，含图片
  "create_job": false,
  "job_context": {}
}
```

Response：`text/plain`（裸文本流）

调 yunwu（heavy 模型，默认 claude-opus-4-6）+ writing_prompt 或 iteration_prompt（根据 scene）。

`create_job=true` 时 BackgroundTask 写 TaskJob + OperationLog。

#### POST /save-output

Request：`{ "content": "...", "title": "...", "task_id": 123, "topic": "选题", "transcript_digest": "对标文案摘要" }`

Response：`{ "success": true, "data": { "output_id": 789 } }`

写 outputs + OperationLog（action=`persona_writer_save_output`）。

---

## 六、管理端 API（2 接口）

基础路径：`/api/admin/persona-writer`（admin 鉴权）

| # | 接口 | 用途 |
|---|------|------|
| 1 | GET `/configs` | 配置列表（通常仅 default 1 条）|
| 2 | PUT `/configs/{config_key}` | 更新 Prompt + 模型 + 启用 |

---

## 七、数据模型

### 7.1 `persona_writer_configs` 表（新建）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | BIGSERIAL | 是 | 主键 |
| `config_key` | VARCHAR(64) | 是 | UNIQUE，默认 'default' |
| `evaluation_prompt` | TEXT | 否 | Step 2.4 开头评估 Prompt 模板 |
| `analysis_prompt` | TEXT | 否 | Step 3.1 结构拆解 Prompt 模板 |
| `writing_prompt` | TEXT | 否 | Step 3.3 写作 Prompt 模板（含 `{{is_custom}}` 占位符区分双模式段落）|
| `iteration_prompt` | TEXT | 否 | Step 3.4 多轮追问 Prompt 模板 |
| `light_model_id` | BIGINT | 否 | 轻量模型 ai_models.id（评估/拆解用，留空默认 `claude-haiku-4-5-20251001`，id=2）|
| `heavy_model_id` | BIGINT | 否 | 重型模型 ai_models.id（写作/追问用，留空默认 `claude-opus-4-6`，id=4）|
| `is_active` | BOOLEAN | 是 | 默认 TRUE |
| `created_at` | TIMESTAMPTZ | 是 | 默认 NOW() |
| `updated_at` | TIMESTAMPTZ | 是 | 默认 NOW() |

### 7.2 Prompt 占位符

| 占位符 | 渲染值 |
|--------|--------|
| `{{name}}` | kols.name |
| `{{soul}}` | kols.persona |
| `{{content_plan}}` | kols.content_plan |
| `{{transcript}}` | 对标文案（evaluate/analyze/writing/iteration 全用）|
| `{{structure_analysis}}` | Step 3.1 拆解结果（writing/iteration 用）|
| `{{topic}}` | 选题（writing 用）|
| `{{is_custom}}` | 'true' / 'false'（writing_prompt 内部 if-else 分支）|

### 7.3 workspace_tools 更新

已有记录 `persona-writer`（status='disabled'），改 status='online'。

### 7.4 迁移文件

`backend/migrations/031_persona_writer.sql`：建 persona_writer_configs + 种子 4 Prompt（从旧版 page.tsx 提取）+ UPDATE workspace_tools status='online'。

---

## 八、前端契约

### 8.1 文件清单（新建/修改）

| 操作 | 文件 |
|------|------|
| 新建 | `frontend/src/types/personaWriter.ts` |
| 新建 | `frontend/src/api/personaWriter.ts`（10 函数：8 operator + 2 admin）|
| **重写** | `frontend/src/pages/operator/PersonaWriterPage.tsx`（替换 placeholder）|
| 新建 | `frontend/src/pages/admin/PersonaWriterConfigTab.tsx` |
| 修改 | `frontend/src/App.tsx`（已有 `/workspace/persona-writer` 路由，保留）|
| 修改 | `frontend/src/pages/admin/WorkspaceConfigPage.tsx`（增加 PersonaWriterConfigTab）|
| 新建 | `frontend/src/__tests__/components/pages/PersonaWriterPage.test.tsx` |

### 8.2 ConfigTab 字段（比 qianchuan-writer 复杂）

| 字段 | 组件 | 说明 |
|------|------|------|
| `evaluation_prompt` | TextArea rows=8 | 开头评估 Prompt |
| `analysis_prompt` | TextArea rows=8 | 结构拆解 Prompt |
| `writing_prompt` | TextArea rows=16 | 写作 Prompt（含 `{{is_custom}}` 占位符）|
| `iteration_prompt` | TextArea rows=12 | 追问 Prompt |
| `light_model_id` | Select allowClear | 评估/拆解用 AI 模型（默认 claude-haiku-4-5）|
| `heavy_model_id` | Select allowClear | 写作/追问用 AI 模型（默认 claude-opus-4-6）|
| `is_active` | Switch | 启用 |

### 8.3 图片上传实现（复用通用接口）

前端 `user.type` / `paste` 拿到 image File → 调**通用** `POST /api/files`（OSS 已接通，参照 qianchuan-writer 头像上传）→ 拿 URL → 前端把 URL 放进 messages content 的 `image_url` 字段 → 调 /chat。

> 决策：**不新增 persona-writer 专用上传接口**。通用 `/api/files` 已写 OssCallLog，账号隔离由 users.id 保证。运营端 API 总数维持 8 个。

### 8.4 导出文件命名

```
人设脚本_${persona.name}_${topic || '终稿'}.txt
人设脚本_${persona.name}_${topic || '终稿'}.docx
```

---

## 九、测试要求

### 9.1 后端测试

| 类型 | 文件 | 用例数 |
|------|------|--------|
| 单测 tikhub_adapter | `tests/unit/services/test_tikhub_adapter.py`（扩展现文件）| +3（fetch_video_by_share_url 成功/失败/URL 解析）|
| 单测 prompt 渲染 | `tests/unit/services/test_persona_writer_prompt.py` | 10+（6 占位符替换 + 双模式 + 缺失 fallback + 多次出现 + 真实模板）|
| 集测 operator | `tests/integration/routers/test_operator_persona_writer.py` | 25+（鉴权 4 + personas 3 + fetch-video 4 + evaluate 3 + analyze 3 + chat 5 + save 3 + export 2 + outputs 2）|
| 集测 admin | `tests/integration/routers/test_admin_persona_writer.py` | 9+（鉴权 4 + GET 1 + PUT 4）|

### 9.2 前端测试

| 文件 | 用例数 |
|------|--------|
| `PersonaWriterPage.test.tsx` | 15+（3 步向导 + 双选题 + 图片上传 mock + 多轮追问 + 终稿编辑 + 保存 + 导出）|

### 9.3 红线自检（6/6 必过）

- convention_guard 全过
- 标准信封（流式/export-word 例外）
- OperationLog 全部用户写操作都写
- request.ts 全部 JSON 调用
- AsyncSessionLocal 注册（如用）

---

## 十、不在本次范围

- ❌ 旧版 transcribe/upload + poll（死代码，不迁移）
- ❌ 旧版 references（达人优质内容参考，UI 死代码，不迁移）
- ❌ 旧版 Soul.md / content-plan.md 文件数据迁移（沿用新架构 kols 表，admin 手工录入或独立任务）
- ❌ workspace_tools 中其他工具的 status 修复（独立任务）
- ❌ qianchuan-writer E2E 验收（并行推进，用户抽空做）
- ❌ tool_transcribe 改造（Sprint 3 债务）

---

## 十一、验收标准 DoD

1. ✅ 管理端可配 4 Prompt + 2 AI 模型 + 启用开关
2. ✅ 运营端 3 步向导全走通（选达人 → 抖音验证 + 评估 → 选题 + 写作 + 追问 + 终稿 + 导出）
3. ✅ 双选题模式行为符合预期（custom vs default Prompt 不同）
4. ✅ 图片追问可用（OSS 上传 + yunwu image_url）
5. ✅ 点赞门槛 `digg_count >= 100000` 硬编码生效
6. ✅ 开头手动替换（终稿编辑页有提示+对标原文展示）
7. ✅ outputs 账号绑定 + 历史可查
8. ✅ 5 张日志表全部留痕（管理端 6 个入口可见）
9. ✅ 所有测试通过（后端 pytest + 前端 vitest + convention_guard）
10. ✅ 契约文档同步（Base_API §22 + Base_Database §26）+ 前后端 README + PM 记忆
11. ✅ workspace_tools 中 persona-writer status='online'

---

## 十二、关键技术决策

| # | 决策 | 理由 |
|---|------|------|
| 1 | 扩展 `tikhub_adapter.fetch_video_by_share_url(share_url, db)` | 调 `GET /api/v1/douyin/web/fetch_one_video_by_share_url`（参照旧版 lib/tikhub.ts），finally 写 TikHubCallLog |
| 2 | 4 Prompt 合并到 1 张表 `persona_writer_configs` | 避免 4 张表 JOIN，DB 种子提供初值，admin 可改 |
| 3 | writing_prompt 用 `{{is_custom}}` 占位符区分双模式 | 减少 Prompt 字段数（不用 default_prompt + custom_prompt 两列）|
| 4 | 图片追问复用通用 `POST /api/files` | 不新增接口；通用 /api/files 已写 OssCallLog，前端拿 URL 后组装 messages 走 yunwu image_url |
| 5 | 点赞门槛 100000 硬编码 | 业务铁律（对标必须 ≥10 万赞），不让 admin 改（避免降标） |
| 6 | 终稿编辑纯前端 | 用户手动改 textarea + 手动复制对标原文，无后端交互 |
| 7 | chat 接口 scene 字段 | 一个接口承担 writing + iteration 两场景，避免接口数爆炸 |
| 8 | tikhub adapter 单测用 mock responses | 不实际调 TikHub API（避免消耗配额）|
| 9 | 三接口分离（chat/save/export）| 同 qianchuan-writer，流式/写库/生成文件各司其职 |
| 10 | 双模型：light（claude-haiku-4-5）+ heavy（claude-opus-4-6）| 评估/拆解用 haiku（ai_models id=2）；写作/追问用 opus（id=4）。旧版 qwen-flash 在新架构未注册 |

---

## 十三、CLAUDE.md 红线自检

| 红线 | 状态 | 说明 |
|------|------|------|
| 标准信封 | ✅ | 8 运营端接口中 7 个用 success_response；evaluate-opening / analyze-structure / chat 流式（裸文本，例外）；export-word StreamingResponse（例外）|
| OperationLog | ✅ | fetch-video / save-output / PUT configs / chat(create_job=true) 都写 |
| 前端走 request.ts | ✅ | api/personaWriter.ts 用 get/post；例外：SSE 3 个 + FormData 1 个 + Blob 1 个 |
| 契约同步 | ✅ | Base_API §22 + Base_Database §26 |
| README 更新 | ✅ | 前后端 README 同步 |
| AiCallLog 由 adapter 写 | ✅ | yunwu.py finally 自动写，router 不重复 |
| AsyncSessionLocal 注册 | ✅ | operator_persona_writer 流式用 AsyncSessionLocal，conftest patch 列表加 |

**9 条一票否决项**：无新增触发。

---

## 十四、实施顺序（节点 B 拆解参考）

0. **前置条件**：qianchuan-writer PR #5 已合并到 main（避免两分支改 ServiceConfigPage/README 等共享文件冲突）
1. **分支**：从更新后的 main 拉新分支 `migrate/persona-writer`
2. **后端 Part A**（B1-B5）：扩展 tikhub_adapter + migration 031 + ORM + prompt 渲染 service + conftest
3. **后端 Part B**（B6-B9）：operator_persona_writer 8 接口 + admin_persona_writer 2 接口 + main.py 注册 + 单测 + 集测
4. **前端 Part C**（F1-F4）：types + api + PersonaWriterPage 重写 + ConfigTab 新建
5. **前端 Part D**（F5-F6）：App.tsx 路由（已有，确认）+ WorkspaceConfigPage Tab 注册 + 组件测试
6. **回归**：后端 pytest 全量 + 前端 vitest 全量 + convention_guard
7. **节点 B++**：文档收尾 + commit + push + PR #6

---

## 十五、风险与预案

| 风险 | 概率 | 预案 |
|------|------|------|
| TikHub fetch_one_video 端点限流/失败 | 中 | adapter 完整 try/except + 429 重试（同 yunwu）+ 友好错误提示 |
| 图片上传 OSS 失败 | 低 | 前端 try/catch + toast 提示重试，不影响文本追问 |
| claude-haiku-4-5 评估超时 | 低 | yunwu 通道稳定；保留旧版"跳过评估"兜底 |
| 双选题 Prompt 模板分支复杂 | 低 | `{{is_custom}}` 占位符 + 后端 if-else 渲染，单测覆盖 |
| workspace_tools UPDATE 失败 | 低 | migration 用 ON CONFLICT 处理 |

---

> **下一步**：PM 签收本文档 → 进入节点 B（拆解前后端任务 + 派 subagent）。
