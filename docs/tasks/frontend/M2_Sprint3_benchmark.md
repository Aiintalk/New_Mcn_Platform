# MCN_Frontend_Agent — M2 Sprint 3 任务指令（对标分析助手）

> **角色**：前端开发  
> **工作目录**：`frontend/`  
> **PM 生成日期**：2026-06-10  
> **前置依赖**：后端 Sprint 3 接口已完成  
> **完成后**：回传 PM，等待联调测试

---

## M2 Sprint 3 目标

构建对标分析助手的运营端页面和管理员配置页面：

1. **运营端** `/workspace/benchmark` — 输入抖音号/粘贴文案 → AI 分析 → 查看结果 + 历史记录 + 导出 Word
2. **管理员** `/admin/benchmark` — Prompt 管理 + 模型选择 + 分析记录查看

---

## 一、类型定义

新建 `src/types/benchmark.ts`：

```typescript
/** 抖音拉取结果 */
export interface FetchResult {
  sec_user_id: string;
  nickname: string;
  total_videos: number;
  top10_count: number;
  recent30_count: number;
  top10_text: string;
  recent30_text: string;
}

/** 分析记录 */
export interface BenchmarkAnalysis {
  id: number;
  account_name: string;
  sec_user_id: string;
  top10_content: string;
  recent30_content: string;
  profile_result: string;
  plan_result: string;
  model_used: string;
  tokens_used: number;
  duration_ms: number;
  status: 'pending' | 'generating' | 'completed' | 'failed';
  created_at: string;
  updated_at: string;
}

/** 管理员配置 */
export interface BenchmarkConfig {
  id: number;
  config_key: string;
  ai_model_id: number | null;
  system_prompt: string;
  is_active: boolean;
  updated_at: string;
}
```

---

## 二、API 层

新建 `src/api/benchmark.ts`：

```typescript
import request from '../utils/request';

// ── 运营端 ──────────────────────────────────────────────

/** 抖音号/链接解析 + 视频拉取 */
export function fetchAccount(input: string) {
  return request.post<FetchResult>('/operator/benchmark/fetch', { input });
}

/** AI 分析（返回 ReadableStream，前端自行解析 SSE） */
export function analyzeStream(body: {
  account_name: string;
  sec_user_id?: string;
  top10_content: string;
  recent30_content: string;
}): Promise<Response> {
  const token = localStorage.getItem('token');
  return fetch(`${import.meta.env.VITE_API_BASE}/operator/benchmark/analyze`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
}

/** 我的分析历史 */
export function getMyHistory() {
  return request.get<BenchmarkAnalysis[]>('/operator/benchmark/history');
}

/** 历史详情 */
export function getHistoryDetail(id: number) {
  return request.get<BenchmarkAnalysis>(`/operator/benchmark/history/${id}`);
}

/** 导出 Word */
export function exportWord(analysisId: number, type: 'profile' | 'plan') {
  return request.post('/operator/benchmark/export-word', { analysis_id: analysisId, type }, { responseType: 'blob' });
}

// ── 管理员 ──────────────────────────────────────────────

/** 配置列表 */
export function getAdminConfigs() {
  return request.get<BenchmarkConfig[]>('/admin/benchmark/configs');
}

/** 更新配置 */
export function updateAdminConfig(key: string, data: { ai_model_id?: number; system_prompt?: string; is_active?: boolean }) {
  return request.put(`/admin/benchmark/configs/${key}`, data);
}

/** 全部分析记录 */
export function getAdminAnalyses() {
  return request.get<BenchmarkAnalysis[]>('/admin/benchmark/analyses');
}

/** 分析详情 */
export function getAdminAnalysisDetail(id: number) {
  return request.get<BenchmarkAnalysis>(`/admin/benchmark/analyses/${id}`);
}
```

---

## 三、运营端页面

新建 `src/pages/operator/BenchmarkPage.tsx`

### 3.1 页面状态

| 状态 | 说明 |
|------|------|
| `input` | 输入模式：抖音号输入 + 文本粘贴 + 历史记录 |
| `result` | 结果模式：Tab 切换（人格档案/内容规划）+ 导出 |

### 3.2 输入模式布局

```
┌─────────────────────────────────────────────────────┐
│  对标分析助手                                         │
│  系统化拆解对标账号，输出人格档案与内容规划              │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─ 已分析的对标账号 ─────────────────────────────┐  │
│  │  [陶然]  [尹可以]  [xxx]  ...（网格卡片）       │  │
│  │  每张卡片显示：账号名 + 作品数 + 分析时间        │  │
│  └────────────────────────────────────────────────┘  │
│                                                     │
│  ┌─ 第一步：获取对标账号数据 ─────────────────────┐  │
│  │                                              │  │
│  │  方式一：抖音号/链接          方式二：直接粘贴  │  │
│  │  ┌──────────────────┐                        │  │
│  │  │ 输入抖音号或链接.. │  [解析]               │  │
│  │  └──────────────────┘                        │  │
│  │  抓取成功！共156条作品                         │  │
│  │                                              │  │
│  └────────────────────────────────────────────────┘  │
│                                                     │
│  ┌─ 账号名称（可选）─────────────────────────────┐  │
│  │  [输入对标账号名称]                            │  │
│  └────────────────────────────────────────────────┘  │
│                                                     │
│  ┌─ 数据一：全账号点赞 TOP10 ────────────────────┐  │
│  │  [textarea - 自动填充或手动粘贴]              │  │
│  │  已输入 2345 字                               │  │
│  └────────────────────────────────────────────────┘  │
│                                                     │
│  ┌─ 数据二：最近30天全部内容 ────────────────────┐  │
│  │  [textarea - 自动填充或手动粘贴]              │  │
│  │  已输入 5678 字                               │  │
│  └────────────────────────────────────────────────┘  │
│                                                     │
│  [开始分析]  ← 全宽绿色按钮                         │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 3.3 结果模式布局

```
┌─────────────────────────────────────────────────────┐
│  对标分析助手        [导出人格档案] [导出内容规划] [← 返回] │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─ Tab: [人格档案] [内容规划] ───────────────────┐  │
│  │                                              │  │
│  │  # 陶然 · 人格档案 v1.0                       │  │
│  │                                              │  │
│  │  > 用于以陶然第一人称口吻创作内容时加载。       │  │
│  │                                              │  │
│  │  ## 一、一句话定位                             │  │
│  │  ...                                         │  │
│  │                                              │  │
│  │  [复制] ← 右上角                              │  │
│  │                                              │  │
│  │  ── 生成中... ──                              │  │
│  └────────────────────────────────────────────────┘  │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 3.4 交互逻辑

**抖音解析：**
1. 输入框输入抖音号或链接 → 点击「解析」
2. 调用 `fetchAccount(input)`
3. 成功后自动填充 TOP10 文本框 + 最近30天文本框 + 账号名称
4. 显示绿色提示：「抓取成功！共 {total} 条作品，TOP10 已选出 {top10} 条，最近30天 {recent30} 条」

**AI 分析：**
1. 点击「开始分析」→ 切换到 result 模式
2. 调用 `analyzeStream()` 获取 ReadableStream
3. 逐 chunk 读取，按 `===SPLIT===` 分割
4. 分割前的内容实时渲染到「人格档案」tab
5. 分割后的内容实时渲染到「内容规划」tab
6. 流结束后自动保存到 history（后端已处理）

**导出 Word：**
1. 点击「导出人格档案」或「导出内容规划」
2. 调用 `exportWord(analysisId, type)`
3. 浏览器下载 docx 文件

**历史记录加载：**
1. 页面加载时调用 `getMyHistory()`
2. 以网格卡片形式展示（2-4 列）
3. 点击卡片 → 调用 `getHistoryDetail(id)` → 切换到 result 模式展示

---

## 四、管理员配置页面

新建 `src/pages/admin/BenchmarkConfigPage.tsx`

### 4.1 页面布局

```
┌─────────────────────────────────────────────────────┐
│  对标分析配置                                         │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─ AI 配置 ─────────────────────────────────────┐  │
│  │                                              │  │
│  │  配置项：analyze                              │  │
│  │                                              │  │
│  │  模型选择：[claude-sonnet-4-6 ▼]             │  │
│  │                                              │  │
│  │  System Prompt：                              │  │
│  │  ┌────────────────────────────────────────┐  │  │
│  │  │ 你是一个专业的抖音账号对标分析师...     │  │  │
│  │  │                                        │  │  │
│  │  │ （可编辑，支持滚动）                    │  │  │
│  │  └────────────────────────────────────────┘  │  │
│  │                                              │  │
│  │  [保存配置]                                   │  │
│  └────────────────────────────────────────────────┘  │
│                                                     │
│  ┌─ 分析记录 ─────────────────────────────────────┐  │
│  │  Table:                                       │  │
│  │  | ID | 账号名 | 模型 | 状态 | Token | 耗时 | 时间 | │
│  │  | 1  | 陶然   | sonnet | ✅完成 | 3200 | 45s | 06-10 | │
│  │  | 2  | 尹可以 | sonnet | ❌失败 | -    | -   | 06-10 | │
│  │                                              │  │
│  │  操作：[查看详情] [重新生成]                   │  │
│  └────────────────────────────────────────────────┘  │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 4.2 交互逻辑

**配置编辑：**
1. 页面加载时调用 `getAdminConfigs()` 填充表单
2. 模型选择下拉框：从 `ai_models` 表获取可用模型列表
3. System Prompt：大文本框（min-height: 400px），支持滚动
4. 点击「保存配置」→ 调用 `updateAdminConfig('analyze', { ai_model_id, system_prompt, is_active })`
5. 成功提示

**分析记录：**
1. 页面加载时调用 `getAdminAnalyses()` 填充表格
2. 表格列：ID、账号名、模型、状态（Tag 颜色）、Token 用量、耗时、创建时间
3. 「查看详情」→ Drawer 展示 profile_result + plan_result（Markdown 渲染）
4. 「重新生成」→ 确认对话框 → 调用重新生成接口

---

## 五、路由注册

在 `src/App.tsx` 中添加：

```tsx
import BenchmarkPage from './pages/operator/BenchmarkPage';
import BenchmarkConfigPage from './pages/admin/BenchmarkConfigPage';

// 运营端路由（在 OperatorLayout 内）
<Route path="/workspace/benchmark" element={<BenchmarkPage />} />

// 管理员路由（在 AdminLayout 内）
<Route path="/admin/benchmark" element={<BenchmarkConfigPage />} />
```

---

## 六、导航栏更新

### 运营端导航

在 `OperatorLayout.tsx` 的菜单项中，「创作中心」分组下新增：

```tsx
{ key: '/workspace/benchmark', label: '对标分析助手' }
```

### 管理员导航

在 `AdminLayout.tsx` 的菜单项中，「系统配置」分组下新增：

```tsx
{ key: '/admin/benchmark', label: '对标分析配置' }
```

---

## 七、字段对齐

| 字段 | 后端返回 | 前端使用 | 说明 |
|------|----------|----------|------|
| `sec_user_id` | ✅ | 传递给 analyze 接口 | TikHub 用户标识 |
| `top10_text` | ✅ | 填充 textarea + 传给 analyze | 格式化后的 TOP10 文案 |
| `recent30_text` | ✅ | 填充 textarea + 传给 analyze | 格式化后的最近30天文案 |
| `profile_result` | ✅ | Markdown 渲染 | 人格档案（===SPLIT=== 前） |
| `plan_result` | ✅ | Markdown 渲染 | 内容规划（===SPLIT=== 后） |
| `status` | ✅ | Tag 颜色映射 | pending/generating/completed/failed |
| `config_key` | ✅ | 固定 'analyze' | 管理员配置标识 |
| `ai_model_id` | ✅ | 下拉框选择 | 关联 ai_models 表 |

---

## 八、联调修复记录（2026-06-10）

| # | 问题 | 根因 | 修复 |
|---|------|------|------|
| 1 | 管理员配置页面入口错误 | 初版将对标分析配置作为独立页面 `/admin/benchmark` 放在系统管理导航下 | 改为 Tab 嵌入 `/admin/workspace`（工具配置页），删除独立路由和导航项 |
| 2 | 配置 UI 不符合规范 | 初版使用内联 textarea 编辑 Prompt，无 AI 模型选择下拉框 | 重写 `BenchmarkConfigTab.tsx`，对齐 `AdminIntakePage` 模式：卡片展示 + Modal 编辑（AI 模型 Select + System Prompt TextArea + "使用参考模板"按钮） |

**涉及文件：**
- `frontend/src/pages/admin/BenchmarkConfigTab.tsx` — 完全重写
- `frontend/src/pages/admin/WorkspaceConfigTab.tsx` — 新增 benchmark Tab
- `frontend/src/App.tsx` — 删除 `/admin/benchmark` 路由

---

## 九、验收标准

| # | 验收项 | 验证方法 |
|---|--------|----------|
| 1 | 运营端页面可访问 | `/workspace/benchmark` 正常渲染 |
| 2 | 抖音号解析 | 输入抖音号 → 点击解析 → 文本框自动填充 |
| 3 | 链接解析 | 输入主页链接 → 点击解析 → 文本框自动填充 |
| 4 | AI 流式分析 | 点击开始分析 → 人格档案/内容规划逐字输出 |
| 5 | Tab 切换 | 人格档案/内容规划两个 Tab 正确切换 |
| 6 | 历史记录 | 分析完成后历史列表出现新卡片 |
| 7 | 历史加载 | 点击历史卡片 → 加载完整结果 |
| 8 | Word 导出 | 点击导出按钮 → 浏览器下载 docx |
| 9 | 管理员配置页 | `/admin/benchmark` 正常渲染，Prompt 可编辑 |
| 10 | 配置保存 | 修改 Prompt → 保存 → 刷新后仍为新值 |
| 11 | 分析记录表格 | 管理员可看到所有用户的分析记录 |
