# M2 Sprint 24 — 前端任务开发验收：红人工作台 UI 一致性优化 v1

## 验收结果

通过。

## 改动摘要

- `KolWorkspacePage` 增加 `workspace-shell` / `workspace-sidebar` / `workspace-nav-item` 等专用 class，左侧导航对齐全站 190px 深色侧栏与橙色 active 状态。
- `PersonaWriterPage` 与 `SeedingWriterPage` 仅在 Module 模式启用 `workspace-tool-module`，独立页面不受影响。
- `PersonaWriterPage`、`SeedingWriterPage`、`QianchuanWriterPage`、`TiktokWriterPage` 的步骤卡片统一挂载 `workspace-step-card`，补齐 20px 内边距，避免输入框/文本框贴边。
- `admin.css` 新增工作台外壳、导航、内嵌工具容器与步骤卡片留白样式。
- `KolWorkspacePage.test.tsx` 增加工作台视觉一致性与写作步骤卡片留白回归断言，并修正一个已过期的对标账号弹窗文案断言。

## 验证

- `npx vitest run src/__tests__/components/pages/KolWorkspacePage.test.tsx`：21 passed。
- Chrome 真实页面预览：
  - `/kol-workspace/1` 工作台首页正常。
  - 人设仿写模块正常，左侧 active 与全站一致。
  - 种草仿写模块正常，内嵌宽度为 960px，左对齐。
  - 种草仿写步骤卡片真实浏览器测量为 `padding: 20px`，输入框距离卡片左边约 21px，不再贴边。

## 契约影响

无。未改接口、数据库、权限和后端逻辑。
