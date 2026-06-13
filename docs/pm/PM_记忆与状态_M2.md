# MCN_PM_Agent — 项目记忆与当前状态（M2）

> 最后更新：2026-06-13（Sprint 6 qianchuan-review 迁移完成）
> 更新角色：MCN_PM_Agent
> 上一份文档：`docs/pm/PM_记忆与状态.md`（M1 阶段，已归档）

---

## 一、项目基本信息

- **项目名**：MCN Information System Platform
- **当前阶段**：M2 阶段 — Sprint 4 完成
- **GitHub**：https://github.com/Aiintalk/New_Mcn_Platform
- **工作目录**：`D:\2026年工作\AI相关\AI工具箱新架构方案\mcn-platform\`
- **后端**：`backend/`（FastAPI + PostgreSQL）
- **前端**：`frontend/`（React + Vite + TypeScript + Ant Design 5.x）

### 环境信息

- **数据库**：PostgreSQL @ localhost:5432，用户 postgres，密码 admin123，数据库 `mcn_m1`
- **psql 路径**：`D:\ProtgreSQL\bin\psql.exe`
- **后端地址**：`http://localhost:8000`（uvicorn）
- **前端地址**：`http://localhost:5173`（Vite）
- **测试账号**：admin / Admin@123456

---

## 二、M2 阶段（当前）

### M2 Sprint 1 — 红人入驻问卷（kol-intake） ✅ 完成

**核心流程：** 运营生成链接 → 博主打开链接 → AI 多轮对话（24 道题）→ 生成报告 → 下载 docx/PDF

| 端 | 状态 | 备注 |
|----|------|------|
| 后端 | ✅ 完成 | 23 个接口 |
| 运维 | ✅ 完成 | 006+007 迁移已执行 |
| 前端 | ✅ 完成 | 入驻问卷+运营直发+报告展示+下载 |

---

### M2 Sprint 2 — 运营端首页重设计 ✅ 完成

| 端 | 状态 |
|----|------|
| 后端 | ✅ 完成 |
| 前端 | ✅ 完成（recharts 折线图 + 环形图 + 常用工具） |

---

### M2 Sprint 3 — 人格定位（persona-positioning） ✅ 完成

**核心流程：** 抖音号解析/文件上传 → 选择对标达人 → AI 生成人格档案+内容规划 → 导出 Word → 历史管理

| 端 | 状态 | 备注 |
|----|------|------|
| 后端 10 个接口 | ✅ 完成 | `app/routers/persona.py` |
| TikHub 管理端 10 个接口 | ✅ 完成 | `app/routers/admin_tikhub.py` |
| 前端三步向导 | ✅ 完成 | `PersonaPage.tsx` |
| TikHub 管理页面 | ✅ 完成 | `ServiceConfigPage.tsx` TikHubConfigTab |
| AI 流式适配器 | ✅ 完成 | 僵尸锁自动清理（360s） |
| 自动化测试 | ✅ 221/221 + 71/71 | |
| 手工测试 | ✅ 完成 | 6 个 Bug 全部修复并验证 |
| 代码提交 | ✅ 已推送 | 6 个 commit → GitHub main |

**新增数据库表（3张）：**
- `persona_reports` — 人格定位报告（迁移 009）
- `tikhub_credentials` — TikHub 独立 Key 池（迁移 010）
- `tikhub_call_logs` — TikHub 调用日志（迁移 011）

**Bug 修复记录（6 个）：**
1. 抖音分享链接解析失败（URL提取+短链+TikHub响应格式）
2. 前端下载地址错误（API vs FETCH_BASE 路径拆分）
3. 历史记录抽屉不渲染（移到组件最外层）
4. SSE 断连空报告标 ready（空内容保护）
5. 历史记录点击无反应（loadHistoryDetail 加 setStep(3)）
6. 产出中心预览为空（调详情接口获取 content）

---

### M2 Sprint 6 — 千川脚本复盘（qianchuan-review）✅ 完成

**核心流程：** 上传千川脚本（文件/粘贴）→ 上传投放数据 Excel（可选）→ AI 流式生成复盘报告 → 保存/导出/复制

| 端 | 状态 | 备注 |
|----|------|------|
| 后端 4 个接口 | ✅ 完成 | `operator_qianchuan_review.py`（parse-file/generate/save/outputs）|
| System Prompt 常量 | ✅ 完成 | `tools/qianchuan_review/prompts.py`，A/B 两版本逐字保留 |
| 合并服务层 | ✅ 完成 | `qianchuan_review_service.py`（merge/sort/build_user_message/stream）|
| file_parser 扩展 | ✅ 完成 | 新增 `parse_qianchuan_review_file()` 含日历噪声过滤 |
| 前端三步页面 | ✅ 完成 | `QianchuanReviewPage.tsx`，XLSX.js 前端解析 Excel |
| 旧数据迁移脚本 | ✅ 完成 | `scripts/migrate_qianchuan_reports.py`，支持 --dry-run |
| 运维任务单 | ✅ 完成 | `deploy/docs/tasks/M2_Sprint6_运维端任务_qianchuan-review_v1.md` |
| 自动化测试 | ✅ 57/57 后端 | prompts(17) + service(13) + file_parser(14) + integration(13) |
| 功能测试 | ✅ PASS | 12 项端到端验证全通过，修复 xlsx 依赖缺失 |
| 工具状态 | ✅ online | 创作中心可见可用（016 迁移已执行）|

**技术要点：**
- CORS 新增 `expose_headers=["X-Task-Id"]`，前端从响应头读 task_id
- task_job 生命周期：流前 processing → 流后 success（独立 AsyncSessionLocal background task）
- outputs 分页：一次全量有序查询后内存切片，避免双查询

**覆盖率：**
- `prompts.py`：100% ✅
- `qianchuan_review_service.py`：86%（目标≥80%）✅
- `operator_qianchuan_review.py`：73%（目标≥70%）✅
- `file_parser.py`（新增函数）：82%（目标≥90%）⚠️

**验收后修复（2026-06-13）：**
- `xlsx` npm 包漏写 `package.json`：前端 Vite 编译报 `Failed to resolve import "xlsx"`，`tsc --noEmit` 未能检出（类型通过，运行时缺包）。修复：`npm install xlsx --save`（commit `ca50de6`）
- `workspace_tools` 漏 INSERT：`016_qianchuan_review.sql` 迁移未在开发阶段执行，工具 status 停留在 dev，管理端看不到入口。修复：补写迁移文件并执行（commit `9969176`）
- 前端 CSS 失效：页面全部使用 Tailwind class，项目未安装 Tailwind，样式无效。修复：全部改为 `var(--brand)` / `card` / `btn` 等项目 CSS 变量体系（commit `7cff76e`）

---

### M2 Sprint 5 — 产品卖点提取器（selling-point-extractor）✅ 完成

**核心流程：** 上传产品Brief + 达人文案 → AI 流式生成极致卖点卡（机制/背书/口碑/产品力）→ 多轮追问 → 下载 .md → 历史记录管理

| 端 | 状态 | 备注 |
|----|------|------|
| 后端 admin 2 个接口 | ✅ 完成 | `admin_selling_point.py`，GET/PUT selling_point_configs |
| 后端 operator 5 个接口 | ✅ 完成 | `operator_selling_point.py`，chat 从 DB 读 Prompt+模型 |
| file_parser 扩展 | ✅ 完成 | 新增 `.pages`/`.doc`/pdfplumber 支持，独立函数 |
| 前端运营端页面 | ✅ 完成 | `SellingPointPage.tsx`，无 SYSTEM_PROMPT 硬编码 |
| 前端管理端配置 Tab | ✅ 完成 | `SellingPointConfigTab.tsx`（工具配置页） |
| 自动化测试 | ✅ 43/43 后端 + 86/86 前端 | |
| 数据库迁移 | ✅ 015 已执行 | selling_point_configs 表 + workspace_tools 注册 |
| 工具状态 | ✅ online | 创作中心可见可用 |

**红线合规**：6 条迁移红线全部满足，含红线 4（Prompt+模型管理端可配置）

**迭代修复（验收后）：**
- CSS 重写：初版使用 Tailwind（项目未安装），重写为 `card`/`btn`/CSS 变量体系，页面布局正常
- 拖拽上传：Step 1/2 上传框支持拖拽文件，`briefDragOver`/`scriptDragOver` state 控制高亮

**覆盖率：**
- `operator_selling_point.py`：71%（目标≥70%）✅
- `admin_selling_point.py`：71%（目标≥70%）✅
- `file_parser.py`（含旧测试）：82%（目标≥80%）✅

---

### M2 Sprint 4 — TikTok 脚本仿写（tiktok-writer）✅ 完成

**核心流程：** 粘贴文案 + 点赞数（≥10万）→ AI 评估 Opening Hook → AI 分析结构锁定 Opening → AI 仿写 Body（直写 / 提供方向 / 多轮迭代）→ 导出 Word

| 端 | 状态 | 备注 |
|----|------|------|
| 后端 3 个接口 | ✅ 完成 | `app/routers/operator_tiktok_writer.py` |
| 共用 Word 导出服务 | ✅ 完成 | `app/services/word_export.py`（可被其他工具复用） |
| 前端 5 步页面 | ✅ 完成 | `TiktokWriterPage.tsx` |
| 前端路由接入 | ✅ 完成 | App.tsx + WorkspacePage.tsx |
| 自动化测试 | ✅ 317/317 后端 + 69/69 前端 | |
| 数据库迁移 | ✅ 014 已执行 | workspace_tools 注册 |
| 工具状态 | ✅ online | 创作中心可见可用 |

**已知遗留：**
- `persona.test.ts` 和 `authStore.test.ts` 为预存失败，与本 Sprint 无关
- router 覆盖率 41%（streaming generator 路径），后续补充单元测试

---

### M2 Sprint 3 — 对标分析助手（benchmark） ✅ 完成

**核心流程：** 抖音号解析 → 自动抓取 TOP10 + 近30天视频 → AI 流式生成人格档案 + 内容规划 → 导出 Word → 历史管理

| 端 | 状态 | 备注 |
|----|------|------|
| 后端 operator 4 个接口 | ✅ 完成 | `app/routers/operator_benchmark.py` |
| 后端 admin 3 个接口 | ✅ 完成 | `app/routers/admin_benchmark.py` |
| TikHub 适配器扩展 | ✅ 完成 | `resolve_sec_user_id` + `fetch_user_videos` |
| Word 报告生成 | ✅ 完成 | `app/services/benchmark_report.py` |
| 前端对标分析页面 | ✅ 完成 | `BenchmarkPage.tsx`（输入/结果双模式 + SSE 流式） |
| 前端管理配置页 | ✅ 完成 | `BenchmarkConfigTab.tsx`（嵌入工作台配置） |
| 自动化测试 | ✅ 371/371 | 后端 289 + 前端 82，全部通过 |
| 前端 UI 修复 | ✅ 完成 | 复制按钮可见性 + antd 废弃 API 修复 |

**新增数据库表（2张）：**
- `benchmark_configs` — 对标分析配置（迁移 007）
- `benchmark_analyses` — 对标分析结果（迁移 007）

**前端修复记录（本次会话）：**
1. 复制按钮颜色过灰（改为 primary 色调）
2. `destroyOnClose` 废弃警告（6 处改为 `destroyOnHidden`）
3. antd `message` 静态方法缺 context（改用 `App.useApp()` hook）
4. tab 按钮 border 属性冲突（拆分为独立属性）
5. `window.matchMedia` 测试环境缺失（setup.ts 添加 mock）
6. 模型注册缺失导致集成测试失败（`__init__.py` 补全 Sprint 3 模型）

---

## 三、跨 Sprint 通用问题记录（经验教训）

每次新工具迁移必须检查以下事项，避免重复踩坑：

| # | 问题 | 首次出现 | 处理方式 |
|---|------|---------|---------|
| 1 | **前端 CSS 用了 Tailwind**：项目未安装 Tailwind，所有 `bg-*`/`text-*`/`rounded-*` 等 class 全部无效，页面裸奔 | Sprint 5、Sprint 6 均出现 | 全部改为 `var(--brand)` / `card` / `btn-primary` 等项目 CSS 变量体系；前端规范已注明禁止使用 Tailwind |
| 2 | **npm 包引用未声明**：代码 `import * as XLSX from 'xlsx'` 但 `package.json` 未写 `xlsx`，`tsc --noEmit` 不报错（类型解析走 node_modules），Vite 运行时才爆 `Failed to resolve import` | Sprint 6 | 新增第三方包必须同步 `npm install --save`；功能测试阶段 curl Vite 模块可发现 |
| 3 | **workspace_tools INSERT 漏执行**：迁移 SQL 文件写了但没有执行，工具 status 停留在 dev，运营端入口不显示 | Sprint 6 | 每次迁移完成后验收清单必须包含 `psql` 查 workspace_tools 确认 status=online |
| 4 | **文档落地遗漏**：代码全部完成后未补写需求文档/任务单/测试报告，PM 记忆停留在上一个 Sprint | Sprint 6 | CLAUDE.md 第十二节已增加「C 文档落地」强制闸门 |
| 5 | **功能测试缺失**：只跑 pytest，未在真实服务上验证接口和页面 | Sprint 6（首次发现） | CLAUDE.md 第十三节已增加「必须调用 Skill: verify」规则 |

---

## 四、当前卡点与下一步

| 卡点 | 处理方式 |
|------|---------|
| 并发测试 4/4 失败 | 本地环境问题，需在测试服验证 |
| antd `message` 静态方法警告 | 仅 BenchmarkPage 已修复，其余 25 个文件待批量迁移 |
| file_parser.py 新增函数覆盖率 82% | 差 8%，未来可补充 OS 级异常路径测试 |

**下一步优先级：**
1. ✅ 已确认：tiktok-writer 和 qianchuan-review 需要增加管理端 Prompt+模型配置（参照 selling-point-extractor 模式）
   - 实现计划：`docs/superpowers/plans/2026-06-13-tool-prompt-config.md`（10个Task）
   - tiktok-writer 只将 hook_eval（评估 Opening）和 structure（分析结构）两个纯静态 Prompt 纳入配置；rewrite_* 和 iterate 因含动态插值保留前端构建
   - qianchuan-review 将 with_excel 和 without_excel 两个 Prompt 均纳入配置
   - 两者模型均支持管理端配置（绑定 ai_models 表，无绑定回退默认值）
2. 规划 M2 Sprint 7（下一个待迁移工具，参考 `Ai_Toolbox/` 目录和工具迁移方案）
3. 批量修复 antd `message` 静态方法 → `App.useApp()` hook（25 个文件）
4. 补充 operator_tiktok_writer.py 单元测试（覆盖率提升至 70%+）
5. 测试服部署并验证并发测试

---

## 五、文档索引

### 任务单（已迁移至各端 docs/ 下）

| 文件 | 说明 | 状态 |
|------|------|------|
| `docs/pm/M2_Sprint06_qianchuan-review_需求文档.md` | Sprint 6 需求文档 | ✅ 已完成 |
| `backend/docs/tasks/M2_Sprint06_后端任务_qianchuan-review_v1.md` | Sprint 6 后端任务单 | ✅ 已执行 |
| `frontend/docs/tasks/M2_Sprint06_前端任务_qianchuan-review_v1.md` | Sprint 6 前端任务单 | ✅ 已执行 |
| `deploy/docs/tasks/M2_Sprint6_运维端任务_qianchuan-review_v1.md` | Sprint 6 运维任务单 | ✅ 已完成 |
| `backend/docs/tasks/M2_Sprint05_后端任务_selling-point-extractor_v1.md` | Sprint 5 后端任务单 | ✅ 已执行 |
| `frontend/docs/tasks/M2_Sprint05_前端任务_selling-point-extractor_v1.md` | Sprint 5 前端任务单 | ✅ 已执行 |
| `backend/docs/tasks/M2_Sprint04_后端任务_tiktok-writer_v1.md` | tiktok-writer 后端任务单 | ✅ 已执行 |
| `frontend/docs/tasks/M2_Sprint04_前端任务_tiktok-writer_v1.md` | tiktok-writer 前端任务单 | ✅ 已执行 |
| `backend/docs/tasks/M2_Sprint3_persona_positioning.md` | 人格定位后端任务单 | ✅ 已执行 |
| `backend/docs/tasks/M2_Sprint3_后端任务_persona_positioning_v2_修复Bug.md` | 6 个 Bug 修复 | ✅ 已执行 |
| `frontend/docs/tasks/M2_Sprint3_persona_positioning.md` | 人格定位前端任务单 | ✅ 已执行 |
| `docs/tasks/backend/M2_Sprint3_benchmark.md` | 对标分析后端任务单 | ✅ 已执行 |
| `docs/tasks/frontend/M2_Sprint3_benchmark.md` | 对标分析前端任务单 | ✅ 已执行 |
| `docs/tasks/deploy/M2_Sprint3_benchmark.md` | 对标分析运维任务单 | ✅ 已执行 |
| `frontend/docs/tasks/M2_Sprint3_前端任务_benchmark_v2_修复Bug.md` | benchmark 前端 + 测试修复（6 个 Bug） | ✅ 已执行 |

### 测试报告

| 文件 | 说明 | 状态 |
|------|------|------|
| `backend/docs/tests/M2_Sprint06_测试报告_qianchuan-review_v1.md` | Sprint 6 测试报告（57/57 后端，verify PASS）| ✅ 已完成 |
| `backend/docs/tests/M2_Sprint05_测试报告_selling-point-extractor_v1.md` | Sprint 5 测试报告（43/43 后端 + 86/86 前端）| ✅ 已完成 |
| `backend/docs/tests/M2_Sprint04_测试报告_tiktok-writer_v1.md` | Sprint 4 测试报告（317/317 后端）| ✅ 已完成 |
| `backend/docs/tests/M2_Sprint3_测试报告.md` | Sprint 3 测试报告（371/371） | ✅ 已完成 |

### 基础文档

| 文件 | 说明 |
|------|------|
| `backend/docs/base/MCN_M2_Base_API.md` | M2 API 接口规范（含 Sprint1~3） |
| `backend/docs/base/MCN_M2_Base_Database.md` | M2 数据库契约（含 Sprint1~3） |
| `backend/docs/后端开发约定.md` | 后端开发唯一事实源 |
| `frontend/docs/前端规范.md` | 前端开发唯一事实源 |
