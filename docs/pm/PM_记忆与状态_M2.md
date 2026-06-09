# MCN_PM_Agent — 项目记忆与当前状态（M2）

> 最后更新：2026-06-08  
> 更新角色：MCN_PM_Agent  
> 上一份文档：`docs/pm/PM_记忆与状态.md`（M1 阶段，已归档）

---

## 一、项目基本信息

- **项目名**：MCN Information System Platform
- **当前阶段**：M2 阶段进行中
- **工作目录**：`D:\2026年工作\AI相关\AI工具箱新架构方案\mcn-platform\`
- **后端**：`backend/`（FastAPI + PostgreSQL）
- **前端**：`frontend/`（React + Vite + TypeScript + Ant Design 5.x）

### 环境信息

- **数据库**：PostgreSQL @ localhost:5432，用户 postgres，密码 admin123，数据库 `mcn_m1`
- **psql 路径**：`D:\ProtgreSQL\bin\psql.exe`
- **后端地址**：`http://localhost:8000`（uvicorn）
- **前端地址**：`http://localhost:5173`（Vite）
- **测试账号**：admin / testop（operator，密码 Operator@123）

---

## 二、团队职责与协作方式

| 角色 | 职责 |
|------|------|
| 产品负责人（用户） | 提出需求、最终决策 |
| PM（Claude） | 拆解需求、出任务单、字段对齐、归档文档、验收把关 |
| 前端开发 | 执行前端任务单，使用 Claude Code 实现，自查后回传 PM |
| 后端开发 | 执行后端任务单，使用 Claude Code 实现，自查后回传 PM |
| 运维 | 执行运维任务单（SQL 迁移、依赖安装、服务重启等） |

**工作流：** PM 出任务单 → 各端执行 → 回传结果 → PM 验收 → 进入下一轮

**关键注意：** 前后端字段名必须对齐（曾多次出现 status 值、字段名不一致问题）。

---

## 三、M1 阶段（全部完成，已归档）

| Sprint | 内容 | 状态 |
|--------|------|------|
| Sprint 0-1 | 基础架构、用户管理、JWT 登录 | ✅ 完成 |
| Sprint 2 | 红人管理（KOL）含 TikHub 抓取、粉丝画像 | ✅ 完成 |
| Sprint 3 | 服务配置（Key Pool、TikHub、基础 AI 接入） | ✅ 完成 |
| Sprint 4 | AI 服务模块（多服务商 Key 池、并发调度、模型管理、使用统计） | ✅ 完成 |

---

## 四、M2 阶段（当前）

### M2 Sprint 1 — 红人入驻问卷（kol-intake）

**核心流程：** 运营生成链接 → 博主打开链接 → AI 多轮对话（24 道题）→ 生成报告 → 下载 docx/PDF

| 端 | 状态 | 备注 |
|----|------|------|
| 后端 | ✅ 完成 | 21 个接口，reportlab 生成 PDF |
| 运维 | ✅ 完成 | 006 迁移已执行，python-docx 1.2.0 + reportlab 4.5.1；⚠️ 需手动重启后端 |
| 前端 | ⏳ 等设计稿 | 任务单已写好，设计稿完成后即可下发 |

**新增数据库表（4张）：**
- `kol_intake_questions`
- `kol_intake_configs`
- `kol_intake_links`
- `kol_intake_submissions`

**关键技术点：**
- AI 对话模型：haiku，max_tokens=300
- 报告生成模型：opus，extended thinking budget=6000
- 链接下架逻辑：下架只阻止新建链接，已有链接继续可用
- workspace_tools 已注册 kol-intake（status='dev'）

**完成后待办（运营后台配置）：**
管理员登录后台「服务配置 → 问卷配置 → AI 配置」填写两段 Prompt：
- `conversation_bridge` 对话 Prompt
- `report_generation` 报告 Prompt
- Prompt 内容详见：`docs/pm/M2_Sprint1_kol_intake_完整流程.md` 4.1、4.2 节

---

### M2 Sprint 2 — 运营端首页重设计

| 端 | 状态 |
|----|------|
| 后端 | ✅ 完成（新增 operator_homepage.py） |
| 前端 | ✅ 完成（recharts 折线图 + 环形图，常用工具 6 个） |

**新增接口：**
- `GET /api/operator/homepage/stats` — 4 卡片数据 + 工具占比 + 常用工具
- `GET /api/operator/homepage/trend` — 最近 7 天产出折线图

**字段说明（供后续参考）：**
- outputs / task_jobs 用户关联字段为 `created_by`（非 operator_id）
- `week_token_usage` 固定返回 null（task_jobs 无 token 字段）
- `last_login_at` 字段在 users 表中存在

**运营端导航栏（已更新）：**
概览 / 创作中心 / 任务中心 / 产出中心

---

## 五、当前卡点与下一步

| 卡点 | 处理方式 |
|------|---------|
| kol-intake 前端等设计稿 | 设计稿完成后，PM 补充设计稿路径，下发前端任务单 |
| kol-intake Prompt 未配置 | 后端+运维完成后，运营进后台手动填写两段 Prompt |

**下一步优先级：**
1. 等设计稿 → 下发 kol-intake 前端任务单
2. 规划 M2 Sprint 3（待产品确认下一个功能模块）

---

## 六、文档索引

### PM 文档

| 文件 | 说明 |
|------|------|
| `docs/pm/PM_记忆与状态.md` | M1 阶段 PM 记忆（已归档，含技术决策 D001-D009） |
| `docs/pm/PM_记忆与状态_M2.md` | 本文件，M2 阶段当前状态 |
| `docs/pm/M2_Sprint1_kol_intake_完整流程.md` | kol-intake 完整流程 + Prompt 内容 |

### 任务单

| 文件 | 说明 | 状态 |
|------|------|------|
| `docs/tasks/backend/M2_Sprint1_kol_intake.md` | kol-intake 后端任务单 | ✅ 已执行 |
| `docs/tasks/deploy/M2_Sprint1_kol_intake.md` | kol-intake 运维任务单 | ✅ 已执行 |
| `docs/tasks/frontend/M2_Sprint1_kol_intake.md` | kol-intake 前端任务单 | ⏳ 等设计稿 |
| `docs/tasks/backend/M2_Sprint2_operator_homepage.md` | 首页后端主任务单 | ✅ 已执行 |
| `docs/tasks/backend/M2_Sprint2_operator_homepage_补充.md` | 首页后端补充任务单 | ✅ 已执行 |
| `docs/tasks/frontend/M2_Sprint2_operator_homepage.md` | 首页前端主任务单 | ✅ 已执行 |
| `docs/tasks/frontend/M2_Sprint2_operator_homepage_补充.md` | 首页前端补充任务单 | ✅ 已执行 |

### 基础文档

| 文件 | 说明 |
|------|------|
| `docs/base/MCN_M1_Base_API_utf8_bom.md` | API 接口规范 |
| `docs/base/MCN_M1_Base_Database_utf8_bom.md` | 数据库契约 |
| `docs/base/MCN_M1_Base_Frontend_utf8_bom.md` | 前端规范 |
| `docs/base/MCN_M1_Base_Permission_utf8_bom.md` | 权限设计 |
| `docs/base/MCN_M1_Base_Acceptance_utf8_bom.md` | 验收标准 |
| `docs/onboarding/新同事开发上手指南.md` | 团队成员上手指南 |
| `docs/design/MCN_系统设计方案.md` | 系统整体设计方案 |
| `docs/design/MCN_UI_设计规范.md` | UI 设计规范（配色/布局/组件，M2 最新）|
