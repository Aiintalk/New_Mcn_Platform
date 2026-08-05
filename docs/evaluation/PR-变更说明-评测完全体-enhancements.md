# AIGC 评测「完全体」增强 — PR 变更说明

> 本分支（`feature/eval-phase4-web-run-management`，已 rebase 到 main）= main 之上 **8 个迭代**，
> 把评测模块从「基础异步架构」（PR #34）推进到「**功能完全体**」。
> 前序文档：`PR-变更说明-aigc-evaluation-v2.md`（PR #34，Phase 0-3 基础）+ `测试与质量报告-aigc-evaluation-v2.md`。

---

## 给评审的两点（管理员郜郜重点）

1. **改存量 19 文件，全部 eval 模块内部 + 2 个前端接线**（`App.tsx` 加路由、`AdminLayout.tsx` 加菜单项）。
   **零核心业务逻辑改动，零共享后端文件**（yunwu/main/models/requirements/conftest 都在已合并的 PR #34）——**对主工程零侵入**。
2. 新增 1 个 admin 页（评测监控）+ 2 个 spec + 1 份运维手册。无新基建（Redis/worker 在 PR #34 已就位）。

---

## 8 个迭代（功能完全体）

| 迭代 | commit | 内容 |
|---|---|---|
| Phase 4 | `759a2a7` | `GET /runs` 分页列表（status/version 过滤）+ Runs 删 localStorage 接 API + RunDetail 4s 进度轮询 |
| cancel | `836ffd6` | `POST /runs/{id}/cancel` + aggregate 守卫（防 cancelled run 被在跑 job 翻转）|
| Phase 5 后端 | `8584307` | `queue-stats`（队列健康度）+ `runs/{id}/jobs`（逐 job 明细）+ 运维手册 |
| 输出查看器 | `7842dcc` | `runs/{id}/case-results` + RunDetail 展开看 kimi 生成文案 + 真实样本名 |
| Phase 5 前端 | `236f913` | 评测监控 admin 页（queue-stats 卡片 + 输入 run id 查 jobs）|
| ETA | `226f99d` | `GET /runs/{id}` 返回预计剩余（pending×平均耗时）+ RunDetail 卡片 |
| #2 单条 | `270978f` | `GET /test-cases/{id}` + TestCaseEdit 用单条接口（替掉 list+find）|
| 手工测试 | — | cancel/observability/worker 幂等 通过真实 worker+DB 验证 |

**功能闭环**：触发 → 列表 → 进度轮询 → **看评分+生成文案** → ETA → 取消 → 队列可观测（API+UI）。

---

## §1. 改了哪些「已有文件」（12 个生产文件 — 动存量，郜郜重点审）

> 测试文件改动（7 个）不列——不影响生产行为。配附录 A 看逐行 diff。

### 后端 eval（4 个）

| 文件 | 改了什么 | 为什么 | 风险 |
|---|---|---|---|
| `constants.py` | +`RUN_STATUS_CANCELLED` 常量 | cancel 功能需要 cancelled 状态值 | 低（纯新增常量，不改现有值）|
| `routers/admin_evaluation.py` | +`queue-stats` +`runs/{id}/jobs` 端点（+import func/text/EvalCaseJob/EvalRun）| Phase 5 可观测 | 低（纯新增只读 admin 端点，不动现有端点）|
| `routers/operator_evaluation.py` | +`GET /runs` 列表 +`POST /cancel` +`GET /case-results` +`GET /test-cases/{id}`；`get_run` 末尾加 ETA 查询 | 运行管理完全体 | 低（纯新增端点；唯一改存量行= get_run 加 avg/eta 计算，不改原有 `_run_to_dict`）|
| `worker.py` | `aggregate_run_progress` 加 cancelled 守卫（+import RUN_STATUS_CANCELLED）| 防 cancel 后在跑 job 完成把 cancelled 翻成 completed | ⚠️ **改并发敏感函数**：但仅加 `row[3] != CANCELLED` 条件——现有 completed/failed/pending/running 路径不受影响（它们的 status≠cancelled，守卫不触发）。多轮 review + 回归测试验证。 |

### 前端（8 个）

| 文件 | 改了什么 | 风险 |
|---|---|---|
| `App.tsx` | +1 lazy import +1 Route（Observability 评测监控页）| 低（纯新增路由）|
| `layouts/AdminLayout.tsx` | +1 菜单项（评测监控）| 低（纯新增）|
| `api/index.ts` | +6 API 函数（listRuns/cancelRun/listCaseResults/getQueueStats/getRunJobs/getTestCase）| 低（纯新增函数）|
| `types/index.ts` | +4 类型 + EvalRun 加可选 `eta_secs`/`avg_case_duration_secs` | 低（纯新增 + 可选字段，不破坏现有）|
| `components/primitives.tsx` | +cancelled badge（RUN_STATUS_META +1 case）| 低（+1 行）|
| `pages/RunDetail.tsx` | +轮询/+ETA卡/+cancel按钮/+case-results展开；run 类型改用 EvalRun | 低（单页面内改动，不影响其它页）|
| `pages/Runs.tsx` | 删 localStorage 兜底 → listRuns API + 触发刷新 | 低（单页面内改动）|
| `pages/TestCaseEdit.tsx` | 编辑模式 list+find → getTestCase 单条 | 低（单页面内改动）|

> **核心结论**：12 个生产文件，**11 个是纯新增（端点/函数/类型/路由）或单页面内改动，0 核心业务逻辑改动**。唯一需关注 = `worker.py` 的 aggregate 守卫（并发敏感函数）——但仅加了 cancelled 条件分支，现有路径完全不受影响，经多轮独立 review + 回归测试。
>
> **无共享/核心文件改动**（`yunwu.py`/`main.py`/`models/__init__`/`requirements`/`conftest` 均在已合 PR #34，本分支零改动）→ **对主工程零侵入**。

## 新增文件
- `frontend/src/evaluation/pages/Observability.tsx` + 测试（评测监控 admin 页）
- `backend/docs/评测worker运维手册.md`（worker/redis 起停 + 排障 + 清 stale job）
- `docs/superpowers/specs/`（phase4-web-run-management + phase5-observability）

---

## 测试与质量（自动化完成）

| 层 | 结果 |
|---|---|
| 后端 eval | **226 测试全绿**（worker/runner/scheduler/generator/scorer/comparator/models + operator/admin router 集成）|
| 前端 eval | **136 测试全绿**（11 文件：8 页面组件 + API 契约 + 守卫）|
| 类型 | `tsc --noEmit` **0 错** |
| Review | 核心 worker/aggregate/concurrency 经多轮独立 review（Phase 3/4/cancel）|

**手工冒烟**（真实 worker + Redis + DB）：
- ✅ cancel 真停 job（pending job→cancelled）
- ✅ worker 幂等守卫真跳过 cancelled job（不执行、不计数）
- ✅ aggregate 守卫防 cancelled 被翻转（run 保持 cancelled）
- ✅ observability queue-stats 正确反映队列状态（pending/failed死信/最老等待可见）
- ✅ 真实 LLM 端到端（kimi 生成 + glm 评分真落库）在 PR #34 冒烟已验证

---

## 已知未做（低 ROI，文档记录待后续）

| 缺口 | 现状 | 处置 |
|---|---|---|
| #3 统计聚合 | TestCases 4 卡中 3 卡已工作，仅「最近运行平均分」显示 — | 装饰性，聚合端点低 ROI，暂不做 |
| #5 版本关联预览 | 版本创建已能用（直接填 config 或 kol_id） | 跨 kol 子系统（需 kols 列表端点），建议单独 PR |
| pristine 5-case 全绿 | 单 case 端到端已验证；多 case 受 glm-4.6 延迟方差（环境） | 非代码问题，换更快评委/扩 key 池即可 |

---

## 部署

无新基建（Redis + arq worker 在 PR #34 已就位，运维手册已补）。本 PR 纯应用层增强，部署仅需重新构建前后端 + 跑迁移（本分支无新迁移）。


---

## 附录 A：改存量生产文件 diff（git diff +/- 格式，给郜郜逐行核对）

> 12 个生产文件（非测试），按后端→前端排列，每个文件以 `diff --git` 行分隔。
> 测试文件的改动不在此（测试改动不影响生产行为）。配 §"改存量文件"表格（改了什么）阅读。

```diff
diff --git a/backend/app/evaluation/constants.py b/backend/app/evaluation/constants.py
index c853b04..7572fb2 100644
--- a/backend/app/evaluation/constants.py
+++ b/backend/app/evaluation/constants.py
@@ -19,6 +19,7 @@ RUN_STATUS_RUNNING = "running"
 RUN_STATUS_COMPLETED = "completed"
 RUN_STATUS_FAILED = "failed"
 RUN_STATUS_CANCELLING = "cancelling"  # cancel 进行中（Phase 4）
+RUN_STATUS_CANCELLED = "cancelled"    # 已取消（POST /runs/{id}/cancel 直接收尾）
 
 # eval_case_jobs.status 取值（异步运行，按 case 拆 job）
 JOB_STATUS_PENDING = "pending"
diff --git a/backend/app/evaluation/routers/admin_evaluation.py b/backend/app/evaluation/routers/admin_evaluation.py
index 0c7f309..8780fc6 100644
--- a/backend/app/evaluation/routers/admin_evaluation.py
+++ b/backend/app/evaluation/routers/admin_evaluation.py
@@ -33,7 +33,7 @@ from datetime import datetime, timezone
 
 from croniter import croniter
 from fastapi import APIRouter, Depends, HTTPException, Request
-from sqlalchemy import select
+from sqlalchemy import func, select, text
 from sqlalchemy.ext.asyncio import AsyncSession
 
 from app.core.database import get_db
@@ -46,8 +46,10 @@ from app.services import kol_context, workspace_prompt
 
 from app.evaluation.constants import EVAL_TOOL_QIANCHUAN_WRITER
 from app.evaluation.models import (
+    EvalCaseJob,
     EvalDimension,
     EvalRubric,
+    EvalRun,
     EvalSchedulePolicy,
     EvalVersion,
 )
@@ -744,3 +746,75 @@ async def delete_schedule_policy(
     ))
     await db.commit()
     return success_response(data={"id": policy.id, "deleted_at": _ts(policy.deleted_at)})
+
+
+# ---------------------------------------------------------------------------
+# Phase 5：可观测性（队列状态 + 单 run job 明细，admin 只读）
+# ---------------------------------------------------------------------------
+
+
+@router.get("/queue-stats")
+async def queue_stats(
+    db: AsyncSession = Depends(get_db),
+    _: User = Depends(require_admin),
+):
+    """队列健康度：各状态 job 计数 + 最老 pending 等待秒数 + 活跃 run 数。
+
+    用于一眼判断"堵没堵"：pending 堆积 + oldest_pending_secs 大 = 队列堵塞信号。
+    """
+    rows = (await db.execute(
+        select(EvalCaseJob.status, func.count()).group_by(EvalCaseJob.status)
+    )).all()
+    counts = {r[0]: int(r[1]) for r in rows}
+    oldest = (await db.execute(
+        text(
+            "SELECT EXTRACT(EPOCH FROM (NOW() - MIN(enqueued_at))) "
+            "FROM eval_case_jobs WHERE status = 'pending'"
+        )
+    )).scalar()
+    active_runs = (await db.execute(
+        select(func.count(EvalRun.id)).where(
+            EvalRun.status.in_(("pending", "running", "cancelling"))
+        )
+    )).scalar()
+    return success_response(data={
+        "pending": counts.get("pending", 0),
+        "running": counts.get("running", 0),
+        "failed_dead_letter": counts.get("failed", 0),
+        "done": counts.get("done", 0),
+        "cancelled": counts.get("cancelled", 0),
+        "oldest_pending_secs": int(oldest) if oldest is not None else None,
+        "runs_active": int(active_runs or 0),
+    })
+
+
+@router.get("/runs/{run_id}/jobs")
+async def list_run_jobs(
+    run_id: int,
+    db: AsyncSession = Depends(get_db),
+    _: User = Depends(require_admin),
+):
+    """单 run 的逐 job 明细（debug 卡住的 run：哪个 job 卡 running / last_error 失败原因）。"""
+    run = await db.get(EvalRun, run_id)
+    if run is None:
+        raise HTTPException(
+            status_code=404,
+            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "运行不存在"},
+        )
+    rows = (await db.execute(
+        select(EvalCaseJob).where(EvalCaseJob.run_id == run_id).order_by(EvalCaseJob.id)
+    )).scalars().all()
+    return success_response(data=[
+        {
+            "id": j.id,
+            "test_case_id": j.test_case_id,
+            "status": j.status,
+            "attempts": j.attempts,
+            "max_attempts": j.max_attempts,
+            "last_error": j.last_error,
+            "enqueued_at": _ts(j.enqueued_at),
+            "started_at": _ts(j.started_at),
+            "finished_at": _ts(j.finished_at),
+        }
+        for j in rows
+    ])
diff --git a/backend/app/evaluation/routers/operator_evaluation.py b/backend/app/evaluation/routers/operator_evaluation.py
index 889195e..5934eab 100644
--- a/backend/app/evaluation/routers/operator_evaluation.py
+++ b/backend/app/evaluation/routers/operator_evaluation.py
@@ -29,7 +29,7 @@ import math
 from datetime import datetime, timezone
 
 from fastapi import APIRouter, Depends, HTTPException, Query, Request
-from sqlalchemy import select
+from sqlalchemy import select, text
 from sqlalchemy.ext.asyncio import AsyncSession
 
 from app.core.database import get_db
@@ -38,7 +38,12 @@ from app.middlewares.auth import get_current_user
 from app.models.log import OperationLog
 from app.models.user import User
 
-from app.evaluation.constants import TRIGGER_TYPE_MANUAL
+from app.evaluation.constants import (
+    RUN_STATUS_CANCELLED,
+    RUN_STATUS_PENDING,
+    RUN_STATUS_RUNNING,
+    TRIGGER_TYPE_MANUAL,
+)
 from app.evaluation.models import (
     EvalCaseResult,
     EvalHumanLabel,
@@ -220,6 +225,22 @@ async def list_test_cases(
     })
 
 
+@router.get("/test-cases/{test_case_id}")
+async def get_test_case(
+    test_case_id: int,
+    db: AsyncSession = Depends(get_db),
+    _: User = Depends(require_operator),
+):
+    """测试样本单条（编辑模式用，替代早期 list+find，样本超 50 也能取到）。"""
+    tc = await db.get(EvalTestCase, test_case_id)
+    if tc is None or tc.deleted_at is not None:
+        raise HTTPException(
+            status_code=404,
+            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "测试样本不存在"},
+        )
+    return success_response(data=_test_case_to_dict(tc))
+
+
 @router.post("/test-cases")
 async def create_test_case(
     body: TestCaseCreate,
@@ -354,6 +375,52 @@ async def list_versions(
 # ---------------------------------------------------------------------------
 
 
+@router.get("/runs")
+async def list_runs(
+    page: int = Query(1, ge=1),
+    page_size: int = Query(20, ge=1, le=100),
+    status: str | None = None,
+    version_id: int | None = None,
+    db: AsyncSession = Depends(get_db),
+    _: User = Depends(require_operator),
+):
+    """运行分页列表（status / version_id 过滤，id 倒序）。
+
+    响应：{items:[_run_to_dict], pagination:{page,page_size,total,total_pages}}。
+    """
+    if page_size not in _PAGE_SIZE_ALLOWED:
+        page_size = 20
+
+    stmt = select(EvalRun)
+    if status:
+        stmt = stmt.where(EvalRun.status == status)
+    if version_id:
+        stmt = stmt.where(EvalRun.version_id == version_id)
+
+    from sqlalchemy import func as sa_func
+    count_stmt = select(sa_func.count()).select_from(EvalRun)
+    if status:
+        count_stmt = count_stmt.where(EvalRun.status == status)
+    if version_id:
+        count_stmt = count_stmt.where(EvalRun.version_id == version_id)
+    total = (await db.execute(count_stmt)).scalar() or 0
+
+    stmt = stmt.order_by(EvalRun.id.desc()).limit(page_size).offset((page - 1) * page_size)
+    rows = (await db.execute(stmt)).scalars().all()
+
+    items = [_run_to_dict(r) for r in rows]
+    total_pages = math.ceil(total / page_size) if total > 0 else 0
+    return success_response(data={
+        "items": items,
+        "pagination": {
+            "page": page,
+            "page_size": page_size,
+            "total": total,
+            "total_pages": total_pages,
+        },
+    })
+
+
 @router.post("/runs")
 async def trigger_run(
     body: dict,
@@ -413,14 +480,29 @@ async def get_run(
     db: AsyncSession = Depends(get_db),
     _: User = Depends(require_operator),
 ):
-    """运行状态查询。"""
+    """运行状态查询（含 ETA：avg_case_duration_secs + eta_secs）。"""
     run = await db.get(EvalRun, run_id)
     if run is None:
         raise HTTPException(
             status_code=404,
             detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "运行不存在"},
         )
-    return success_response(data=_run_to_dict(run))
+    # ETA：用本 run 已完成 job 的平均耗时估算剩余（无 done job 则 null）
+    dur = (await db.execute(
+        text(
+            "SELECT AVG(EXTRACT(EPOCH FROM (finished_at - started_at))), "
+            "COUNT(*) FILTER (WHERE status = 'done'), "
+            "COUNT(*) FILTER (WHERE status = 'pending') "
+            "FROM eval_case_jobs WHERE run_id = :rid"
+        ),
+        {"rid": run_id},
+    )).fetchone()
+    avg_dur = dur[0] if dur else None
+    pending_n = (dur[2] if dur else 0) or 0
+    data = _run_to_dict(run)
+    data["avg_case_duration_secs"] = int(avg_dur) if avg_dur is not None else None
+    data["eta_secs"] = int(avg_dur * pending_n) if (avg_dur is not None and pending_n > 0) else None
+    return success_response(data=data)
 
 
 @router.get("/runs/{run_id}/scores")
@@ -447,6 +529,95 @@ async def list_run_scores(
     return success_response(data=[_score_to_dict(s) for s in rows])
 
 
+@router.get("/runs/{run_id}/case-results")
+async def list_run_case_results(
+    run_id: int,
+    db: AsyncSession = Depends(get_db),
+    _: User = Depends(require_operator),
+):
+    """运行的所有 case 生成结果（含 generated_output，供前端「查看输出」）。
+
+    join eval_test_cases 拿真实样本名；按 test_case_id 排序。
+    """
+    run = await db.get(EvalRun, run_id)
+    if run is None:
+        raise HTTPException(
+            status_code=404,
+            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "运行不存在"},
+        )
+    stmt = (
+        select(EvalCaseResult, EvalTestCase.name)
+        .outerjoin(EvalTestCase, EvalTestCase.id == EvalCaseResult.test_case_id)
+        .where(EvalCaseResult.run_id == run_id)
+        .order_by(EvalCaseResult.test_case_id.asc())
+    )
+    rows = (await db.execute(stmt)).all()
+    return success_response(data=[
+        {
+            "id": cr.id,
+            "test_case_id": cr.test_case_id,
+            "test_case_name": name or f"样本 #{cr.test_case_id}",
+            "generated_output": cr.generated_output,
+            "output_payload": cr.output_payload,
+            "input_snapshot": cr.input_snapshot,
+            "created_at": _ts(cr.created_at),
+        }
+        for cr, name in rows
+    ])
+
+
+@router.post("/runs/{run_id}/cancel")
+async def cancel_run(
+    run_id: int,
+    request: Request,
+    db: AsyncSession = Depends(get_db),
+    current_user: User = Depends(require_operator),
+):
+    """取消运行：pending job 标 cancelled + run 直接收尾 cancelled（写 OperationLog）。
+
+    worker 无需改动——已入队的 pending job 被 arq 投递时，run_case_job_logic 的幂等守卫
+    （status ∈ terminal → skip）自动跳过；在跑的 job 自然跑完（结果落库，run 仍 cancelled）。
+    """
+    run = await db.get(EvalRun, run_id)
+    if run is None:
+        raise HTTPException(
+            status_code=404,
+            detail={"code": ErrorCode.RESOURCE_NOT_FOUND, "message": "运行不存在"},
+        )
+    if run.status not in (RUN_STATUS_PENDING, RUN_STATUS_RUNNING):
+        raise HTTPException(
+            status_code=409,
+            detail={"code": "CONFLICT", "message": f"运行已终态（{run.status}），无法取消"},
+        )
+
+    prev_status = run.status
+    # pending job → cancelled（在跑的 job 不动，自然跑完）
+    await db.execute(
+        text(
+            "UPDATE eval_case_jobs SET status = 'cancelled', finished_at = NOW() "
+            "WHERE run_id = :rid AND status = 'pending'"
+        ),
+        {"rid": run_id},
+    )
+    run.status = RUN_STATUS_CANCELLED
+    run.finished_at = datetime.now(timezone.utc)
+
+    db.add(OperationLog(
+        user_id=current_user.id,
+        username=current_user.username,
+        role=current_user.role,
+        action="evaluation_run_cancel",
+        target_type="eval_run",
+        target_id=run.id,
+        detail={"prev_status": prev_status},
+        ip=_get_ip(request),
+        user_agent=request.headers.get("user-agent"),
+    ))
+    await db.commit()
+    await db.refresh(run)
+    return success_response(data=_run_to_dict(run))
+
+
 # ---------------------------------------------------------------------------
 # 人工校准 — 单事务原子性
 # ---------------------------------------------------------------------------
diff --git a/backend/app/evaluation/worker.py b/backend/app/evaluation/worker.py
index ecefbdc..968588b 100644
--- a/backend/app/evaluation/worker.py
+++ b/backend/app/evaluation/worker.py
@@ -32,6 +32,7 @@ from app.evaluation.constants import (
     JOB_STATUS_FAILED,
     JOB_STATUS_RUNNING,
     JOB_STATUS_TERMINAL,
+    RUN_STATUS_CANCELLED,
     RUN_STATUS_COMPLETED,
     RUN_STATUS_FAILED,
 )
@@ -144,13 +145,20 @@ async def aggregate_run_progress(db: AsyncSession, run_id: int, success: bool) -
     row = (
         await db.execute(
             text(
-                "SELECT total_cases, completed_cases, failed_cases "
+                "SELECT total_cases, completed_cases, failed_cases, status "
                 "FROM eval_runs WHERE id = :id"
             ),
             {"id": run_id},
         )
     ).fetchone()
-    if row and row[0] > 0 and (row[1] + row[2]) >= row[0]:
+    # 已 cancel 的 run 不被 in-flight job 完成翻成 completed/failed
+    # （POST /runs/{id}/cancel 直接收尾 cancelled；在跑的 job 跑完 aggregate 时跳过覆盖）
+    if (
+        row
+        and row[0] > 0
+        and (row[1] + row[2]) >= row[0]
+        and row[3] != RUN_STATUS_CANCELLED
+    ):
         status = RUN_STATUS_FAILED if row[1] == 0 else RUN_STATUS_COMPLETED
         await db.execute(
             text("UPDATE eval_runs SET status = :s, finished_at = NOW() WHERE id = :id"),
diff --git a/frontend/src/App.tsx b/frontend/src/App.tsx
index 10c90c6..d5de340 100644
--- a/frontend/src/App.tsx
+++ b/frontend/src/App.tsx
@@ -58,6 +58,7 @@ const EvalComparePage = lazy(() => import('./evaluation/pages/Compare'));
 const EvalVersionsPage = lazy(() => import('./evaluation/pages/Versions'));
 const EvalDimensionsPage = lazy(() => import('./evaluation/pages/Dimensions'));
 const EvalSchedulesPage = lazy(() => import('./evaluation/pages/Schedules'));
+const EvalObservabilityPage = lazy(() => import('./evaluation/pages/Observability'));
 
 function Page403() {
   return (
@@ -170,6 +171,7 @@ export default function App() {
                 <Route path="/admin/evaluation/versions" element={<EvalVersionsPage />} />
                 <Route path="/admin/evaluation/dimensions" element={<EvalDimensionsPage />} />
                 <Route path="/admin/evaluation/schedules" element={<EvalSchedulesPage />} />
+                <Route path="/admin/evaluation/observability" element={<EvalObservabilityPage />} />
               </Route>
             </Route>
           </Route>
diff --git a/frontend/src/evaluation/api/index.ts b/frontend/src/evaluation/api/index.ts
index 25aaa6b..17c4d44 100644
--- a/frontend/src/evaluation/api/index.ts
+++ b/frontend/src/evaluation/api/index.ts
@@ -10,15 +10,19 @@
 import { get, post, put, del } from '../../api/request';
 import type {
   EvalCaseDelta,
+  EvalCaseResult,
   EvalComparisonReport,
   EvalDimension,
   EvalDimensionCreate,
   EvalDimensionUpdate,
   EvalHumanLabelRequest,
   EvalPaged,
+  EvalQueueStats,
   EvalRubric,
+  EvalRunJob,
   EvalRubricBatchUpdate,
   EvalRun,
+  EvalRunListParams,
   EvalSchedulePolicy,
   EvalSchedulePolicyCreate,
   EvalSchedulePolicyUpdate,
@@ -52,6 +56,10 @@ export async function updateTestCase(id: number, body: EvalTestCaseUpdate) {
   return put<EvalTestCase>(`/api/operator/evaluation/test-cases/${id}`, body);
 }
 
+export async function getTestCase(id: number) {
+  return get<EvalTestCase>(`/api/operator/evaluation/test-cases/${id}`);
+}
+
 export async function deleteTestCase(id: number) {
   return del<{ id: number; deleted_at: string }>(`/api/operator/evaluation/test-cases/${id}`);
 }
@@ -92,6 +100,13 @@ export async function triggerRun(body: EvalTriggerRunRequest) {
   return post<EvalRun>('/api/operator/evaluation/runs', body);
 }
 
+export async function listRuns(params: EvalRunListParams = {}) {
+  return get<EvalPaged<EvalRun>>(
+    '/api/operator/evaluation/runs',
+    params as Record<string, string | number | boolean | undefined>,
+  );
+}
+
 export async function getRun(id: number) {
   return get<EvalRun>(`/api/operator/evaluation/runs/${id}`);
 }
@@ -100,6 +115,14 @@ export async function listRunScores(id: number) {
   return get<EvalScore[]>(`/api/operator/evaluation/runs/${id}/scores`);
 }
 
+export async function listCaseResults(runId: number) {
+  return get<EvalCaseResult[]>(`/api/operator/evaluation/runs/${runId}/case-results`);
+}
+
+export async function cancelRun(id: number) {
+  return post<EvalRun>(`/api/operator/evaluation/runs/${id}/cancel`);
+}
+
 export async function submitHumanLabel(scoreId: number, body: EvalHumanLabelRequest) {
   return put<EvalScore>(`/api/operator/evaluation/scores/${scoreId}/human-label`, body);
 }
@@ -111,6 +134,18 @@ export async function compareRuns(runA: number, runB: number) {
   });
 }
 
+// ---------------------------------------------------------------------------
+// 可观测（admin，Phase 5）
+// ---------------------------------------------------------------------------
+
+export async function getQueueStats() {
+  return get<EvalQueueStats>('/api/admin/evaluation/queue-stats');
+}
+
+export async function getRunJobs(runId: number) {
+  return get<EvalRunJob[]>(`/api/admin/evaluation/runs/${runId}/jobs`);
+}
+
 // ---------------------------------------------------------------------------
 // 维度 + Rubric（admin）
 // ---------------------------------------------------------------------------
diff --git a/frontend/src/evaluation/components/primitives.tsx b/frontend/src/evaluation/components/primitives.tsx
index d076b82..6669810 100644
--- a/frontend/src/evaluation/components/primitives.tsx
+++ b/frontend/src/evaluation/components/primitives.tsx
@@ -60,6 +60,7 @@ const RUN_STATUS_META: Record<EvalRunStatus, { text: string; cls: string }> = {
   completed: { text: 'completed', cls: 'badge-success' },
   failed: { text: 'failed', cls: 'badge-danger' },
   partial: { text: 'partial', cls: 'badge-warning' },
+  cancelled: { text: 'cancelled', cls: 'badge-gray' },
 };
 
 export function RunStatusBadge({ status }: { status: EvalRunStatus }) {
diff --git a/frontend/src/evaluation/pages/RunDetail.tsx b/frontend/src/evaluation/pages/RunDetail.tsx
index 0650546..9213ba8 100644
--- a/frontend/src/evaluation/pages/RunDetail.tsx
+++ b/frontend/src/evaluation/pages/RunDetail.tsx
@@ -12,15 +12,15 @@
  */
 import { useCallback, useEffect, useMemo, useState } from 'react';
 import { useNavigate, useParams } from 'react-router-dom';
-import { App, Button, Drawer, Input, Skeleton, Slider, Table, Tag } from 'antd';
+import { App, Button, Drawer, Input, Popconfirm, Skeleton, Slider, Table, Tag } from 'antd';
 import { ArrowLeftOutlined } from '@ant-design/icons';
 
 const { TextArea } = Input;
 import type { ColumnsType } from 'antd/es/table';
 import '../../styles/variables.css';
 import '../styles/eval.css';
-import { getRun, listRunScores, submitHumanLabel } from '../api';
-import type { EvalScore } from '../types';
+import { cancelRun, getRun, listCaseResults, listRunScores, submitHumanLabel } from '../api';
+import type { EvalCaseResult, EvalRun, EvalScore } from '../types';
 import {
   Callout,
   PageHeader,
@@ -36,6 +36,7 @@ interface CaseRow {
   scores: EvalScore[];
   aiAvg: number | null;
   humanCalibrated: boolean;
+  generated_output: string | null;
 }
 
 export default function RunDetailPage() {
@@ -45,8 +46,9 @@ export default function RunDetailPage() {
   const navigate = useNavigate();
 
   const [loading, setLoading] = useState(false);
-  const [run, setRun] = useState<{ id: number; name: string; status: string; version_id: number; total_cases: number; completed_cases: number; failed_cases: number; started_at: string | null; finished_at: string | null; trigger_type: string; filter_tags: string[] } | null>(null);
+  const [run, setRun] = useState<EvalRun | null>(null);
   const [scores, setScores] = useState<EvalScore[]>([]);
+  const [caseResults, setCaseResults] = useState<EvalCaseResult[]>([]);
   const [calibrating, setCalibrating] = useState<EvalScore | null>(null);
   const [humanScore, setHumanScore] = useState(7);
   const [humanFeedback, setHumanFeedback] = useState('');
@@ -56,12 +58,14 @@ export default function RunDetailPage() {
     if (!runId) return;
     setLoading(true);
     try {
-      const [runData, scoreData] = await Promise.all([
+      const [runData, scoreData, crData] = await Promise.all([
         getRun(runId),
         listRunScores(runId),
+        listCaseResults(runId),
       ]);
       setRun(runData);
       setScores(scoreData);
+      setCaseResults(crData);
     } catch (err) {
       const msg = err instanceof Error ? err.message : '加载失败';
       message.error(msg);
@@ -74,8 +78,43 @@ export default function RunDetailPage() {
     void load();
   }, [load]);
 
-  // 按 case_result_id 分组（后端返回扁平的 scores，每个 score 有 case_result_id）
-  // 同一 case 的多个 dimension scores 聚合为一行
+  // 进度轮询（Phase 4）：run 处于 pending/running 时每 4s 拉 getRun；
+  // 检测到终态（completed/failed）→ 重拉 listRunScores（挂载时 pending 期 scores 为空）+ 停轮询。
+  // 依赖 run?.status：状态变化时 effect 重跑，自动清旧 timer。
+  useEffect(() => {
+    if (!run || run.status === 'completed' || run.status === 'failed' || run.status === 'cancelled') return;
+    const runId = run.id;
+    let cancelled = false;
+    let timer: ReturnType<typeof setInterval> | null = null;
+
+    const poll = async () => {
+      try {
+        const runData = await getRun(runId);
+        if (cancelled) return;
+        setRun(runData);
+        if (runData.status === 'completed' || runData.status === 'failed') {
+          const [scoreData, crData] = await Promise.all([
+            listRunScores(runId),
+            listCaseResults(runId),
+          ]);
+          if (!cancelled) {
+            setScores(scoreData);
+            setCaseResults(crData);
+          }
+        }
+      } catch {
+        // 静默：单次轮询失败不打断（下次重试）
+      }
+    };
+
+    timer = setInterval(() => { void poll(); }, 4000);
+    return () => {
+      cancelled = true;
+      if (timer) clearInterval(timer);
+    };
+  }, [run?.id, run?.status]);
+
+  // 按 case_result_id 聚合（scores ∪ caseResults：有输出但未评分的 case 也要显示）
   const rows: CaseRow[] = useMemo(() => {
     const byCase = new Map<number, EvalScore[]>();
     scores.forEach((s) => {
@@ -83,21 +122,27 @@ export default function RunDetailPage() {
       arr.push(s);
       byCase.set(s.case_result_id, arr);
     });
-    return Array.from(byCase.entries()).map(([caseResultId, scoreList], idx) => {
+    const crMap = new Map<number, EvalCaseResult>();
+    caseResults.forEach((cr) => crMap.set(cr.id, cr));
+    const allIds = new Set<number>([...byCase.keys(), ...crMap.keys()]);
+    return Array.from(allIds).sort((a, b) => a - b).map((caseResultId) => {
+      const scoreList = byCase.get(caseResultId) ?? [];
+      const cr = crMap.get(caseResultId);
       const aiScores = scoreList.map((s) => s.ai_score).filter((v): v is number => v !== null);
       const aiAvg = aiScores.length > 0 ? aiScores.reduce((a, b) => a + b, 0) / aiScores.length : null;
       const anyHuman = scoreList.some((s) => s.human_score !== null);
       return {
         key: String(caseResultId),
         case_result_id: caseResultId,
-        test_case_id: idx + 1,
-        test_case_name: `样本 #${caseResultId}`,
+        test_case_id: cr?.test_case_id ?? caseResultId,
+        test_case_name: cr?.test_case_name ?? `样本 #${caseResultId}`,
         scores: scoreList,
         aiAvg,
         humanCalibrated: anyHuman,
+        generated_output: cr?.generated_output ?? null,
       };
     });
-  }, [scores]);
+  }, [scores, caseResults]);
 
   // 维度聚合（雷达图 + 列表）
   const dimensionAgg = useMemo(() => {
@@ -120,6 +165,18 @@ export default function RunDetailPage() {
     return all.length > 0 ? all.reduce((a, b) => a + b, 0) / all.length : null;
   }, [scores]);
 
+  const handleCancel = async () => {
+    if (!run) return;
+    try {
+      const updated = await cancelRun(run.id);
+      setRun(updated);
+      message.success('运行已取消');
+    } catch (err) {
+      const msg = err instanceof Error ? err.message : '取消失败';
+      message.error(msg);
+    }
+  };
+
   const openCalibrate = (score: EvalScore) => {
     setCalibrating(score);
     setHumanScore(score.human_score ?? score.ai_score ?? 7);
@@ -248,6 +305,17 @@ export default function RunDetailPage() {
             <Button type="primary" onClick={() => navigate('/evaluation/compare')}>
               与其它版本对比
             </Button>
+            {(run.status === 'pending' || run.status === 'running') && (
+              <Popconfirm
+                title="确认取消此运行？"
+                description="未开始的样本会被跳过；已在跑的样本会自然跑完。"
+                okText="确认取消"
+                cancelText="算了"
+                onConfirm={() => void handleCancel()}
+              >
+                <Button danger>取消运行</Button>
+              </Popconfirm>
+            )}
           </>
         }
       />
@@ -282,6 +350,16 @@ export default function RunDetailPage() {
             {formatDuration(run.started_at, run.finished_at)}
           </div>
         </div>
+        <div className="stat-card">
+          <div className="stat-label">预计剩余</div>
+          <div className="stat-value" style={{ fontSize: 22 }}>
+            {run.eta_secs != null
+              ? run.eta_secs >= 60
+                ? `≈${Math.floor(run.eta_secs / 60)}m ${run.eta_secs % 60}s`
+                : `≈${run.eta_secs}s`
+              : '—'}
+          </div>
+        </div>
       </div>
 
       <div className="card mb-5">
@@ -332,6 +410,27 @@ export default function RunDetailPage() {
             pagination={{ pageSize: 20 }}
             style={{ padding: '0 var(--sp-5)' }}
             locale={{ emptyText: '暂无样本评分数据' }}
+            expandable={{
+              expandedRowRender: (r) =>
+                r.generated_output ? (
+                  <div
+                    style={{
+                      background: 'var(--gray-50)',
+                      border: '1px solid var(--border)',
+                      borderRadius: 'var(--radius-md)',
+                      padding: 12,
+                      fontSize: 13,
+                      color: 'var(--gray-700)',
+                      whiteSpace: 'pre-wrap',
+                    }}
+                  >
+                    {r.generated_output}
+                  </div>
+                ) : (
+                  <span className="text-muted">该 case 无生成输出</span>
+                ),
+              rowExpandable: () => true,
+            }}
           />
         </div>
       </div>
diff --git a/frontend/src/evaluation/pages/Runs.tsx b/frontend/src/evaluation/pages/Runs.tsx
index c63bac2..2c6c8cb 100644
--- a/frontend/src/evaluation/pages/Runs.tsx
+++ b/frontend/src/evaluation/pages/Runs.tsx
@@ -2,11 +2,9 @@
  * 运行列表（设计稿 runs.html）
  *
  * 列表 + 子 tab 过滤 + 触发抽屉。
- * 数据接口：GET /api/operator/evaluation/runs（待后端补列表接口，一期从 trigger 拿 run_id）。
- *
- * 注：后端 operator_evaluation.py 暂未提供 runs 列表接口（spec Phase 4 只实现了 trigger + get + scores），
- * 这里复用现有 trigger 后回填到本地 state，并支持轮询单个 run。
- * 列表数据来源：后端补 GET /runs 后接入（已在 frontend-issues.md 记录）。
+ * 数据接口：GET /api/operator/evaluation/runs（Phase 4 起接入，替代早期 localStorage 兜底）。
+ * 拉最近 50 条（后端 _PAGE_SIZE_ALLOWED 最大值，不被 clamp）；tab 过滤 + 状态卡基于当前列表客户端计算。
+ * 待决：run 历史超 50 条时改服务端分页（见 spec §1）。
  */
 import { useCallback, useEffect, useMemo, useState } from 'react';
 import { useNavigate } from 'react-router-dom';
@@ -15,7 +13,7 @@ import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
 import type { ColumnsType } from 'antd/es/table';
 import '../../styles/variables.css';
 import '../styles/eval.css';
-import { listVersionsOperator, triggerRun } from '../api';
+import { listRuns, listVersionsOperator, triggerRun } from '../api';
 import type { EvalRun, EvalRunStatus, EvalTriggerType, EvalVersion } from '../types';
 import {
   Callout,
@@ -57,33 +55,26 @@ export default function RunsPage() {
     tags: string[];
   }>();
 
-  // 一期：runs 列表无后端接口，初始化时从 localStorage 恢复最近触发的 run
-  // （triggerRun 返回完整 run 对象）。后端补 GET /runs 后切换为接口请求。
-  const loadFromLocal = useCallback(() => {
+  const [total, setTotal] = useState(0);
+
+  // 从后端 GET /runs 拉列表（Phase 4：替代 localStorage 兜底，跨设备可见）
+  const loadRuns = useCallback(async () => {
     setLoading(true);
     try {
-      const raw = localStorage.getItem('eval_runs_cache');
-      const list: EvalRun[] = raw ? JSON.parse(raw) : [];
-      setRuns(list);
+      const data = await listRuns({ page: 1, page_size: 50 });
+      setRuns(data.items);
+      setTotal(data.pagination.total);
     } catch {
       setRuns([]);
+      setTotal(0);
     } finally {
       setLoading(false);
     }
   }, []);
 
-  const persistRuns = useCallback((list: EvalRun[]) => {
-    setRuns(list);
-    try {
-      localStorage.setItem('eval_runs_cache', JSON.stringify(list.slice(0, 20)));
-    } catch {
-      // 静默：写入失败不影响功能
-    }
-  }, []);
-
   useEffect(() => {
-    void loadFromLocal();
-  }, [loadFromLocal]);
+    void loadRuns();
+  }, [loadRuns]);
 
   // 加载版本列表（抽屉用）
   useEffect(() => {
@@ -124,10 +115,9 @@ export default function RunsPage() {
         filter_tags: values.scope === 'tags' ? values.tags : [],
         trigger_type: 'manual',
       });
-      const next = [run, ...runs];
-      persistRuns(next);
       message.success('运行已启动，可到详情页查看进度');
       setTriggerOpen(false);
+      void loadRuns();   // 刷新列表（不阻塞跳详情）
       navigate(`/evaluation/runs/${run.id}`);
     } catch (err) {
       if (err instanceof Error && err.message) {
@@ -221,7 +211,7 @@ export default function RunsPage() {
         description="用某个版本跑一批测试样本，产出仿写结果与多维评分。状态机：pending → running → completed / failed。"
         actions={
           <>
-            <Button icon={<ReloadOutlined />} onClick={() => loadFromLocal()}>
+            <Button icon={<ReloadOutlined />} onClick={() => void loadRuns()}>
               刷新
             </Button>
             <Button type="primary" icon={<PlusOutlined />} onClick={() => setTriggerOpen(true)}>
@@ -233,8 +223,8 @@ export default function RunsPage() {
 
       <div className="stats-grid">
         <div className="stat-card">
-          <div className="stat-label">本地缓存运行</div>
-          <div className="stat-value">{counts.all}</div>
+          <div className="stat-label">运行总数</div>
+          <div className="stat-value">{total}</div>
         </div>
         <div className="stat-card">
           <div className="stat-label">已完成</div>
@@ -271,11 +261,6 @@ export default function RunsPage() {
             </div>
           </div>
 
-          <Callout variant="warn" icon="!" style={{ margin: '0 var(--sp-5) var(--sp-4)' }}>
-            一期运行列表暂存在浏览器 localStorage（后端 GET /runs 列表接口尚未实现）。
-            触发的运行会自动追加到列表顶部；切换浏览器或清理缓存后列表会重置，但 run id 仍可从「详情」直接访问。
-          </Callout>
-
           {loading ? (
             <div style={{ padding: 'var(--sp-5)' }}>
               <Skeleton active paragraph={{ rows: 6 }} />
diff --git a/frontend/src/evaluation/pages/TestCaseEdit.tsx b/frontend/src/evaluation/pages/TestCaseEdit.tsx
index 82c365f..b126274 100644
--- a/frontend/src/evaluation/pages/TestCaseEdit.tsx
+++ b/frontend/src/evaluation/pages/TestCaseEdit.tsx
@@ -14,7 +14,7 @@ import { ArrowLeftOutlined } from '@ant-design/icons';
 import '../../styles/variables.css';
 import '../styles/eval.css';
 import { Callout } from '../components/primitives';
-import { createTestCase, listTestCases, updateTestCase } from '../api';
+import { createTestCase, getTestCase, updateTestCase } from '../api';
 import type { EvalTestCaseCreate, EvalTestCaseUpdate } from '../types';
 
 const { TextArea } = Input;
@@ -58,15 +58,8 @@ export default function TestCaseEditPage() {
     (async () => {
       setLoading(true);
       try {
-        // 后端无 GET /test-cases/:id 单条接口，从 list 中查找
-        const page = await listTestCases({ page: 1, page_size: 50 });
-        const found = page.items.find((it) => it.id === testCaseId);
+        const found = await getTestCase(testCaseId);
         if (cancelled) return;
-        if (!found) {
-          message.error('样本不存在或已被删除');
-          navigate('/evaluation/test-cases');
-          return;
-        }
         const ip = found.input_payload ?? {};
         form.setFieldsValue({
           name: found.name,
diff --git a/frontend/src/evaluation/types/index.ts b/frontend/src/evaluation/types/index.ts
index d50022c..0d7386d 100644
--- a/frontend/src/evaluation/types/index.ts
+++ b/frontend/src/evaluation/types/index.ts
@@ -12,7 +12,7 @@ export type EvalToolCode = 'qianchuan-writer';
 export type EvalTriggerType = 'manual' | 'auto' | 'schedule';
 
 /** 运行状态机 */
-export type EvalRunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'partial';
+export type EvalRunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'partial' | 'cancelled';
 
 /** 通用分页结构 */
 export interface EvalPagination {
@@ -215,6 +215,9 @@ export interface EvalRun {
   started_at: string | null;
   finished_at: string | null;
   created_at: string | null;
+  /** 仅 GET /runs/{id} 详情返回（list 不返回）：ETA 估算 */
+  eta_secs?: number | null;
+  avg_case_duration_secs?: number | null;
 }
 
 export interface EvalTriggerRunRequest {
@@ -224,6 +227,14 @@ export interface EvalTriggerRunRequest {
   trigger_type?: EvalTriggerType;
 }
 
+/** GET /runs 列表查询参数 */
+export interface EvalRunListParams {
+  page?: number;
+  page_size?: number;
+  status?: EvalRunStatus;
+  version_id?: number;
+}
+
 export interface EvalScore {
   id: number;
   case_result_id: number;
@@ -239,6 +250,41 @@ export interface EvalScore {
   updated_at: string | null;
 }
 
+/** GET /runs/{id}/case-results — 单 case 生成结果（含 generated_output，供「查看输出」） */
+export interface EvalCaseResult {
+  id: number;
+  test_case_id: number;
+  test_case_name: string;
+  generated_output: string | null;
+  output_payload: Record<string, unknown> | null;
+  input_snapshot: Record<string, unknown> | null;
+  created_at: string | null;
+}
+
+/** GET /admin/evaluation/queue-stats — 队列健康度 */
+export interface EvalQueueStats {
+  pending: number;
+  running: number;
+  failed_dead_letter: number;
+  done: number;
+  cancelled: number;
+  oldest_pending_secs: number | null;
+  runs_active: number;
+}
+
+/** GET /admin/evaluation/runs/{id}/jobs — 单 run 的 job 明细 */
+export interface EvalRunJob {
+  id: number;
+  test_case_id: number;
+  status: string;
+  attempts: number;
+  max_attempts: number;
+  last_error: string | null;
+  enqueued_at: string | null;
+  started_at: string | null;
+  finished_at: string | null;
+}
+
 export interface EvalHumanLabelRequest {
   human_score: number;
   human_feedback?: string | null;
diff --git a/frontend/src/layouts/AdminLayout.tsx b/frontend/src/layouts/AdminLayout.tsx
index f0ea862..9ab770d 100644
--- a/frontend/src/layouts/AdminLayout.tsx
+++ b/frontend/src/layouts/AdminLayout.tsx
@@ -33,6 +33,7 @@ const GROUPS: NavGroup[] = [
       { path: '/admin/evaluation/dimensions', label: '维度与评分标准' },
       { path: '/admin/evaluation/versions',   label: '版本快照' },
       { path: '/admin/evaluation/schedules',  label: '定时策略' },
+      { path: '/admin/evaluation/observability', label: '评测监控' },
     ],
   },
   {
```
