# AIGC 评测 — 异步运行架构 & 长期计划（方案 C：arq + Redis）

> 2026-07-26 · PM · 方案已选定：C（arq + Redis，按 case 拆任务）。
> 前序：`docs/evaluation/run-execution-design-options.md`（方案对比与选型理由）。
> 本文件为正式长期计划，确认后按阶段 TDD 推进。

---

## 0. 目标与规模基线

| 项 | 基线 |
|---|---|
| 单 run 体量 | **200+ test case**（× 每维度 1 次评分 + 1 次生成 ≈ 800+ LLM 调用） |
| 队列深度 | 多业务场景 + 多达人工作台 → **几十~上百个 run 并发排队** |
| 总调用量 | 数万~十万级 LLM 调用 |
| 硬瓶颈 | LLM 凭证池 `credentials.max_concurrent`（现为 glm 1 条=5）→ 并发天花板由 key 池决定 |
| 持久性 | 触发即返回；浏览器关闭/进程重启都不丢 run；卡死的能恢复重跑 |

**核心设计决策**（已选）：
1. **队列载体 = Redis**，任务框架 = **arq**（async 原生，契合 FastAPI）。
2. **按 case 拆任务**：一个 200-case run = 200 个 case-job（不是一个大 job）。→ run 内并行、跨 run 公平、故障隔离。
3. **结果落 PG**（eval_case_results/eval_scores 仍在 Postgres，强一致）；Redis 只做任务分发 + 重试。
4. **并发受凭证池限流**：worker 并发 ≤ Σ(credentials.max_concurrent)。
5. **run 完成判定** = 其所有 case-job 完成（`completed_cases/total_cases`）。

---

## 1. 分阶段路线图（长期）

### Phase 0 — 评分标准重置（安雅版）【纯数据，无基建】
**Why**：安雅初稿把维度从 3 改 4、换名、给真实 criteria；当前 seed 是占位。
- **eval_dimensions 重置**：删 `copy_quality`；新增 `hook_strength`(0.35) + `structure_fidelity`(0.20)；保留 `conversion_power`(→0.30) + `persona_consistency`(→0.15)。合计 1.00，共 4 维。
- **eval_rubrics 重置**：4 维 × 5 档（10/8/6/4/2）× default 通用版，写入安雅的真实 criteria。**删掉之前加的 skincare/diet 品类变体**（一期不启用）。
- **dimension.prompt_template**：为 2 个新维度（hook_strength / structure_fidelity）按安雅口径补评分 prompt 模板（沿用现有 `{{rubric_text}}/{{generated_output}}/{{persona}}/{{product_info}}` 占位）。
- **eval_versions.config_payload.dimension_weights**：从旧 3 维权重改成新 4 维权重。
- **清旧测试 run/score**（引用了旧 dimension_id），用新维度重 seed 2 条 demo run。
- **测试**：rubric_resolver 渲染、dimension/rubric seed 断言、generator 用新模板渲染。
- **退出标准**：4 维 + 20 条 default rubric 落库；旧维度无残留引用；单测全绿。

### Phase 1 — Redis + arq 基建【infra】
- **依赖**：`arq`、`redis` 入 requirements。
- **dev**：docker-compose 加 redis 服务（或复用现有 hermes 之外的实例）；`.env` 加 `REDIS_URL`。
- **prod**：单机起 redis（PM2 或 systemd 守护 + AOF 持久化 + 备份）。
- **arq worker 骨架**：`app/evaluation/worker/__init__.py` 的 `WorkerSettings`（functions 注册、queue、max_jobs、job_timeout）。
- **冒烟**：起 worker + enqueue 一个 echo job 跑通。
- **退出标准**：`arq` worker 能连 Redis 取到并执行一个测试任务；dev compose 一键起 redis。

### Phase 2 — Job 模型 + 触发改异步【core】
- **DDL（新表）** `eval_case_jobs`：
  ```
  id BIGSERIAL PK
  run_id BIGINT FK→eval_runs
  test_case_id BIGINT FK→eval_test_cases
  status VARCHAR(20) NOT NULL DEFAULT 'pending'   -- pending/running/done/failed/cancelled
  attempts INT NOT NULL DEFAULT 0
  max_attempts INT NOT NULL DEFAULT 3
  last_error TEXT
  enqueued_at TIMESTAMPTZ DEFAULT NOW()
  started_at TIMESTAMPTZ
  finished_at TIMESTAMPTZ
  UNIQUE(run_id, test_case_id)
  INDEX (status, enqueued_at)
  ```
- **trigger_run 重写**：建 run(status=pending, total_cases=N) → 批量建 N 条 `eval_case_jobs`(pending) → `await pool.enqueue_job('eval_case_job', job_id)` → run(status=queued) → **立即返回 run_id**（不再 await execute_run）。
- **run 聚合**：每个 case-job 完成时 `completed_cases += 1`（或 failed_cases），全部完成 → run status=completed/failed。
- **测试**：触发后立即返回 pending + N 条 job；不阻塞；run 聚合正确。

### Phase 3 — Worker 执行 + 并发受控 + 重启恢复【core，最重】
- **arq task `eval_case_job(job_id)`**：
  1. 取 job → status=running, started_at, attempts+=1。
  2. 复用**已修好的 runner case 逻辑**：generate（LLM）→ score 每维（LLM）→ 写 case_result + scores（每 case commit，失败 rollback）。
  3. 成功 → job.status=done + run.completed_cases+=1；失败 → job.status=failed（attempts 未满可重试）+ run.failed_cases+=1。
  4. run 全部 job 终态 → run.status 收尾。
- **并发受控**：worker `max_jobs` ≤ 凭证池容量；yunwu `_wait_queue` 已对单凭证限流（30s 超时需放宽，避免重负载误杀）。
- **重启恢复**（lifespan/worker 启动）：把 `status='running'` 且 `started_at` 超阈值（如 30min）的 job 重置 `pending` 重新入队；把无 case-job 终态的 run 标记重算。
- **公平调度**（跨 run）：入队时按 `enqueued_at` FIFO；若需"多 run 交错"，加一个调度器按 run 轮转取 case（一期 FIFO 先够用，标注为可演进项）。
- **测试**：单 job 全流程；并发上限；attempts 重试；重启恢复（卡 running→重置重跑，**B/C 区别于 A 的关键 e2e**）；case 级失败隔离。

### Phase 4 — Web Run 管理【api + 前端】
- **后端**：
  - `GET /api/operator/evaluation/runs`（分页 + status/version_id 过滤）→ 补 `frontend-issues.md #1`，**去掉前端 localStorage 兜底**。
  - `GET /runs/{id}`：返回 progress（completed/total/failed）+ ETA 估算（按平均 case 耗时）。
  - （可选一期）`POST /runs/{id}/cancel`：run.status=cancelling，worker 跳过其 pending job。
- **前端**：
  - Runs 列表接 API；触发后立即跳详情页 + 轮询 status（completed/failed 止）。
  - RunDetail：进度条、ETA、样本逐条状态（pending/running/done/failed）。
- **测试**：router 集成（列表分页/过滤、进度、cancel）；前端组件 + e2e（Playwright：触发→轮询→完成）。

### Phase 5 — 可观测 + 运维【ops】
- **指标**：队列深度（pending job 数）、worker 在跑数、平均 case 耗时、失败率 → 一个 `/api/admin/evaluation/queue-stats` 或复用服务状态页。
- **重试/死信**：arq `max_tries`；超过的 job 进 dead-letter（status=failed + last_error），admin 可手动重投。
- **部署**：PM2 加 arq worker 进程（按凭证池容量定进程数/并发）；redis 守护 + 备份；日志。
- **文档**：`backend/docs/` 补"评测 worker 运维手册"（起停、扩容、排障、恢复）。

### Phase 6 — 迁移 & 上线【rollout】
- prod 部署 Redis + arq worker 进程。
- 评测模块尚未上线（feature 分支），无历史 run 迁移负担；dev 现有 demo run 用新架构重跑验证。
- 灰度：先 dev 全量 → 安雅/团队人工 spot check 几条 run → 上线。

---

## 2. 数据流（选定后）

```
浏览器 POST /runs {version_id}
  → router: 建 eval_runs(pending, total=N) + N 条 eval_case_jobs(pending) + commit
  → arq enqueue N 个 'eval_case_job' → Redis
  → 立即返回 run_id

[arq worker × M 进程]（max_jobs ≤ 凭证池容量）
  loop: 从 Redis 取一个 case_job
    → job: running；generate(LLM) → score×维度(LLM) → 写 case_result+scores（commit）
    → job: done/failed；更新 run.completed/failed_cases
    → 若 run 所有 job 终态 → run: completed/failed

浏览器 GET /runs（列表）/ GET /runs/{id}（进度轮询）
[worker 启动] 恢复：stuck running job → pending 重投
```

---

## 3. 测试与 e2e 总策略
- **单测**：Phase 0 rubric 渲染；Phase 2 入队/聚合；Phase 3 worker 单 job + 重试 + 恢复；Phase 4 router。
- **集成**：触发→入队→worker 消费→评分落库→run 完成（用 mock LLM）；重启恢复（真起停 worker）。
- **e2e（Playwright，后端栈起来）**：web 触发→列表见 pending→详情轮询到 completed→评分可查；取消 run；多 run 排队公平性。
- **覆盖率门禁**：worker/job 模块 ≥ 80%（参考 CLAUDE.md 门禁）。

---

## 4. 风险与待决
| 风险/决策 | 说明 | 倾向 |
|---|---|---|
| Redis 运维 | 新基建，需 HA/备份/监控 | 单机 AOF + 定时备份起步 |
| 凭证池是真实瓶颈 | 1 key=5 并发 → 上百 run 排队很慢 | 扩 key 池（多 key/多 provider）；worker 并发跟随 |
| `_wait_queue` 30s 超时 | 重负载下误杀排队请求 | 放宽到 5~10min 或改阻塞等待 |
| 公平调度 | FIFO 可能让大 run 饿死小 run | 一期 FIFO；按需加 run 轮转 |
| case-job 粒度 | 200 job/run × 上百 run = 数万 job | Redis/arq 扛得住；监控队列深度 |
| 品类变体（skincare/diet） | 安雅一期不启用 | 结构预留，不写变体数据 |

---

## 5. 选型决策（2026-07-26 已确认）
1. ✅ **Phase 0 已执行**（安雅 rubric 重置，纯数据，独立于架构）—— 4 维 + 20 rubric + demo 数据落 dev 库，110 eval 测试通过。
2. ✅ **Redis 部署**：dev docker-compose；prod 单机 AOF + 定时备份（默认）。
3. ✅ **worker 并发上限**：一期**固定保守值 = 2**（glm 1 条 key=5，留余量；后续按 key 池扩）。
4. ✅ **cancel run**：一期**要做**（POST /runs/{id}/cancel，状态机加 cancelling）。
5. ✅ **公平调度**：一期 **FIFO**（按 enqueued_at）。

下一步：Phase 1（Redis + arq 基建）→ 按 Phase 顺序 TDD，每阶段出 spec 细化（DDL + 改动清单 + 伪码）。
