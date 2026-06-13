# MCN_PM_Agent — 项目记忆与当前状态（M2）

> 最后更新：2026-06-13（Sprint 5 selling-point-extractor 迁移完成）
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

## 三、当前卡点与下一步

| 卡点 | 处理方式 |
|------|---------|
| 测试任务单结果列为空 | 仅第一章执行完毕，需补充执行 |
| 并发测试 4/4 失败 | 本地环境问题，需在测试服验证 |
| antd `message` 静态方法警告 | 仅 BenchmarkPage 已修复，其余 25 个文件待批量迁移 |

**下一步优先级：**
1. 人工验收 selling-point-extractor（浏览器 3 步流程 + AI 真实调用，需先在管理端配置 Prompt 和模型）
2. 规划 M2 Sprint 6（下一个待迁移工具）
3. 批量修复 antd `message` 静态方法 → `App.useApp()` hook（25 个文件）
4. 补充 operator_tiktok_writer.py 单元测试（提升覆盖率至 70%+）
5. 测试服部署并验证并发测试

---

## 四、文档索引

### 任务单（已迁移至各端 docs/ 下）

| 文件 | 说明 | 状态 |
|------|------|------|
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
