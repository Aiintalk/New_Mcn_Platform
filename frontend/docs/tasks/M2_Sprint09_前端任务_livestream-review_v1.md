# M2 Sprint 9 — 前端任务：直播间脚本复盘（livestream-review）

> 状态：✅ 已完成，人工验证通过  
> 完成日期：2026-06-16  
> 分支：`0615_livestream-review`（已合并 main）

---

## 一、任务范围

| 文件 | 说明 |
|------|------|
| `frontend/src/api/livestreamReview.ts` | API 封装：parseFile / generateStream / saveReport / getOutputs |
| `frontend/src/pages/operator/LivestreamReviewPage.tsx` | 三步向导页面（上传脚本 → 上传直播数据 → 复盘报告） |
| `frontend/src/App.tsx` | 注册路由 `/workspace/livestream-review` |

## 二、功能说明

### Step 1 — 上传脚本
- 点击/拖拽上传（.txt / .md / .docx / .pages），支持批量
- .txt/.md 前端直读，.docx/.pages 调后端 parse-file
- 手动粘贴区（`===` 分隔多场）
- 已添加列表展示（序号、标题、来源、字数、删除）

### Step 2 — 上传直播数据（可选）
- 上传 Excel（.xlsx/.xls/.csv），XLSX.js 前端解析
- 支持标准格式（首行列头）和转置格式（首列指标名）两种布局
- 识别 14 个字段（liveTheme/gmv/peakViewers 等）
- 解析预览表格（8 列）
- 「跳过直接生成」按钮

### Step 3 — 复盘报告
- SSE 流式展示报告（实时滚动）
- 生成完成后：保存到产出中心 / 复制 / 导出 .md
- 历史报告弹层

## 三、技术约束

- 所有 JSON 请求走 `request.ts`（get/post/put）
- parse-file 用原生 fetch + FormData（例外标记已注明）
- generateStream 用原生 fetch + Promise\<Response\>（例外标记已注明）
- 全部 inline style，无 Tailwind class
- 绿色系（#10b981）主色调
