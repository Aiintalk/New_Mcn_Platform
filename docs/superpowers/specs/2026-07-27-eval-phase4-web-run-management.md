# AIGC 评测 — Phase 4 实现 spec：Web Run 管理（列表 + 详情轮询）

> 2026-07-27 · PM · 上游计划：`docs/superpowers/plans/2026-07-26-async-run-architecture.md`（Phase 4）。
> 分支：`feature/eval-phase4-web-run-management`（off PR #34 分支，不 push 直到 #34 合并）。
> 前置：Phase 0-3 已落地（异步 worker 真实执行 kimi 生成 + glm 评分）。

---

## 1. 目标与范围

**做什么**：补 `GET /runs` 列表接口 + 前端 Runs 页丢 localStorage 改接 API + RunDetail 实时轮询进度。让用户能看到所有 run（跨设备）、实时看跑分进度。

**不做（本期剔除，留后续）**：
- **cancel run**（`POST /runs/{id}/cancel` + worker 跳过 cancelling run 的 job）：要改 `aggregate_run_progress`（并发敏感、已 review），单独迭代。
- **ETA 估算**（按平均 case 耗时）：需历史耗时数据，一期显示 completed/total 进度即可。
- **逐 case-job 状态**（pending/running/done/failed 明细）：一期 run 级进度（completed/failed/total）够用。
- **服务端分页 + 状态卡下钻**：一期前端 `listRuns({page:1,page_size:50})` 拉最近 50 条 + 客户端 tab/卡过滤（eval run 量级低，≤50 完全正确）。run 历史超 50 条时需改服务端分页（Table onChange 带 page）+ `/runs/stats` 状态计数接口。
- frontend-issues #2-#5（test-case 单条 GET / 统计聚合 / 输出查看 / 版本关联预览）：与本 Phase 无关。

---

## 2. 现状（已核实）

**后端 `operator_evaluation.py`**：
- ✅ `POST /runs`（触发）、`GET /runs/{id}`（单条，`_run_to_dict` 已含 status/completed_cases/failed_cases/total_cases/started_at/finished_at）、`GET /runs/{id}/scores`
- ✅ `list_test_cases` 分页范式可复用（`_PAGE_SIZE_ALLOWED` + count + offset + `{items, pagination}`）
- ❌ **`GET /runs` 列表缺失**（→ 前端 localStorage 兜底）

**前端**：
- `api/index.ts`：有 `triggerRun / getRun / listRunScores`，**无 `listRuns`**
- `Runs.tsx`：用 `localStorage('eval_runs_cache')` 存触发结果，UI 标注"后端 GET /runs 尚未实现"
- `RunDetail.tsx`：挂载时单次 `getRun` + `listRunScores`，**无轮询**（进度不实时）

**EvalRun 字段**：id, version_id, strategy_id, name, trigger_type, status, filter_tags, total_cases, completed_cases, failed_cases, metadata_, created_by, started_at, finished_at, created_at。

---

## 3. 后端改动

### 3.1 `GET /operator/evaluation/runs`（新增，复用 list_test_cases 范式）
```
参数：page(≥1) / page_size(∈{10,20,50}, 默认20) / status(可选) / version_id(可选)
查询：EvalRun 按 status / version_id 过滤，id.desc 排序，offset 分页
响应：success_response({ items: [_run_to_dict], pagination: {page,page_size,total,total_pages} })
权限：require_operator
```
不新建 schema（复用 `_run_to_dict`，与 `GET /runs/{id}` 一致）。

### 3.2 红线遵守
- 标准信封 `success_response` ✓（list_test_cases 同款）
- GET 只读，**无需 OperationLog**（list_test_cases 也是 GET 无 log）✓
- 列表必须分页 ✓（一票否决项：列表无分页）

---

## 4. 前端改动

### 4.1 `api/index.ts` + `types/index.ts`
- 加 `listRuns(params: { page?, page_size?, status?, version_id? })` → `get<EvalPaged<EvalRun>>('/api/operator/evaluation/runs', params)`
- types 加 `EvalRunListParams`

### 4.2 `Runs.tsx`（核心）
- **删** localStorage 兜底（`eval_runs_cache` 读写 + "暂存浏览器"提示 UI）
- 改用 `listRuns({page, page_size, status})` 拉列表 + 分页控件 + status 过滤
- 触发后：刷新列表（不再写 localStorage），可选跳详情
- loading / empty / error 态对齐其它页

### 4.3 `RunDetail.tsx`（轮询）
- 挂载单次 `getRun`（保留）
- **加轮询**：`status ∈ {pending, running}` 时每 4s `getRun` 刷新；status 进终态（completed/failed）停
- **关键**：检测到 status→终态时，**重新拉 `listRunScores`**（挂载时 pending 期 scores 为空，不重拉看不到评分）
- 进度展示用 run.completed_cases/total_cases/failed_cases（已有）

---

## 5. 数据流

```
Runs 页 mount → listRuns({page:1,page_size:20,status?}) → 渲染分页列表
  ├ 点行 → 跳 /runs/:id
  └ 触发 → triggerRun → 刷新 listRuns

RunDetail mount → getRun + listRunScores
  └ status pending/running → 每 4s getRun → 进度更新 → status 终态停轮询
```

---

## 6. 测试计划（TDD）

### 后端集成（`tests/integration/routers/test_operator_evaluation.py` 增量）
1. **列表分页**：seed N 条 run，`GET /runs?page=1&page_size=10` → items 10 条 + total=N + total_pages 正确
2. **status 过滤**：seed pending+completed 各若干，`?status=completed` → 只返回 completed
3. **version_id 过滤**：`?version_id=X` → 只返回该版本
4. **page_size 校验**：非法 page_size → 回退 20
5. **权限**：未登录 / 非 operator-admin → 403
6. **信封**：响应 `{success,code,message,data:{items,pagination}}`

### 前端（`Runs.test.tsx` / `RunDetail.test.tsx` 增量）
7. **Runs 接 API**：mock `listRuns` 返回分页 → 列表渲染 + 分页交互；**不再有 localStorage**
8. **Runs status 过滤**：切 status → 重新 listRuns 带参
9. **RunDetail 轮询**：mock getRun 先返 pending、再返 completed → 轮询触发 2 次后停（用 jest fake timer）
10. **RunDetail 终态停**：completed → 不再轮询
11. **RunDetail 完成重拉 scores**：getRun 由 pending→completed → 触发 listRunScores 二次请求（挂载那次是空）

### 验收
- 后端 eval 套件全绿（基线 200 → ≥206）；routers 覆盖率不降
- 前端 Runs/RunDetail 测试绿；`tsc --noEmit` 0 错
- 手动：触发 run → Runs 列表见 → RunDetail 进度实时跳 → completed 停
- ≥1 轮独立 review（小迭代，单轮即可；若动多则 2 轮）

---

## 7. 风险

| 风险 | 应对 |
|---|---|
| Runs.tsx 重写引入回归 | 现有 98.7% 覆盖测试托底；逐个改 + 跑测试 |
| 轮询致请求风暴 | 4s 间隔 + 终态停 + 单页 only（离开页 clearInterval） |
| 列表大 run 数（200+ case × 多 run） | 分页 + id.desc 索引（eval_runs PK 自带） |

---

## 8. 执行顺序（TDD）

1. 后端 `GET /runs` + 集成测试（§6-1~6）。
2. 前端 `listRuns` API + types。
3. Runs.tsx 重写（删 localStorage，接 API）+ 测试（§6-7~8）。
4. RunDetail 轮询 + 测试（§6-9~10）。
5. 全量 eval 套件 + tsc。
6. ≥1 轮 review → 修 → 本地 commit（不 push，等 #34 合后 rebase 到 main 再发 PR）。
