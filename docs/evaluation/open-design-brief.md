# AIGC 评测体系 — Open Design 设计简报

> **用途**：喂给 Open Design（或设计师），产出与现有平台风格一致的评测模块界面。  
> **原则**：UI 风格 100% 沿用现有 New_Mcn_Platform（Stone 暖灰 + 橙色品牌色），代码独立但视觉统一。  
> **配套**：周会对齐文档 `weekly-alignment-summary.md`、技术 spec `2026-07-17-aigc-evaluation-system-design.md`。  
> **日期**：2026-07-17

---

## 一、设计语言（必须严格遵守）

现有平台是 **Ant Design 5 + 自定义 CSS token**，配色是「Stone 暖灰系 + 橙色品牌」，**不是** AntD 默认蓝。所有新页面必须用同一套 token，禁止引入新主色。

### 1.1 配色

| 用途 | 变量 | 值 |
|------|------|-----|
| 品牌主色（按钮/强调/active） | `--brand` | `#f59a23`（橙） |
| 品牌浅底 | `--brand-light` | `rgba(245,149,35,0.08)` |
| 品牌描边 | `--brand-border` | `rgba(245,149,35,0.25)` |
| 品牌悬停 | `--brand-hover` | `#e08a1a` |
| 页面背景 | `--bg-page` | `#F8F7F4`（米色） |
| 卡片/表面 | `--bg-surface` / `--bg-card` | `#FFFFFF` |
| 表头底 | `--bg-header` | `#FAFAF9` |
| 侧边栏深底 | `--bg-sidebar` | `#1C1917`（近黑） |
| 描边 | `--border` | `#E7E5E4` |
| 灰阶（Stone） | `--gray-50…900` | `#FAFAF9` → `#1C1917` |
| 成功 | success | `#16A34A` / bg `#F0FDF4` |
| 警告 | warning | `#D97706` / bg `#FFFBEB` |
| 危险 | danger | `#DC2626` / bg `#FEF2F2` |
| 信息 | info | `#2563EB` / bg `#EFF6FF` |
| 辅色（多类别区分） | purple / cyan / pink | `#7C3AED` / `#0891B2` / `#EC4899` |

### 1.2 字体

- 正文：`Inter, -apple-system, "PingFang SC", BlinkMacSystemFont, "Segoe UI", sans-serif`
- 等宽（代码/评分明细）：`"SF Mono", "Fira Code", monospace`
- 基础字号：14px

### 1.3 圆角 / 间距 / 阴影

| token | 值 | 用途 |
|-------|-----|------|
| `--radius-sm` | 6px | 小元素、badge |
| `--radius-md` | 10px | 输入框、按钮、气泡 |
| `--radius-lg` | 14px | **卡片默认** |
| `--radius-xl` | 20px | 登录卡/大容器 |
| `--sp-1…8` | 4 / 8 / 12 / 16 / 20 / 24 / 32 | 间距节奏 |
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.04)` | **卡片默认** |
| `--shadow-md` | `0 2px 8px rgba(0,0,0,0.06)` | 卡片 hover |
| `--shadow-lg` | `0 8px 24px rgba(0,0,0,0.08)` | 弹窗/抽屉 |

**卡片统一视觉**：白底 + `1px solid var(--border)` + `radius-lg` + `shadow-sm`，hover 升 `shadow-md`。**禁止大投影 / 玻璃态 / 渐变卡**。

### 1.4 布局节奏

- 工具页外层 `padding: var(--sp-6)`（24px），单列可加 `maxWidth: 900px; margin: 0 auto`。
- 卡片内 padding `--sp-5`（20px）。
- 元素间距 `--sp-3`/`--sp-4`（12/16px）。

---

## 二、整体框架与入口

### 2.1 放在哪

评测体系挂两个入口，复用现有布局：

- **运营侧**（`OperatorLayout`，深色侧边栏 190px + 顶栏 52px + 主区 24px padding）：作为工作台的一个工具卡，进 `评测工作台`。
- **管理后台**（`AdminLayout`，分组菜单）：配置类（维度/rubric/版本/定时策略）放进「功能管理」分组，作为一个 tab。

侧边栏菜单沿用现有风格：深底 `#1C1917`，文字 `#A8A29E`，active 项直接用品牌橙 `#f59a23`。菜单图标用 emoji 字符（与现有一致，不用图标库）。

### 2.2 页面骨架（每个页面都用这个开头）

```
.page-header
  ├─ 左：.page-title（H1 22px 700）+ .page-desc（13px 灰）
  └─ 右：.page-actions（主操作按钮）
.card / .card-header + .card-body
```

---

## 三、复用组件（不要新造）

现有项目「通用组件」主要是 **CSS class**（在 `src/styles/admin.css`），评测模块直接用：

| class | 用途 |
|-------|------|
| `.page-header` / `.page-title` / `.page-desc` / `.page-actions` | 页头 |
| `.section-title`（带 `.st-line` 分隔线）| 区块小标题 |
| `.card` / `.card-header` / `.card-body` / `.workspace-step-card` | 卡片 |
| `.btn .btn-primary` / `.btn-ghost` / `.btn-danger-ghost` / `.btn-sm` | 按钮 |
| `.badge badge-{success,warning,danger,gray,info,brand,purple,cyan,pink}` | 状态标签 |
| `.filter-bar` / `.filter-input` / `.filter-select` | 筛选条 |
| `.ant-table`（已覆盖样式）| 表格 |
| `.pagination` / `.page-btn` | 分页（最多 5 页码）|
| `.empty-state` | 空态（36px 灰图标 + 14px 灰文字）|
| `.sub-tabs` / `.sub-tab.active` | 子页签 |
| `.stat-card` / `.stats-grid` | 统计卡 |

> 表格用**原生 `<table className="ant-table">`**，**不要引入 ProTable**。多步流程用 AntD `<Steps>`。反馈用 `App.useApp()` 的 `message`，删除用 `<Popconfirm okButtonProps={{danger:true}}>`。

---

## 四、待设计页面清单

按使用角色分两组，共 7 个页面（含若干子视图）。

### 页面 1 · 测试集管理（TestCaseList / TestCaseEdit）
**角色**：开发者/管理员 + 运营

- **列表页**：`.page-header`（标题「测试集」+ 右上「新建样本」主按钮）+ `.filter-bar`（按标签/关键词筛选）+ `.ant-table`。
  - 列：名称、标签（badge 多色）、最近评分、是否启用（switch）、创建人、操作（编辑/软删，行内 `.btn-ghost btn-sm` + Popconfirm）。
  - 分页用 `.pagination`。
- **编辑页**：`.page-header` + 一张 `.card` 表单：
  - 名称、描述
  - **选择达人**（下拉，复用现有达人选择交互）
  - **产品卖点卡**（文本域 / 文件上传拖拽区 `border: 2px dashed var(--brand-border)`）
  - **参考脚本/原版**（文本域）
  - **对话上下文 messages**（JSON 或多行文本）
  - **标签 tags**（可多选/自定义的 tag 输入）
  - 期望输出（可选，文本域）
  - 底部「保存」主按钮 + 「取消」。

### 页面 2 · 维度管理（DimensionList / DimensionEdit）
**角色**：开发者/管理员

- **列表页**：`.ant-table` 列：维度名（中英）、默认权重（进度条或百分比）、分数区间、是否启用、操作。
- **编辑页**：`.card` 表单 —— 维度英文名 name、展示名 display_name、说明 description、默认权重（数字/滑块 0–1）、分数区间 score_min/max、**评分 Prompt 模板**（多行代码框，等宽字体，支持 `{{generated_output}}` 等占位符提示）。
- **Rubric 子表**：同页下方一张 `.card`，表格列 —— 分数等级 level（如 1/3/5/7/10）、标准描述 criteria、场景标签 scenario_tag（可空）、操作。可整表编辑保存。

### 页面 3 · 版本快照管理（VersionList / VersionCreate / Clone）
**角色**：开发者/管理员

- **列表页**：`.ant-table` 列 —— 版本名、工具、模型、创建时间、是否启用、操作（查看 / **复制为新版本** / 软删）。**注意：版本不可编辑**，没有"编辑"按钮，只有"复制"。
- **创建/复制页**（抽屉或独立页）：`.card` 表单 ——
  - 版本名、说明
  - **生成模型**（model_id + provider 下拉，复用 ai_models）
  - **system_prompt 模板**（大文本代码框，等宽，带占位符提示）
  - temperature / max_tokens（数字输入）
  - **维度权重覆盖**（每个维度一行：维度名 + 权重数字框，默认填入维度默认值）
  - **评分模型**（scoring_model_id + provider + scoring_temperature）
  - 选项：☑ 创建后自动触发回归（+ 选标签集）
  - 源版本（如果是 clone，只读显示 parent）
  - 底部「创建版本」主按钮。
- **版本详情**：只读展示 config_payload 全部内容（只读代码块）+ 历史运行列表。

### 页面 4 · 运行管理（RunList / RunDetail）
**角色**：开发者/管理员 + 运营

- **触发运行**（列表页右上「新建运行」打开抽屉）：选版本 + 选样本范围（全部/按标签）+ 运行名 → 「开始运行」。
- **列表页**：`.ant-table` 列 —— 运行名、版本、触发方式（badge：手动/自动/定时）、状态（badge + `.step-dot`：pending/processing/success/failed）、进度（`completed/total` + 进度条 `.bar-track`/`.bar-fill`）、平均分、时间、操作（查看）。
- **详情页**：
  - 顶部 `.page-header`（运行名 + 状态 badge + 整体平均分大数字）+ 一排 `.stat-card`（总样本/完成/失败/平均分/耗时）。
  - 维度概览：3 个维度的平均分（可用 `.stat-card` 或小雷达图 Recharts）。
  - **样本明细表** `.ant-table`：每行一个 case —— 样本名、标签、生成输出（截断 + 点击展开 Modal/Drawer 看全文）、各维度 AI 分（badge 着色）、人工分、操作（**人工校准**、查看）。
  - 状态为 running 时显示进度条 + 自动刷新提示。

### 页面 5 · 人工校准（RunDetail 子视图 / Modal）
**角色**：开发者/管理员 + 运营

- 对单条 case 的某维度：左侧展示「生成输出 + AI 评分 + AI 理由」，右侧「人工分数（数字/滑块）+ 反馈文本」。保存后写入历史。可参照现有 `OutputHistoryDrawer` 抽屉模式。

### 页面 6 · 版本对比报告（ComparePage）
**角色**：开发者/管理员

- 顶部选择两个 run（A 基线 vs B 新版）。
- **总体 diff**：`.stat-card` 卡 —— 平均分变化（大数字 + ↑↓ 箭头，绿色改善/红色恶化/灰色持平）。
- **维度 diff**：3 行，每行一个维度，左右两个 run 的平均分 + 变化箭头（可用 Recharts 条形对比或简单表格）。
- **样本级 diff**：`.ant-table` —— 样本名、标签、A 分、B 分、变化（↑↓→ badge）、操作（查看输出对比）。
  - 顶部 tab/筛选：全部 / 改善 / 恶化 / 持平。
  - 「改善」绿、「恶化」红 badge 一目了然。

### 页面 7 · 定时策略（SchedulePolicyList）
**角色**：开发者/管理员

- `.ant-table` 列 —— 策略名、cron 表达式（等宽显示）、版本、标签、是否启用（switch）、操作。
- 新建/编辑（Modal 或抽屉）：策略名、cron（输入 + 下次执行时间预览）、选版本（或"最新启用版本"）、标签集、启用开关。

---

## 五、交互规范（与现有一致）

1. **反馈**：成功/失败/警告全走 `message.success/error/warning`，文案短促（"已保存"、"运行已启动"）。
2. **危险操作**：软删用 `<Popconfirm okButtonProps={{danger:true}}>`，确认文案"确定删除？此操作可恢复"。
3. **加载态**：表格/列表用 `.empty-state`"加载中…"；抽屉内 `<Spin>`；按钮 `loading`。
4. **运行进度**：running 时进度条 + "生成中…"小 spinner（品牌橙色），完成后自动刷新。
5. **流式输出**（详情页查看生成过程，可选）：assistant 左白底描边气泡、user 右橙色实心，底部只读，不在此处发送。
6. **空态**：无数据时 `.empty-state` + 引导文案（"还没有测试样本，点击右上角新建"）。

---

## 六、一致性 Checklist（交付前对照）

- [ ] 主色只用 `#f59a23`，无新主色
- [ ] 卡片：白底 + `--border` 描边 + `radius-lg` + `shadow-sm`
- [ ] 页头用 `.page-header` + `.page-title` + `.page-desc`
- [ ] 表格用原生 `<table className="ant-table">` + `.pagination`
- [ ] 状态用 `.badge badge-{success/warning/danger/gray/brand}`
- [ ] 多步用 AntD `<Steps>`；两态用 input/result 切换
- [ ] 反馈用 `App.useApp()` 的 `message`，删除用 `Popconfirm`
- [ ] 间距用 `--sp-*`，圆角用 `--radius-*`，不写魔法数字
- [ ] 统计卡用 `.stat-card`，图表用 Recharts（已装）
- [ ] 菜单/工具卡入口复用 `WorkspacePage` + `App.tsx` 路由模式

---

## 七、给 Open Design 的提示词建议

把以上 1–4 节投喂时，可附一句总指令：

> 为 New_Mcn_Platform 的「AIGC 评测体系」设计 7 个页面。风格严格沿用：Ant Design 5 + Stone 暖灰底（#F8F7F4）+ 橙色品牌色（#f59a23），卡片白底描边圆角 14px 浅阴影，表格原生样式，状态用彩色 badge。页面骨架统一「页头（标题+副标题+右上主操作）+ 卡片内容区」。先出：① 测试集列表+编辑 ② 运行详情（含评分明细+人工校准）③ 版本对比报告 这三个核心页面的高保真稿，其余页面同风格延展。
