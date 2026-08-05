# AIGC 评测 — Phase 5 实现 spec：可观测性

> 2026-07-27 · PM · 上游计划：`docs/superpowers/plans/2026-07-26-async-run-architecture.md`（Phase 5）。
> 分支：`feature/eval-phase4-web-run-management`（叠在 Phase 4/cancel 上）。
> 动机：Phase 4 冒烟时 run 卡住（stale job 堵队列 + glm 超时）但**完全不可见**——本 Phase 把异步运行状态变可观测。

---

## 1. 目标与范围

**做什么**：admin 可看队列状态 + 单 run 的逐 job 状态/失败原因 + worker 运维手册。让"队列堵了/某 job 卡了/某 job 为啥失败"一眼可见。

**不做（剔除）**：
- **ETA 估算**：需历史 case 耗时数据（一期无），先不做。
- **PM2/systemd 部署配置**：属 Phase 6 上线，本 Phase 只补文档。
- **死信自动重投**：一期 failed job 由 admin 手动看 last_error 决定（重跑靠重新触发 run），不做自动重投队列。
- 前端可观测页：一期 admin 用 API + 文档排查；前端仪表盘后续。

---

## 2. 后端（admin router，只读，admin-only）

### 2.1 `GET /admin/evaluation/queue-stats`
全局队列健康度：
```
{
  pending: <int>,              # 待消费 job 数（队列深度）
  running: <int>,              # 在跑 job 数
  failed_dead_letter: <int>,   # 失败 job 数（attempts>=max_attempts，需关注）
  done: <int>,
  cancelled: <int>,
  oldest_pending_secs: <int|null>,  # 最老 pending job 等了多久（堵没堵的信号）
  runs_active: <int>           # status in (pending/running/cancelling) 的 run 数
}
```
实现：`SELECT status, count(*) FROM eval_case_jobs GROUP BY status` + 最老 pending 的 `EXTRACT(EPOCH FROM NOW()-enqueued_at)` + active runs count。纯聚合查询，无写。

### 2.2 `GET /admin/evaluation/runs/{id}/jobs`
单 run 的逐 job 明细（debug 卡住的 run）：
```
[{ id, test_case_id, status, attempts, max_attempts, last_error, enqueued_at, started_at, finished_at }]
```
按 id 排序。一眼看出哪个 job 卡 running / 失败原因（last_error，如 glm ReadTimeout）。

### 2.3 红线
- 标准信封 `success_response` ✓；GET 只读无 OperationLog ✓；admin-only（admin_evaluation router 已是 admin 权限）✓。

---

## 3. 运维手册 `backend/docs/评测worker运维手册.md`

- 起/停 worker（arq 命令 + PM2 示例）
- redis 起/停/备份（start_redis.sh + AOF）
- **排查卡住的 run**：看 `queue-stats`（pending 堆积？oldest_pending 大？）→ 看 `runs/{id}/jobs`（哪个 job 卡？last_error？）
- **stale job 清理**：worker 重启会 recover 重投 pending job；老测试 run 的 pending job 会堵——手动 `UPDATE eval_case_jobs SET status='cancelled' WHERE run_id IN (旧run) AND status='pending'` 或清理旧 run
- **慢评委**：glm-4.6 评分延迟方差大→调 `_HTTP_TIMEOUT` / 换更快评委 / 扩 key 池

---

## 4. 测试（TDD，integration）

`tests/integration/routers/test_admin_evaluation.py` 增量：
1. queue-stats：seed 各状态 job → 计数正确 + oldest_pending_secs 合理
2. queue-stats：空表 → 全 0 + oldest_pending null
3. queue-stats：权限（admin ok / operator 403 / 无 token 401）
4. runs/{id}/jobs：seed run + 多状态 job → 返回明细含 last_error
5. runs/{id}/jobs：run 不存在 404

---

## 5. 执行顺序

1. 后端 queue-stats + jobs view（admin router）+ 集成测试。
2. 运维手册。
3. 全量 eval 套件 + 1 轮 review。
4. 本地 commit（不 push，等 #34 合后统一发 PR）。
