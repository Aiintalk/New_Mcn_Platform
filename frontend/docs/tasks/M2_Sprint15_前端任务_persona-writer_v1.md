# M2 Sprint 15 — 前端任务：人设脚本仿写（persona-writer）

> 状态：**已完成**（待 PM 签收 + 推 PR）
> 完成日期：2026-06-23
> 对应需求文档：`docs/pm/M2_Sprint15_persona-writer_需求文档.md`
> 对应分支：`migrate/persona-writer`

---

## 一、范围（本次前端任务）

涵盖人设脚本仿写工具迁移的所有前端工作：
- `types/personaWriter.ts` 类型定义
- `api/personaWriter.ts` 10 函数（8 运营端 + 2 管理端）
- `PersonaWriterPage.tsx` 3 步向导主页面（重写 placeholder）
- `PersonaWriterConfigTab.tsx` 管理端配置 Tab（4 Prompt + 2 模型 + Switch）
- `WorkspaceConfigPage.tsx` Tab 注册
- `PersonaWriterPage.test.tsx` 19 用例全绿
- 全量回归 157 passed / 0 failed，`tsc --noEmit` exit 0

## 二、任务清单

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| F1 | 类型定义 + API 层（10 函数）| `frontend/src/types/personaWriter.ts` + `frontend/src/api/personaWriter.ts` | ✅ |
| F2 | 运营端 3 步向导主页面（重写 placeholder）| `frontend/src/pages/operator/PersonaWriterPage.tsx` | ✅ |
| F3 | 管理端配置 Tab | `frontend/src/pages/admin/PersonaWriterConfigTab.tsx` | ✅ |
| F4 | App.tsx 路由确认（已存在）| `frontend/src/App.tsx` | ✅ |
| F5 | WorkspaceConfigPage Tab 注册 | `frontend/src/pages/admin/WorkspaceConfigPage.tsx` | ✅ |
| F6 | 组件测试 19 用例 | `frontend/src/__tests__/components/pages/PersonaWriterPage.test.tsx` | ✅ |
| F7 | 任务文档（本文件）| `frontend/docs/tasks/M2_Sprint15_前端任务_persona-writer_v1.md` | ✅ |

## 三、PersonaWriterPage 实现要点

### 3.1 3 步向导业务逻辑（忠于需求文档 §四）

| Step | 用户操作 | 关键交互 |
|------|---------|---------|
| 1. 加载风格 | 下拉选达人（必选）| 显示 content_plan 前 8 行预览 |
| 2. 对标验证 | 2.1 粘贴抖音链接 → POST /fetch-video<br>2.2 显示点赞 + ✅/❌（门槛 ≥100,000 硬编码）<br>2.3 粘贴文案<br>2.4 点评估 → POST /evaluate-opening 流式<br>2.5 同意/不同意 | 点赞✅ + 评估✅ + 同意 → 进 Step 3；任意❌留在 Step 2 |
| 3. 仿写创作 | 3.1 POST /analyze-structure 流式拆解<br>3.2 💡custom / 🤖default 双选<br>3.3 POST /chat scene=writing 流式写作<br>3.4 多轮追问（可贴图）POST /chat scene=iteration<br>3.5 终稿编辑（手动改 + 复制对标原文前 2-3 句提示）<br>3.6 导出 .docx / .txt | 3 个动作按钮：保存历史 / .txt / .docx |

### 3.2 质量门判定逻辑

```
likesOk = videoInfo.likes_pass === true
evaluationPassed = evaluationResult 含"通过"且不含"不通过"
qualityGateOk = likesOk && evaluationPassed && userAgreeEvaluation === true
```

### 3.3 双选题模式

- 💡 **custom 模式**：用户输入选题想法（必填），POST /chat body 含 `topic_mode='custom'` + `topic=用户输入`
- 🤖 **default 模式**：系统自动生成默认选题（前端显示"将基于对标原文结构 + 人格档案自动生成"），POST /chat body 含 `topic_mode='default'` + `topic=''`

### 3.4 图片上传（复用通用 /api/files）

多轮追问用户贴图时：前端 `input[type=file]` → `POST /api/files`（FormData）→ 拿 URL → 放进 messages content 的 `image_url` 字段 → 调 /chat。不新增专用上传接口（决策 #15）。

### 3.5 终稿编辑提示

Step 3.5 终稿编辑 textarea 上方显示：
> 💡 提示：建议手动复制对标原文前 2-3 句，粘贴替换本脚本开头，确保吸引力对齐。

并展示对标原文前 3 句（可复制）。

### 3.6 导出文件命名

```
人设脚本_${persona.name}_${topic || '终稿'}.txt
人设脚本_${persona.name}_${topic || '终稿'}.docx
```

- `.txt`：前端 Blob 下载（不走后端）
- `.docx`：调 `/api/tools/persona-writer/export-word` 返回 StreamingResponse

### 3.7 CSS 规范

- 使用项目 CSS 变量（`var(--brand)` / `card` / `btn` 等）
- **禁止 Tailwind class**（项目未安装）
- 使用 Ant Design 5 组件（Steps / Select / Input.TextArea / Radio / Button / App.useApp）

## 四、PersonaWriterConfigTab 实现要点

参照 `QianchuanWriterConfigTab.tsx` 模式，字段更丰富：

| 字段 | 组件 | 说明 |
|------|------|------|
| `evaluation_prompt` | TextArea rows=8 | 开头评估 Prompt（light 模型）|
| `analysis_prompt` | TextArea rows=8 | 结构拆解 Prompt（light 模型）|
| `writing_prompt` | TextArea rows=16 | 写作 Prompt（含 `{{is_custom}}...{{/is_custom}}` 块语法）|
| `iteration_prompt` | TextArea rows=12 | 追问 Prompt（heavy 模型）|
| `light_model_id` | Select allowClear | 评估/拆解用 AI 模型（默认 claude-haiku-4-5）|
| `heavy_model_id` | Select allowClear | 写作/追问用 AI 模型（默认 claude-opus-4-6）|
| `is_active` | Switch | 配置启用开关 |

调用：
- GET `/api/admin/persona-writer/configs`（通常返回 1 条 config_key='default'）
- PUT `/api/admin/persona-writer/configs/default`

Modal 使用 `destroyOnHidden`（antd 5，不用 `destroyOnClose`）。

## 五、API 层 10 函数

| 函数 | 方法 | 路径 | 例外 |
|------|------|------|------|
| `getPersonas()` | GET | `/api/tools/persona-writer/kols/personas` | — |
| `fetchVideo(share_url)` | POST | `/api/tools/persona-writer/fetch-video` | — |
| `evaluateOpeningStream(transcript, onChunk)` | POST | `/api/tools/persona-writer/evaluate-opening` | SSE fetch |
| `analyzeStructureStream(transcript, onChunk)` | POST | `/api/tools/persona-writer/analyze-structure` | SSE fetch |
| `chatStream(body, onChunk)` | POST | `/api/tools/persona-writer/chat` | SSE fetch |
| `saveOutput(body)` | POST | `/api/tools/persona-writer/save-output` | — |
| `exportWord(body)` | POST | `/api/tools/persona-writer/export-word` | Blob |
| `getOutputs(page,pageSize)` | GET | `/api/tools/persona-writer/outputs` | — |
| `getConfigs()` | GET | `/api/admin/persona-writer/configs` | — |
| `updateConfig(configKey, payload)` | PUT | `/api/admin/persona-writer/configs/${configKey}` | — |

**红线 #3 合规**：所有 JSON 调用走 `request.ts`（`import { get, post, put } from './request'`）。例外：SSE 3 个 + Blob 1 个。

**与 qianchuan-writer API 层的关键差异**：persona-writer 的流式函数接收 `onChunk` 回调参数（内部用 `readPlainStream` helper 封装 reader 逻辑），返回 `Promise<string>`（完整文本）。qianchuan-writer 的 chatStream 返回原始 `Promise<Response>`。这一设计决策让调用方代码更简洁（不需要重复写 reader 循环）。

## 六、测试覆盖（PersonaWriterPage.test.tsx，19 用例）

### PersonaWriterPage（16 用例）

| 用例 | 说明 |
|------|------|
| 3 步向导渲染 | 3 个 Step 标签可见 |
| Step 1 达人下拉 + 预览 | 列表渲染 + 选中后预览 |
| Step 2 抖音链接解析 + 点赞达标 ✅ | fetchVideo 调用 + 250,000 赞 + 达标 |
| Step 2 点赞不达标 ❌ | 50,000 赞 + 未达门槛 |
| Step 2 文案粘贴 + AI 评估流式 | evaluateOpeningStream mock + 流式渲染 |
| 质量门判定 — 全 ✅ | 点赞 + 评估 + 同意三件套全过 |
| 质量门判定 — 点赞 ❌ 按钮禁用 | likesOk=false 时下一步 disabled |
| Step 3 结构拆解流式 | analyzeStructureStream mock |
| Step 3 双选题切换 | 💡/🤖 Radio 切换显示不同输入框 |
| Step 3 写作流式 | chatStream scene=writing mock |
| Step 3 多轮追问输入框 | 生成完成后追问输入框可见 |
| Step 3 图片上传控件 | input[type=file] 可见 |
| Step 3 终稿编辑提示 | 显示手动复制对标原文提示 |
| 保存历史按钮 | 调 saveOutput API |
| 导出 .txt 按钮 | 触发 Blob 下载 |
| 导出 .docx 按钮 | 调 exportWord API |

### PersonaWriterConfigTab（3 用例）

| 用例 | 说明 |
|------|------|
| ConfigTab 渲染 | 配置项加载 + 字段可见 |
| ConfigTab 编辑 Modal 打开 | 4 Prompt + 2 模型 + Switch 全可见 |
| ConfigTab 表单提交 | 调 updateConfig |

## 七、关键约定

- 所有 JSON 调用走 `request.ts`（红线 #3），例外：SSE / Blob
- TypeScript 类型检查通过（`npx tsc --noEmit` exit 0）
- antd 5 用 `destroyOnHidden` 不用 `destroyOnClose`
- antd `message` 用 `App.useApp()` hook（不用静态方法）
- 禁止 Tailwind class（项目未装）
- 点赞门槛 `100000` 硬编码（业务铁律，不让 admin 改）
- 图片上传复用通用 `/api/files`（不新增专用接口）

## 八、全量回归结果

- 组件测试：**19/19 ✅**（PersonaWriterPage 16 + ConfigTab 3）
- 全量 vitest：**157 passed / 0 failed**（18 个测试文件全绿）
- TypeScript：`npx tsc --noEmit` **exit 0**
- conventionGuard（红线 #3）：**通过**

## 九、实施过程中的技术决策

1. **流式 API 用 onChunk 回调**：persona-writer 的 3 个流式函数（evaluateOpeningStream / analyzeStructureStream / chatStream）接收 `onChunk: (full: string) => void` 参数，内部封装 `readPlainStream` helper。比 qianchuan-writer 返回原始 Response 更简洁，调用方不需要重复写 reader 循环
2. **conventionGuard 注释标记**：每个 SSE fetch 调用前加注释 `// SSE 流式：resp.body.getReader()（例外不走 request.ts）`，确保守卫扫描窗口内命中 `getReader` 关键词
3. **AntD Button 两字空格**：AntD 自动在"解析"等两字按钮文本间加空格，测试用 `/解\s*析/` 正则匹配
4. **getAllByText 替代 getByText**：当文本同时出现在 message warning 和持久 DOM 元素中时（如点赞数、评估结果），用 `getAllByText` + `length > 0` 避免多元素冲突
5. **三接口分离**：chat / save-output / export-word 各自独立（同 qianchuan-writer 模式）
6. **content_plan 预览**：达人选中后从 soul_preview（后端返回 persona 前 400 字）近似推导展示，真实 content_plan 由后端在 chat 接口读取
