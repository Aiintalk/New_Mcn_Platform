# AIGC 评测 异步架构 — Phase 3 实现 spec：worker 真实执行

> 2026-07-27 · PM · 上游计划：`docs/superpowers/plans/2026-07-26-async-run-architecture.md`（Phase 3「最重」）。
> 前置已完成：Phase 0（rubric 重置）、Phase 1（Redis+arq 基建）、Phase 2（job 模型 + 触发改异步，`eb21adc`）。
> 本 spec 落 Phase 3 的「改动清单 + 数据流 + 伪码 + 测试计划」，确认后 TDD 推进。

---

## 1. 目标与边界

**做什么**：把 `run_case_job_logic` 里的 STUB 换成真实 case 执行——一个 case-job = 1 次生成（LLM）+ N 维评分（LLM）+ 写 `eval_case_results` + `eval_scores`。让 worker 进程真正能跑出带分数的 run。

**不做（推迟到后续 Phase，本 spec 明确剔除）**：
- Phase 4：`GET /runs` 列表分页、`/runs/{id}` 进度轮询、`POST /runs/{id}/cancel`、前端 Runs 列表接 API。
- Phase 5：队列深度/ETA/死信指标、运维手册。
- cancel 执行期跳过（run.status=cancelling 时 worker 跳过其 pending job）——Phase 3 无 cancel API，job 一旦起跑就跑完。
- `_wait_queue` 30s 超时放宽（plan §4 待决项）——Phase 3 不动 yunwu。
- 公平调度跨 run 轮转——一期 FIFO，已由 arq 入队顺序保证。

---

## 2. 现状关键事实（来自代码核实）

1. **`runner.execute_run` 已是死代码**：Phase 2 后 `scheduler.trigger_run` 不再调它（改异步入队）。生产无调用方；仅 `test_eval_runner.py`（11 处）+ `test_eval_scheduler.py:163`（patch 验证"不被调用"）引用。
2. **要抽取的 case body** = `execute_run` 第 261-313 行的循环体（去掉 `for tc in test_cases:` 包一层，因为 job 只绑**一个** test_case）。
3. **三条已踩过的硬约束**（必须在 `execute_case` 里保住，否则回归已修的 bug）：
   - generate/score（经 yunwu.chat）**必须在任何事务/savepoint 之外**调——yunwu.chat 内部 commit（写 AiCallLog），裹进 nested txn 会触发 `InvalidRequestError`。
   - **每 case 一次 commit**（case 级隔离）。
   - run 计数**不再用 ORM `+=`**，改走 `aggregate_run_progress`（原子 `UPDATE ... = ... + 1`）——这已由 `run_case_job_logic` 的 try/except 收尾处理，`execute_case` 只管"成功写库 / 失败抛错"。
4. **B-C2 可复现性**（`run.metadata['resolved_scoring']`）：原由 execute_run 在 run 启动时写入。删 execute_run 会回归——需在 `trigger_run` 建 run 时补写（它手上正好有 version+strategy）。
5. **helper 已现成**：runner.py 的 `_get_active_dimensions`/`_get_default_rubrics`/`_resolve_weight`/`_resolve_with_strategy_override` 全部可复用；test_eval_runner.py 的 `_make_*` 系列 + `generate_fn=/score_fn=` 注入模式可直接用于 execute_case 的 TDD。

---

## 3. 数据流（Phase 3 后）

```
[arq worker] eval_case_job(ctx, job_id)
  └─ AsyncSessionLocal() as db
     └─ run_case_job_logic(db, job_id, execute=execute_case)
        ├─ 幂等守卫：job 已终态 → skip
        ├─ job → running, attempts+1, commit
        ├─ try: execute_case(db, job_id)        ← Phase 3 真实执行
        │    ├─ load job→run→version→strategy→test_case
        │    ├─ resolve scoring identity + 绑 adapter（None 时）
        │    ├─ generated = await generate(gen_fn, version, tc)   【事务外 LLM】
        │    ├─ for dim: parsed = await score(score_fn, dim, rubrics, gen, ctx)  【事务外 LLM】
        │    ├─ 写 EvalCaseResult + EvalScores
        │    └─ commit（每 case 落盘）
        ├─ except: rollback, job→failed+last_error, commit
        ├─ job→done, commit（成功路径）
        └─ aggregate_run_progress(db, run_id, success)  ← 原子计数 + run 收尾
```

**关键不变量**：
- 单 job 失败 → 只该 job 的 case_result 不写 + job.failed + run.failed_cases+1，**不波及其它 job**。
- run 全部 job 终态 → run completed（部分失败仍 completed）/ failed（全失败）——由 aggregate 保证（Phase 2 已测）。

---

## 4. 改动清单

### 4.1 新增 `runner.execute_case`（核心）
- 签名：`async def execute_case(db, job_id, *, generate_fn=None, score_fn=None) -> None`
- 从 `execute_run` 循环体抽取；job.test_case_id 决定唯一 test_case（无循环）。
- 复用 runner.py 现有私有 helper + generator.generate + scorer.score + adapter_registry.get_adapter。
- `generate_fn`/`score_fn` 默认 None → 经 adapter_registry 绑定（生产路径）；测试注入 mock 绕过 LLM。
- 异常**不捕获**，向上抛给 `run_case_job_logic`（它负责 job 失败收尾 + aggregate）。

### 4.2 `worker.py`：接线 + 替换 STUB
- `eval_case_job`：`return await run_case_job_logic(db, job_id, execute=execute_case)`。
- `run_case_job_logic` 的 `execute is None` STUB 分支**保留**（单测/Phase 2 已有 stub 测试仍绿；execute_case 走 `else` 分支）。
- import `from app.evaluation.services.runner import execute_case`。

### 4.3 `scheduler.trigger_run`：补 B-C2 resolved_scoring
- 建 run 时把 `_resolve_with_strategy_override(...)` 算出的 `{model_id, provider, adapter}` 写入 `run.metadata_['resolved_scoring']`。
- 抽 `runner._compute_resolved_scoring(strategy, config)` 为可复用 helper（trigger_run + execute_case 共用，避免逻辑漂移）。

### 4.4 删除 `runner.execute_run` + 迁移其测试（见 §6 决策）
- execute_run 死代码，其职责被 execute_case（单 case）+ aggregate_run_progress（run 收尾）替代。
- `test_eval_runner.py` 改写为 `execute_case` 测试（复用 `_make_*` helper + 注入模式）。
- `test_eval_scheduler.py:163` 的 patch（验证 execute_run 不被调）改为验证 execute_case 不被 trigger_run 直接调用。

---

## 5. `execute_case` 伪码

```python
async def execute_case(db, job_id, *, generate_fn=None, score_fn=None) -> None:
    job = await db.get(EvalCaseJob, job_id)
    if job is None:
        raise ValueError(f"EvalCaseJob not found: id={job_id}")
    run = await db.get(EvalRun, job.run_id)
    version = await db.get(EvalVersion, run.version_id)
    strategy = await db.get(EvalStrategy, run.strategy_id)
    tc = await db.get(EvalTestCase, job.test_case_id)
    config = dict(version.config_payload or {})

    # resolve scoring identity（与 trigger_run 共用 helper，保证一致）
    resolved_scoring = _compute_resolved_scoring(strategy, config)

    # 绑 adapter callable（生产路径；测试注入 mock 时跳过）
    if generate_fn is None or score_fn is None:
        adapter = get_adapter(resolved_scoring["adapter"])
        if generate_fn is None:
            generate_fn = functools.partial(adapter.chat, db=db,
                model_id=config.get("model_id"),
                provider=config.get("provider", DEFAULT_ADAPTER))
        if score_fn is None:
            score_fn = functools.partial(adapter.chat, db=db,
                model_id=resolved_scoring["model_id"],
                provider=resolved_scoring["provider"])

    dimensions = await _get_active_dimensions(db, version.tool_code)

    # ── LLM 调用：事务外（yunwu.chat 内部 commit）──
    generated_output = await generate(generate_fn, version, tc)
    input_context = dict(tc.input_payload or {})
    scored = []
    for dim in dimensions:
        rubrics = await _get_default_rubrics(db, dim.id)
        weight = _resolve_weight(strategy, config, dim)
        parsed = await score(score_fn, dim, rubrics, generated_output, input_context)
        scored.append((dim, weight, parsed))

    # ── 结果写入：单 case 一次 commit（case 级隔离）──
    case_result = EvalCaseResult(
        run_id=run.id, test_case_id=tc.id,
        generated_output=generated_output,
        input_snapshot=tc.input_payload,
        output_payload={"text": generated_output},
    )
    db.add(case_result)
    await db.flush()  # 拿 case_result.id
    for dim, weight, parsed in scored:
        db.add(EvalScore(
            case_result_id=case_result.id, dimension_id=dim.id,
            ai_score=parsed.score, ai_reasoning=parsed.reasoning,
            ai_strengths=parsed.strengths, ai_weaknesses=parsed.weaknesses,
            weight_used=weight,
        ))
    await db.commit()
```

---

## 6. 决策点（需确认）

### 决策 A：`execute_run` 去留 — 推荐「删 + 迁移测试」

| 方案 | 改动 | 风险 |
|---|---|---|
| **B（推荐）删 execute_run + 改写其测试为 execute_case 测试** | 160 行死代码消失，单一执行路径 | TDD 先写 execute_case 测试再删，覆盖不丢 |
| A 保留 execute_run（标 deprecated） | blast radius 最小 | 留双份同逻辑 case 执行代码 → 后续改 bug 易漏改一处（维护陷阱） |

**推荐 B**：execute_run 是被 Phase 3 **替代**的旧路径（非无关 dead code），删除属本 Phase 范围内；TDD 保证覆盖迁移。符合「单一事实源」。

### 决策 B：resolved_scoring 写入时机 — 推荐「trigger_run 建 run 时写」

把 `_compute_resolved_scoring` 结果在 trigger_run 建 run 时写入 metadata（执行期只读 config）。理由：run 创建 = 意图快照点；execute_run 删除后这是唯一保住 B-C2 可复现性的位置；execute_case 不再各自写 metadata（避免多 job 并发写同一行竞争）。

---

## 7. 测试计划（TDD，覆盖率门禁 ≥ 80%）

### 7.1 新增 `test_eval_runner.py` 改写（execute_case 维度）
复用 `_make_dimension/_make_rubrics/_make_version/_make_strategy/_make_test_case/_make_run` + `generate_fn=/score_fn=` 注入：

1. **happy path**：1 job + 2 维 → execute_case 写 1 case_result + 2 scores，score 字段正确（ai_score/reasoning/strengths/weaknesses/weight_used）。
2. **多维度权重**：3 维不同 weight → 每个 EvalScore.weight_used 等于 strategy override / version config / dim default 三级 resolve。
3. **生成失败隔离**：generate_fn 抛错 → execute_case 抛错（不写 case_result）；调方 run_case_job_logic 收尾 job=failed + run.failed_cases+1（在 worker 测试里联测）。
4. **单维评分失败隔离**：score_fn 第 2 维抛错 → 整个 execute_case 抛错，**不写**任何 case_result/score（无半成品落库）。
5. **adapter 绑定路径**：generate_fn/score_fn=None → 走 get_adapter（mock registry 验证 partial 绑定参数正确）。
6. **输入快照**：case_result.input_snapshot == tc.input_payload（被测输入留痕）。
7. **job 绑定正确 test_case**：job.test_case_id 唯一决定 tc（不串 case）。

### 7.2 worker 集成（test_eval_worker.py 增量）
8. **execute_case 接线**：`run_case_job_logic(db, job.id, execute=execute_case)` + mock generate/score → job=done + run.completed+1 + case_result/scores 落库。
9. **失败路径**：execute_case 抛错 → job=failed + last_error 非空 + run.failed+1（端到端验证 §5 不变量）。

### 7.3 scheduler（test_eval_scheduler.py 增量）
10. **resolved_scoring 落 metadata**：trigger_run 后 run.metadata_['resolved_scoring'] 含 {model_id, provider, adapter}（B-C2）。
11. 原 patch「execute_run 不被调」改为「execute_case 不被 trigger_run 直接调」。

### 7.4 验收
- 全量 eval 套件绿（Phase 2 基线 193 → Phase 3 后 ≥ 200）。
- 覆盖率：runner.py（execute_case 路径）+ worker.py ≥ 80%。
- **≥ 2 轮独立子 agent code review**（用户硬性门禁），直到无显性错误。
- 手动冒烟（dev）：起 redis + worker，触发 1 条 run，确认 case_result + scores 真落库（Phase 3 收尾验收，非阻塞 commit）。

---

## 8. 风险

| 风险 | 应对 |
|---|---|
| execute_case 删 execute_run 后遗漏某 run 级行为 | §4.3 把 resolved_scoring 迁到 trigger_run；finalize 已在 aggregate（Phase 2 测过） |
| yunwu.chat 内部 commit 污染 execute_case 事务 | 保持 generate/score 在 commit 之后、写库之前调用（与 execute_run 已验证的顺序一致） |
| 真 LLM 调用拖慢单测 | 全部 mock generate_fn/score_fn；真 LLM 只在手动冒烟跑 |
| coverage.py segfault（redis import 路径） | 沿用 Phase 2 workaround：单测全绿即放行，覆盖率定性报告（已与用户对齐） |

---

## 9. 执行顺序（TDD）

1. 先写 `_compute_resolved_scoring` helper + trigger_run 写 metadata（决策 B）+ 其测试（§7.3-10）。
2. TDD 写 `execute_case`（§7.1 测试先行）。
3. worker 接线 execute_case（§7.2）。
4. 删 execute_run + 迁移测试（决策 A-B）。
5. 全量 eval 套件 + 覆盖率核验。
6. ≥ 2 轮独立 review → 修复 → 直到无显性错误。
7. commit（本地，不 push PR，用户要先本地看）。
8. （收尾）手动冒烟：起 redis+worker 触发 run 验真落库。
