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

## 四、tsc + 测试结果

- `tsc --noEmit`：0 错误 ✅
- `vitest run`：**86/86 通过**（11 个测试文件）✅
