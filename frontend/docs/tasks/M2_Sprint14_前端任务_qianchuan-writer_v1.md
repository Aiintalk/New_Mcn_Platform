# M2 Sprint 14 — 前端任务：千川文案写作（qianchuan-writer）

> 状态：**已完成**（待 PM 签收 + 推 PR）
> 完成日期：2026-06-22
> 对应需求文档：`docs/pm/M2_Sprint14_qianchuan-writer_需求文档.md`
> 对应分支：`migrate/qianchuan-writer`

---

## 一、范围（本次前端任务）

涵盖千川文案写作工具迁移的所有前端工作：
- `types/qianchuanWriter.ts` 类型定义
- `api/qianchuanWriter.ts` 8 函数（6 运营端 + 2 管理端）
- `QianchuanWriterPage.tsx` 4 步向导主页面
- `QianchuanWriterConfigTab.tsx` 管理端配置 Tab
- `App.tsx` 路由注册（React.lazy）
- `WorkspaceConfigPage.tsx` Tab 注册
- `QianchuanWriterPage.test.tsx` 11 用例全绿
- 全量回归 138 passed / 0 failed，`tsc --noEmit` exit 0

## 二、任务清单

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| F1 | 类型定义 + API 层（8 函数）| `frontend/src/types/qianchuanWriter.ts` + `frontend/src/api/qianchuanWriter.ts` | ✅ |
| F2 | 运营端 4 步向导主页面 | `frontend/src/pages/operator/QianchuanWriterPage.tsx` | ✅ |
| F3 | 管理端配置 Tab | `frontend/src/pages/admin/QianchuanWriterConfigTab.tsx` | ✅ |
| F4 | App.tsx 路由注册 | `frontend/src/App.tsx` | ✅ |
| F5 | WorkspaceConfigPage Tab 注册 | `frontend/src/pages/admin/WorkspaceConfigPage.tsx` | ✅ |
| F6 | 组件测试 11 用例 | `frontend/src/__tests__/components/pages/QianchuanWriterPage.test.tsx` | ✅ |

## 三、QianchuanWriterPage 实现要点

### 3.1 4 步向导业务逻辑（忠于原版）

| Step | 用户操作 | 关键交互 |
|------|---------|---------|
| 1. 选达人 | 下拉选达人（必选）| 预览 soul 前 400 字；显示创建者标签（系统预设 / 用户添加：xxx）|
| 2. 加载产品 | 上传文件 或 粘贴（必填）| 6 种格式支持（.txt/.md/.docx/.pdf/.xlsx/.pptx）；切换上传/粘贴模式 |
| 3. 输入脚本 | 粘贴原版脚本（必填）| 实时去空白字数显示 |
| 4. 生成仿写 | 点按钮流式输出 + 多轮追问 + 保存 + 导出 | SSE 流式接收；多轮追问累积上下文；3 个动作按钮（保存历史 / .txt / .docx）|

### 3.2 导出文件命名

```
千川仿写_${persona.name}_${productName || '终稿'}.txt
千川仿写_${persona.name}_${productName || '终稿'}.docx
```

- .txt：前端 Blob 下载（不走后端）
- .docx：调 `/api/tools/qianchuan-writer/export-word` 返回 StreamingResponse

### 3.3 CSS 规范

- 使用项目 CSS 变量（`var(--brand)` / `card` / `btn` 等）
- **禁止 Tailwind class**（项目未安装）
- 使用 Ant Design 5 组件（Select / Upload / Input.TextArea / Button / Steps）

## 四、QianchuanWriterConfigTab 实现要点

参照 `TiktokWriterConfigTab.tsx` 模式：

| 字段 | 组件 | 说明 |
|------|------|------|
| `system_prompt` | `Input.TextArea rows=12` | Prompt 模板（含 `{{name}}`/`{{soul}}`/`{{content_plan}}` 占位符）|
| `ai_model_id` | `Select allowClear` | 从 `ai_models WHERE status='active'` 下拉选；留空走默认 `claude-opus-4-6-thinking` |
| `is_active` | `Switch` | 配置启用开关 |

调用：
- GET `/api/admin/qianchuan-writer/configs`（通常返回 1 条 config_key='default'）
- PUT `/api/admin/qianchuan-writer/configs/default`

Modal 使用 `destroyOnHidden`（antd 5，不用 `destroyOnClose`）。

## 五、API 层 8 函数

| 函数 | 方法 | 路径 | 例外 |
|------|------|------|------|
| `getPersonas()` | GET | `/api/tools/qianchuan-writer/kols/personas` | — |
| `parseFile(file)` | POST | `/api/tools/qianchuan-writer/parse-file` | FormData |
| `chatStream(...)` | POST | `/api/tools/qianchuan-writer/chat` | SSE fetch |
| `saveOutput(...)` | POST | `/api/tools/qianchuan-writer/save-output` | — |
| `exportWord(...)` | POST | `/api/tools/qianchuan-writer/export-word` | Blob |
| `getOutputs(page,pageSize)` | GET | `/api/tools/qianchuan-writer/outputs` | — |
| `getConfigs()` | GET | `/api/admin/qianchuan-writer/configs` | — |
| `updateConfig(configKey, payload)` | PUT | `/api/admin/qianchuan-writer/configs/${configKey}` | — |

**红线 #3 合规**：所有 JSON 调用走 `request.ts`（`import { get, post } from './request'`）。例外：FormData / SSE / Blob 三类。

## 六、测试覆盖（QianchuanWriterPage.test.tsx，11 用例）

| 用例 | 说明 |
|------|------|
| 4 步向导渲染 | 4 个 Step 标签可见 |
| Step 1 达人下拉 + 预览 | 列表渲染 + 选中后预览 soul 前 400 字 |
| Step 2 文件上传 + 粘贴切换 | 上传/粘贴模式切换正常 |
| Step 3 字数实时显示 | 输入脚本后实时更新字数 |
| Step 4 流式输出 mock | chatStream 返回的文本增量渲染 |
| 多轮追问输入框 | 流式完成后输入框可继续输入 |
| 保存历史按钮 | 调 saveOutput API |
| 导出 .txt 按钮 | 触发 Blob 下载 |
| 导出 .docx 按钮 | 调 exportWord API |
| ConfigTab 渲染 | 字段可见 |
| ConfigTab 表单提交 | 调 updateConfig |

## 七、关键约定

- 所有 JSON 调用走 `request.ts`（红线 #3），例外：FormData / SSE / Blob
- TypeScript 类型检查通过（`npx tsc --noEmit` exit 0）
- React.lazy 加载新页面（路由懒加载，首屏轻量）
- antd 5 用 `destroyOnHidden` 不用 `destroyOnClose`
- antd `message` 用 `App.useApp()` hook（不用静态方法）
- 禁止 Tailwind class（项目未装）
- AppKey/Secret 脱敏显示（如需要）
- 导出文件名 URL 编码（后端 Content-Disposition `filename*=UTF-8''<encoded>`）

## 八、全量回归结果

- 组件测试：**11/11 ✅**
- 全量 vitest：**138 passed / 0 failed**（17 个测试文件全绿）
- TypeScript：`npx tsc --noEmit` **exit 0**

## 九、实施过程中的技术决策

1. **textarea 交互**：React 19 + AntD 5 的 TextArea 受控组件在 jsdom 中 `user.type` 可正常工作，但需要"下一步"按钮点击触发 Step 切换
2. **AntD Button 空格**：AntD 自动在两个字符的按钮文本间加空格（"确认"→"确 认"），测试用 `/确\s*认/` 正则匹配
3. **scrollIntoView mock**：jsdom 不支持 `Element.scrollIntoView`，测试文件顶部 mock
4. **三接口分离**：chat / save-output / export-word 各自独立（比 tiktok-writer 合并写库更清晰，前端两按钮独立调用）
