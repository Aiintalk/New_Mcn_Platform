# KOL Persona Profile Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让人格定位、红人工作台、入驻资料和下游工具围绕同一个正式 `kols.id` 工作，并把红人工作台“人物档案”收口为七项正式档案的唯一编辑入口。

**Architecture:** 保留现有人格定位三步页和 `kols` 七字段，不建第二套档案表。通过一个幂等迁移给人格报告、分享链接和运营直发会话增加可空 `kol_id`；后端新增正式达人和关联入驻资料查询、报告同步服务及字段级覆盖接口；前端在现有页面加入目标达人选择、覆盖确认和统一七字段编辑。五项事实由 AI 返回报告原文片段，服务端逐条验证片段确实存在于 `profile_result` 后才允许只填空值。

**Tech Stack:** FastAPI、SQLAlchemy 2 async、PostgreSQL 手写 SQL 迁移、React 19、TypeScript 6、Ant Design 5、Vitest、pytest。

## Global Constraints

- 起始提交固定为 `5264628d3a0270e010ed1178e56fd6d0ebce67bd`，分支固定为 `feature/kol-persona-profile-unification`。
- 正式达人只读取未删除的 `kols`，所有生成、报告、同步、历史与日志沿用同一个 `kol_id`；禁止姓名匹配和会话编号冒充达人编号。
- 入驻资料只按明确保存的 `kol_id` 查询，并且只返回 `operator_id=current_user.id` 的最近完成资料；历史空关联记录保留但不展示、不回填。
- `persona` / `content_plan` 空值自动写入；非空分别默认保留，只有显式 `overwrite` 才覆盖；拒绝覆盖不删除报告历史。
- 五项事实只接受能在报告正文中找到原文证据的内容，只填空值，不逐项询问，不覆盖人工内容；提取失败不影响报告成功或已完成的定位字段同步。
- 红人工作台是七字段唯一编辑入口；红人管理和旧素材库只读摘要并跳转工作台。
- 下游统一上下文继续返回并明确分段七字段；本期不改下游页面主流程。
- 所有非流式接口使用标准信封；所有用户写操作写 OperationLog，detail 只记录对象编号、字段名和动作，不记录档案正文。
- 所有 JSON 前端请求走 `request.ts`；流式、文件和表单上传继续使用现有例外。
- 迁移必须非破坏、可重复执行；只验证本地临时数据库或测试数据库，不执行生产迁移。
- 不合并 main、不部署、不执行生产数据库迁移、不上线；开发侧最终状态只能是“可供产品经理验收”。

---

### Task 1: Data links and permission-scoped identity APIs

**Files:**
- Create: `backend/migrations/055_kol_persona_profile_unification.sql`
- Modify: `backend/app/models/persona_report.py`
- Modify: `backend/app/models/kol_intake.py`
- Modify: `backend/app/routers/operator_intake.py`
- Modify: `backend/app/routers/operator_intake_direct.py`
- Modify: `backend/app/routers/persona.py`
- Test: `backend/tests/integration/routers/test_persona.py`
- Test: `backend/tests/integration/test_persona_profile_migration.py`
- Test: `backend/tests/integration/routers/test_persona_identity_binding.py`
- Test: `backend/tests/integration/routers/test_intake_kol_binding.py`

**Interfaces:**
- Produces: `PersonaReport.kol_id`, `KolIntakeLink.kol_id`, `KolIntakeOperatorSession.kol_id` as nullable foreign keys to `kols.id` with `ON DELETE SET NULL`.
- Produces: `GET /api/persona/kols?page&page_size&keyword` returning formal KOL IDs and seven-field completeness.
- Produces: `GET /api/persona/kols/{kol_id}/intake` returning `null` or `{completed_at, formatted_answers, report}` from the current operator's latest bound ready intake.
- Produces: `GenerateRequest.kol_id: int`; report creation, Output JSON and OperationLog all retain it.
- Produces: optional `kol_id` on intake link/direct-session creation, validated against an undeleted formal KOL.

- [ ] **Step 1: Write failing migration/model tests**

Add assertions that the three ORM models expose nullable `kol_id` foreign keys and a migration test that runs `055` twice against an isolated PostgreSQL database, then confirms all three columns, foreign keys and indexes exist while pre-existing rows keep `NULL`.

- [ ] **Step 2: Verify the data-link tests fail**

Run:
```bash
cd backend
DATABASE_URL='postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test' JWT_SECRET='test-only-secret' .venv/bin/pytest tests/unit/models/test_models.py tests/integration/test_persona_profile_migration.py -q
```

Expected: failures name missing `kol_id` attributes and missing migration `055`.

- [ ] **Step 3: Implement the idempotent migration and ORM fields**

The migration must use `ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, and guarded `DO $$ ... pg_constraint ... $$` blocks. Exact foreign-key behavior is `REFERENCES kols(id) ON DELETE SET NULL`; no historical update statement is allowed.

- [ ] **Step 4: Write failing identity and permission tests**

Cover these literal cases:

```python
assert formal_item["id"] == formal_kol.id
assert formal_item["profile_filled_count"] == 2
assert "会话_" not in response.text
assert own_bound_intake["report"] == "本人绑定报告"
assert other_operator_report not in response.text
assert unbound_historical_report not in response.text
assert generated_report.kol_id == formal_kol.id
assert output.content_json["kol_id"] == formal_kol.id
```

Also assert missing/deleted KOL returns not-found, search matches `name` / `account_name` / `douyin_id`, list is paginated, and link/direct session persist an optional valid `kol_id` while rejecting an invalid one.

- [ ] **Step 5: Verify the identity tests fail for the current bug**

Run:
```bash
cd backend
DATABASE_URL='postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test' JWT_SECRET='test-only-secret' .venv/bin/pytest tests/integration/routers/test_persona_identity_binding.py tests/integration/routers/test_intake_kol_binding.py -q
```

Expected: the old endpoint reads `kol_intake_operator_sessions`, exposes synthetic session values, ignores current-operator scope, and generate does not accept or persist a formal KOL ID.

- [ ] **Step 6: Implement minimum formal identity APIs**

Use shared-company access for the formal KOL list, matching the existing admin/operator read permission. For intake material, enforce `operator_id == current_user.id` for both direct sessions and share-link submissions, merge the two candidates in memory, and return only the newest completion without exposing source session IDs.

- [ ] **Step 7: Run Task 1 regression**

Run the two new test files plus `test_persona.py`; all must pass with no production-network calls.

- [ ] **Step 8: Commit Task 1**

```bash
git add backend/migrations/055_kol_persona_profile_unification.sql backend/app/models/persona_report.py backend/app/models/kol_intake.py backend/app/routers/operator_intake.py backend/app/routers/operator_intake_direct.py backend/app/routers/persona.py backend/tests
git commit -m "feat: bind persona flows to formal KOL IDs"
```

### Task 2: Report synchronization, grounded facts, unified profile API, and backend entry closure

**Files:**
- Create: `backend/app/services/persona_profile_sync.py`
- Modify: `backend/app/routers/persona.py`
- Modify: `backend/app/routers/admin_kols.py`
- Modify: `backend/app/routers/operator_material_library.py`
- Modify: `backend/app/services/kol_context.py`
- Test: `backend/tests/unit/services/test_persona_profile_sync.py`
- Test: `backend/tests/integration/routers/test_persona_profile_sync.py`
- Test: `backend/tests/integration/routers/test_operator_kols_persona.py`
- Test: `backend/tests/integration/routers/test_operator_material_library.py`
- Test: `backend/tests/unit/services/test_kol_context.py`

**Interfaces:**
- Consumes: `PersonaReport.kol_id` from Task 1.
- Produces: `parse_grounded_fact_candidates(profile_result: str, raw_json: str) -> dict[str, str]` that keeps only exact report substrings for the five fixed fact keys.
- Produces: initial sync result with per-field actions `auto_written`, `pending`, `kept`, `overwritten`, `unchanged`.
- Produces: `POST /api/persona/reports/{report_id}/sync-decisions` with `keep|overwrite` decisions.
- Produces: seven-field GET and exactly-one-field PUT at `/api/operator/kols/{kol_id}/persona-details`.
- Produces: `POST .../persona-details/fill-empty` scoped to the current operator's latest ready report.

- [ ] **Step 1: Write failing pure service tests**

Test a matrix where `persona` and `content_plan` are both empty, one empty, both nonempty, identical to the report, and whitespace-only. Test fact JSON with one exact quote, one hallucinated quote absent from the report, an unknown key, and malformed JSON. Expected accepted fields are limited to `background`, `experience`, `relationships`, `unique_story`, `extra_notes` and only exact substrings.

- [ ] **Step 2: Verify service tests fail**

Run `pytest tests/unit/services/test_persona_profile_sync.py -q`; expected failure is missing service functions.

- [ ] **Step 3: Implement the small pure synchronization service**

Keep pure decisions separate from database writes. The extraction prompt requests JSON arrays of exact source excerpts; the parser discards any excerpt not literally present in `profile_result`. Join accepted excerpts with newlines and leave missing facts empty.

- [ ] **Step 4: Write failing integration tests for synchronization and idempotency**

Cover empty auto-write, mixed empty/nonempty, default keep, independent overwrite, modal-close-as-keep, repeated submission, report history retained, deleted KOL during generation, extraction failure isolation, five facts only filling empty values, log detail without full text, and no duplicate overwrite log when values are already identical.

- [ ] **Step 5: Implement finalization and decision endpoints**

Finalize the report and Output first, then synchronize positioning fields. Run fact extraction in a separately guarded block; its exception records a fact-sync failure result but does not change report `ready`. Re-fetch the KOL before every write. Details and list history must return `kol_id`.

- [ ] **Step 6: Write failing unified profile and old-entry tests**

Assert GET returns all seven fields and `filled_count`; PUT accepts exactly one field, permits `""` to clear, rejects two fields, and logs only the field name. Assert fill-empty preserves nonempty facts. Assert admin create/update no longer accept positioning fields and the material-library profile PUT route no longer exists.

- [ ] **Step 7: Implement unified API and close backend write paths**

Extend `PersonaDetailsRequest` with seven optional fields but inspect `model_fields_set` to require exactly one submitted key. Remove `persona` / `content_plan` from admin KOL create/update schemas and remove material-library `PUT /profile`. Keep read responses unchanged for summaries.

- [ ] **Step 8: Prove downstream compatibility**

Keep `KolContext.prompt_sections()` returning seven nonempty sections, but rename the persona label to `人格档案（角色定位和表达原则）`, the plan label to `内容规划（内容方向和创作策略）`, and prefix five fact labels with `人物事实：`. Run direct service tests and the existing qianchuan/persona/livestream/values/retrospective related tests.

- [ ] **Step 9: Commit Task 2**

```bash
git add backend/app backend/tests
git commit -m "feat: synchronize persona reports into unified profiles"
```

### Task 3: Existing three-step persona page binding and overwrite interaction

**Files:**
- Modify: `frontend/src/types/persona.ts`
- Modify: `frontend/src/api/persona.ts`
- Modify: `frontend/src/pages/operator/PersonaPage.tsx`
- Create: `frontend/src/__tests__/components/pages/PersonaPage.test.tsx`
- Modify: `frontend/src/__tests__/unit/api/persona.test.ts`
- Modify: `frontend/src/styles/admin.css`
- Modify: `frontend/docs/前端规范.md`

**Interfaces:**
- Consumes Task 1 formal KOL and intake APIs and Task 2 detail/sync APIs.
- Produces `getPersonaKols`, `getPersonaKolIntake`, `syncPersonaReportDecisions` through `request.ts`.
- Produces `GenerateParams.kol_id` on the existing streaming request.

- [ ] **Step 1: Write failing API tests**

Assert exact paths and payloads: `/api/persona/kols`, `/api/persona/kols/43/intake`, `/api/persona/reports/88/sync-decisions`, and generate body containing `kol_id: 43`.

- [ ] **Step 2: Write failing component tests**

Cover list loading error with visible retry, search by a typed keyword, formal option showing name/account/completeness, next-step disabled before target selection, bound intake found/imported, no-intake upload path, generate carrying the selected KOL ID, overwrite dialog defaulting both fields to keep, independent decisions, and closing the dialog submitting keep.

- [ ] **Step 3: Verify the current page fails for the expected reasons**

Run both new/modified test files. Expected failures: old `getKolSubmissions`, silent load failure, synthetic session selection semantics, and no overwrite dialog.

- [ ] **Step 4: Implement the minimum interaction in the existing page**

Do not create a new route. Keep the three steps and existing upload/parse/optimize/export/history areas. Add a searchable target block above the upload section, preserve user-entered data on list retry, load intake only after target selection, and tag imported virtual files so switching target removes only the old intake import. Do not let selecting a KOL alone satisfy the required input-material gate.

- [ ] **Step 5: Implement sync feedback**

After the stream ends, fetch the report detail. If pending fields exist, open one dialog with independent radio choices defaulting to keep; otherwise show the auto-write/fact-fill result. On close, submit keep for all pending fields so the backend can audit preservation.

- [ ] **Step 6: Run Task 3 tests and production type/build check**

Run targeted Vitest, `npx tsc --noEmit`, and `npm run build`.

- [ ] **Step 7: Commit Task 3**

```bash
git add frontend/src frontend/docs/前端规范.md
git commit -m "feat: bind persona positioning to formal KOLs"
```

### Task 4: Seven-field workspace UI and frontend closure of duplicate editors

**Files:**
- Modify: `frontend/src/types/kolWorkspace.ts`
- Modify: `frontend/src/api/kolWorkspace.ts`
- Modify: `frontend/src/pages/operator/workspace/WorkspacePersona.tsx`
- Modify: `frontend/src/pages/admin/KolsPage.tsx`
- Modify: `frontend/src/pages/operator/MaterialLibraryPage.tsx`
- Modify: `frontend/src/api/materialLibrary.ts`
- Modify: `frontend/src/__tests__/components/pages/WorkspacePersona.test.tsx`
- Modify: `frontend/src/__tests__/components/pages/MaterialLibraryPage.test.tsx`
- Create: `frontend/src/__tests__/components/pages/KolsPage.test.tsx`

**Interfaces:**
- Consumes Task 2 seven-field GET/single-field PUT/fill-empty endpoints.
- Produces `fillEmptyPersonaFacts(kolId)` API.

- [ ] **Step 1: Write failing workspace tests**

Assert two sections in order, all seven labels, `已填写`/`待补充`, completeness `6/7`, independent edit/save/cancel, and fill-empty result message naming only filled fields. Add a 1024-width DOM assertion that no fixed child width exceeds its container.

- [ ] **Step 2: Write failing duplicate-entry tests**

Admin KOL detail and create/edit form must have no editable persona/content-plan textarea or save button, must show read-only summaries, and must provide a `/kol-workspace/{id}` jump. Material library must not call `updateKolProfile`, must show read-only summaries and the same jump while all six reference types remain editable.

- [ ] **Step 3: Implement the unified page**

Use the existing workspace shell, orange tokens and CSS variables. Keep one field editor open at a time. Positioning fields render above facts. The fill button disables while running and reports `filled_fields`; no per-fact confirm is added.

- [ ] **Step 4: Remove duplicate frontend mutations**

Delete `updateKolProfile` export and all callers. Remove persona/content_plan from admin create/edit payload construction. Preserve read-only data in detail responses.

- [ ] **Step 5: Run Task 4 tests and related workspace regression**

Run the three task test files plus `KolWorkspacePage.test.tsx`, then `npx tsc --noEmit` and `npm run build`.

- [ ] **Step 6: Commit Task 4**

```bash
git add frontend/src
git commit -m "feat: make workspace the unified profile editor"
```

### Task 5: Integration evidence, documentation, screenshots, and delivery gates

**Files:**
- Create: `backend/docs/tasks/M2_Sprint25_后端任务_达人档案统一_v1.md`
- Create: `frontend/docs/tasks/M2_Sprint25_前端任务_达人档案统一_v1.md`
- Create: `backend/docs/tests/M2_Sprint25_达人档案统一_测试报告_v1.md`
- Create: `frontend/docs/tests/M2_Sprint25_达人档案统一_测试报告_v1.md`
- Create: `backend/docs/tasks/M2_Sprint25_后端任务_开发验收_达人档案统一_v1.md`
- Create: `frontend/docs/tasks/M2_Sprint25_前端任务_开发验收_达人档案统一_v1.md`
- Create: `docs/pm/M2_Sprint25_达人档案统一_开发验收清单_v1.md`
- Modify: `backend/docs/README.md`
- Modify: `frontend/docs/README.md`
- Modify: `README.md`
- Modify: `docs/pm/PM_记忆与状态_M2.md`

**Interfaces:**
- Consumes all earlier tasks.
- Produces reproducible test evidence and two real-page screenshot sizes.

- [ ] **Step 1: Run complete related backend tests**

Run persona, intake binding, unified profile, material-library closure, KOL context and affected downstream router suites from repository root. Record exact counts and commands, not partial parallel output.

- [ ] **Step 2: Run complete related frontend tests and production build**

Run PersonaPage, WorkspacePersona, KolsPage, MaterialLibraryPage, API convention guard, related workspace suite, TypeScript check, and production build. Record warnings separately from failures.

- [ ] **Step 3: Verify migration upgrade and repeat execution**

Create an isolated temporary PostgreSQL database, apply migrations through `054`, insert unbound historical rows, apply `055` twice, verify rows remain and columns/FKs/indexes are correct, then drop only that explicit temporary database.

- [ ] **Step 4: Browser acceptance and screenshots**

Start local backend/frontend with test data and no real provider call. Capture the real Persona page target/intake state, overwrite dialog, and unified workspace page at 1440x900 and 1024x768. Verify no horizontal scroll, overlap, clipped buttons or console errors.

- [ ] **Step 5: Independent read-only technical review**

Provide the reviewer the full branch diff and test report. Reviewer must explicitly verdict formal KOL source, operator isolation, end-to-end `kol_id`, no synthetic session values, empty/overwrite rules, grounded fill-only facts, old-entry closure, downstream compatibility and evidence quality. Reviewer may not edit files.

- [ ] **Step 6: Documentation and whitelist closure**

Update the two READMEs, root README, PM status, task/acceptance/test reports. Run `git diff --check`, `git status --short`, tracked-secret scan, changed-file whitelist, and `git diff 5264628...HEAD` review.

- [ ] **Step 7: Commit, push, and prepare PR**

Commit only whitelisted task files, push `feature/kol-persona-profile-unification`, verify remote SHA with `git ls-remote`, and prepare—but do not merge—the PR title/body.
