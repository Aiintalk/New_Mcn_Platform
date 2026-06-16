# M2 Sprint 08 — 直播脚本仿写（livestream-writer）迁移需求文档

> 产出节点：节点 A
> 创建日期：2026-06-15
> 状态：已确认，待开发

---

## 一、工具概述

| 项目 | 说明 |
|------|------|
| 工具名 | 直播脚本仿写（livestream-writer） |
| 原工具路径 | `Ai_Toolbox/livestream-writer-web/`（Next.js，端口 3013） |
| 新路由前缀 | `/api/tools/livestream-writer` |
| 功能描述 | 选达人 + 上传产品卖点卡 + 上传对标直播间文案，AI 生成完整7模块开播方案（标题/封面/简介/讲解脚本/循环话术/贴纸/筹备清单），支持多轮对话修改，导出 .txt |
| AI 模型 | `claude-opus-4-6-thinking`（默认） |
| 外部依赖 | 无（无 TikHub / OSS / ASR） |
| 文件支持 | `.txt / .md / .docx / .pages`，**不支持 .pdf** |

---

## 二、需求澄清记录（2026-06-15）

| 问题 | 结论 |
|------|------|
| outputs 写入方式 | 方案 A：后端 chat 接口 BackgroundTask 积累 chunks，生成结束后一次性写 task_jobs + outputs |
| parse-file 函数 | 新增 `parse_livestream_writer_file`（独立于 qianchuan-review 版本，逻辑等价但保持隔离） |
| kols/personas 查询条件 | `WHERE content_plan IS NOT NULL AND persona IS NOT NULL AND deleted_at IS NULL` |
| 管理端配置页 | 需要，参考 qianchuan-review 的配置 Tab 模式，支持配置 system_prompt 和 ai_model_id |

---

## 三、变与不变

**不变：**
- 所有工作流步骤（4步）
- System Prompt 两个版本原文（首次生成 / 多轮迭代）
- autoTrimIfTooLong 逻辑（前端）
- .txt 导出（前端 Blob，不经过后端）
- .pages 文件解析逻辑（含日历噪音过滤，与 qianchuan-review 一致）

**变（新增）：**
- JWT 认证
- AI 调用改走 `credentials` 表 Key 池（yunwu adapter）
- 写 ai_call_logs（adapter 层自动）
- 写 task_jobs + outputs（BackgroundTask）
- 达人列表改查 `kols` 表
- System Prompt 支持管理端可配置（存 `livestream_writer_configs` 表）

---

## 四、工作流步骤（4步，完全保留）

| 步骤 | 用户操作 | 系统行为 |
|------|---------|---------|
| Step 1 · 选达人 | 从下拉列表选择达人 | GET `/kols/personas`，查 kols 表 content_plan 和 persona 均非空的记录 |
| Step 2 · 粘贴卖点 | 上传文件或粘贴卖点卡文本；选卖点顺序（3种） | POST `/parse-file` 解析；前端正则提取产品名；展示产品名和卖点内容 |
| Step 3 · 粘贴对标 | 上传对标直播间文案文件或粘贴；确认锁定 | POST `/parse-file` 解析；前端显示字数；用户确认后锁定 |
| Step 4 · 仿写脚本 | 点击"生成开播方案"→ 多轮对话修改 → 导出终稿 | POST `/chat` 流式生成；前端自动检查字数超限（autoTrimIfTooLong）；导出 .txt（浏览器 Blob） |

---

## 五、API 接口

### 5.1 POST `/api/tools/livestream-writer/chat`

- **认证**：JWT（operator / admin）
- **入参（JSON body）**：

```json
{
  "messages": [{"role": "user"|"assistant", "content": "string"}],
  "systemPrompt": "string（由前端动态构建，含变量已注入）",
  "model": "string（可选，默认 claude-opus-4-6-thinking）",
  "createJob": true,
  "jobContext": {
    "productName": "string",
    "personaName": "string",
    "spOrder": "string（如：背书→机制→种草）",
    "refLength": 1234,
    "finalContent": "string（最终全文，仅在最后一轮传入）"
  }
}
```

- **出参**：`text/plain` 流式文本（raw text stream，非 SSE）
- **重试策略**：429 时最多重试 5 次，指数退避 5s（5s/10s/15s/20s/25s）
- **BackgroundTask**：积累 chunks → 生成结束后写 task_jobs + outputs（仅 createJob=true 时）

### 5.2 POST `/api/tools/livestream-writer/parse-file`

- **认证**：JWT（operator / admin）
- **入参**：`multipart/form-data`，字段名 `file`
- **出参**：`{ "text": "string", "filename": "string" }`
- **支持格式**：`.txt / .md / .docx / .pages`，不支持 `.pdf`
- **parse-file 函数**：新增 `parse_livestream_writer_file`（含日历噪音过滤，逻辑与 qianchuan-review 版等价）

### 5.3 GET `/api/tools/livestream-writer/kols/personas`

- **认证**：JWT（operator / admin）
- **SQL**：`SELECT id, name, persona, content_plan FROM kols WHERE content_plan IS NOT NULL AND persona IS NOT NULL AND deleted_at IS NULL ORDER BY name`
- **出参**：`{ "personas": [{ "name": "...", "soul": "...", "contentPlan": "..." }] }`

### 5.4 管理端接口（admin 角色）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/livestream-writer/configs` | 配置列表 |
| PUT | `/api/admin/livestream-writer/configs/{key}` | 更新配置 |

---

## 六、数据库变更

### 新增表 `livestream_writer_configs`

```sql
CREATE TABLE livestream_writer_configs (
  id            SERIAL PRIMARY KEY,
  config_key    VARCHAR(50)   NOT NULL UNIQUE,
  ai_model_id   INT           REFERENCES ai_models(id) ON DELETE SET NULL,
  system_prompt TEXT,
  is_active     BOOLEAN       NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ   NOT NULL DEFAULT now()
);
```

config_key 两条：`generate`（首次生成）、`iterate`（多轮迭代）

### workspace_tools 注册

```sql
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, tags, sort_order)
VALUES ('livestream-writer', '直播脚本仿写', '内容创作', '...', 'online', '...', ...)
ON CONFLICT (tool_code) DO NOTHING;
```

### task_jobs 写入字段

| 字段 | 值 |
|------|------|
| tool_code | `'livestream-writer'` |
| tool_name | `'直播脚本仿写'` |
| status | `'completed'` |
| input_payload | `{"productName": "...", "personaName": "...", "spOrder": "...", "refLength": 数字}` |
| created_by | 当前登录用户 ID |

### outputs 写入字段

| 字段 | 值 |
|------|------|
| title | `"开播方案 · {productName} · {personaName}"` |
| tool_code | `'livestream-writer'` |
| content | 最终开播方案全文 |
| word_count | 去空格后字符数 |
| task_id | 关联 task_jobs.id |
| created_by | 当前登录用户 ID |

---

## 七、前端特殊逻辑（保留在前端）

### autoTrimIfTooLong

生成完成或每轮对话结束后，前端检查讲解脚本字数是否超出对标文案字数。若超出，**自动追加压缩请求**：

```
脚本超字数了。当前约{actual}字，上限{targetMax}字，需要砍掉{actual - targetMax}字以上。
请精简内容，删减冗余表达，压到{targetMax}字以内。直接输出压缩后的完整脚本+自检表，不要解释。
```

字数计算：`text.replace(/\s/g, '').length`

### .txt 导出

```js
const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
a.download = `开播方案_${product.name || '终稿'}.txt`
```

---

## 八、管理端配置页

- 挂载在 `ServiceConfigPage.tsx` 的 Tab 列表，新增 Tab「直播脚本仿写」
- 显示两条配置（generate / iterate），支持编辑 system_prompt 和绑定 ai_model_id
- 参考 `QianchuanReviewConfigTab.tsx` 实现

---

## 九、不做清单

- 不实现 .pdf 文件解析
- 不实现 Word 导出（保留 .txt）
- 不把 autoTrimIfTooLong 移到后端
- 不实现历史记录查看
- 不修改任何 System Prompt 原文

---

## 十、覆盖率目标

| 模块 | 目标 |
|------|------|
| `app/routers/operator_livestream_writer.py` | ≥ 70% |
| `app/routers/admin_livestream_writer.py` | ≥ 70% |
| `app/services/file_parser.py`（新增函数） | ≥ 90% |
| 整体模块 | ≥ 75% |
