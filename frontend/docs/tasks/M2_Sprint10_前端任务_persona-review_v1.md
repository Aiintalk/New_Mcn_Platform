# M2 Sprint 10 — 前端任务：人设脚本复盘（persona-review）

> 状态：进行中  
> 路由：`/workspace/persona-review`

---

## 一、任务清单

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| F1 | API 模块 | `src/api/personaReview.ts` | generateStream / saveReport / getOutputs（无 parseFile） |
| F2 | 类型定义 | `src/types/personaReview.ts`（可内联） | ScriptEntry / ExcelRow / MergedItem / OutputItem |
| F3 | 主页面 | `src/pages/operator/PersonaReviewPage.tsx` | 三步向导，XLSX 解析仅转置格式，SSE 流式 |
| F4 | 管理端 Tab | `src/pages/admin/PersonaReviewConfigTab.tsx` | Prompt + 模型配置 |
| F5 | 路由注册 | `src/App.tsx` | 新增 `/workspace/persona-review` |
| F6 | 工具配置页挂载 | `src/pages/admin/WorkspaceConfigPage.tsx` | 挂载 PersonaReviewConfigTab |

---

## 二、关键约束

- 禁止 Tailwind class（项目未安装），使用 `var(--brand)` / `card` / `btn-primary` 等 CSS 变量体系
- xlsx 包已安装（Sprint 6 已加），直接 import
- 前端 Excel 解析：**仅转置格式**（首列为指标名），识别 10 个字段
- 两侧清洗规则不同：Excel 侧无 `#@`，脚本侧有 `#@`（由后端处理，前端只传原始数据）
- 保存后展示历史抽屉，复用 outputs 接口
- 导出文件名格式：`人设脚本复盘_YYYY-MM-DD.md`
