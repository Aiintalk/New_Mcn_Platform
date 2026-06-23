# M2 Sprint 14 — 千川文案写作（qianchuan-writer）迁移需求文档

> 产出节点：节点 A
> 创建日期：2026-06-22
> 状态：已确认，待开发
> 对应分支：`migrate/qianchuan-writer`
> 旧架构路径：`Ai_Toolbox/qianchuan-writer-web/`（Next.js 单页，无独立后端）

---

## 一、工具概述

| 项目 | 说明 |
|------|------|
| 工具名 | 千川文案写作（qianchuan-writer） |
| 工具定位 | **围绕达人视角**的千川脚本仿写工具：用户选一个达人人设 → 上传该达人推广的产品卖点卡 → 粘贴现成千川爆款脚本 → AI 保留原版结构 100%，只把产品和视角换掉，产出"像这个达人语气"的新脚本 |
| 新路由前缀 | `/api/tools/qianchuan-writer`（运营端）/ `/api/admin/qianchuan-writer`（管理端）|
| 前端路由 | `/workspace/qianchuan-writer` |
| AI 模型默认 | `claude-opus-4-6-thinking`（DB 可配，留空时 fallback）|
| 外部依赖 | **仅 yunwu AI**（TikHub/OSS/ASR 在旧版是死代码，迁移时抛弃）|
| 文件支持 | `.txt / .md / .docx / .pdf / .xlsx / .pptx`（复用 `file_parser.py` 现成能力）|
| workspace_tools 注册 | tool_code = `qianchuan-writer`，初始 status = `dev` |

---

## 二、需求澄清记录（2026-06-22）

| 问题 | 结论 |
|------|------|
| 权限边界 | operator + admin 都能用（`require_operator`）|
| 达人选择范围 | `WHERE persona IS NOT NULL AND content_plan IS NOT NULL AND deleted_at IS NULL`；全公开可见 + 显示创建者标签（`created_by` JOIN users），预留未来"A 用户私享达人"扩展（零返工：改 WHERE 即可）|
| Prompt 管理方式 | DB 存带占位符模板（`{{name}}`/`{{soul}}`/`{{content_plan}}`），后端渲染时替换；管理端文本域直接编辑 |
| AI 模型管理 | DB 外键 `ai_models.id` + 管理端下拉选（从 `ai_models WHERE status='active'` 取），留空走默认 |
| 历史记录 | 每次生成保存一条到 `outputs` 表，通过 `created_by` 字段绑定账号；管理员可查全量，运营只查自己 |
| 产出格式 | **.txt + .docx 两个按钮都给**（.txt 沿用原版 Blob 下载，.docx 走 `word_export.py`）|
| 多轮追问 | 沿用原版（累积上下文 messages），不限轮数 |
| 工具初始状态 | `dev`（测试通过后管理端改 online）|
| 管理端 Tab 位置 | 挂 `WorkspaceConfigPage`（与其他 writer 一致），新建 `QianchuanWriterConfigTab.tsx` |
| 达人数据来源 | 旧架构本地仓库只有 2 个达人（孙知羽 v6.0、陶然 v2.0），不导入；功能上线后用户在 KolsPage 自行填充 `persona`/`content_plan` 字段 |
| 死代码处理 | `fetch-video` / `transcribe/upload` / `transcribe/poll` / `parse-product` / `personas/references` 5 个 route 直接抛弃 |
| 业务逻辑改动 | **零改动**。4 步向导、Prompt 铁律、必填校验、多轮追问全部保留，只换技术底座 |

---

## 三、变与不变

### 不变（业务逻辑核心）

- **4 步工作流顺序与交互**：选达人 → 加载产品 → 输入脚本 → 生成仿写
- **Prompt 铁律**：结构 100% 保留 + 产品卖点全替换 + 必须换成选定达人语气视角
- **必填校验**：达人必选、产品必填、脚本必填
- **多轮追问修改**：生成后可在输入框继续追问，累积上下文
- **达人预览**：选中达人后预览 soul 前 400 字
- **字数实时显示**：脚本输入框实时显示去空白字数
- **导出文件命名**：`千川仿写_${persona.name}_${productName || '终稿'}.txt/.docx`

### 变（技术底座切换）

| 维度 | 旧架构 | 新架构 |
|------|--------|--------|
| 鉴权 | 无 | JWT + `require_operator` |
| AI Key 来源 | 前端硬编码 yunwu endpoint | `service_credentials` 表 + yunwu adapter 凭证池 |
| Prompt 存储 | 前端硬编码 `page.tsx:93-113` | DB `qianchuan_writer_configs.system_prompt` |
| AI 模型 | 硬编码 `claude-opus-4-6-thinking` | DB `qianchuan_writer_configs.ai_model_id` FK |
| 人设来源 | 本地文件 `data/personas/*/soul.md` | `kols` 表 `persona`/`content_plan` 字段 |
| 历史记录 | 无（刷新丢失）| `outputs` 表 + 账号绑定（`created_by`）|
| 产出下载 | 仅 .txt（前端 Blob）| .txt（前端 Blob）+ .docx（后端 word_export）|
| 文件解析 | Mammoth/unpdf/XLSX/JSZip（前端 Next.js route）| 复用 `app/services/file_parser.py` |
| 日志 | 无 | ai_call_logs（adapter 自动）+ operation_logs（router 显式）|
| 抖音链接→ASR→自动转写工作流 | 5 个 route（死代码）| **抛弃** |

---

## 四、工作流步骤（4 步，完全保留）

| 步骤 | 用户操作 | 系统行为 |
|------|---------|---------|
| Step 1 · 选达人 | 下拉选一个达人人设（必选）| GET `/api/tools/qianchuan-writer/kols/personas`，查 kols 表 `persona` 和 `content_plan` 均非空且未删除的记录；返回 `id`/`name`/`soul`(前400字预览)/`creator_name`（JOIN users）|
| Step 2 · 加载产品 | 上传文件（.txt/.md/.docx/.pdf/.xlsx/.pptx）**或** 直接粘贴（必填）| POST `/api/tools/qianchuan-writer/parse-file`（FormData），后端 `file_parser` 解析为纯文本返回；前端展示文本内容 + 字数 |
| Step 3 · 输入脚本 | 粘贴原版千川脚本（必填）| 前端实时显示去空白字数 |
| Step 4 · 生成仿写 | 点"生成仿写脚本"→ 流式输出 → 可多轮追问 → 保存历史 → 导出 .txt/.docx | POST `/api/tools/qianchuan-writer/chat`（流式 SSE）；POST `/api/tools/qianchuan-writer/save-output`（保存历史）；POST `/api/tools/qianchuan-writer/export-word`（.docx 下载）|

---

## 五、API 接口契约（运营端）

### 5.1 GET `/api/tools/qianchuan-writer/kols/personas`

- **认证**：JWT（operator / admin）
- **用途**：Step 1 达人下拉列表
- **返回**：

```json
{
  "success": true,
  "code": 200,
  "message": "",
  "data": [
    {
      "id": 123,
      "name": "孙知羽",
      "soul_preview": "前 400 字...",
      "creator_name": "系统预设"  // created_by IS NULL 时显示"系统预设"，否则 JOIN users.username
    }
  ]
}
```

- **SQL**：`SELECT k.id, k.name, LEFT(k.persona, 400) AS soul_preview, COALESCE(u.username, '系统预设') AS creator_name FROM kols k LEFT JOIN users u ON k.created_by = u.id WHERE k.persona IS NOT NULL AND k.content_plan IS NOT NULL AND k.deleted_at IS NULL AND k.status = 'active' ORDER BY k.name`

### 5.2 POST `/api/tools/qianchuan-writer/parse-file`

- **认证**：JWT（operator / admin）
- **入参**：`multipart/form-data`，字段 `file`
- **用途**：Step 2 解析产品卖点卡文件
- **返回**：

```json
{
  "success": true,
  "code": 200,
  "message": "",
  "data": { "text": "解析后的纯文本", "word_count": 1234 }
}
```

- **实现**：复用 `app/services/file_parser.py` 的通用解析能力（支持 .txt/.md/.docx/.pdf/.xlsx/.pptx）

### 5.3 POST `/api/tools/qianchuan-writer/chat`（流式）

- **认证**：JWT（operator / admin）
- **Content-Type**：`application/json`
- **入参**：

```json
{
  "messages": [
    {"role": "user", "content": "用户输入（含产品 + 脚本 + 指令）"}
  ],
  "persona_id": 123,
  "create_job": true,
  "job_context": {
    "product_name": "产品名（前端从产品文本提取或留空）",
    "original_script_length": 1234
  }
}
```

- **行为**：
  1. 从 DB 读 `qianchuan_writer_configs WHERE config_key='default' AND is_active=true`，拿 `system_prompt` 模板 + `ai_model_id`
  2. 从 `kols` 表读 `persona_id` 对应的 `persona`（soul 全文）+ `content_plan` + `name`
  3. 后端模板渲染：替换 `{{name}}`/`{{soul}}`/`{{content_plan}}` 占位符
  4. 调 `yunwu_adapter.chat_stream(messages, db, model_id, feature='qianchuan_writer_chat', user_id=current_user.id)`
  5. 返回 `StreamingResponse`（media_type `text/plain`），流式输出 assistant 内容
  6. adapter finally 块自动写 `ai_call_logs`
  7. router 显式写 `operation_logs`（action=`qianchuan_writer_chat`）

- **响应头**：`X-Task-Id: <task_job_id>`（用于后续 save-output 关联）

### 5.4 POST `/api/tools/qianchuan-writer/save-output`

- **认证**：JWT（operator / admin）
- **入参**：

```json
{
  "task_id": 123,
  "title": "千川仿写_孙知羽_生发精华",
  "content": "完整仿写脚本文本",
  "product_name": "生发精华"
}
```

- **行为**：
  1. 写 `outputs` 表：`tool_code='qianchuan-writer'`、`tool_name='千川文案写作'`、`created_by=current_user.id`、`content` 为完整文本
  2. 写 `operation_logs`（action=`qianchuan_writer_save_output`）
  3. 返回标准信封 `{success: true, data: {output_id: 123}}`

### 5.5 POST `/api/tools/qianchuan-writer/export-word`

- **认证**：JWT（operator / admin）
- **入参**：

```json
{
  "content": "完整仿写脚本文本",
  "filename": "千川仿写_孙知羽_生发精华"
}
```

- **行为**：调 `app/services/word_export.py::markdown_to_docx_bytes(content, filename)`，返回 `StreamingResponse`（media_type `application/vnd.openxmlformats-officedocument.wordprocessingml.document`）
- **响应头**：`Content-Disposition: attachment; filename*=UTF-8''<url_encoded>.docx`
- **信封例外**：文件流不包标准信封（红线 #1 例外）

### 5.6 GET `/api/tools/qianchuan-writer/outputs`（历史记录）

- **认证**：JWT（operator / admin）
- **入参**：Query `page=1&page_size=20`
- **行为**：`SELECT * FROM outputs WHERE tool_code='qianchuan-writer' AND created_by=current_user.id AND deleted_at IS NULL ORDER BY created_at DESC`
- **返回**：标准信封分页 `{data: {items: [...], total: 123, page: 1, page_size: 20}}`

---

## 六、API 接口契约（管理端）

### 6.1 GET `/api/admin/qianchuan-writer/configs`

- **认证**：JWT（admin）
- **返回**：`qianchuan_writer_configs` 表全部记录（通常只有 1 条 `config_key='default'`）

### 6.2 PUT `/api/admin/qianchuan-writer/configs/{config_key}`

- **认证**：JWT（admin）
- **入参**：

```json
{
  "system_prompt": "你是千川脚本仿写专家...{{name}}...{{soul}}...",
  "ai_model_id": 5,
  "is_active": true
}
```

- **行为**：更新 `system_prompt` / `ai_model_id` / `is_active`，写 `operation_logs`（action=`admin_update_qianchuan_writer_config`）

---

## 七、数据模型

### 7.1 新建表 `qianchuan_writer_configs`

```sql
CREATE TABLE IF NOT EXISTS qianchuan_writer_configs (
  id            BIGSERIAL PRIMARY KEY,
  config_key    VARCHAR(64) NOT NULL UNIQUE,  -- 'default'
  system_prompt TEXT,
  ai_model_id   BIGINT REFERENCES ai_models(id) ON DELETE SET NULL,
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 种子数据：从旧架构 page.tsx:93-113 buildSystemPrompt 原文迁移（含 {{name}}/{{soul}}/{{content_plan}} 占位符）
INSERT INTO qianchuan_writer_configs (config_key, system_prompt, ai_model_id, is_active)
VALUES ('default', $TEMPLATE_CONTENT, NULL, TRUE);
```

### 7.2 workspace_tools 注册

```sql
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, sort_order)
VALUES ('qianchuan-writer', '千川文案写作', '脚本创作', '围绕达人视角的千川脚本仿写工具', 'dev', 100)
ON CONFLICT (tool_code) DO UPDATE SET tool_name = EXCLUDED.tool_name;
```

### 7.3 复用现有表

- `kols`（已有，字段 `persona`/`content_plan`/`created_by`/`owner_id`/`status`）
- `outputs`（已有，字段 `tool_code`/`tool_name`/`created_by`/`content`）
- `ai_models`（已有）
- `ai_call_logs`（已有，adapter 自动写）
- `operation_logs`（已有）

### 7.4 迁移文件

- 文件：`backend/migrations/030_qianchuan_writer.sql`
- 内容：CREATE TABLE + INSERT 种子 Prompt + INSERT workspace_tools

---

## 八、前端契约

### 8.1 新建文件

| 文件 | 用途 |
|------|------|
| `frontend/src/pages/operator/QianchuanWriterPage.tsx` | 运营端主页面（4 步向导）|
| `frontend/src/api/qianchuanWriter.ts` | API 封装（6 函数：getPersonas/parseFile/chatStream/saveOutput/exportWord/getOutputs + 管理端 getConfig/updateConfig）|
| `frontend/src/types/qianchuanWriter.ts` | TypeScript 类型定义 |
| `frontend/src/pages/admin/QianchuanWriterConfigTab.tsx` | 管理端配置 Tab（参照 TiktokWriterConfigTab）|

### 8.2 主页面交互（4 步向导）

```
┌─────────────────────────────────────────────┐
│ Step 1 · 选达人                              │
│   [下拉: 系统预设 / 用户添加：xxx]            │
│   [预览: soul 前 400 字]                     │
├─────────────────────────────────────────────┤
│ Step 2 · 加载产品                            │
│   [拖拽/点击上传] 或 [切换粘贴模式]           │
│   [展示解析结果 + 字数]                      │
├─────────────────────────────────────────────┤
│ Step 3 · 输入脚本                            │
│   [textarea: 粘贴原版千川脚本]               │
│   [实时字数: 1234 字]                        │
├─────────────────────────────────────────────┤
│ Step 4 · 生成仿写                            │
│   [按钮: 生成仿写脚本]                       │
│   [流式输出区域 + 输入框（多轮追问）]         │
│   [按钮: 保存到历史 / 导出 .txt / 导出 .docx] │
└─────────────────────────────────────────────┘
```

### 8.3 路由注册

- `App.tsx` 加：`<Route path="/workspace/qianchuan-writer" element={<QianchuanWriterPage />} />`（React.lazy）
- `WorkspaceConfigPage.tsx` 加：`QianchuanWriterConfigTab` 挂载

### 8.4 红线合规

- **红线 #3**：所有 JSON 调用走 `request.ts`（`import { get, post } from './request'`）。例外：chatStream（SSE 流式）、parse-file（FormData）、export-word（Blob）

---

## 九、测试要求

### 9.1 后端单元测试（`tests/unit/services/test_qianchuan_writer_prompt.py`）

- Prompt 模板渲染：占位符替换正确（`{{name}}`/`{{soul}}`/`{{content_plan}}`）
- 占位符缺失时不崩溃（fallback 空字符串）

### 9.2 后端集成测试（`tests/integration/routers/test_operator_qianchuan_writer.py`）

- 4 个鉴权测试（无 token / operator OK / admin OK / invalid token）
- `GET /kols/personas` 空列表 + 有数据
- `POST /parse-file` 成功 + 不支持格式
- `POST /chat` 流式成功 + AI 失败
- `POST /save-output` 成功 + 账号绑定校验（用户 A 查不到用户 B 的 output）
- `POST /export-word` 返回 docx
- `GET /outputs` 分页 + 账号隔离

### 9.3 后端集成测试（`tests/integration/routers/test_admin_qianchuan_writer.py`）

- 4 个鉴权测试（admin OK / operator forbidden / invalid / unauthenticated）
- `GET /configs` 返回种子配置
- `PUT /configs/default` 更新 Prompt + ai_model_id

### 9.4 前端测试（`src/__tests__/components/pages/QianchuanWriterPage.test.tsx`）

- 4 步向导渲染
- Step 1 达人下拉 + 预览
- Step 2 文件上传 + 粘贴切换
- Step 3 字数实时显示
- Step 4 流式输出 + 多轮追问
- 保存历史按钮调用 saveOutput
- 导出 .txt 按钮触发 Blob 下载
- 导出 .docx 按钮调用 exportWord
- 管理端 ConfigTab 渲染 + 表单提交

---

## 十、不在本次范围

1. **抖音链接解析 + ASR 自动转写** — 旧版 5 个死代码 route，本次抛弃，不迁
2. **达人数据导入** — 孙知羽/陶然的 soul.md 不导入，用户自行在 KolsPage 填充
3. **A 用户私享达人** — 当前全公开，仅预留 `created_by`/`owner_id` 字段，未来改 WHERE 即可
4. **selling-point-extractor 联动** — 产品卖点卡不支持从 selling_point_extractions 表导入，保持独立
5. **温度/max_tokens 配置** — DB 不暴露，用 adapter 默认
6. **产品卖点卡文件大小/脚本长度上限** — 不设硬上限（用 ai_call_logs 监控异常）

---

## 十一、验收标准（DoD）

### 11.1 功能验收

- [ ] 运营端 `/workspace/qianchuan-writer` 能打开 4 步向导页面
- [ ] Step 1 下拉显示所有 `persona`+`content_plan` 非空的达人 + 创建者标签
- [ ] Step 2 支持 6 种文件格式上传 + 粘贴模式切换
- [ ] Step 3 字数实时显示
- [ ] Step 4 流式生成 + 多轮追问可用
- [ ] 历史记录按账号隔离，用户只看自己的
- [ ] .txt 和 .docx 两个下载按钮都可用
- [ ] 管理端 `WorkspaceConfigPage` 能编辑 Prompt + 选 AI 模型
- [ ] 管理端改 Prompt 后立即生效（下次 chat 用新 Prompt）

### 11.2 红线合规

- [ ] 迁移红线 7 条全部满足
- [ ] 一票否决 9 条全部避开
- [ ] 不触碰冻结区（`app/core/`、`src/api/request.ts`、`src/store/` 等）
- [ ] yunwu/tikhub/oss/asr adapter 零改动

### 11.3 日志/契约

- [ ] 每次 AI 调用产生 `ai_call_logs` 记录（adapter 自动）
- [ ] 每次 chat/save-output 产生 `operation_logs`（router 显式）
- [ ] 每次 save-output 产生 `outputs` 记录（账号绑定）
- [ ] 管理端「外部服务日志页」可见 AI 调用日志
- [ ] 管理端「操作审计日志页」可见用户操作日志
- [ ] 管理端「产出中心」可见千川产出
- [ ] Base_API / Base_Database 契约文档同步更新

### 11.4 测试

- [ ] 后端单元测试 + 集成测试全绿（含鉴权、流式、账号隔离）
- [ ] 前端组件测试全绿（4 步向导、多轮追问、保存/导出）
- [ ] `tsc --noEmit` 退出码 0
- [ ] `pytest --gate` 覆盖率门禁通过

### 11.5 文档落地（节点 B++）

- [ ] 任务文档（前后端各 1 份）落 `backend/docs/tasks/` 和 `frontend/docs/tasks/`
- [ ] 测试报告落 `backend/docs/tests/`
- [ ] README 同步更新（根 + backend + frontend，文件计数 +1）
- [ ] PM 记忆与状态 M2 加本次 Sprint 记录
- [ ] workspace_tools 状态从 `dev` 改 `online`（测试通过后）

---

## 十二、关键技术决策

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| 1 | 工作流 | 4 步向导（忠于原版）| 业务逻辑不变 |
| 2 | Prompt 模板化 | DB 存 `{{name}}`/`{{soul}}`/`{{content_plan}}` 占位符 | 管理端可编辑，运行时渲染 |
| 3 | AI 模型 | DB FK `ai_models`，留空走默认 | 与其他 writer 一致，复用现有 AI 管理页 |
| 4 | 人设来源 | `kols` 表 `persona`+`content_plan` | 数据库化，替代文件系统 |
| 5 | 历史记录 | `outputs` 表，`created_by` 绑账号 | 红线 #2 强制 + 9 否决 #3（不看他人数据）|
| 6 | 产出格式 | .txt（前端 Blob）+ .docx（后端 word_export）| 用户明确要求两个都给 |
| 7 | 文件解析 | 复用 `app/services/file_parser.py` | 避免重复造轮子 |
| 8 | 死代码 | 抛弃 5 个 route | 旧版前端未调用，无价值 |
| 9 | 私享达人预留 | 仅用现有 `created_by`/`owner_id` 字段显示标签 | 未来改一行 SQL 即可启用访问控制 |
| 10 | 工具状态 | 初始 `dev`，测试后改 `online` | 与其他迁移工具一致 |

---

## 十三、CLAUDE.md 红线自检

| 红线 | 状态 | 说明 |
|------|------|------|
| #1 标准信封 | ✅ | 6 个 JSON 接口走 success_response；export-word 例外（文件流）|
| #2 OperationLog | ✅ | chat/save-output/update-config 三处显式写 |
| #3 前端走 request.ts | ✅ | qianchuanWriter.ts 用 get/post；SSE/FormData/Blob 例外 |
| #4 契约同步 | ✅ | 本文档即契约，Base_API/Base_Database 同步 |
| #5 README 更新 | ✅ | 验收清单 11.5 明确 |
| #6 AiCallLog 由 adapter 写 | ✅ | 调 yunwu adapter.chat_stream，finally 块自动 |
| #7 AsyncSessionLocal | ✅ | chat 接口用 BackgroundTask 写 outputs，参照 tiktok-writer 模式，需加 conftest patch |

**9 条一票否决**：无新增触发。outputs 表用软删（`deleted_at`），账号隔离（`WHERE created_by=current_user.id`）。
