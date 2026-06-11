# 前端任务单 · kol-intake 页面位置整合

> 目标：将 kol-intake 在运营端和管理员端的入口位置调整到正确的地方。
>
> 原则：运营端工具统一在「创作中心」工具卡片进入；管理员端工具配置统一在「工具配置」页面管理。
>
> 涉及文件：
> - `src/layouts/OperatorLayout.tsx`
> - `src/layouts/AdminLayout.tsx`
> - `src/pages/admin/WorkspaceConfigPage.tsx`
> - `src/pages/admin/AdminIntakePage.tsx`
>
> **不涉及**：`App.tsx` 路由不需要改动，原有路由全部保留。

---

## 改动 1 — OperatorLayout：删除「入驻问卷」独立菜单项

**文件**：`src/layouts/OperatorLayout.tsx`

`kol-intake` 不再独占侧边栏菜单，运营从「创作中心」工具卡片进入。

**改前：**
```ts
const MENU = [
  { path: '/',                     label: '概览',     icon: '⊞' },
  { path: '/workspace',            label: '创作中心', icon: '✦' },
  { path: '/workspace/kol-intake', label: '入驻问卷', icon: '📋' },  // ← 删除
  { path: '/tasks',                label: '任务中心', icon: '☑' },
  { path: '/outputs',              label: '产出中心', icon: '⬇' },
];
```

**改后：**
```ts
const MENU = [
  { path: '/',          label: '概览',     icon: '⊞' },
  { path: '/workspace', label: '创作中心', icon: '✦' },
  { path: '/tasks',     label: '任务中心', icon: '☑' },
  { path: '/outputs',   label: '产出中心', icon: '⬇' },
];
```

---

## 改动 2 — WorkspacePage：kol-intake 工具卡片点击跳转

**文件**：`src/pages/operator/WorkspacePage.tsx`

`WorkspacePage` 从后端读工具列表，`kol-intake` 的卡片点击逻辑需要和其他工具一样处理。当前 `handleToolClick` 只对 `persona-writer` 做了特殊路由，`kol-intake` 会跳到 `/workspace/kol-intake`（通用逻辑已正确），**无需修改**。

> ✅ 该文件不需要改动，通用跳转逻辑 `navigate('/workspace/${t.tool_code}')` 已覆盖。

---

## 改动 3 — AdminLayout：删除「入驻问卷」菜单项，同步优化命名

**文件**：`src/layouts/AdminLayout.tsx`

删除「入驻问卷」独立菜单项，同时修正其他几处命名混乱问题（趁此机会一并处理）。

**改前：**
```ts
const GROUPS: NavGroup[] = [
  {
    title: '功能管理',
    items: [
      { path: '/admin',           label: '仪表盘' },
      { path: '/admin/users',     label: '用户管理' },
      { path: '/admin/kols',      label: '红人管理' },
      { path: '/admin/intake',    label: '入驻问卷' },   // ← 删除
      { path: '/admin/workspace', label: '功能管理' },   // ← 与分组标题同名
      { path: '/admin/tasks',     label: '产品管理' },   // ← 实际是任务记录
      { path: '/admin/outputs',   label: '用户产出' },
    ],
  },
  {
    title: '系统管理',
    items: [
      { path: '/admin/system',  label: '服务状态' },
      { path: '/admin/config',  label: '服务配置' },
      { path: '/admin/audit',   label: '用户日志' },   // ← 实际是操作日志
      { path: '/admin/logs',    label: '系统日志' },   // ← 实际是调用日志
    ],
  },
];
```

**改后：**
```ts
const GROUPS: NavGroup[] = [
  {
    title: '功能管理',
    items: [
      { path: '/admin',           label: '仪表盘' },
      { path: '/admin/users',     label: '用户管理' },
      { path: '/admin/kols',      label: '红人管理' },
      { path: '/admin/workspace', label: '工具配置' },   // 改名，含「红人信息采集助手」Tab
      { path: '/admin/tasks',     label: '任务记录' },   // 改名
      { path: '/admin/outputs',   label: '产出记录' },   // 改名
    ],
  },
  {
    title: '系统管理',
    items: [
      { path: '/admin/system',  label: '服务状态' },
      { path: '/admin/config',  label: '服务配置' },
      { path: '/admin/audit',   label: '操作日志' },   // 改名
      { path: '/admin/logs',    label: '调用日志' },   // 改名
    ],
  },
];
```

---

## 改动 4 — WorkspaceConfigPage：加「红人信息采集助手」Tab

**文件**：`src/pages/admin/WorkspaceConfigPage.tsx`

页面标题改为「工具配置」，加 Ant Design Tabs，第二个 Tab 嵌入 `AdminIntakePage`。

### 4.1 import 补充

```tsx
import { Tabs } from 'antd';
import AdminIntakePage from './AdminIntakePage';
```

### 4.2 页面标题改名

```tsx
// 改前
<h1 className="page-title">工具配置</h1>
<p className="page-desc">管理内容工作台的 AI 工具</p>

// 改后
<h1 className="page-title">工具配置</h1>
<p className="page-desc">管理内容工作台工具及 AI 功能配置</p>
```

### 4.3 原有工具列表内容用 Tabs 包裹

将原来 `return` 里的所有内容（card + modal）整体放进 `tools` Tab 的 `children`，新增 `intake` Tab 嵌入 `AdminIntakePage`：

```tsx
return (
  <>
    <div className="page-header">
      <div>
        <h1 className="page-title">工具配置</h1>
        <p className="page-desc">管理内容工作台工具及 AI 功能配置</p>
      </div>
    </div>

    <Tabs
      defaultActiveKey="tools"
      items={[
        {
          key: 'tools',
          label: '工具列表',
          children: (
            <>
              {/* 原有 card + modal 全部内容，原样保留，只去掉 page-header */}
            </>
          ),
        },
        {
          key: 'intake',
          label: '红人信息采集助手',
          children: <AdminIntakePage embedded />,
        },
      ]}
    />
  </>
);
```

---

## 改动 5 — AdminIntakePage：加 embedded prop 隐藏内部标题

**文件**：`src/pages/admin/AdminIntakePage.tsx`

嵌入 `WorkspaceConfigPage` 时，`AdminIntakePage` 自己的 `page-header`（「入驻问卷配置」）与外层标题重叠，用 `embedded` prop 控制隐藏。

### 5.1 函数签名加 prop

```tsx
export default function AdminIntakePage({ embedded = false }: { embedded?: boolean }) {
```

### 5.2 page-header 加条件渲染

```tsx
{!embedded && (
  <div className="page-header">
    <div>
      <h1 className="page-title">入驻问卷配置</h1>
      <p className="page-desc">管理 AI 对话模型、系统提示词和题目提纲</p>
    </div>
  </div>
)}
```

---

## 改动 6 — 工具名称全局改名

**涉及范围**：前端 2 处文案 + 后端数据库 1 处记录

### 6.1 OperatorIntakePage：页面标题改名

**文件**：`src/pages/operator/OperatorIntakePage.tsx`

```tsx
// 改前
<h1 className="page-title">红人入驻问卷</h1>

// 改后
<h1 className="page-title">红人信息采集助手</h1>
```

### 6.2 AdminIntakePage：页面标题改名

**文件**：`src/pages/admin/AdminIntakePage.tsx`

```tsx
// 改前
<h1 className="page-title">入驻问卷配置</h1>
<p className="page-desc">管理 AI 对话模型、系统提示词和题目提纲</p>

// 改后
<h1 className="page-title">红人信息采集助手 · 配置</h1>
<p className="page-desc">管理 AI 对话模型、系统提示词和题目提纲</p>
```

### 6.3 数据库：workspace_tools 工具名称更新

执行以下 SQL（在数据库或后端开发工具中执行一次即可）：

```sql
UPDATE workspace_tools
SET tool_name = '红人信息采集助手'
WHERE tool_code = 'kol-intake';
```

> 此更新同时覆盖「工具状态改为 online」的需求，可合并一起执行：
> ```sql
> UPDATE workspace_tools
> SET tool_name = '红人信息采集助手',
>     status    = 'online'
> WHERE tool_code = 'kol-intake';
> ```

---

## 后端配合 — kol-intake 工具状态改为 online（已合并至改动 6.3）

工具名称和状态已统一在改动 6.3 的 SQL 中处理，无需单独操作。

> 管理员也可登录后台「工具配置」页面手动改状态，两种方式均可。

---

## 改动汇总

| # | 文件 | 改动 |
|---|------|------|
| 1 | `OperatorLayout.tsx` | 删「入驻问卷」菜单项（1行） |
| 2 | `WorkspacePage.tsx` | **无需改动**，通用跳转逻辑已覆盖 |
| 3 | `AdminLayout.tsx` | 删「入驻问卷」菜单项 + 修正 4 处命名 |
| 4 | `WorkspaceConfigPage.tsx` | 加 Tabs，嵌入 AdminIntakePage |
| 5 | `AdminIntakePage.tsx` | 加 `embedded` prop，嵌入时隐藏 page-header |
| 6a | `OperatorIntakePage.tsx` | 页面标题「红人入驻问卷」→「红人信息采集助手」 |
| 6b | `AdminIntakePage.tsx` | 页面标题「入驻问卷配置」→「红人信息采集助手 · 配置」 |
| 6c | DB `workspace_tools` | `tool_name` + `status` 执行 SQL 更新 |

**改动量**：约 28 行净改，无新依赖，TypeScript 零新 `any`。

---

## 完成后验证

| 验证点 | 预期 |
|--------|------|
| 运营侧边栏 | 只有「概览 / 创作中心 / 任务中心 / 产出中心」，无「入驻问卷」 |
| 运营创作中心 `/workspace` | 工具卡片里有「红人信息采集助手」卡片（status online 后可点击） |
| 点击卡片 | 跳转 `/workspace/kol-intake`，页面正常 |
| 管理员侧边栏 | 无「入驻问卷」菜单，「功能管理」已改名「工具配置」 |
| 管理员工具配置 `/admin/workspace` | 有「工具列表」和「红人信息采集助手」两个 Tab |
| 切换到「红人信息采集助手」Tab | 显示 AI 配置 + 题目管理 + 全量提交，无重复标题 |
| `/admin/intake` 直接访问 | 仍可正常独立打开（路由保留） |
