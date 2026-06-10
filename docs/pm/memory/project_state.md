---
name: project_state
description: MCN平台当前开发进度和下一步计划
type: project
updated: 2026-06-10
---

## 项目：MCN Platform

**工作目录：** `D:\2026年工作\AI相关\AI工具箱新架构方案\mcn-platform`
- 后端：`backend/`（FastAPI + PostgreSQL）
- 前端：`frontend/`（React + Vite + TypeScript + Ant Design 5.x）
- GitHub：https://github.com/Aiintalk/New_Mcn_Platform.git

---

## M1 阶段（已全部完成）

| Sprint | 内容 |
|--------|------|
| Sprint 0-1 | 基础架构、用户管理、登录 |
| Sprint 2 | 红人管理（KOL）含 TikHub 抓取、粉丝画像 |
| Sprint 3 | 服务配置（Key Pool、TikHub、基础AI接入） |
| Sprint 4 | AI 服务模块（多服务商Key池、并发调度、模型管理、使用统计） |

---

## M2 阶段（当前）

### M2 Sprint 1 — 红人入驻问卷（kol-intake）✅ 后端完成，前端部分待执行

**核心流程：** 运营生成链接 → 博主打开链接 → AI 多轮对话（24道题） → 生成报告 → 下载 docx/PDF

| 端 | 状态 | 备注 |
|----|------|------|
| 后端基础接口 | ✅ 完成 | 21个接口，reportlab生成PDF，007迁移 |
| 后端 bridge 接口 | ✅ 完成 | GET /intake/questions + POST /intake/{token}/bridge |
| 后端运营直发接口 | ✅ 完成 | 5个接口：start/chat/submit/status/download |
| 后端报告展示修复 | ✅ 完成 | status接口加ai_report字段 + download支持?token=参数 |
| 后端 bridge 优化 | ✅ 完成 | 陈述句收尾 + system_prompt 从DB读取 |
| 运维 | ✅ 完成 | 006+007迁移执行，python-docx + reportlab |
| 前端基础页面 | ✅ 完成 | IntakePage / OperatorIntakeChatPage / OutputsPage |
| 前端对话逻辑重构 | ✅ 完成 | 前端驱动题目流程，AI只生成过渡语 |
| 前端布局修复 | ✅ 完成 | Header固定 + 去除留白 |
| 前端报告展示修复 | ⏳ 待执行 | 页面展示报告文本 + 下载按钮携带token |

**待执行任务单：**
- `docs/tasks/frontend/M2_Sprint1_kol_intake_报告展示与下载修复.md` → 前端执行

**关键技术点：**
- 5张新表：kol_intake_questions / kol_intake_configs / kol_intake_links / kol_intake_submissions / kol_intake_operator_sessions
- 对话模式：前端驱动题目流程，AI只生成1-2句过渡语（bridge接口，haiku模型 max_tokens=200）
- 报告模型：opus，extended thinking budget=6000，max_tokens=8000
- workspace_tools：tool_name='红人信息采集', status='online'

---

### M2 Sprint 2 — 运营端首页重设计 ✅ 完成

| 端 | 状态 |
|----|------|
| 后端 | ✅ 完成（新增 operator_homepage.py） |
| 前端 | ✅ 完成（recharts 折线图 + 环形图） |

**补充任务单（已写，待执行）：**
- `docs/tasks/backend/M2_Sprint2_operator_homepage_补充2.md` — 使用日志接口
- `docs/tasks/frontend/M2_Sprint2_operator_homepage_补充2.md` — 使用日志页面

---

### M2 Sprint 3 — 人格定位（persona-positioning）⏳ 任务单已写，待启动

**核心流程：** 3步向导（上传达人资料 + 对标资料）→ SSE 流式生成 → 两Tab展示（人格档案/内容规划）+ Word导出

**任务单已写：**
- `docs/tasks/backend/M2_Sprint3_persona_positioning.md`
- `docs/tasks/frontend/M2_Sprint3_persona_positioning.md`

---

## BugFix 记录

### BugFix-01（2026-06-09）✅ 全部修复

| Bug | 根因 | 状态 |
|-----|------|------|
| TikHub Key 无法保存 | 前端字段 `api_key` vs 后端 Pydantic `secret` 不匹配 | ✅ |
| TikHub enable/disable 无效 | 后端缺少路由 | ✅ |
| 添加红人被 TikHub 阻塞 | create_kol 自动调用 TikHub，未配置时报错 | ✅ |
| AI Key 并发列显示 undefined | 后端返回 `active_requests`，前端期望 `concurrency` | ✅ |
| AI 模型占比图全为 0% | 后端返回 `percentage`(0-1)，前端期望 `pct`(0-100) | ✅ |
| 改密码旧密码错误无提示 | 代码逻辑正确，待复核 | ⏳ |

### BugFix-02（2026-06-09）✅ 全部修复

| 内容 | 状态 |
|------|------|
| 新增 `008_schema_catchup.sql`：补全 5 张缺失表 + 8个 kols 字段 | ✅ |
| 001_init.sql 改为幂等写法 | ✅ |
| 新增 `backend/scripts/init_db.sh` 一键初始化脚本 | ✅ |

**缺失的5张表：** `service_credentials` / `outputs` / `files` / `tool_sessions` / `external_service_logs`

**Mac 本地初始化：**
```bash
git pull
bash backend/scripts/init_db.sh   # 默认 postgres/admin123/mcn_m1
```

---

## 迁移文件清单

| 文件 | 内容 |
|------|------|
| 001_init.sql | 基础表（users/kols/workspace_tools等） |
| 002_kols_add_owner.sql | kols 表加 owner 字段 |
| 003_ai_tables.sql | AI相关表（credentials/ai_models/ai_call_logs）|
| 004_credentials_test_fields.sql | credentials 加测试字段 |
| 005_ai_models_test_fields.sql | ai_models 加测试字段 |
| 006_kol_intake.sql | kol-intake 5张表 |
| 007_kol_intake_operator_sessions.sql | 运营直发会话表 |
| 008_schema_catchup.sql | 补全缺失表和字段（幂等） |

---

## 技术债务

| # | 问题 | 解法 | 优先级 |
|---|------|------|--------|
| 1 | 手写SQL迁移易出错 | 考虑引入 Alembic（M3评估） | 中 |
| 2 | 无 schema 自动校验 | 启动时对比模型 vs DB，不一致打警告 | 中 |
| 3 | AI 无流式输出 | Bridge 已用短回复暂不需要，待需求驱动 | 低 |
