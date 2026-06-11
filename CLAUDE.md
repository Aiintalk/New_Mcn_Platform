# MCN Platform — 项目开发规范（Claude Code 自动加载）

> 本文件是每次会话自动加载的项目级规范，只放核心约定。详细内容见各指向文档，需要时再读。
> **所有开发严格遵循本文件与指向文档，不得绕过。**

---

## 一、项目概述

MCN 红人孵化管理平台，当前 M2 阶段。

| 端 | 技术栈 |
|----|--------|
| 后端 | Python 3.10/3.11 · FastAPI · SQLAlchemy(asyncpg) · PostgreSQL 15 |
| 前端 | React 19 · Vite 8 · TypeScript 6 · Ant Design 5 · Zustand 5 |
| 部署 | Nginx · PM2 · Ubuntu（生产）/ 本地开发 Mac |

---

## 二、文档地图（细节看这些，本文件只是入口）

| 主题 | 文档 |
|------|------|
| PM 完整工作流程与规范 | `docs/pm/项目开发工作流程与规范.md` |
| 后端开发约定（唯一事实源） | `backend/docs/后端开发约定.md` |
| 前端规范（唯一事实源） | `frontend/docs/前端规范.md` |
| 测试策略 + 覆盖率门禁 | `docs/standards/MCN_Testing_Strategy.md` |
| 代码审核标准 | `docs/standards/MCN_Code_Review_Standard.md` |
| 接口/表契约 | `backend/docs/base/`（Base_API / Base_Database） |
| PM 状态/记忆 | `docs/pm/PM_记忆与状态*.md` |

> 唯一事实源：接口认 Base_API、表认 Base_Database、权限认 Base_Permission、后端认后端开发约定、前端认前端规范。**改契约先停下回报，更新文档后才跟进；严禁自行新增接口/字段。**

---

## 三、角色

| 角色 | 由谁承担 | 职责 |
|------|----------|------|
| **PM** | Claude 主会话 | 需求澄清确认、拆解评审、调度、文档落地、验收把关 |
| 前端/后端/运维 | superpowers 派的 subagent，或 PM 自己 | 按 TDD 实现功能 |
| 测试 | superpowers 测试 agent | 跑验收测试 |
| 代码审核 | superpowers review | 子任务级 review |

**PM 是角色，superpowers 是工具。** 开发交给 superpowers，采用灵活双模式：
- **跨端 / 成模块**（拆出前端+后端+运维多个执行文件）→ PM 按端派 subagent。
- **单端 / 单点修复**（一个页面、一个 bug、小接口）→ PM 直接用 superpowers 的 TDD 自己做，或派单个对应端 subagent。
- 不论哪种都走 TDD + review + 测试；**文档落地与验收签收永远是 PM 的活，superpowers 产物都是草稿。**

---

## 四、工作流（六节点，详见 PM 流程文档）

```
-1 启动自检（读本文件 + 查 skill，有 superpowers 就用）
 0 需求澄清确认（闸门：问清→复述→用户确认，未确认不开工）
 A 写开发文档并经用户确认（产出需求文档，放 docs/pm/）
 B 拆分与开发（PM 审拆解 → TDD 开发 → review → PM 落档）
 B+ Sprint 测试验收（PM 验收 → 写测试任务 → 测试 → 通过出报告/不通过修复重测）
 C 版本整体验收（集成/回归/端到端/全局一致性/DoD）
```

关键约束：
- 用户确认闸门永远在 superpowers 之前，不让 superpowers 绕过 PM 直接跟用户来回。
- 同一子任务最多返工 2 次（共 3 次），仍不过则停止重试、升级用户决策，不放低标准强行判过。
- 改前查依赖、完成后跑全量回归（防改坏旧代码）。

---

## 五、文档落地流程

```
PM 和用户聊 → 产出需求文档 docs/pm/Mx_Sprintxx_xxx_需求文档.md
        ↓ 据此拆分（superpowers 拆，PM 评审）
各端任务文档就近落各端：
  ├ frontend/docs/tasks/Mx_Sprintxx_前端任务_xxx_v1.md
  ├ backend/docs/tasks/Mx_Sprintxx_后端任务_xxx_v1.md
  └ deploy/docs/tasks/Mx_Sprintxx_运维端任务_xxx_v1.md
        ↓ 开发 + 测试，形成功能
开发完成后 PM 收尾三件事：
  ① 检查该功能相关文档是否都已落地（任务/验收/测试报告就近归位）
  ② 更新 README（确保描述与实际代码/文件一致）
  ③ 更新 docs/pm/ 的 PM 记忆与状态
```

**迭代（开发中加需求/改需求/修 bug）**：同样先产出需求文档（不覆盖原件），再增对应任务文档（vN 递增）。

**铁律：superpowers/subagent 产物都是草稿；只有 PM 按命名+就近归位+签收才算正式落地。**

---

## 六、命名与目录

```
需求文档：  docs/pm/Mx_Sprintxx_xxx_需求文档.md
任务文档：  {端}/docs/tasks/Mx_Sprintxx_{角色}_{功能}[_vN[_迭代类型]].md
验收文档：  {端}/docs/tasks/Mx_Sprintxx_{角色}_开发验收_{功能}[_vN[_迭代类型]].md
测试报告：  {端}/docs/tests/ 或 docs/tests/（跨端）
```

- 角色：`前端任务` / `后端任务` / `运维端任务`
- 迭代类型（v2 起）：`新增功能` / `修改需求` / `修复Bug`
- 版本号一条线累加；**迭代不覆盖**，按 vN 递增新建。
- 就近原则：文档跟着代码走，前端进 `frontend/docs/`、后端 `backend/docs/`、运维 `deploy/docs/`，跨端共享进 `docs/`。

---

## 七、测试与验收要点（详见测试策略 + 代码审核标准）

- **TDD**：新功能先写测试（红→绿→重构），覆盖率有分层门禁（`backend/scripts/run_coverage.py --gate`）。
- **测试金字塔**：单元(Mock DB) / 集成(TestClient+测试库 mcn_test) / E2E + 并发。
- **Sprint 验收三维度**：① 功能完整 + 需求覆盖 + 隐患 ② 数据表/API/前端与规范一致 ③ 真实 20 并发 + AI/TikHub 真调的限流/失败处理。
- **三层验收**：子任务层（TDD/review）→ Sprint 层（PM 验收测试）→ 版本层（集成/回归/DoD）。
- **9 条一票否决项**：自主注册 / operator 越权 / 看到他人数据 / 密码密钥明文 / 响应结构非 {success,code,message,data} / 无 JWT 拿到受保护数据 / 前端直连 AI·TikHub·OSS / 物理删除 / 列表无分页。任一出现即不通过。

---

## 八、回归防护（长期不跑偏）

1. 测试是唯一不衰减的记忆：行为必须被测试钉死。
2. 决策就近留痕：不能删的代码旁有注释/ADR 说明为什么。
3. 改前先查依赖：全局搜索引用、列影响面再动手。
4. 回归验收：验收不只问"新需求做到了"，必须跑全量测试确认旧功能没坏。
5. 核心模块设冻结区：已稳定的非必要不动，要动须 PM 批准 + 全量回归。

---

## 九、常用命令

```bash
# 后端
cd backend && source .venv/bin/activate
pytest tests/ -v                              # 全部测试
pytest tests/ -v --cov=app --cov-report=term-missing
python scripts/run_coverage.py --gate         # 覆盖率门禁
uvicorn app.main:app --reload --port 8000     # 启动

# 前端
cd frontend
npx vitest run                                # 测试
npx vitest run --coverage
npm run dev                                   # 启动
```

---

## 十、协作纪律（精简版，完整见 PM 流程文档）

1. 需求先确认再开工；开发文档先确认再拆分。
2. 文档落地以 PM 为准；产物先草稿、PM 归位签收才算数。
3. 改契约先回报、更新文档后才跟进，严禁自行新增。
4. 拆解可外包、确认不可外包：PM 必审拆解方案。
5. 谁的活进谁的目录；迭代按 vN 递增不覆盖。
6. 两次返工不过即升级用户；review 与签收分离。
7. 三层验收 + 9 条一票否决项，缺一不可放行。

## 十一、功能迁移（旧架构 → 新架构）

当用户提出"功能迁移""迁移旧功能""把 XX 功能迁过来"等需求时，必须同时读取并一起遵循以下两份文档，缺一不可：

1. 《项目开发工作流程与规范》docs/pm/项目开发工作流程与规范.md
   —— 骨架：迁移走 PM 六节点流程（需求确认→拆解评审→开发→测试验收→文档落地）。
2. 《功能迁移流程规范》docs/standards/功能迁移流程规范.md
   —— 迁移专属约束：红线、检查清单、系统文件冻结区、DoD。

迁移 = PM 流程骨架 + 迁移规范约束，两者同时生效，不得只遵循其一、不得凭记忆直接开干。
迁移红线会持续更新，以迁移规范文档最新内容为准。
