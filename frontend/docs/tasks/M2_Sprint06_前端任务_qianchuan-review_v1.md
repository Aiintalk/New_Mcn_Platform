# M2 Sprint 6 · 前端任务 · qianchuan-review v1

> 状态：✅ 已完成（2026-06-13）
> 需求文档：`docs/pm/M2_Sprint06_qianchuan-review_需求文档.md`

---

## 一、新建 / 修改文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/types/qianchuanReview.ts` | 新建 | ScriptEntry / ExcelRow / GenerateRequest / SaveRequest / OutputItem / OutputsResponse 类型 |
| `src/api/qianchuanReview.ts` | 新建 | parseFile / generateReport / saveReport / getOutputs 四个 API 函数 |
| `src/pages/operator/QianchuanReviewPage.tsx` | 新建 | 三步流程页面（脚本上传 → Excel上传 → 复盘报告）+ 底部历史记录 |
| `src/App.tsx` | 修改 | 注册路由 `/workspace/qianchuan-review` + import QianchuanReviewPage |
| `frontend/package.json` | 修改 | 新增 `"xlsx": "^0.18.5"` 依赖 |

---

## 二、关键设计决策

| 决策 | 说明 |
|------|------|
| Excel 解析保留前端 | XLSX.js 本地解析（标准格式 + 转置格式），发 JSON 给后端，省去后端 openpyxl 依赖 |
| X-Task-Id 读取 | `generateReport()` 返回原始 `Response`，调用方读 `resp.headers.get('X-Task-Id')` 暂存，保存时带入 `/save` |
| .md 导出保留前端 | 浏览器 Blob 下载，文件名 `千川脚本复盘_{date}.md` |
| 复制报告 | `navigator.clipboard.writeText(report)` |
| 历史记录 | 工具页底部展示最近10条，点击「刷新」按需加载，不自动加载 |
| SimpleMarkdown 渲染 | 前端正则替换实现轻量 Markdown 渲染（与旧代码等价，无第三方 MD 库）|

---

## 三、Excel 字段映射（前端解析，10个字段）

| 字段 | 别名列表 |
|------|---------|
| `video_theme` | 素材名称、视频主题、素材标题、视频名称 |
| `spend` | 整体消耗、消耗、花费、总消耗 |
| `impressions` | 展示次数、展示、曝光、曝光次数 |
| `ctr` | 点击率、CTR、ctr、整体点击率 |
| `three_sec_rate` | 3s完播率、3秒完播率、3s完播、3秒播放率 |
| `conversions` | 转化数、成交数、订单数 |
| `cost_per_conversion` | 转化成本、成交成本、单次转化成本 |
| `roi` | ROI、roi、投产比、投产、整体支付ROI、支付ROI |
| `cpm` | 千次展示成本、CPM、cpm、千展成本、千次展现费用、整体千次展现费用 |
| `time_range` | 投放时段、时段、投放时间 |

同时支持标准格式（首行表头）和转置格式（首列字段名，千川常见导出）。

---

## 四、路由

- 路径：`/workspace/qianchuan-review`
- 组件：`QianchuanReviewPage`
- 入口：WorkspacePage → 点击「千川脚本复盘」工具卡片（tool_code='qianchuan-review'）

---

## 五、迭代修复记录

### v2 — 修复 xlsx 包缺失（2026-06-13）

**问题**：`QianchuanReviewPage.tsx` 引用了 `import * as XLSX from 'xlsx'`，但 `package.json` 未声明该依赖，导致 Vite 编译报错 `Failed to resolve import "xlsx"`，前端页面无法加载。

**修复**：在 `frontend/` 目录下执行 `npm install xlsx --save`，将 `"xlsx": "^0.18.5"` 写入 `package.json`，重启 Vite 后编译正常。

**发现时机**：功能测试（`/verify`）阶段 curl 模块时发现，TypeScript 编译（`tsc --noEmit`）未能检出（xlsx 包含自带 types，tsc 通过 node_modules resolution 找到了类型定义但实际运行时包不存在）。

---

## 六、tsc 结果

- `npx tsc --noEmit`：**0 错误** ✅

---

## 七、功能测试结果（/verify）

| 验证项 | 结果 |
|--------|------|
| 4个接口全部注册（/openapi.json）| ✅ |
| 未鉴权返回 401 | ✅ |
| parse-file 上传 txt | ✅ |
| parse-file 上传 xlsx → 400 UNSUPPORTED_FORMAT | ✅ |
| generate 空 scripts → 400 INVALID_INPUT | ✅ |
| generate 超 30 条 → 400 SCRIPTS_LIMIT_EXCEEDED | ✅ |
| generate 正常请求 → 流式返回 + X-Task-Id Header | ✅ |
| task_job 状态 processing → success | ✅ |
| save 保存报告 → outputs 表写入 | ✅ |
| outputs 列表返回正确结构 | ✅ |
| CORS expose_headers 含 X-Task-Id | ✅ |
| 前端页面模块编译正常（修复 xlsx 后）| ✅ |
