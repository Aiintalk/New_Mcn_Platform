# MCN Platform — UI 设计规范

> 最后更新：2026-06-08（M2 阶段）  
> 技术栈：React + TypeScript + Ant Design 5.x + Recharts  
> CSS 方案：CSS 自定义属性（variables.css + admin.css），不使用 Tailwind

---

## 一、品牌色与配色系统

### 主色

| 变量 | 值 | 用途 |
|------|----|------|
| `--brand` / `--accent` | `#f59a23` | 主色调，按钮、激活态、高亮 |
| `--brand-light` | `rgba(245,149,35,0.08)` | 品牌色背景浅色填充 |
| `--brand-border` | `rgba(245,149,35,0.25)` | 品牌色边框 |
| `--brand-hover` | `#e08a1a` | 主按钮 hover |
| `--brand-dark` | `#d47800` | 主按钮 active |

### 灰阶（暖灰石色系）

| 变量 | 值 |
|------|----|
| `--gray-50` | `#FAFAF9` |
| `--gray-100` | `#F5F5F4` |
| `--gray-200` | `#E7E5E4` |
| `--gray-300` | `#D6D3D1` |
| `--gray-400` | `#A8A29E` |
| `--gray-500` | `#78716C` |
| `--gray-600` | `#57534E` |
| `--gray-700` | `#44403C` |
| `--gray-800` | `#292524` |
| `--gray-900` | `#1C1917` |

### 语义色

| 变量 | 值 | 用途 |
|------|----|------|
| `--success` | `#16A34A` | 成功、在线 |
| `--warning` | `#D97706` | 警告、进行中 |
| `--danger` | `#DC2626` | 错误、危险操作 |
| `--info` | `#2563EB` | 信息提示 |
| `--purple` | `#7C3AED` | 辅助色 |
| `--cyan` | `#0891B2` | 辅助色 |
| `--pink` | `#EC4899` | 辅助色 |

### 背景层级

| 变量 | 值 | 用途 |
|------|----|------|
| `--bg-page` | `#F8F7F4` | 页面底色 |
| `--bg-card` | `#FFFFFF` | 卡片背景 |
| `--bg-muted` | `#F5F5F4` | 次要区域背景 |
| `--bg-header` | `#FAFAF9` | 表头背景 |
| `--bg-sidebar` | `#1C1917` | 侧边栏深色背景 |

---

## 二、字体

| 变量 | 值 |
|------|----|
| `--font-sans` | `Inter, -apple-system, "PingFang SC", BlinkMacSystemFont, "Segoe UI", sans-serif` |
| `--font-mono` | `"SF Mono", "Fira Code", "Cascadia Code", monospace` |

---

## 三、圆角 / 间距 / 阴影

### 圆角

| 变量 | 值 |
|------|----|
| `--radius-sm` | `6px` |
| `--radius-md` | `10px` |
| `--radius-lg` | `14px` |
| `--radius-xl` | `20px` |

### 间距

| 变量 | 值 |
|------|----|
| `--sp-1` | `4px` |
| `--sp-2` | `8px` |
| `--sp-3` | `12px` |
| `--sp-4` | `16px` |
| `--sp-5` | `20px` |
| `--sp-6` | `24px` |
| `--sp-8` | `32px` |

### 阴影

| 变量 | 值 |
|------|----|
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.04)` |
| `--shadow-md` | `0 2px 8px rgba(0,0,0,0.06)` |
| `--shadow-lg` | `0 8px 24px rgba(0,0,0,0.08)` |

---

## 四、页面结构

### 整体布局（.app-shell）

```
┌──────────────────────────────────────────────────┐
│  sidebar(190px)  │  main-content(flex:1)          │
│                  │  ┌────────────────────────────┐ │
│  logo            │  │ topbar(52px)               │ │
│  nav             │  ├────────────────────────────┤ │
│  user/logout     │  │ main-body(overflow-y:auto) │ │
│                  │  └────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

- 侧边栏：深色（`#1C1917`），宽 190px
- Topbar：白底，52px 高，面包屑 + 用户名
- Main-body：`padding: 24px`，可垂直滚动

---

## 五、侧边栏导航

### 运营端菜单

| 路径 | 标签 | 图标 |
|------|------|------|
| `/` | 概览 | ⊞ |
| `/workspace` | 创作中心 | ✦ |
| `/workspace/kol-intake` | 入驻问卷 | 📋 |
| `/tasks` | 任务中心 | ☑ |
| `/outputs` | 产出中心 | ⬇ |

### 管理后台菜单

**功能管理组：**
- 仪表盘 `/admin`
- 用户管理 `/admin/users`
- 红人管理 `/admin/kols`
- 入驻问卷 `/admin/intake`
- 功能管理 `/admin/workspace`
- 产品管理 `/admin/tasks`
- 用户产出 `/admin/outputs`

**系统管理组：**
- 服务状态 `/admin/system`
- 服务配置 `/admin/config`
- 用户日志 `/admin/audit`
- 系统日志 `/admin/logs`

### 导航项样式

- 默认：`color: --sidebar-text (#A8A29E)`
- Hover：`rgba(255,255,255,0.06)` 背景，白色文字
- Active：`background: --brand (#f59a23)`，白色文字

---

## 六、通用组件

### 卡片（.card）

```
background: white
border: 1px solid --border (#E7E5E4)
border-radius: --radius-lg (14px)
box-shadow: --shadow-sm
margin-bottom: 16px
```

- `.card-header`：`padding: 16px 20px`，下边框，标题 + 操作区
- `.card-body`：`padding: 20px`
- `.card-title`：`font-size: 14px, font-weight: 600`

### 按钮

| 类名 | 样式 |
|------|------|
| `.btn-primary` | 品牌橙背景，白字 |
| `.btn-ghost` | 透明背景，灰色边框 |
| `.btn-danger-ghost` | 透明背景，红色边框 |
| `.btn-sm` | `padding: 4px 10px, font-size: 12px` |

### 徽章（.badge）

| 类名 | 颜色 | 用途 |
|------|------|------|
| `.badge-success` | 绿色 | 成功/在线 |
| `.badge-warning` | 橙色 | 进行中/警告 |
| `.badge-danger` | 红色 | 失败/危险 |
| `.badge-gray` | 灰色 | 待处理/归档 |
| `.badge-brand` | 品牌橙 | 工具名/分类 |
| `.badge-info` | 蓝色 | 信息 |
| `.badge-purple` | 紫色 | 辅助 |

### 表格（.ant-table）

- 表头：`background: --bg-header`，字重 600
- 行高：`padding: 12px 16px`
- Hover：`background: --gray-50`
- 边框：行间 `1px solid --gray-100`

### 筛选栏（.filter-bar）

- `.filter-input`：输入框，focus 时品牌橙边框 + 光晕
- `.filter-select`：下拉选择，自定义箭头图标

### 分页（.pagination）

- 分页按钮：32×32px，active 状态品牌橙背景

---

## 七、运营端首页布局

```
┌─────────────────────────────────────────────────┐
│  欢迎语 + "开始创作"按钮                          │
├────────┬────────┬────────┬────────┤
│ 今日产出│ 本周产出│ 进行中  │ Token  │  ← 4卡片
├──────────────────────┬──────────────┤
│ 内容生成趋势（折线图）  │ 工具使用占比  │
│ 最近7天               │ 环形图+图例   │
├─────────────────────────────────────────────────┤
│ 常用工具快捷入口（3列，最多6个）                    │
├──────────────────┬──────────────────┤
│ 最近任务（表格）   │ 最近产出（表格）   │
└──────────────────┴──────────────────┘
```

**图表库：** Recharts  
**折线图色：** `--accent (#f59a23)`  
**环形图色：** `['#4F6EF7', '#36CFC9', '#FFA940', '#FF7875', '#D9D9D9']`

---

## 八、登录页

- 背景：品牌橙渐变 `135deg, #f59a23 → #e07a00 → #c85e00`
- 登录卡片：白底，`border-radius: --radius-xl (20px)`，`width: 400px`
- Logo 区：`64×64px` 橙色圆角方块，白色文字
- 动效：卡片入场 `slideUp 0.35s ease`

---

## 九、公开页面（/intake/:token）

博主入驻问卷，无需登录，独立路由，不使用 app-shell 布局。

---

## 十、页面标题规范

```tsx
<div className="page-header">
  <div>
    <h1 className="page-title">页面标题</h1>
    <p className="page-desc">副标题说明</p>
  </div>
  <div className="page-actions">
    <button className="btn btn-primary">主操作</button>
  </div>
</div>
```

- 标题：`font-size: 22px, font-weight: 700`
- 副标题：`font-size: 13px, color: --gray-500`
