# M2 Sprint 5 · 前端任务 · selling-point-extractor v1

> 状态：✅ 已完成（2026-06-13）
> 需求文档：`docs/pm/M2_Sprint05_selling-point-extractor_需求文档.md`

---

## 一、新建 / 修改文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/types/sellingPoint.ts` | 新建 | UploadedFile / HistoryItem / HistoryRecord / SellingPointConfig 类型 |
| `src/api/sellingPoint.ts` | 新建 | chatStream / parseFile / 历史 CRUD / admin config API |
| `src/pages/operator/SellingPointPage.tsx` | 新建 | 运营端 3 步页面 |
| `src/pages/admin/SellingPointConfigTab.tsx` | 新建 | 管理端 Prompt+模型配置 Tab |
| `src/App.tsx` | 修改 | 注册路由 `/workspace/selling-point-extractor` |
| `src/pages/operator/WorkspacePage.tsx` | 修改 | 新增 `selling-point-extractor` tool_code 跳转 |
| `src/pages/admin/WorkspaceConfigPage.tsx` | 修改 | 新增「产品卖点提取器」Tab |

---

## 二、关键设计决策

| 决策 | 说明 |
|------|------|
| chatStream 不传 systemPrompt | 后端从 `selling_point_configs` 表读取，前端只传 `messages` |
| 消息裁剪保留前端 | `trimMessages()`：保留第 1 条 + 最后 8 条 |
| .md 导出保留前端 | 浏览器 Blob 下载，文件名 `极致卖点卡.md` |
| 产品名提取保留旧逻辑 | 正则从 AI 返回内容提取，默认「未命名产品」 |

---

## 三、路由

- 路径：`/workspace/selling-point-extractor`
- 组件：`SellingPointPage`
- 管理端 Tab key：`selling-point`（位于「工具配置」页）

---

## 四、迭代修复记录

### v2 — CSS 重写（2026-06-13）

**问题**：`SellingPointPage.tsx` 初版使用 Tailwind CSS 类（`min-h-screen`、`rounded-2xl` 等），项目未安装 Tailwind，样式全部失效，页面布局破碎。

**修复**：将 return JSX 中所有 Tailwind 类替换为项目 CSS 体系：
- 容器改用 `card` / `card-body`
- 按钮改用 `btn btn-primary` / `btn btn-ghost`
- 配色改用 `var(--brand)`、`var(--gray-*)`、`var(--danger)`、`var(--success)` 等 CSS 变量
- 标题区改用 `page-header` / `page-title` / `page-desc`
- 去掉全屏渐变背景，由 OperatorLayout 的 `.main-body` 提供容器

### v3 — 拖拽上传（2026-06-13）

**需求**：上传框支持直接拖拽文件，提升操作效率。

**修复**：
- 新增 `briefDragOver` / `scriptDragOver` state
- Step 1、Step 2 上传区从 `<button>` 改为 `<div>`，绑定 `onDragOver` / `onDragLeave` / `onDrop`
- 拖拽悬浮时边框加深、背景变深、文字提示「松开即可上传」
- 松手后复用 `handleFilesUpload`，与点击共用同一逻辑

---

## 五、tsc + 测试结果

- `tsc --noEmit`：0 错误 ✅
- `vitest run`：**86/86 通过**（11 个测试文件）✅
