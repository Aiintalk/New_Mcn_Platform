# MCN_Frontend_Agent — M2 Sprint 1 任务指令（红人入驻问卷）

> 角色：MCN_Frontend_Agent（前端开发 Claude）  
> 工作目录：`frontend/`  
> PM 生成时间：2026-06-08  
> 前置条件：M1 全部验收通过，后端 M2 Sprint 1 接口已就绪  
> 完成后：回传 PM，等待联调测试

---

## M2 Sprint 1 目标

新增 3 个页面/功能区：
1. **公开对话页** `/intake/:token`（无需登录，博主与 AI 对话填写问卷）
2. **运营端 - 链接管理页** `/workspace/kol-intake`（从工作台进入）
3. **管理员端 - 问卷配置 Tab**（追加到现有服务配置页）

---

## 一、类型定义（新建 `src/types/intake.ts`）

```typescript
// 对话消息
export interface ChatMessage {
  role: 'assistant' | 'user'
  content: string
  ts: string  // ISO8601
}

// 题目（管理员配置用）
export interface IntakeQuestion {
  id: number
  order_num: number
  category: string
  question_text: string
  question_type: 'text' | 'multi_collect'
  max_items: number | null
  is_required: boolean
  is_active: boolean
}

// 分享链接
export interface IntakeLink {
  id: number
  token: string
  kol_name: string | null
  expires_at: string
  is_active: boolean
  created_at: string
  used_at: string | null
  submitted_at: string | null
  report_status: 'pending' | 'generating' | 'ready' | 'failed' | null
}

// 提交记录
export interface IntakeSubmission {
  id: number
  link_id: number
  kol_name: string | null
  report_status: 'pending' | 'generating' | 'ready' | 'failed'
  created_at: string
  report_generated_at: string | null
  kol_downloaded_at: string | null
  messages?: ChatMessage[]   // 详情接口返回
  ai_report?: string | null  // 详情接口返回
}

// AI 配置表单
export interface IntakeConfigForm {
  ai_model_id: number | null
  system_prompt: string | null
}

// 题目表单
export interface QuestionForm {
  order_num: number
  category: string
  question_text: string
  question_type: 'text' | 'multi_collect'
  max_items: number | null
  is_required: boolean
}
```

---

## 二、API 层（新建 `src/api/intake.ts`）

```typescript
import { request } from './request'  // 已有的请求封装
import type {
  ChatMessage, IntakeQuestion, IntakeLink,
  IntakeSubmission, IntakeConfigForm, QuestionForm
} from '../types/intake'

// ── 公开接口（不携带 Authorization header）────────────────────

// 校验链接，返回初始状态
export const getIntakeInfo = (token: string) =>
  request.get(`/api/intake/${token}`)

// AI 多轮对话（每次传入完整对话历史）
export const chatIntake = (token: string, messages: ChatMessage[]) =>
  request.post(`/api/intake/${token}/chat`, { messages })

// 提交完整对话，触发报告生成
export const submitIntake = (token: string, messages: ChatMessage[]) =>
  request.post(`/api/intake/${token}/submit`, { messages })

// 轮询报告生成状态
export const getIntakeStatus = (token: string) =>
  request.get(`/api/intake/${token}/status`)

// 下载报告（直接触发浏览器下载）
export const getIntakeDownloadUrl = (token: string, format: 'docx' | 'pdf') =>
  `/api/intake/${token}/download?format=${format}`

// ── 运营端接口 ─────────────────────────────────────────────────

export const createIntakeLink = (data: { kol_name?: string; expires_hours: number }) =>
  request.post('/api/operator/intake/links', data)

export const getIntakeLinks = () =>
  request.get('/api/operator/intake/links')

export const getOperatorSubmissions = () =>
  request.get('/api/operator/intake/submissions')

export const getOperatorSubmissionDetail = (id: number) =>
  request.get(`/api/operator/intake/submissions/${id}`)

export const getOperatorDownloadUrl = (id: number, format: 'docx' | 'pdf') =>
  `/api/operator/intake/submissions/${id}/download?format=${format}`

// ── 管理员接口 ─────────────────────────────────────────────────

export const getAdminQuestions = () =>
  request.get('/api/admin/intake/questions')

export const createQuestion = (data: QuestionForm) =>
  request.post('/api/admin/intake/questions', data)

export const updateQuestion = (id: number, data: Partial<QuestionForm>) =>
  request.patch(`/api/admin/intake/questions/${id}`, data)

export const deleteQuestion = (id: number) =>
  request.delete(`/api/admin/intake/questions/${id}`)

export const reorderQuestions = (items: { id: number; order_num: number }[]) =>
  request.put('/api/admin/intake/questions/reorder', items)

export const getIntakeConfigs = () =>
  request.get('/api/admin/intake/configs')

export const updateIntakeConfig = (key: string, data: IntakeConfigForm) =>
  request.put(`/api/admin/intake/configs/${key}`, data)

export const getAdminSubmissions = () =>
  request.get('/api/admin/intake/submissions')
```

---

## 三、公开对话页（新建 `src/pages/intake/IntakePage.tsx`）

路由：`/intake/:token`，**不包裹 ProtectedRoute**。

### 3.1 页面状态机

| 状态 | 展示内容 |
|------|----------|
| `loading` | 加载中（验证 token） |
| `invalid` | 链接无效（404） |
| `expired` | 链接已过期（410） |
| `chatting` | AI 对话进行中 |
| `generating` | 已提交，报告生成中 |
| `ready` | 报告已生成，显示下载按钮 |
| `failed` | 报告生成失败 |
| `submitted` | 已提交过（只读，展示历史对话） |

### 3.2 页面结构

```
┌─────────────────────────────────────┐
│  达人说 Logo    「红人入驻信息采集」  │  ← 顶部 Header
├─────────────────────────────────────┤
│                                     │
│  [AI] 你好！我是达人说的内容顾问…   │
│                                     │  ← 对话消息流
│       叫我小红就好 [博主]            │
│                                     │
│  [AI] 好名字！你的抖音账号是？       │
│                                     │
├─────────────────────────────────────┤
│  [输入框：说点什么…]    [发送 ▶]    │  ← 底部输入区
│  [生成报告] ← 覆盖必填题后显示      │
└─────────────────────────────────────┘
```

### 3.3 chatting 状态交互逻辑

**初始化（进入 chatting 状态）：**
1. 调用 `chatIntake(token, [])` — 空 messages，触发 AI 开场白
2. 将 AI 回复追加到本地 `messages` 状态数组
3. 展示消息，输入框聚焦

**博主发送消息：**
1. 将博主消息追加到本地 `messages`：`{ role: 'user', content: '...', ts: new Date().toISOString() }`
2. 输入框 disabled，显示发送中状态
3. 调用 `chatIntake(token, messages)`（传完整对话历史）
4. 将 AI 回复追加到 `messages`
5. 输入框恢复可用，消息区滚动到底部

**「生成报告」按钮显示逻辑：**
- 监听最新一条 assistant 消息，若包含「生成」「报告」等关键词则显示按钮
- 或：始终在底部显示，但初始为灰色禁用，对话满 10 轮后变为可点击
- 具体规则与后端确认后实现，两种方案均可

**消息气泡样式：**
- `role: 'assistant'`：左对齐，浅灰背景，头像用 AI 图标
- `role: 'user'`：右对齐，蓝色背景，头像用首字母

### 3.4 generating 状态

- 隐藏输入框
- 中央显示：`Spin` + 「报告生成中，请稍候…（约30-60秒）」
- 每 3 秒调用 `getIntakeStatus(token)`
  - `report_status === 'ready'` → 切换到 ready 状态
  - `report_status === 'failed'` → 切换到 failed 状态

### 3.5 ready 状态

- 显示：「✅ 报告已生成！」
- 两个下载按钮：
  - 「下载 Word 版（.docx）」→ `window.open(getIntakeDownloadUrl(token, 'docx'))`
  - 「下载 PDF 版」→ `window.open(getIntakeDownloadUrl(token, 'pdf'))`
- 链接过期后按钮变灰 + 提示「下载链接已过期」

### 3.6 submitted 状态（已提交，只读）

- 顶部提示：「您已完成信息填写，以下是您的对话记录」
- 展示历史 `messages`（只读，无输入框）
- 若 `report_status === 'ready'`，显示下载按钮

---

## 四、运营端 - 链接管理页（新建 `src/pages/operator/KolIntakePage.tsx`）

路由：`/workspace/kol-intake`（ProtectedRoute 保护）

> WorkspacePage 已有通用跳转逻辑 `navigate('/workspace/${t.tool_code}')`，kol-intake 录入 workspace_tools 后点击卡片自动跳转，**无需修改 WorkspacePage**。

### 4.1 页面布局

```
标题：红人入驻问卷                    [+ 生成链接]
──────────────────────────────────────────────────
链接列表 Table
```

### 4.2 链接列表 Table

| 列 | 字段 | 说明 |
|----|------|------|
| 博主姓名 | `kol_name` | 空时显示「未指定」 |
| 链接状态 | 计算 | 见下方状态逻辑 |
| 有效期至 | `expires_at` | `YYYY-MM-DD HH:mm` |
| 创建时间 | `created_at` | `YYYY-MM-DD HH:mm` |
| 报告状态 | `report_status` | 见下方映射 |
| 操作 | — | 复制链接 / 查看详情 / 下载报告 |

**链接状态 Badge：**
```
submitted_at 不为空       → 「已提交」green
used_at 不为空            → 「对话中」blue
expires_at < 当前时间     → 「已过期」gray
其余                      → 「未访问」orange
```

**报告状态映射：**
```
null                      → —
'pending'/'generating'    → 「生成中」（spinning icon）
'ready'                   → 「已就绪」green
'failed'                  → 「生成失败」red
```

**操作列：**
- 「复制链接」：复制 `window.location.origin + /intake/ + token`，成功提示 `message.success('链接已复制')`
- 「查看详情」：打开 Drawer 展示完整对话 + 报告
- 「下载报告」：仅 `report_status === 'ready'` 时显示，点击弹出格式选择（docx / pdf）

### 4.3 生成链接 Modal

字段：
- 博主姓名（选填）：`Input`
- 有效期：`Select`，选项 `[{label:'1天',value:24},{label:'3天',value:72},{label:'7天',value:168}]`，默认 `24`

提交逻辑：
1. 调用 `createIntakeLink`
2. 若后端返回 403（功能已下架）：`message.error('红人入驻问卷功能已下架，无法创建新链接')`
3. 成功：`Modal.success` 展示链接地址 + 复制按钮 + 有效期，刷新列表

### 4.4 详情 Drawer

宽度：`720px`

内容分三区：
1. **基本信息**：博主姓名、链接状态、创建时间、提交时间
2. **完整对话记录**：渲染 `messages` 数组，样式同对话页气泡（assistant 左/user 右），时间戳显示在气泡下方
3. **AI 评估报告**：`Typography.Paragraph` 展示 `ai_report`（Markdown 渲染），若为 null 显示「报告尚未生成」

底部：下载按钮（docx / pdf，仅 ready 状态显示）

---

## 五、管理员端 - 问卷配置（追加到 `ServiceConfigPage.tsx`）

在现有 Tabs 中追加「问卷配置」Tab，内含两个子 Tab。

### 子 Tab 1：题目管理

**题目列表 Table：**

| 列 | 字段 | 说明 |
|----|------|------|
| 序号 | `order_num` | — |
| 分类 | `category` | 基本信息 / 野心评估 等 |
| 题目内容 | `question_text` | — |
| 类型 | `question_type` | text / multi_collect |
| 必填 | `is_required` | Switch，inline 修改 |
| 状态 | `is_active` | Switch，inline 修改 |
| 操作 | — | 编辑 / 删除 |

**新增/编辑 Modal 字段：**
- 分类：`Input`（必填）
- 题目文本：`Input.TextArea`（必填）
- 类型：`Select`，选项 `[{label:'文字输入',value:'text'},{label:'多条收集',value:'multi_collect'}]`
- 最多条数：`InputNumber`（仅 multi_collect 时显示，范围 1-5）
- 是否必填：`Switch`
- 排序号：`InputNumber`

删除使用 `Popconfirm` 二次确认。

### 子 Tab 2：AI 配置

展示两个配置卡片：

**卡片 1：对话模型（conversation_bridge）**

| 字段 | 组件 | 说明 |
|------|------|------|
| 使用模型 | `Select`，选项来自 `getAiModels()` | 展示 model_name，value 为 id |
| 对话 System Prompt | `Input.TextArea` autoSize minRows=6 | 控制 AI 面试官的说话风格 |

提示文字：「此 Prompt 决定 AI 与博主对话的风格。后端会自动在末尾追加 24 道题目提纲，无需手动填写题目。」

**卡片 2：报告生成（report_generation）**

| 字段 | 组件 | 说明 |
|------|------|------|
| 使用模型 | `Select`，同上 | — |
| 报告 System Prompt | `Input.TextArea` autoSize minRows=6 | 控制报告结构和措辞，支持 `{qa_content}` 占位符 |

提示文字：「使用 `{qa_content}` 占位符代表完整对话提炼内容。」

每个卡片底部「保存」按钮，调用 `updateIntakeConfig(key, data)`。

---

## 六、路由注册（`src/App.tsx`）

```tsx
// 新增 import
import IntakePage    from './pages/intake/IntakePage'
import KolIntakePage from './pages/operator/KolIntakePage'

// 公开路由（ProtectedRoute 外部，与 /login 同级）
<Route path="/intake/:token" element={<IntakePage />} />

// 运营路由（ProtectedRoute 内，OperatorLayout 内）
<Route path="/workspace/kol-intake" element={<KolIntakePage />} />
```

---

## 七、字段对齐（前后端对齐表）

| 后端字段 | 前端字段 | 类型 | 备注 |
|----------|----------|------|------|
| `messages` | `messages` | `ChatMessage[]` | 完整对话历史，role/content/ts |
| `report_status` | `report_status` | string | pending/generating/ready/failed |
| `expires_hours` | `expires_hours` | number | 整数，单位：小时 |
| `share_url` | — | — | 后端返回相对路径，前端拼接 origin |
| `ai_report` | `ai_report` | string \| null | Markdown 格式，前端渲染展示 |
| `docx_path` / `pdf_path` | — | — | 后端内部路径，前端不直接使用 |
| config_key `conversation_bridge` | — | — | 对话 AI 配置的标识符 |
| config_key `report_generation` | — | — | 报告生成 AI 配置的标识符 |

---

## 八、验收标准

1. `/intake/:token` 过期显示「链接已过期」，已提交显示历史对话（只读）
2. 进入对话页后 AI 自动发送开场白，博主回复后 AI 继续引导
3. 点击「生成报告」后进入生成中状态，轮询后自动切换为下载页
4. 下载页同时提供 docx 和 PDF 两个按钮，均可下载
5. 运营端「生成链接」：功能下架时提示不可创建，正常时生成成功并展示链接
6. 运营端详情 Drawer：正确展示完整对话气泡 + AI 报告 Markdown 内容
7. 管理员端题目管理：新增/编辑/删除/排序正常，`multi_collect` 类型可设置最多条数
8. 管理员端 AI 配置：两个卡片保存后重新加载数据一致
