# M2 Sprint 11 — 前端任务：千川文案预审（qianchuan-preview）v1

> 状态：已完成  
> 完成日期：2026-06-18  
> 对应需求文档：`docs/pm/M2_Sprint11_qianchuan-preview_需求文档.md`

---

## 一、任务清单

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| F1 | 类型定义 | `src/types/qianchuanPreview.ts` | ✅ 完成 |
| F2 | API 模块 | `src/api/qianchuanPreview.ts` | ✅ 完成 |
| F3 | 运营端页面 | `src/pages/operator/QianchuanPreviewPage.tsx` | ✅ 完成 |
| F4 | 管理端 Tab | `src/pages/admin/QianchuanPreviewConfigTab.tsx` | ✅ 完成 |
| F5 | 路由注册 | `src/App.tsx` | ✅ 完成 |
| F6 | 工具配置页挂载 | `src/pages/admin/WorkspaceConfigPage.tsx` | ✅ 完成 |

---

## 二、关键约束落实

- ✅ 禁用 Tailwind：全部使用 `var(--brand)` / `card` / `btn-primary` / `var(--success)` 等 CSS 变量体系
- ✅ API 三个接口均为 fetch 例外（FormData / SSE getReader / .blob()），并在 `qianchuanPreview.ts` 注释中明确标注
- ✅ 无历史记录功能（与旧工具保持一致）
- ✅ `SimpleMarkdown` 组件内联实现，不引入新依赖

---

## 三、API 封装说明（红线 #3 合规）

| 函数 | 例外类型 | 说明 |
|------|---------|------|
| `parseFile` | FormData | FormData 上传，手动处理标准信封 `.data` |
| `chatStream` | SSE getReader | 原生 fetch 返回 Response，由页面 getReader 消费 |
| `exportWord` | .blob() | Blob 下载，不用 request.ts |

---

## 四、页面结构

```
QianchuanPreviewPage
├── Header（页面标题 + 描述）
├── 错误提示区
├── 双列文案输入（renderSide('a') / renderSide('b')）
│   ├── 文件上传拖拽区（.txt / .docx，调 parseFile）
│   └── textarea 粘贴区
├── 开始预审按钮
└── 报告展示区（SimpleMarkdown 渲染）
    └── 操作按钮（复制 / 导出 Word）
```

---

## 五、管理端 ConfigTab

`QianchuanPreviewConfigTab.tsx` 对齐项目标准模式：
- empty-state 初始态
- Prompt 编辑 textarea
- AI 模型选择
- 保存后刷新
- 使用 `destroyOnHidden`（非废弃 API）
