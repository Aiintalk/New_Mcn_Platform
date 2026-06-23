# M2 Sprint 15 — 后端任务：人设脚本仿写（persona-writer）

> 状态：**已完成**（待 PM 签收 + 推 PR）
> 完成日期：2026-06-23
> 对应需求文档：`docs/pm/M2_Sprint15_persona-writer_需求文档.md`
> 对应分支：`migrate/persona-writer`

---

## 一、范围（本次后端任务）

涵盖人设脚本仿写工具迁移的所有后端工作：
- Migration 031（persona_writer_configs 表 + 4 种子 Prompt + workspace_tools status='online'）
- ORM 模型 PersonaWriterConfig + 注册 __init__.py
- Prompt 渲染 service（7 占位符 + {{is_custom}} 双模式条件块）
- 扩展 tikhub adapter（fetch_video_by_share_url）
- operator_persona_writer.py 8 个接口（personas / fetch-video / evaluate-opening / analyze-structure / chat / save-output / export-word / outputs）
- admin_persona_writer.py 2 个接口（configs GET / PUT）
- main.py + conftest.py 注册
- 单测 16（prompt）+ tikhub adapter +3 + operator 集测 30 + admin 集测 9 全绿
- 全量回归通过（863 passed，2 failed 为预存 snappy 问题，非本次引入）

## 二、任务清单

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| B1 | Migration 031（建表 + 种子 4 Prompt + workspace_tools online）| `backend/migrations/031_persona_writer.sql` | ✅ |
| B2 | ORM 模型 PersonaWriterConfig | `backend/app/models/persona_writer.py` | ✅ |
| B3 | 注册到 `models/__init__.py` | `backend/app/models/__init__.py` | ✅ |
| B4 | Prompt 渲染 service（7 占位符 + is_custom 双模式）| `backend/app/services/persona_writer_prompt.py` | ✅ |
| B5 | 扩展 tikhub adapter `fetch_video_by_share_url` | `backend/app/adapters/tikhub.py` | ✅ |
| B6 | operator router 8 接口 | `backend/app/routers/operator_persona_writer.py` | ✅ |
| B7 | admin router 2 接口 | `backend/app/routers/admin_persona_writer.py` | ✅ |
| B8 | main.py 注册两个 router | `backend/app/main.py` | ✅ |
| B9 | conftest.py 加 AsyncSessionLocal patch | `backend/tests/conftest.py` | ✅ |
| B10 | 单测 + 集测 | 见下表 | ✅ |
| B11 | 任务文档 | 本文件 | ✅ |

## 三、API 设计

### 3.1 运营端接口（operator_persona_writer.py）

| 接口 | 用途 |
|------|------|
| GET `/api/tools/persona-writer/kols/personas` | Step 1 达人下拉（JOIN users 拿 creator_name）|
| POST `/api/tools/persona-writer/fetch-video` | Step 2.1 抖音分享链接解析（调 tikhub_adapter）|
| POST `/api/tools/persona-writer/evaluate-opening` | Step 2.4 AI 开头评估流式（light 模型）|
| POST `/api/tools/persona-writer/analyze-structure` | Step 3.1 对标结构拆解流式（light 模型）|
| POST `/api/tools/persona-writer/chat` | Step 3.3/3.4 写作+追问流式（heavy 模型）|
| POST `/api/tools/persona-writer/save-output` | 保存到 outputs 表 + OperationLog |
| POST `/api/tools/persona-writer/export-word` | 导出 .docx（StreamingResponse，不包信封）|
| GET `/api/tools/persona-writer/outputs` | 历史记录（账号隔离 WHERE created_by=current_user.id）|

### 3.2 管理端接口（admin_persona_writer.py）

| 接口 | 用途 |
|------|------|
| GET `/api/admin/persona-writer/configs` | 读配置（4 Prompt + 2 模型 ID + is_active）|
| PUT `/api/admin/persona-writer/configs/{config_key}` | 更新 4 Prompt + 2 模型 ID + is_active |

### 3.3 chat 接口关键流程

```
1. 读 DB persona_writer_configs WHERE config_key='default' AND is_active=true
2. 读 kols WHERE id=persona_id（persona + content_plan + name）
3. render_prompt(template, name, soul, content_plan, transcript, structure_analysis, topic, is_custom)
   → 先处理 {{is_custom}}/{{!is_custom}} 条件块，再正则替换占位符
4. yunwu_adapter.chat_stream(messages, db, model_id=heavy_model, feature='persona_writer_writing', user_id)
5. StreamingResponse media_type='text/plain'
6. BackgroundTask: 写 TaskJob + OperationLog（create_job=true 时）
7. adapter finally 自动写 ai_call_logs
```

### 3.4 fetch-video 接口关键流程

```
1. tikhub_adapter.fetch_video_by_share_url(share_url, db)
   → _extract_douyin_url → _resolve_short_url → GET /api/v1/douyin/web/fetch_one_video_by_share_url
2. 返回 {title, digg_count, aweme_id, play_url, likes_pass}
3. likes_pass = (digg_count >= 100000) 硬编码
4. 写 OperationLog（action='persona_writer_fetch_video'）
```

## 四、测试覆盖

### 4.1 单元测试

| 文件 | 用例数 | 关键点 |
|------|--------|--------|
| `tests/unit/services/test_persona_writer_prompt.py` | 16 | 7 占位符替换 + 双模式 is_custom 条件块 + 缺失 fallback + 多次出现 + 真实模板 + 防二次替换 |
| `tests/unit/services/test_tikhub_adapter.py` | +3 | fetch_video_by_share_url 成功/失败/URL 解析 |

### 4.2 operator 集成测试（test_operator_persona_writer.py，30 用例）

| 分类 | 用例数 | 关键点 |
|------|--------|--------|
| 鉴权 | 4 | 无 token / operator OK / admin OK / invalid token |
| personas | 3 | 空列表 / 有数据 / 含 creator_name 标签 |
| fetch-video | 5 | 成功 / 低赞 likes_pass=false / 空 URL / tikhub 错误 / 验 OperationLog |
| evaluate-opening | 3 | 成功流式 / 空 transcript / AI 失败 |
| analyze-structure | 3 | 成功流式 / 空 transcript / AI 失败 |
| chat | 5 | writing 成功 / iteration 成功 / persona 不存在 / 无效 scene / 空 messages |
| save-output | 3 | 成功+账号绑定 / 空 content / 账号隔离 |
| export-word | 2 | 成功返回 docx / 空 content |
| outputs | 2 | 分页 / 账号隔离 |

### 4.3 admin 集成测试（test_admin_persona_writer.py，9 用例）

| 分类 | 用例数 | 关键点 |
|------|--------|--------|
| 鉴权 | 4 | admin OK / operator forbidden / invalid / unauthenticated |
| GET configs | 1 | 返回种子配置（4 Prompt + 2 模型字段）|
| PUT configs | 4 | 更新 4 Prompt / 更新 model IDs / 不存在 404 / 写 OperationLog |

## 五、关键约定

- **4 Prompt 模板化**：DB 存 evaluation/analysis/writing/iteration 4 列，后端 `render_prompt()` 渲染
- **7 占位符 + 双模式**：`{{name}}` / `{{soul}}` / `{{content_plan}}` / `{{transcript}}` / `{{structure_analysis}}` / `{{topic}}` / `{{is_custom}}`
- **{{is_custom}} 条件块**：`{{is_custom}}...{{/is_custom}}` 和 `{{!is_custom}}...{{/!is_custom}}` 区分 custom vs default 模式
- **正则一次性替换**：`re.compile(r"\{\{\s*(name|soul|content_plan|transcript|structure_analysis|topic|is_custom)\s*\}\}")` 避免 soul 内容含 `{{name}}` 时二次替换
- **双模型**：light（claude-haiku-4-5，评估/拆解）+ heavy（claude-opus-4-6，写作/追问），admin 可配
- **点赞门槛硬编码**：`digg_count >= 100000`（业务铁律，不让 admin 改）
- **fetch-video / evaluate / analyze / chat / save-output / export-word 六接口分离**：各司其职
- **outputs 账号隔离**：查询 `WHERE created_by=current_user.id AND deleted_at IS NULL`
- **流式例外**：evaluate-opening / analyze-structure / chat 返回 text/plain 裸文本流（不包信封）
- **export-word 例外**：StreamingResponse（不包信封）
- **workspace_tools**：UPDATE status='online'（旧表已有 disabled 记录）
- **adapter 扩展**：tikhub.py 加 `fetch_video_by_share_url`，沿用 report_success/report_failure 模式

## 六、全量回归结果

- 单元测试：19/19 ✅（prompt 16 + tikhub +3）
- 集成测试：39/39 ✅（operator 30 + admin 9）
- convention_guard：6/6 ✅（红线守卫全过）
- 全量 pytest：**863 passed / 2 failed / 1 skipped**
  - 2 failed 是 `test_livestream_writer_file_parser` 的 `.pages` 解析（`ModuleNotFoundError: No module named 'snappy'`），已验证为基线预存问题，与本次改动无关

## 七、种子 Prompt 来源（旧版 page.tsx 提取改造）

| Prompt | 旧版位置 | 改造说明 |
|--------|---------|---------|
| evaluation_prompt | `checkOpening()` 第 232 行 inline systemPrompt | `${}` 不适用，无变量替换；改为 `{{transcript}}` |
| analysis_prompt | `analyzeStructure()` 第 262 行 inline systemPrompt | 改为 `{{transcript}}` |
| writing_prompt | `handleWrite()` 第 336-382 行 systemPrompt | `${selectedPersona.soul}` → `{{soul}}`；`${transcript}` → `{{transcript}}`；`${structureAnalysis}` → `{{structure_analysis}}`；`${topic}` → `{{topic}}`；`isCustomTopic ? ... : ...` 三元表达式 → `{{is_custom}}...{{/is_custom}}{{!is_custom}}...{{/!is_custom}}` |
| iteration_prompt | `handleChatSend()` 第 449-471 行 systemPrompt | 同 writing 改造方式 |
