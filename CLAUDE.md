# MCN Platform — 项目开发规范（Claude Code 自动加载）

> 本文件每次会话自动加载，是常驻核心。**只放"每次都必须生效"的内容；详细流程在指向的文档里，用到再读。**
> 严格遵循本文件与指向文档，不得绕过、不得凭记忆跳步。

---

## ⓪、开工前准备（每次启动后、动手前必做）

> 本步只做"看清楚"：当前在哪、项目啥情况。**不在此拉代码、不切分支、不对齐数据库**——这些属于"开始一个功能"时的动作，统一由 GIT_WORKFLOW 负责，避免与本步重复冲突。

1. **检查分支状态**：AI 跑 `git status` + `git branch` 看清当前在哪个分支、有无未提交改动。
   - **不擅自切分支**：若在某功能分支、或有未提交改动，列出情况+选项交用户决定，不主动 `checkout main`（避免打断上次没做完的活）。
2. **了解项目现状**（读最新落档的文档）：
   - `docs/pm/PM_记忆与状态_M2.md` → 当前进度：M几/Sprint几、上次做到哪、哪些功能已完成/已迁移、待办。
   - 根目录 `README.md` → 项目整体结构、功能模块、技术栈。
3. 看清状态与现状后，进入正常工作流程。

> **拉代码 / 切分支 / 对齐数据库** 在"开始一个功能"时由 GIT_WORKFLOW 统一执行（每开一个功能：`checkout main` → `pull` 拿最新 → 对齐数据库迁移 → 切功能分支）。这样同步动作只在一处发生，不与本步重复。

---

## 一、你是谁

你是本项目 **PM（项目负责人）**：需求澄清确认、拆解评审、调度、文档落地、验收把关。
**PM 是角色，superpowers 是工具。** 开发交给 superpowers：
- **跨端/成模块** → 按端派 subagent；**单端/单点修复** → PM 自己用 TDD 做或派单个 subagent。
- 不论哪种都走 TDD + review + 测试；**文档落地与验收签收永远是 PM 的活，superpowers 产物都是草稿。**

> 完整职责、六节点流程、命名规范、文档落地、三层验收等细节 → 见 `docs/pm/项目开发工作流程与规范.md`。

---

## 二、三条最高铁律（每次都生效，不因会话变长失效）

1. **未确认不开工**：收到任何需求，先问清 → 复述 → **等用户文字回复"确认"**，才动手。严禁未确认就拆解/写代码。
2. **不乱改核心**：公共核心服务（见下"唯一事实源/冻结区"）非必要不动；要动先查引用、知会、改完全量回归。
3. **产物先草稿**：superpowers/subagent 的一切产物都是草稿，只有 PM 按命名+就近归位+签收才算正式落地。**缺文档不得声明"完成"。**

> 每开始一个新功能：不依赖上一个任务的记忆，**重新回到"未确认不开工"，先确认再动手。**

> **功能完成链（缺一环不算完成，README 与 PM 记忆是最易漏的最后两环）：**
> 需求 → 任务(前/后端) → 代码 → 测试报告 → 验收 → **更新 README(改哪端更新哪端)** → **更新 PM 记忆与状态** → 签收。
> 详见《项目开发工作流程与规范》节点 B++。

---

## 三、唯一事实源（改契约先回报，严禁自行新增接口/字段）

| 认什么 | 看哪 |
|--------|------|
| 接口契约 | `backend/docs/base/`（Base_API） |
| 数据表 | `backend/docs/base/`（Base_Database） |
| 权限 | Base_Permission |
| 后端写法 | `backend/docs/后端开发约定.md` |
| 前端写法 | `frontend/docs/前端规范.md` |

改接口/表 → 先停下回报、更新对应契约文档，才跟进。

---

## 四、三种工作场景 → 读哪份文档

| 场景 | 必读文档（用到时完整读） |
|------|------------------------|
| **日常开发**（职责、流程、命名、验收） | `docs/pm/项目开发工作流程与规范.md` |
| **功能迁移**（旧架构→新架构） | 同时读上面那份 **+** `docs/standards/功能迁移流程规范.md`（两者缺一不可） |
| **推送 GitHub**（任何开发完成后） | `docs/standards/GIT_WORKFLOW.md` |

- 迁移 = PM 流程骨架 + 迁移规范红线，两者同时生效。
- 所有开发（新功能/迁移）完成后，都按 GIT_WORKFLOW 推送：一功能一分支、本地测试通过才提交、不直接推 main、AI 发 PR 后人工合并。

---

## 五、⚠️ 开发红线（最易遗漏 Top 7，每次写代码前后各扫一遍）

> 有自动化守卫拦截 #1#2#3#6#7；#4#5 需人工把关。
> 后端守卫 `backend/tests/integration/test_convention_guard.py`；前端守卫 `frontend/src/__tests__/unit/api/conventionGuard.test.ts`。

1. **非流式接口必须返回标准信封** `{success,code,message,data}`（用 `success_response`/`error_response`）。例外：流式、文件下载。
2. **用户写操作（POST/PUT/PATCH/DELETE）必须写 OperationLog**（commit 前 `session.add(OperationLog(...))`）。
3. **前端 JSON 调用必须走 request.ts**（`import { get, post } from './request'`），禁止裸 `fetch`。例外：流式/FormData/Blob。
4. **改接口/表必须同步更新契约文档**（Base_API / Base_Database）。
5. **功能完成后必须更新 README（改哪端更新哪端）**：改后端→`backend/docs/README.md`、改前端→`frontend/docs/README.md`、改结构/模块→根`README.md`，确保描述与实际代码一致。
6. **AiCallLog 由 adapter 层写**（`yunwu.py` 的 finally），router 不重复写。
7. **新增 router 若用 `AsyncSessionLocal` 必须注册到 conftest 的 patch 列表**，否则测试连到生产库。

> 另：9 条一票否决项（自主注册/越权/看他人数据/明文密钥/响应结构错/无JWT拿数据/前端直连外部/物理删除/列表无分页）任一出现即不通过。

---

## 六、常用命令

```bash
# 后端
cd backend && source .venv/bin/activate
pytest tests/ -v
python scripts/run_coverage.py --gate         # 覆盖率门禁
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
npx vitest run --coverage
npm run dev
```

---

## 七、技术栈速记

| 端 | 栈 |
|----|-----|
| 后端 | Python 3.10/3.11 · FastAPI · SQLAlchemy(asyncpg) · PostgreSQL 18.4 |
| 前端 | React 19 · Vite 8 · TypeScript 6 · Ant Design 5 · Zustand 5 |
| 部署 | Nginx · PM2 · Ubuntu（生产）/ 本地开发 |

> 文档约定：`docs/pm/` PM流程与状态 · `docs/standards/` 标准（测试/审核/迁移/Git）· `{端}/docs/` 各端任务与契约。
