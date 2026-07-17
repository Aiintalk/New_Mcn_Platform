# AIGC 工具回归测试评价体系 — 实施计划（分阶段路线图）

> **For agentic workers:** 本文档是**分阶段路线图**（roadmap altitude），不是逐条 2 分钟步骤的 bite-sized 计划。每个 Phase 独立可测、独立 commit、可单独发 PR。**开工某个 Phase 前，再为该 Phase 写 bite-sized TDD 细节**（用 superpowers:writing-plans 展开）。
>
> **spec 来源**：`docs/superpowers/specs/2026-07-17-aigc-evaluation-system-design.md`（三轮独立 review 收敛）  
> **分支**：`feature/aigc-evaluation`（已建，已提交 spec + 周会材料）  
> **当前状态**：待 2026-07-17 晚周会对齐 6 个确认问题后再启动 Phase 1

**Goal:** 为千川仿写等 AIGC 工具建一套可配置的回归测试评价体系，量化追踪提示词/流程版本效果。

**Architecture:** 独立子模块 `backend/app/evaluation/` + `frontend/src/evaluation/` + 独立 `eval_` 表，只读复用 yunwu adapter / kol 数据，一期不动现有模块。方案 B（可配置评测平台）+ 预留方案 C（插件化）扩展点。

**Tech Stack:** FastAPI · SQLAlchemy(asyncpg) · PostgreSQL 18.4 · React 19 · Vite · TypeScript · Ant Design 5 · Vitest · pytest

## Global Constraints（每个 Phase 的任务都隐含遵守，逐条抄自 spec）

- **红线 #1**：非流式接口必须返回标准信封 `{success, code, message, data}`（`success_response`/`error_response`）。
- **红线 #2**：所有写操作（POST/PUT/PATCH/DELETE）必须在 `db.commit()` 前 `session.add(OperationLog(...))`。
- **红线 #3**：前端 JSON 调用必须走 `frontend/src/api/request.ts`（`import { get, post, put, del }`），禁止裸 `fetch`。例外：流式/FormData/Blob。**注意守卫盲点**：现有 `conventionGuard.test.ts` 只扫 `src/api/*.ts`（单层，不递归），evaluation 的 API 在 `src/evaluation/api/` 完全在窗外 → Phase 5 必须扩展守卫 glob（见 Phase 5 task）。
- **红线 #7**：新增 router/service 若 `import AsyncSessionLocal`，必须注册到 `backend/tests/conftest.py` 的 `_SESSION_LOCAL_PATCH_TARGETS`（当前在 `tests/conftest.py:46`）。**最终清单见 Phase 3/4**（仅 runner/scheduler + 可能的 operator router BackgroundTask 点；generator/scorer 纯函数不 import，无需 patch；admin router 纯 `Depends(get_db)` 无需 patch）。
- **软删规则（每表明确）**：主数据表 `test_cases` / `versions` / `dimensions` / `schedule_policies` 一律用 `deleted_at` 软删（DELETE 接口置此字段）；`is_active` 仅作业务启停开关（不影响 DELETE 语义，查询时 `deleted_at IS NULL AND is_active`）。`rubrics` 子表只有 `is_active`（随父维度 rubrics 接口整体替换，不做软删）。`runs` 是历史记录不软删（归档另议）。
- **Prompt 占位符**：统一双花括号 `{{}}`，与 `render_system_prompt` 一致。
- **评分 JSON 输出**：通过 `extra_body={"response_format": {"type": "json_object"}}` 透传（`yunwu.chat` 无 `response_format` 形参），后备正则提取 `{...}`。
- **版本快照不可编辑**：无 `PUT versions/{id}`；改配置走 `clone` 新版本；`config_payload` 固化 resolved `model_id`+`provider`+`system_prompt_template`+维度权重（dimension_id 为 key）+评分模型。
- **下一个 migration 编号 = `053`**（rebase 后更新：main 的 PR #28 已占用 049–052）。
- **覆盖率门禁**：Models ≥ 90% / Services ≥ 80% / API ≥ 70% / 整体 ≥ 75%（`python scripts/run_coverage.py --gate`）。
- **不推 main**：分支提交 → 发 PR → 人工合并。

---

## 分阶段总览

| Phase | 目标 | 产出可测软件 | 依赖 | 测试门禁 |
|-------|------|------------|------|---------|
| **1. 数据层** | 9 张表 + ORM + 常量 + seed | 模型 CRUD 单测通过 | 无 | models ≥ 90% |
| **2. 核心服务层** | generator/scorer/rubric_resolver/comparator + 单测 | 纯函数可单测 | Phase 1 | services ≥ 80% |
| **3. 运行编排层** | runner + scheduler + 异步执行 + case 级隔离 | 端到端跑通一次 run（mock AI） | Phase 2 | services ≥ 80% |
| **4. 后端 API 层** | admin + operator routers + OperationLog + conftest patch | API 集成测试通过 | Phase 3 | API ≥ 70% |
| **5. 前端** | api/types + 10 页面 + 测试 + 守卫扩展 | 页面可交互 + 组件测试通过 | Phase 4 | vitest 通过 |
| **6. 联调 + 文档** | 契约文档 + README + PM 记忆 + 全量回归 | 全量回归绿 | Phase 5 | 覆盖率达标 |

每个 Phase 一个独立 commit 序列（TDD：先测试后实现，频繁 commit），Phase 间用依赖串行（不并行）。

---

## Phase 1: 数据层（DB + ORM + 常量）

**Goal:** 建立 9 张 `eval_` 表的 schema 和 ORM，管理员可在测试库里建表/读写维度。

**Files:**
- Create: `backend/migrations/053_eval_core.sql`（9 表 + 索引 + seed 维度）
- Create: `backend/app/evaluation/__init__.py`
- Create: `backend/app/evaluation/constants.py`（tool_code 常量、维度名常量、trigger_type/status 枚举）
- Create: `backend/app/evaluation/models/__init__.py` + 9 个 model 文件：`dimension.py` / `rubric.py` / `test_case.py` / `version.py` / `run.py` / `case_result.py` / `score.py` / `human_label.py` / `schedule_policy.py`
- Modify: `backend/app/models/__init__.py`（注册 eval models）
- Test: `backend/tests/unit/models/test_eval_models.py`

**Interfaces:**
- Produces: `EvalDimension` / `EvalRubric` / `EvalTestCase` / `EvalVersion` / `EvalRun` / `EvalCaseResult` / `EvalScore` / `EvalHumanLabel` / `EvalSchedulePolicy` ORM 类，字段与 spec §5.4 完全一致；`EvalToolCode`、`EvalTriggerType`、`EvalRunStatus` 常量。

**Tasks:**
1. 写 `test_eval_models.py`：建表（metadata.create_all）、各表插入/查询、软删 `deleted_at` 过滤、唯一约束（`eval_case_results(run_id, test_case_id)`、`eval_scores(case_result_id, dimension_id)`）、ON DELETE 级联（删 run 连带删 case_results→scores）。
2. 写 migration `053_eval_core.sql`：9 张表 + spec §5.5 全部索引 + seed 3 个维度（copy_quality 0.4 / conversion_power 0.35 / persona_consistency 0.25）+ seed rubric 等级占位。
3. 写 `constants.py`：`EVAL_TOOL_QIANCHUAN_WRITER = "qianchuan-writer"`、触发/状态枚举字符串。
4. 写 9 个 ORM model（参照现有 `QianchuanWriterConfig` 风格，`Base` 来自 `app.core.database`；需补 `Numeric`/`SmallInteger`/`JSONB`/`ARRAY(String)` 导入）。
5. `app/models/__init__.py` **跨包注册** eval models（关键：conftest 依赖 `import app.models` 触发 `Base.metadata.create_all` 覆盖所有表，否则测试库建不出 eval 表）。在 `__init__.py` 末尾加 `from app.evaluation.models.dimension import EvalDimension` 等 9 行 import + 同步 `__all__`。
6. 跑测试 → 通过 → commit。

**Test gate:** `pytest tests/unit/models/test_eval_models.py -v` 全绿；`migration 053` 在测试库 `metadata.create_all` 后可建表。

**Dependencies:** 无。

---

## Phase 2: 核心服务层（纯函数，可单测）

**Goal:** 实现 prompt 渲染、评分、对比、rubric 解析，全部纯逻辑，不碰 AI 调用（AI 用接口注入，便于 mock）。

**Files:**
- Create: `backend/app/evaluation/services/__init__.py`
- Create: `backend/app/evaluation/services/rubric_resolver.py`（dimension + rubrics → 评分 prompt 文本，双花括号占位符渲染）
- Create: `backend/app/evaluation/services/generator.py`（先 `render_system_prompt` 渲染 name/soul/content_plan，再用 eval 自有渲染器处理 `{{product_info}}` 等其余字段）
- Create: `backend/app/evaluation/services/scorer.py`（解析 AI 返回 JSON：`extra_body` 启用 json mode + 后备正则 + 字段校验 score∈[min,max]）
- Create: `backend/app/evaluation/services/comparator.py`（两个 run 的 scores → 总体/维度/样本级 diff，改善/恶化/持平）
- Test: `backend/tests/unit/services/test_eval_rubric_resolver.py` / `test_eval_generator.py` / `test_eval_scorer.py` / `test_eval_comparator.py`

**Interfaces:**
- Consumes: Phase 1 的 ORM；AI 调用以可注入 callable 形式（`generate_fn`/`score_fn` 参数），测试用 mock。
- Produces:
  - `rubric_resolver.build_scoring_prompt(dimension, rubrics, context) -> str`
  - `generator.render_generation_prompt(template, input_payload) -> str`
  - `scorer.parse_score_response(raw, score_min, score_max) -> ParsedScore`
  - `comparator.compare_runs(scores_a, scores_b) -> ComparisonReport`

**Tasks:**
1. `rubric_resolver`：双花括号占位符替换 + rubric 等级拼接 + scenario_tag 一期不参与选择（spec §2.4）。
2. `generator`：两步渲染（先 `render_system_prompt`，再 eval 渲染器）+ 缺失值 fallback 空串。
3. `scorer`：JSON 解析三策略（json mode 输出 / 代码块提取 / `{...}` 正则）+ score 范围校验 + 缺失字段默认。
4. `comparator`：总体平均分 diff、每维度平均分 diff、样本级（**按 `test_case_id` 对齐**两次 run 的 case_result，再比 score；不能用 case_result 主键对齐，跨 run 主键不同）↑↓→ 分类。**签名收敛**：`EvalScore` 只有 `case_result_id` 无 `test_case_id`，故 comparator 入参应接受「带 test_case_id 的 case_result 元组 + 其 scores」的联合结构（由 runner/API 层组装），而非裸 `scores` 列表；bite-sized 阶段据此定形签名。
5. 每个服务先写失败测试 → 实现 → 通过 → commit（TDD，每个服务一个 commit）。

**Test gate:** 4 个服务单测全绿，覆盖率 ≥ 80%。AI 全程 mock，无真实调用。

**Dependencies:** Phase 1。

---

## Phase 3: 运行编排层（runner + scheduler）

**Goal:** 串起一次完整 run：生成→存 case_result→评分→存 score→更新 run 状态，case 级错误隔离，异步执行。

**Files:**
- Create: `backend/app/evaluation/services/runner.py`（编排：查 test_cases → 逐 case 调 generator/scorer（纯函数）→ **runner 自己**写 case_results/scores → 更新 completed/failed 计数 + 失败原因写入 `eval_runs.metadata['errors']`）
- Create: `backend/app/evaluation/services/scheduler.py`（手动触发入口 + 版本创建后自动触发；一期定时触发占位）
- Modify: `backend/tests/conftest.py`（`_SESSION_LOCAL_PATCH_TARGETS` 加 `app.evaluation.services.runner.AsyncSessionLocal` + `app.evaluation.services.scheduler.AsyncSessionLocal`；generator/scorer 纯函数不 import，不加）

**Interfaces:**
- Consumes: Phase 1 ORM + Phase 2 服务（AI callable 注入）。
- Produces:
  - `runner.execute_run(run_id, *, generate_fn, score_fn) -> None`（case 级 try/except，单 case 失败不中断）
  - `scheduler.trigger_run(version_id, filter_tags, trigger_type, user_id) -> run_id`

**Tasks:**
1. 写 runner 测试（mock AI）：3 case × 2 维度的 happy path → 全部 case_results/scores 落库 + run.status=completed。
2. 测试 case 级隔离：第 2 case 生成抛异常 → run 仍 completed，failed_cases=1，其余 case 正常；**且该 case 的 error message 落入 `run.metadata['errors']`**（spec §6.5）。
3. 实现 runner（`AsyncSessionLocal` 后台 session；DB 写入归 runner，generator/scorer 只返回结果）。
4. 写 scheduler 测试：手动触发建 run + 调 runner；版本创建后自动触发。
5. 改 conftest patch 列表（runner + scheduler 两路径）。
6. 通过 → commit。

> **测试策略**：runner 单测直接 `await runner.execute_run(...)`（绕过 endpoint/BackgroundTask，同步断言落库）；集成测试（Phase 4）经 endpoint 触发后轮询 `GET /runs/{id}` 到终态再断言。

**Test gate:** runner/scheduler 单测绿；case 级隔离验证通过。

**Dependencies:** Phase 2。

> **注**：一期异步用 BackgroundTask + DB 状态机（spec §6.2）。worker 持久化（Celery/RQ）二期。

---

## Phase 4: 后端 API 层

**Goal:** 暴露 admin + operator REST 接口，全部标准信封 + OperationLog + 鉴权。

**Files:**
- Create: `backend/app/evaluation/routers/admin_evaluation.py`（维度/rubric/版本/调度策略 CRUD；版本无 PUT，有 clone）
- Create: `backend/app/evaluation/routers/operator_evaluation.py`（测试集 CRUD + 运行触发/查询 + 评分明细 + 人工校准 + 对比）
- Create: `backend/app/evaluation/schemas/`（Pydantic 请求/响应模型）
- Modify: `backend/app/main.py`（include 两个 router：`import` + `app.include_router(..., prefix="/api")` 各两行）
- Modify: `backend/tests/conftest.py`（patch 列表按需补：仅当某 router endpoint 自开 BackgroundTask session 才加其 `AsyncSessionLocal` 路径；纯 `Depends(get_db)` 的 admin CRUD router **不加**）
- Test: `backend/tests/integration/routers/test_admin_evaluation.py` / `test_operator_evaluation.py`

**Interfaces (spec §9):**
- Admin: dimensions CRUD+DELETE / rubrics / versions (POST+GET+DELETE+clone) / schedule-policies CRUD+DELETE
- Operator: test-cases CRUD+DELETE / versions 只读 / runs 触发+查询 / scores 明细 / human-label / compare

**Tasks:**
1. schemas（每个接口的 request/response Pydantic）。
2. admin router（参照 `admin_qianchuan_writer.py` 风格，每个写操作写 OperationLog）。**schedule-policies POST/PUT 必须用 `croniter` 校验 cron 表达式**，非法返回 400（spec §3.4），写失败测试。
3. operator router（参照 `operator_qianchuan_writer.py`，鉴权用 `require_operator`——按手术刀原则**在本文件内复制** `require_operator`/`_get_ip`，不抽公共；运行触发走 scheduler）。
4. `main.py` include + conftest patch（以 grep `AsyncSessionLocal` 实际 import 点为准）。
5. **人工校准 `PUT /scores/{id}/human-label`**：必须在**单事务**内完成 ①更新 `eval_scores.human_score`/`human_feedback` ②插入 `eval_human_labels` 历史记录 ③写 OperationLog；集成测试断言事务原子性（spec §5.4）。
6. 集成测试：鉴权（401/403）+ happy path + OperationLog 写入断言 + 账号隔离 + 版本不可编辑（PUT 返回 405）+ 软删（DELETE 置 `deleted_at`）+ 非法 cron → 400。**AI 在集成测试全 mock**（patch `yunwu_adapter.chat`，或经 scheduler 注入 mock generate_fn/score_fn）。
7. 通过 → commit。

**OperationLog action 命名清单（统一前缀 `evaluation_`）**：`evaluation_dimension_create/update/delete`、`evaluation_rubric_update`、`evaluation_version_create/clone/delete`、`evaluation_test_case_create/update/delete`、`evaluation_run_trigger/cancel`、`evaluation_human_label_submit`、`evaluation_schedule_policy_create/update/delete`（与 spec §6.6 一致）。

**Test gate:** 集成测试全绿，API 覆盖率 ≥ 70%；convention_guard 通过（红线自动守卫）。

**Dependencies:** Phase 3。

---

## Phase 5: 前端

**Goal:** 10 个页面可交互，UI 风格与现有一致（Stone 暖灰 + 橙 #f59a23）。

**Files:**
- Create: `frontend/src/evaluation/api/index.ts`（基于 `@/api/request.ts`，`import { get, post, put, del }`）
- Create: `frontend/src/evaluation/types/`
- Create: `frontend/src/evaluation/pages/`（**10 个**：TestCaseList/Edit、VersionList/Edit、RunList/Detail、ComparePage、DimensionList/Edit、SchedulePolicyList）+ Rubric 管理嵌入 DimensionEdit
- Create: `frontend/src/evaluation/components/`（含 `RubricEditor.tsx`）
- Modify: `frontend/src/App.tsx`（路由 lazy）
- Modify: `frontend/src/pages/operator/WorkspacePage.tsx`（工具卡入口，若挂工作台）
- Modify: `frontend/src/__tests__/unit/api/conventionGuard.test.ts`（**扩展扫描 glob**）
- Test: `frontend/src/__tests__/`（页面组件测试）

**Interfaces:** 调 Phase 4 的 API；风格遵循 `docs/evaluation/open-design-brief.md`。

**Tasks:**
0. **先扩展前端守卫**（红线 #3 盲点修复）：把 `conventionGuard.test.ts` 的扫描从 `src/api/*.ts` 扩到 `src/**/api/*.ts`（递归），使 `src/evaluation/api/index.ts` 进守卫窗口。跑一次确认现有 api 仍通过 + 新窗口能扫到 evaluation api。
1. 按页面顺序实现：测试集(List/Edit) → 版本(List/Create/Clone) → 运行(List/Detail)+人工校准 → 对比(ComparePage) → 维度(List/Edit)+**Rubric 管理** → 定时策略(List)。每页：测试 → 实现 → commit。
2. **Rubric 管理**：嵌入 DimensionEdit 页（或独立 RubricEditor 组件），消费 `GET/PUT /api/admin/evaluation/dimensions/{id}/rubrics`，编辑各分数等级 level/criteria/scenario_tag。

**Test gate:** vitest 组件测试绿；`tsc --noEmit` 0 错；扩展后的 conventionGuard 扫描覆盖 evaluation api（无裸 fetch）。

**Dependencies:** Phase 4（API 稳定后再写前端，避免契约漂移）。

---

## Phase 6: 联调 + 文档 + 全量回归

**Goal:** 端到端跑通 + 文档落地 + 覆盖率达标 + 发 PR。

**Files:**
- Create: `docs/evaluation/api-contract.md`、`docs/evaluation/database-schema.md`、`docs/evaluation/architecture.md`、`docs/evaluation/user-guide.md`、`docs/evaluation/qianchuan-writer-integration.md`（对齐 spec §12 全部文档；`data-model-diagram.html` 已存在，表结构若调整需同步）
- Modify: `backend/docs/README.md`、`frontend/docs/README.md`、`docs/pm/PM_记忆与状态_M2.md`
- Test: 全量 `pytest tests/ -v` + `npx vitest run --coverage`

**Tasks:**
1. 端到端手测：建维度→建版本→录样本→触发 run→看评分→人工校准→两版本对比。
2. 补契约文档（`docs/evaluation/*` + Base_API / Base_Database 同步）；**缺文档不得声明完成**（CLAUDE.md 三铁律 #3）。
3. 更新 3 个 README + PM 记忆（PM 签收）。
4. 全量回归 + 覆盖率门禁；**覆盖率数据写入 PR 描述/交付报告**（CLAUDE.md 要求重大迭代交付带覆盖率数据）。
5. commit + push 分支 + 发 PR（AI 发，人工合并）。
6. **发 PR 后等 CI 完成**，运行 `gh pr checks <PR号>` 确认全绿，再通知人工合并；有新增失败回到对应 Phase 修复后再推（CLAUDE.md PR 合并门禁）。

**Test gate:** 后端全量绿 + 前端全量绿 + 覆盖率达标 + convention_guard 绿 + CI 全绿。

**Dependencies:** Phase 5。

---

## 测试与覆盖率策略（贯穿所有 Phase）

- **TDD**：每个任务先写失败测试。
- **AI 全 mock**：Phase 2/3/4 测试不调真实 AI（注入 callable / mock yunwu）。
- **分层覆盖率**：models ≥ 90% / services ≥ 80% / routers ≥ 70% / 整体 ≥ 75%。
- **convention_guard**：后端守卫自动拦截红线 #1#2#3#6#7。
- **case 级隔离测试**：Phase 3 必测（单个 case 失败不中断 run）。
- **版本不可编辑测试**：Phase 4 必测（PUT versions/{id} 返回 405）。

---

## 风险与依赖

1. **周会结论可能微调**：6 个确认问题若改维度/权重 → 调 Phase 1 seed 数据，不改结构。
2. **AI 评分稳定性**：Phase 2 scorer 的 JSON 解析三策略兜底；人工校准沉淀基准。
3. **异步可靠性**：一期 BackgroundTask 不适合长任务（spec §6.2 已明确限制），Phase 3 用 DB 状态机保存进度，中断后手动重跑。
4. **现有模块零改动**：所有 Phase 只读复用 yunwu/kol/ai_models，不改它们；conftest patch 是唯一对现有文件的修改（追加，不改逻辑）。

---

## 执行选择

开工某个 Phase 时再展开 bite-sized TDD 细节。两个执行方式：

1. **Subagent-Driven（推荐）**：每个 Phase 派 subagent，Phase 间 PM review。
2. **Inline**：当前会话逐 Phase 执行。

**建议**：等周会结论 → 我按结论微调 spec → 启动 Phase 1（最稳，meeting-independent 的数据层）。
