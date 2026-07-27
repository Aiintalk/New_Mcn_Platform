# AIGC 评测系统 v2 — PR 变更说明

> 给：项目负责人 + 仓库管理员（郜郜）。
> 范围：`feature/aigc-evaluation-v2` vs `main`（origin/main = 135a9b2）。**95 文件，+17890 / -67**。
> 一句话：新增「千川仿写」AIGC 工具的回归测试评价体系——测试集 + 安雅 4 维评分标准 + 异步运行架构（arq+Redis）+ admin/operator 前端。**绝大部分是新增模块；动存量的只有 14 个文件。**

管理员重点关注两节：**§1 改了哪些已有文件**、**§2 部署环境变更**。

---

## §1. 改了哪些「已有文件」（14 个 — 动存量，重点审）

### 后端（6 个）

| 文件 | 改了什么 | 为什么 | 风险 |
|---|---|---|---|
| `backend/app/adapters/yunwu.py` | `_HTTP_TIMEOUT` 60→**150** | 推理模型（glm-4.6 评委 / kimi-k3 生成）长 prompt 响应慢，60s 触发 `httpx.ReadTimeout` | ⚠️ **共享 adapter，全局生效**：所有非流式 `yunwu.chat` 超时从 60s 放宽到 150s（流式仍 300s 不变）。代价=挂起请求最多多等 90s 才失败；收益=不误杀慢响应。无逻辑改动。 |
| `backend/app/main.py` | +2 行 `include_router`（admin/operator eval） | 挂载评测 API | 低（纯新增挂载，不动现有路由） |
| `backend/app/models/__init__.py` | +12 个 eval 模型 import + `__all__` | Alembic 迁移 autogenerate 需要模型注册可见 | 低（纯新增） |
| `backend/requirements.txt` | +`croniter` +`arq` +`redis` | cron 解析 / 异步队列载体 | 部署需 `pip install`（见 §2） |
| `backend/tests/conftest.py` | +5 行 `AsyncSessionLocal` patch 目标 | 测试隔离（红线 #7：新模块用 AsyncSessionLocal 必须注册，否则测试连生产库） | 低（仅测试基建） |
| `.gitignore` | +`coverage/` | 忽略覆盖率产物 | 无 |

### 前端（8 个）

| 文件 | 改了什么 | 风险 |
|---|---|---|
| `frontend/package.json` / `package-lock.json` | +`@vitest/coverage-v8` | 部署需 `npm install` |
| `frontend/src/App.tsx` | +lazy 路由挂载 8 个评测页面 | 低（纯新增路由） |
| `frontend/src/layouts/AdminLayout.tsx` | +「评测配置」菜单组 | 低 |
| `frontend/src/layouts/OperatorLayout.tsx` | +评测菜单项（**admin-only**，按 role 过滤）+ Suspense 修闪烁 | 低（已修导航刷白） |
| `frontend/vite.config.ts` | `host:true` + `allowedHosts:true` | ⚠️ `allowedHosts:true` 放开所有 host——**仅开发用**（LAN/Tailscale 访问）；生产 nginx 前置不受影响 |
| `frontend/src/__tests__/unit/api/conventionGuard.test.ts` / `src/test/setup.ts` | 测试守卫 + 配置 | 低（仅测试） |

> **核心结论**：14 个存量文件里，**没有一处改动核心业务逻辑**。最需注意的是 `yunwu.py` 超时全局放宽（§1 后端首行）和 `vite.config` 的 `allowedHosts:true`（开发限定）。

---

## §2. 部署环境变更（管理员必读）

### 2.1 Redis（新基建）
评测异步队列的载体。**仅评测模块使用，主工程其它部分不依赖**——将来评测工程独立部署时，连同 Redis 一起迁出。

- **dev**：`bash backend/scripts/start_redis.sh` → 起 docker 容器 `mcn-redis`（`redis:7-alpine`，端口 6379）
- **prod**：单机 Redis + AOF 持久化 + 定时备份（PM2/systemd 守护）
- **新 env**：`REDIS_URL`（默认 `redis://localhost:6379/0`，**不进全局 config.py**，仅评测 worker 读）

### 2.2 新进程：arq worker（与 web 分离）
- 启动：`REDIS_URL=redis://localhost:6379/0 arq app.evaluation.worker.WorkerSettings`（PM2 管理）
- 配置：`max_jobs=2`（凭证池限流）、`job_timeout=900s`、`max_tries=3`、`on_startup` 恢复卡死 job
- 职责：从 Redis 取 `eval_case_job` → 真实执行（kimi 生成 + glm 多维评分）→ 写结果 → 聚合 run

### 2.3 DB 迁移（2 个，**全新增表，不动任何存量表**）
- `053_eval_core.sql`：11 张表——`eval_dimensions / rubrics / test_cases / versions / strategies / runs / case_results / scores / human_labels / schedule_policies / judge_models`
- `054_eval_case_jobs.sql`：`eval_case_jobs`（异步 job：`status` 机 pending→running→done/failed/cancelled + `UNIQUE(run_id,test_case_id)` + `CHECK` 约束 + 索引）

### 2.4 依赖
- 后端：`pip install -r requirements.txt`（新增 `arq>=0.26` `redis>=5.0` `croniter>=1.4.0`）
- 前端：`npm install`（新增 `@vitest/coverage-v8`）

### 2.5 凭证（运行时配，**绝不进代码/seed/提交**）
`credentials` 表需：
- **glm**：智谱 Coding Plan key（base_url `/api/coding/paas/v4`，授权 **glm-4.6 / glm-4.5**，**不含 glm-4-flash**）
- **kimi**：`api.kimi.com/coding/v1`，模型 `k3`（OpenAI 兼容），**temperature 必须 1**（推理模型硬要求）

### 2.6 建议部署顺序
1. `pip install -r requirements.txt` + `npm install`
2. 跑迁移 `053` + `054`
3. `credentials` 表配 glm + kimi key（运行时 INSERT）
4. seed demo：`psql ... -f backend/scripts/seed_eval_demo.sql`
5. `.env` 加 `REDIS_URL=redis://localhost:6379/0`
6. 起 redis：`bash backend/scripts/start_redis.sh`
7. 起 web（`uvicorn`）+ 起 worker（`arq ...`，独立进程）

---

## §3. 新增文件（~80，按模块）

- **后端 `app/evaluation/`**：models(13) · schemas(9) · services(7: runner/scheduler/generator/scorer/rubric_resolver/comparator + worker) · routers(3: admin/operator) · adapters(4) · constants
- **后端测试**：unit/services(7) · integration/routers(2) · unit/models(1)
- **前端 `src/evaluation/`**：pages(8) + api/types/components/styles + 单测/e2e
- **文档**：docs/evaluation(3) + specs/plans

---

## §4. 测试与质量

- **200+ eval 测试全绿**；覆盖率 runner 93% / scheduler 97% / worker 87%（全过 80% 门禁）
- Phase 3（worker 真实执行）经 **2 轮独立子 agent review**（R1 双 reviewer + R2 验证轮），无显性错误
- **冒烟验证**（真实 LLM）：kimi-k3 生成真实千川文案 + glm-4.6 四维评分 `[8/9/10/8]` 真落库，异步全链路打通

---

## §5. 风险与回滚

- **回滚**：评测是全新模块 + 2 张新表（不动存量表）→ 回滚 = 不部署 / drop `eval_*` 表 / 不起 worker，不影响主工程
- **存量改动**均为：超时常量、路由挂载、模型注册、依赖、测试配置——**无核心业务逻辑改动**
- **Redis 隔离**：依赖限定在 `app/evaluation/`，主工程零侵入；迁出时 `mcn-redis` 容器同迁
- **生产注意**：`vite allowedHosts:true` 仅开发；生产走 nginx 前置，该配置不生效


---

## 附录 A：改存量文件 diff（git diff `+/-` 格式，逐行证据）

> 配合 §1 表格阅读：表格给"改了什么/为什么/风险"，此处给逐行 diff。
> 已排除 `frontend/package-lock.json`（锁文件自动生成，纯噪音）。
> 共 13 个存量文件，按「后端 → 前端」排列，每个文件以 `diff --git` 行分隔。

```diff
diff --git a/.gitignore b/.gitignore
index 7ffcacf..1007256 100644
--- a/.gitignore
+++ b/.gitignore
@@ -19,6 +19,7 @@ node_modules/
 dist/
 build/
 .cache/
+coverage/
 
 # 日志
 *.log
@@ -65,3 +66,6 @@ backend/legacy_for_server_*.sql
 
 # Walkthrough 生成产物（skill 自动产出，每次重新生成，不进 git）
 docs/walkthrough/
+
+# 评测 UI 设计稿导出（Open Design handoff，本地参考用，不进 git）
+frontend/docs/design_reference/
diff --git a/backend/app/adapters/yunwu.py b/backend/app/adapters/yunwu.py
index 709665b..4c41d80 100644
--- a/backend/app/adapters/yunwu.py
+++ b/backend/app/adapters/yunwu.py
@@ -29,7 +29,7 @@ _DEFAULT_BASE_URLS = {
     "siliconflow": os.getenv("SILICONFLOW_BASE_URL",  "https://api.siliconflow.cn/v1"),
     "glm":         os.getenv("GLM_BASE_URL",          "https://open.bigmodel.cn/api/paas/v4"),
 }
-_HTTP_TIMEOUT  = 60
+_HTTP_TIMEOUT  = 150  # 推理模型（glm-4.6 评委 / kimi k3 生成）长 prompt 响应慢；配合 job_timeout 留余量（见 worker.WorkerSettings）
 _STREAM_TIMEOUT = 300  # 流式生成超时（秒），人格定位等长输出场景
 _QUEUE_TIMEOUT = 30   # 排队等待上限（秒）
 _STALE_LOCK_SECS = 360  # 僵尸锁超时（秒）：active_requests > 0 但 updated_at 超过此时间的视为泄漏
diff --git a/backend/app/main.py b/backend/app/main.py
index 8d6c5de..8860dc8 100644
--- a/backend/app/main.py
+++ b/backend/app/main.py
@@ -71,6 +71,8 @@ from app.routers import admin_values_writer, operator_values_writer
 from app.routers import admin_script_review, operator_script_review
 from app.routers import admin_retrospective, operator_retrospective
 from app.routers import admin_kol_workspace
+from app.evaluation.routers.admin_evaluation import router as admin_eval_router
+from app.evaluation.routers.operator_evaluation import router as operator_eval_router
 
 
 @asynccontextmanager
@@ -196,3 +198,5 @@ app.include_router(operator_script_review.router, prefix="/api")
 app.include_router(admin_retrospective.router, prefix="/api")
 app.include_router(operator_retrospective.router, prefix="/api")
 app.include_router(admin_kol_workspace.router, prefix="/api")
+app.include_router(admin_eval_router, prefix="/api")
+app.include_router(operator_eval_router, prefix="/api")
diff --git a/backend/app/models/__init__.py b/backend/app/models/__init__.py
index 13bc5e0..c0e0a3d 100644
--- a/backend/app/models/__init__.py
+++ b/backend/app/models/__init__.py
@@ -44,6 +44,20 @@ from app.models.values_writer import ValuesWriterConfig
 from app.models.qianchuan_script_review import QianchuanScriptReviewConfig
 from app.models.retrospective import RetrospectiveConfig, RetrospectiveSession
 from app.models.kol_workspace_config import KolWorkspaceConfig
+from app.evaluation.models import (
+    EvalCaseJob,
+    EvalCaseResult,
+    EvalDimension,
+    EvalHumanLabel,
+    EvalJudgeModel,
+    EvalRubric,
+    EvalRun,
+    EvalSchedulePolicy,
+    EvalScore,
+    EvalStrategy,
+    EvalTestCase,
+    EvalVersion,
+)
 
 __all__ = [
     "User",
@@ -97,4 +111,16 @@ __all__ = [
     "RetrospectiveConfig",
     "RetrospectiveSession",
     "KolWorkspaceConfig",
+    "EvalCaseJob",
+    "EvalCaseResult",
+    "EvalDimension",
+    "EvalHumanLabel",
+    "EvalJudgeModel",
+    "EvalRubric",
+    "EvalRun",
+    "EvalSchedulePolicy",
+    "EvalScore",
+    "EvalStrategy",
+    "EvalTestCase",
+    "EvalVersion",
 ]
diff --git a/backend/requirements.txt b/backend/requirements.txt
index 5714e63..ad1ea81 100644
--- a/backend/requirements.txt
+++ b/backend/requirements.txt
@@ -23,3 +23,7 @@ pytest>=8.0
 pytest-asyncio>=0.23
 pytest-cov>=5.0
 pytz
+croniter>=1.4.0
+# —— 评测模块异步运行（arq + Redis）—— 仅评测模块依赖，将来评测工程独立时随迁 ——
+arq>=0.26
+redis>=5.0
diff --git a/backend/tests/conftest.py b/backend/tests/conftest.py
index 71e5052..6150bad 100644
--- a/backend/tests/conftest.py
+++ b/backend/tests/conftest.py
@@ -81,6 +81,11 @@ _SESSION_LOCAL_PATCH_TARGETS = [
     "app.routers.operator_script_review.AsyncSessionLocal",
     "app.routers.operator_retrospective.AsyncSessionLocal",
     "app.routers.operator_qianchuan_preview.AsyncSessionLocal",
+    # AIGC 评测 Phase 3：runner 后台执行 run（持 session 写库）+ scheduler 自动/定时触发建 run
+    "app.evaluation.services.runner.AsyncSessionLocal",
+    "app.evaluation.services.scheduler.AsyncSessionLocal",
+    # Phase 2 异步运行：worker 的 eval_case_job 开独立 session 执行 case-job（防连生产库）
+    "app.evaluation.worker.AsyncSessionLocal",
 ]
 
 
diff --git a/frontend/package.json b/frontend/package.json
index d902897..cbe35f1 100644
--- a/frontend/package.json
+++ b/frontend/package.json
@@ -37,6 +37,7 @@
     "@types/react": "^19.2.14",
     "@types/react-dom": "^19.2.3",
     "@vitejs/plugin-react": "^6.0.1",
+    "@vitest/coverage-v8": "^3.2.7",
     "eslint": "^10.3.0",
     "eslint-plugin-react-hooks": "^7.1.1",
     "eslint-plugin-react-refresh": "^0.5.2",
diff --git a/frontend/src/App.tsx b/frontend/src/App.tsx
index 20f687e..10c90c6 100644
--- a/frontend/src/App.tsx
+++ b/frontend/src/App.tsx
@@ -49,6 +49,15 @@ const QianchuanScriptReviewPage = lazy(() => import('./pages/operator/QianchuanS
 const KolWorkspacePage = lazy(() => import('./pages/operator/KolWorkspacePage'));
 const KolHubPage = lazy(() => import('./pages/operator/KolHubPage'));
 const KolWorkspaceConfigPage = lazy(() => import('./pages/admin/KolWorkspaceConfigPage'));
+// AIGC 评测模块（Phase 5）
+const EvalTestCasesPage = lazy(() => import('./evaluation/pages/TestCases'));
+const EvalTestCaseEditPage = lazy(() => import('./evaluation/pages/TestCaseEdit'));
+const EvalRunsPage = lazy(() => import('./evaluation/pages/Runs'));
+const EvalRunDetailPage = lazy(() => import('./evaluation/pages/RunDetail'));
+const EvalComparePage = lazy(() => import('./evaluation/pages/Compare'));
+const EvalVersionsPage = lazy(() => import('./evaluation/pages/Versions'));
+const EvalDimensionsPage = lazy(() => import('./evaluation/pages/Dimensions'));
+const EvalSchedulesPage = lazy(() => import('./evaluation/pages/Schedules'));
 
 function Page403() {
   return (
@@ -131,6 +140,13 @@ export default function App() {
               <Route path="/tasks" element={<TasksPage />} />
               <Route path="/outputs" element={<OutputsPage />} />
               <Route path="/kol-hub" element={<KolHubPage />} />
+              {/* AIGC 评测系统（Phase 5）— operator 可访问，admin 亦可用 */}
+              <Route path="/evaluation/test-cases" element={<EvalTestCasesPage />} />
+              <Route path="/evaluation/test-cases/new" element={<EvalTestCaseEditPage />} />
+              <Route path="/evaluation/test-cases/:id/edit" element={<EvalTestCaseEditPage />} />
+              <Route path="/evaluation/runs" element={<EvalRunsPage />} />
+              <Route path="/evaluation/runs/:id" element={<EvalRunDetailPage />} />
+              <Route path="/evaluation/compare" element={<EvalComparePage />} />
             </Route>
           </Route>
 
@@ -150,6 +166,10 @@ export default function App() {
                 <Route path="/admin/audit" element={<OperationLogsPage />} />
                 <Route path="/admin/config" element={<ServiceConfigPage />} />
                 <Route path="/admin/intake" element={<AdminIntakePage />} />
+                {/* AIGC 评测 — admin only */}
+                <Route path="/admin/evaluation/versions" element={<EvalVersionsPage />} />
+                <Route path="/admin/evaluation/dimensions" element={<EvalDimensionsPage />} />
+                <Route path="/admin/evaluation/schedules" element={<EvalSchedulesPage />} />
               </Route>
             </Route>
           </Route>
diff --git a/frontend/src/__tests__/unit/api/conventionGuard.test.ts b/frontend/src/__tests__/unit/api/conventionGuard.test.ts
index 83ef40b..92428b3 100644
--- a/frontend/src/__tests__/unit/api/conventionGuard.test.ts
+++ b/frontend/src/__tests__/unit/api/conventionGuard.test.ts
@@ -1,7 +1,8 @@
 /**
  * 前端规范守卫 — 红线 #3: API 调用必须走 request.ts
  *
- * 扫描 src/api/*.ts（排除 request.ts 自身），检查是否有裸 fetch() 调用。
+ * 扫描范围：src 下所有 api 子目录里的 .ts 文件（含 src/api 与 src/evaluation/api 等）。
+ * 检查：是否存在裸 fetch() 调用（未走 request.ts 的 get/post/put/del）。
  *
  * 例外场景（允许直接使用 fetch）:
  *   - FormData 上传（代码中出现 FormData）
@@ -12,10 +13,10 @@
  * 例外函数也必须手动解包 .data（见 CLAUDE.md §12 #3）。
  */
 import { describe, it } from 'vitest'
-import { readFileSync, readdirSync } from 'fs'
-import { join, resolve } from 'path'
+import { readFileSync, readdirSync, statSync, existsSync } from 'fs'
+import { join, resolve, relative } from 'path'
 
-const API_DIR = resolve(process.cwd(), 'src', 'api')
+const ROOT_DIR = resolve(process.cwd(), 'src')
 
 // fetch() 附近出现以下任一模式时视为合法例外
 const EXCEPTION_INDICATORS = [
@@ -35,19 +36,54 @@ interface FetchViolation {
   context: string
 }
 
+/** 递归收集所有 src 下 api 子目录里的 .ts 文件（排除 request.ts 自身） */
+function collectApiFiles(): string[] {
+  const result: string[] = []
+
+  function walk(dir: string) {
+    if (!existsSync(dir)) return
+    let entries: string[]
+    try {
+      entries = readdirSync(dir)
+    } catch {
+      return
+    }
+    for (const name of entries) {
+      const abs = join(dir, name)
+      let st
+      try {
+        st = statSync(abs)
+      } catch {
+        continue
+      }
+      if (st.isDirectory()) {
+        walk(abs)
+      } else if (st.isFile() && name.endsWith('.ts') && name !== 'request.ts') {
+        // 只接受路径段包含 /api/ 的文件
+        const normalized = abs.replace(/\\/g, '/')
+        // 排除测试文件（自身守卫扫描不应触发自己）
+        if (normalized.includes('/api/') && !normalized.includes('.test.') && !normalized.includes('/__tests__/')) {
+          result.push(abs)
+        }
+      }
+    }
+  }
+
+  walk(ROOT_DIR)
+  return Array.from(new Set(result))
+}
+
 function findFetchViolations(): FetchViolation[] {
   const violations: FetchViolation[] = []
+  const files = collectApiFiles()
 
-  let files: string[]
-  try {
-    files = readdirSync(API_DIR)
-      .filter((f) => f.endsWith('.ts') && f !== 'request.ts')
-  } catch {
-    return [{ file: '(api-dir)', line: 0, context: `无法读取目录 ${API_DIR}` }]
+  if (files.length === 0) {
+    return [{ file: '(api-dir)', line: 0, context: `未扫描到任何 .ts 文件（${ROOT_DIR}）` }]
   }
 
-  for (const file of files) {
-    const content = readFileSync(join(API_DIR, file), 'utf-8')
+  for (const abs of files) {
+    const rel = relative(process.cwd(), abs)
+    const content = readFileSync(abs, 'utf-8')
     const lines = content.split('\n')
 
     for (let i = 0; i < lines.length; i++) {
@@ -66,7 +102,7 @@ function findFetchViolations(): FetchViolation[] {
       const hasException = EXCEPTION_INDICATORS.some((p) => window.includes(p))
       if (!hasException) {
         violations.push({
-          file,
+          file: rel,
           line: i + 1,
           context: trimmed.substring(0, 80),
         })
@@ -78,7 +114,7 @@ function findFetchViolations(): FetchViolation[] {
 }
 
 describe('红线 #3: API 调用必须走 request.ts', () => {
-  it('src/api/*.ts 中不应有未经例外的裸 fetch() 调用', () => {
+  it('src/api/*.ts 与 src/**/api/*.ts 中不应有未经例外的裸 fetch() 调用', () => {
     const violations = findFetchViolations()
 
     if (violations.length > 0) {
diff --git a/frontend/src/layouts/AdminLayout.tsx b/frontend/src/layouts/AdminLayout.tsx
index 943b0d1..f0ea862 100644
--- a/frontend/src/layouts/AdminLayout.tsx
+++ b/frontend/src/layouts/AdminLayout.tsx
@@ -1,7 +1,16 @@
+import { Suspense } from 'react';
 import { Outlet, useNavigate, useLocation } from 'react-router-dom';
 import { useAuthStore } from '../store/authStore';
 import { logout } from '../api/auth';
-import { message } from 'antd';
+import { message, Spin } from 'antd';
+
+function ContentFallback() {
+  return (
+    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 'calc(100vh - 110px)' }}>
+      <Spin />
+      </div>
+  );
+}
 
 type NavLink  = { path: string; label: string };
 type NavGroup = { title: string; items: NavLink[] };
@@ -18,6 +27,14 @@ const GROUPS: NavGroup[] = [
       { path: '/admin/outputs',   label: '产出记录' },
     ],
   },
+  {
+    title: '评测配置',
+    items: [
+      { path: '/admin/evaluation/dimensions', label: '维度与评分标准' },
+      { path: '/admin/evaluation/versions',   label: '版本快照' },
+      { path: '/admin/evaluation/schedules',  label: '定时策略' },
+    ],
+  },
   {
     title: '系统管理',
     items: [
@@ -94,7 +111,9 @@ export default function AdminLayout() {
           </div>
         </div>
         <div className="main-body">
-          <Outlet />
+          <Suspense fallback={<ContentFallback />}>
+            <Outlet />
+          </Suspense>
         </div>
       </div>
     </div>
diff --git a/frontend/src/layouts/OperatorLayout.tsx b/frontend/src/layouts/OperatorLayout.tsx
index 31853e3..8be5cc2 100644
--- a/frontend/src/layouts/OperatorLayout.tsx
+++ b/frontend/src/layouts/OperatorLayout.tsx
@@ -1,14 +1,27 @@
+import { Suspense } from 'react';
 import { Outlet, useNavigate, useLocation } from 'react-router-dom';
 import { useAuthStore } from '../store/authStore';
 import { logout } from '../api/auth';
-import { message } from 'antd';
+import { message, Spin } from 'antd';
 
-const MENU = [
+function ContentFallback() {
+  return (
+    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 'calc(100vh - 110px)' }}>
+      <Spin />
+    </div>
+  );
+}
+
+const MENU: { path: string; label: string; icon: string; adminOnly?: boolean }[] = [
   { path: '/',          label: '概览',     icon: '⊞' },
   { path: '/workspace', label: 'AI工具箱', icon: '✦' },
   { path: '/kol-hub',   label: '红人工作台', icon: '★' },
   { path: '/tasks',     label: '任务中心', icon: '☑' },
   { path: '/outputs',   label: '产出中心', icon: '⬇' },
+  // AIGC 评测（一期：千川仿写文案工具回归评测）—— 仅管理员可见
+  { path: '/evaluation/test-cases', label: '测试集',   icon: '⚑', adminOnly: true },
+  { path: '/evaluation/runs',       label: '运行管理', icon: '▶', adminOnly: true },
+  { path: '/evaluation/compare',    label: '版本对比', icon: '⇄', adminOnly: true },
 ];
 
 export default function OperatorLayout() {
@@ -16,8 +29,10 @@ export default function OperatorLayout() {
   const { pathname } = useLocation();
   const { user, clearAuth } = useAuthStore();
   const displayName = user?.real_name || user?.username || 'U';
-  const currentLabel = MENU.find(n => n.path === pathname)?.label
-    ?? MENU.slice().reverse().find(n => pathname.startsWith(n.path))?.label
+  // 仅管理员能看到评测入口（评测一期限定管理员）
+  const items = MENU.filter(n => !n.adminOnly || user?.role === 'admin');
+  const currentLabel = items.find(n => n.path === pathname)?.label
+    ?? items.slice().reverse().find(n => pathname.startsWith(n.path))?.label
     ?? '页面';
 
   async function handleLogout() {
@@ -36,7 +51,7 @@ export default function OperatorLayout() {
         </div>
         <nav className="sidebar-nav">
           <div className="nav-group">
-            {MENU.map(n => (
+            {items.map(n => (
               <div
                 key={n.path}
                 className={pathname === n.path ? 'nav-item active' : 'nav-item'}
@@ -68,7 +83,9 @@ export default function OperatorLayout() {
           </div>
         </div>
         <div className="main-body">
-          <Outlet />
+          <Suspense fallback={<ContentFallback />}>
+            <Outlet />
+          </Suspense>
         </div>
       </div>
     </div>
diff --git a/frontend/src/test/setup.ts b/frontend/src/test/setup.ts
index a2d2a83..a5376a4 100644
--- a/frontend/src/test/setup.ts
+++ b/frontend/src/test/setup.ts
@@ -14,3 +14,27 @@ Object.defineProperty(window, 'matchMedia', {
     dispatchEvent: () => false,
   }),
 });
+
+// jsdom localStorage 兜底：某些环境下未注入 localStorage 全局对象
+const __lsStore = new Map<string, string>();
+const localStorageMock: Storage = {
+  get length() {
+    return __lsStore.size;
+  },
+  clear: () => __lsStore.clear(),
+  getItem: (k: string) => __lsStore.get(k) ?? null,
+  key: (i: number) => Array.from(__lsStore.keys())[i] ?? null,
+  removeItem: (k: string) => {
+    __lsStore.delete(k);
+  },
+  setItem: (k: string, v: string) => {
+    __lsStore.set(k, String(v));
+  },
+};
+if (typeof globalThis.localStorage === 'undefined' || !globalThis.localStorage?.setItem) {
+  Object.defineProperty(globalThis, 'localStorage', {
+    value: localStorageMock,
+    configurable: true,
+    writable: true,
+  });
+}
diff --git a/frontend/vite.config.ts b/frontend/vite.config.ts
index 6e66a5f..e75e471 100644
--- a/frontend/vite.config.ts
+++ b/frontend/vite.config.ts
@@ -8,6 +8,8 @@ export default defineConfig({
     // 固定 5175（5173/5174 历史被旧项目占用；与 playwright.config.ts webServer.url 一致）
     port: 5175,
     strictPort: true, // 端口被占则直接报错（避免静默切换到 5176 导致 E2E 探活失败）
+    host: true, // 暴露到 LAN/Tailscale（等价 --host；npm run dev 不带参也能被其它主机访问）
+    allowedHosts: true, // 放开 Host 头校验：允许经 LAN IP / Tailscale 域名等非 localhost 形式访问（dev-only）
     proxy: {
       '/api': 'http://127.0.0.1:8010',
     },
```

> 新增文件（~80 个，全部在 `app/evaluation/` / `src/evaluation/` / `backend/migrations/` / `backend/tests/` 下）为纯新增模块，无存量改动风险，不在此附录展开；如需查看完整新增清单见 §3。
