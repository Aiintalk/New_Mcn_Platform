# 千川脚本复盘（qianchuan-review）· 迁移需求文档

> 读者：协作开发者，无需阅读原始代码即可完成实现
> 源码位置：`Ai_Toolbox/qianchuan-review-web/`
> 原始迁移需求文档：`Ai_Toolbox/系统架构方案及M1进度同步/qianchuan_review_迁移需求文档.md`（v1.3）
> 文档状态：需求澄清完成（2026-06-13），Sprint 6 实施完成（2026-06-13）

---

## 一、工具概述

| 项目 | 说明 |
|------|------|
| 原工具路径 | `Ai_Toolbox/qianchuan-review-web/` |
| 功能描述 | 三步工作流：上传千川脚本 → 上传投放数据（可选）→ AI 流式生成复盘报告；支持下载 .md 报告，保存到产出中心，查看历史记录 |
| AI 模型 | 固定 `claude-sonnet-4-6`（不依赖 Key Pool 默认值）|
| 外部依赖 | 无（无 TikHub / OSS / ASR）|
| 语言 | 中文界面，中文 System Prompt，中文输出 |

**变与不变总结：**
- **不变**：三步工作流、System Prompt A/B 两个版本（逐字保留）、脚本-Excel 模糊匹配算法（12字前缀/6字 includes）、Excel 字段别名映射、脚本截断 2000 字、消耗降序排列、.pages 解析逻辑、AI 流式输出、.md 导出（留前端）
- **变**：加 JWT 认证、Excel 解析保留前端（XLSX.js），发 JSON 给后端、结果保存到 `outputs` 表、AI 调用走统一 yunwu adapter、脚本-Excel 合并移至后端、System Prompt 移至 `prompts.py` 常量、旧历史 JSON 文件迁移到 `outputs` 表

---

## 二、需求澄清记录（2026-06-13）

| 问题 | 结论 |
|------|------|
| API 路由前缀 | 跟随现有惯例 `/api/tools/qianchuan-review/...` |
| Excel 解析位置 | 保留前端 XLSX.js 解析，发 JSON 给后端（省去 openpyxl 依赖）|
| stream_chat() 是否新增 | 直接复用 `yunwu_adapter.chat_stream()`，无需新增 |
| file_parser.py `.pages` 是否已有 | 已有 `_parse_pages_selling_point()`，但缺日历噪声过滤，新增专用函数 |
| 旧数据迁移 | 需要，归属 `username='admin'` 账号 |
| Nginx 超时 | 为 `/generate` 单独配置 `proxy_read_timeout 300s`，写进运维任务单 |
| 脚本数量上限 | 硬上限 30 条，超出返回 400 |
| task_id 传递方式 | Response Header `X-Task-Id`，前端读 header 后带入 /save |
| 模型 | 固定 `claude-sonnet-4-6` |

---

## 三、工作流步骤（3步，完全保留）

| 步骤 | 用户操作 | 系统行为 |
|------|---------|---------|
| **Step 1 · 上传脚本** | 上传文件（.txt/.md/.docx/.pages，可批量）；或粘贴文案（多条用 `===` 分隔）| 逐文件解析文本，提取标题（首行非空，最多60字）；粘贴内容按分隔符切分 |
| **Step 2 · 上传投放数据** | 上传千川后台导出的 Excel（.xlsx/.xls/.csv）；可跳过 | 浏览器端 XLSX.js 解析（标准格式+转置格式），提取 10 个指标字段；预览表格 |
| **Step 3 · 复盘报告** | 点击「生成复盘报告」或「跳过直接生成」| 后端合并匹配+排序+Prompt 构建+AI 流式生成；前端实时展示，可保存/导出/复制 |

---

## 四、接口设计

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tools/qianchuan-review/parse-file` | 上传脚本文件，返回文本（.txt/.md/.docx/.pages，不支持 .pdf）|
| POST | `/api/tools/qianchuan-review/generate` | 提交脚本+数据，SSE 流式返回复盘报告，Header 含 `X-Task-Id` |
| POST | `/api/tools/qianchuan-review/save` | 保存报告到 outputs 表 |
| GET  | `/api/tools/qianchuan-review/outputs` | 查询历史复盘报告列表（operator 只看自己，admin 看全部）|

**关键规则：**
- `scripts` 至少 1 条，最多 30 条（超出返回 400）
- `excel_data` 可为空数组（跳过投放数据场景）
- has_excel=true 时用 PROMPT_WITH_EXCEL，否则用 PROMPT_WITHOUT_EXCEL
- CORS 新增 `expose_headers=["X-Task-Id"]`

---

## 五、.pages 解析差异（与 selling-point 版本）

qianchuan-review 的 `.pages` 解析新增4条日历噪声过滤（与原始 JS 逻辑等价）：
- `星期[一二三四五六日][BJR]`
- `[一二...十]+月` 开头且长度 < 20
- `第[一二三四]季度` 且长度 < 20
- `公元` 开头且长度 < 10

selling-point 版本无此过滤（有意为之）。

---

## 六、迁移规范合规清单

| 红线 | 状态 |
|------|------|
| 红线 1：入口在创作中心 | ✅ WorkspacePage + workspace_tools 已注册（migrations/011已有） |
| 红线 2：产出接入产出中心 | ✅ 存 outputs 表，tool_code='qianchuan-review' |
| 红线 3：AI 走统一 adapter | ✅ yunwu_adapter.chat_stream |
| 红线 4：Prompt 写进代码常量 | ✅ `tools/qianchuan_review/prompts.py`（本工具 Prompt 无需管理端配置）|
| 红线 5：纳入功能配置 | ✅ workspace_tools 已注册 status=dev |
| 红线 6：调用写日志 | ✅ yunwu_adapter 内置写 ai_call_logs |

---

## 七、旧数据迁移

旧系统在 `/opt/qianchuan-review/reports/` 存有历史 JSON 报告。

| 旧字段 | 新字段 | 说明 |
|--------|--------|------|
| `report` | `content` | 报告 Markdown 文本 |
| `scripts.length` | `content_json.script_count` | 脚本条数 |
| `excelData.length > 0` | `content_json.has_excel` | 是否含投放数据 |
| `createdAt` | `created_at` | 创建时间 |
| 无 | `created_by` = admin 账号 | 旧系统无用户概念 |

迁移脚本：`backend/scripts/migrate_qianchuan_reports.py`，支持 `--dry-run`。

---

## 八、不做清单

- 不把 .md 导出改为经过后端
- 不把 Excel 解析移到后端（省去 openpyxl 依赖）
- 不对 Prompt 做管理端配置（本工具固定 Prompt，与 selling-point 不同）
- 不做频率限制（内部50人使用，前端防抖足够）
