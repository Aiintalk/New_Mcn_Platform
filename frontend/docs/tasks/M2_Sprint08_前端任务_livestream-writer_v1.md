# M2 Sprint 08 — 前端任务 · 直播脚本仿写（livestream-writer）迁移 v1

> 节点：B
> 创建日期：2026-06-15
> 依赖需求文档：`docs/pm/M2_Sprint08_livestream-writer_需求文档.md`

---

## 一、交付文件清单

| 文件 | 动作 |
|------|------|
| `frontend/src/api/livestreamWriter.ts` | 新增 |
| `frontend/src/types/livestreamWriter.ts` | 新增 |
| `frontend/src/pages/operator/LivestreamWriterPage.tsx` | 新增 |
| `frontend/src/pages/admin/LivestreamWriterConfigTab.tsx` | 新增 |
| `frontend/src/pages/admin/ServiceConfigPage.tsx` | 修改（加 Tab） |
| `frontend/src/App.tsx` | 修改（加路由） |
| `frontend/src/__tests__/unit/api/conventionGuard.test.ts` | 验证通过（守卫自动检测） |

---

## 二、API 层 `api/livestreamWriter.ts`

所有 JSON 调用走 `request.ts` 的 `get / post / put`（#3 红线）。
流式调用用原生 `fetch`（例外项）。

```typescript
// 达人列表
export const getKolPersonas = () => get<PersonasResp>('/api/tools/livestream-writer/kols/personas');

// 文件解析（FormData，例外）
export const parseFile = async (file: File): Promise<ParseFileResp> => { ... };

// 流式对话（fetch 例外）
export const chatStream = (body: ChatRequest, onChunk, onDone, onError) => { ... };
```

**chatStream 重试策略**：429 时最多 5 次，退避 5/10/15/20/25 秒（与后端对齐）。

---

## 三、页面 `LivestreamWriterPage.tsx`

### 4 步工作流

```
Step 1 · 选达人  →  Step 2 · 上传卖点  →  Step 3 · 锁定对标  →  Step 4 · 生成方案
```

#### Step 1 · 选达人

- 进入页面时调 `getKolPersonas`，Select 展示达人列表
- 选中后缓存 `selectedPersona`（含 soul / contentPlan）
- 点击"下一步"进入 Step 2

#### Step 2 · 上传卖点

- 支持拖拽/点击上传文件（.txt / .md / .docx / .pages），调 `parseFile`
- 或直接粘贴文本到 TextArea
- 正则提取产品名（匹配"一句话总结："后的内容）
- 卖点顺序选择（单选3种：背书→机制→种草 / 机制→背书→种草 / 种草→背书→机制）
- 点击"下一步"进入 Step 3

#### Step 3 · 锁定对标

- 支持拖拽/点击上传或粘贴对标文案
- 展示对标文案字数（`text.replace(/\s/g, '').length`）
- 点击"确认锁定"按钮（锁定后不可修改）
- 点击"开始仿写"进入 Step 4

#### Step 4 · 仿写 + 对话

- **首次生成**：调 chatStream（systemPrompt=Prompt 1，messages=[首次 user message]，createJob=true，jobContext 含完整 context）
- **autoTrimIfTooLong**：生成完成后检查讲解脚本字数，若超出则自动追加压缩请求
- **多轮迭代**：用户输入追加到 messages，调 chatStream（systemPrompt=Prompt 2）
- **生成中**：显示 loading 状态，禁用输入
- **导出终稿**：前端 Blob 下载 .txt，文件名 `开播方案_{productName || '终稿'}.txt`

---

## 四、System Prompt 构建（前端动态）

### Prompt 1（首次生成）变量注入

| 变量 | 来源 |
|------|------|
| `{orderLabels}` | 卖点顺序选择，如 `背书→机制→种草` |
| `{refLength}` | `refScript.replace(/\s/g, '').length` |
| `{sellingPoints}` | 卖点卡文本 |
| `{refScript}` | 对标文案文本 |
| `{personaSoul}` | `selectedPersona.soul` |

messages[0].content 模板（含 personaName / orderLabels / refLength 等）：见需求文档第四节。

### Prompt 2（多轮迭代）

同样注入 5 个变量，systemPrompt 内容来自需求文档 Prompt 2 原文。

> **实时拉取**：进入 LivestreamWriterPage 时调 GET `/api/tools/livestream-writer/config`，获取 `generate_prompt` / `iterate_prompt` / `model_id` 存入 state，chat 时直接用。不硬编码 Prompt 原文。

---

## 五、管理端配置 Tab `LivestreamWriterConfigTab.tsx`

参照 `QianchuanReviewConfigTab.tsx` 实现：

- 调 GET `/api/admin/livestream-writer/configs` 加载两条配置（generate / iterate）
- config_key 显示名：`generate` → "首次生成方案"、`iterate` → "多轮迭代修改"
- 支持编辑 system_prompt（TextArea）和绑定 ai_model_id（Select，调 getAiModels）
- 保存调 PUT `/api/admin/livestream-writer/configs/{key}`

### 挂载到 `ServiceConfigPage.tsx`

在现有 Tab 列表中追加：

```tsx
<Tabs.TabPane tab="直播脚本仿写" key="livestream-writer">
  <LivestreamWriterConfigTab />
</Tabs.TabPane>
```

---

## 六、路由 `App.tsx`

```tsx
import LivestreamWriterPage from './pages/operator/LivestreamWriterPage';
// 在 operator 路由区域追加：
<Route path="/tools/livestream-writer" element={<LivestreamWriterPage />} />
```

WorkspacePage 的工具卡片点击跳转（`tool_code === 'livestream-writer'` → `/tools/livestream-writer`）已由现有 WorkspacePage 逻辑处理，无需单独修改。

---

## 七、UI 规范

- 组件库：Ant Design 5.x
- 风格：与 TiktokWriterPage / SellingPointPage 保持一致（Steps 顶部导航、Card 内容区、蓝色主色调）
- 文件上传：`Dragger` 组件，支持拖拽
- 流式内容展示：白底 pre 样式块，支持换行，实时追加
- 导出按钮：仅在有 AI 内容时启用

---

## 八、测试要求

- 守卫测试 `conventionGuard.test.ts` 自动通过（livestreamWriter.ts 中 chatStream 和 parseFile 标注例外）
- 手工验证：4 步流程黄金路径 + autoTrimIfTooLong 触发 + .txt 导出内容正确

---

## 九、不做清单

- 不实现 Word 导出
- 不把 autoTrimIfTooLong 移到后端
- 不修改 System Prompt 原文
- 不实现历史记录
