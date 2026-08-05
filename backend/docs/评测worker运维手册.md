# 评测 Worker 运维手册

> AIGC 评测异步运行（arq + Redis）的起停、排障、恢复。
> 架构：一个 run 拆 N 个 case-job → arq 入 Redis → 独立 worker 进程消费（generate + 多维 score → 写库 → 聚合 run）。

---

## 1. 起停

### Redis（队列载体，仅评测用）
```bash
# dev：docker 容器（mcn-redis，redis:7-alpine，:6379）
bash backend/scripts/start_redis.sh
# 健康检查
docker exec mcn-redis redis-cli ping   # → PONG
# 清队列（慎用，会丢未消费 job；调试卡死时可用）
docker exec mcn-redis redis-cli FLUSHDB
```
prod：单机 Redis + AOF 持久化 + 定时备份（PM2/systemd 守护）。`REDIS_URL` 默认 `redis://localhost:6379/0`（不进全局 config.py）。

### Worker（与 web 分离的独立进程）
```bash
cd backend
REDIS_URL=redis://localhost:6379/0 arq app.evaluation.worker.WorkerSettings
```
PM2 示例（按凭证池容量定进程数，一期 1 个进程 max_jobs=2 即可）：
```bash
pm2 start "arq app.evaluation.worker.WorkerSettings" --name eval-worker
pm2 logs eval-worker
pm2 restart eval-worker   # 重启会触发 on_startup 恢复（见 §3）
```
配置（`app/evaluation/worker.py` `WorkerSettings`）：`max_jobs=2`、`job_timeout=900s`、`max_tries=3`、`on_startup=恢复卡死 job`。

### Web（FastAPI）
```bash
cd backend && uvicorn app.main:app --reload --port 8010
```

---

## 2. 可观测（Phase 5）

### 队列健康度
```bash
curl /api/admin/evaluation/queue-stats   # admin only
# → { pending, running, failed_dead_letter, done, cancelled,
#     oldest_pending_secs, runs_active }
```
- `pending` 堆积 + `oldest_pending_secs` 大 → **队列堵塞**（worker 挂了 / 评分太慢 / 凭证耗尽）。
- `failed_dead_letter` 增长 → job 持续失败（看 §3 的 last_error）。

### 单 run 排查（卡住 / 失败）
```bash
curl /api/admin/evaluation/runs/{id}/jobs   # admin only
# → [{ id, test_case_id, status, attempts, last_error, ... }]
```
- 哪个 job 卡 `running`（worker 崩溃遗留，见 §3 恢复）。
- `failed` job 的 `last_error`（如 `chat failed [glm]: ...` = LLM 超时/鉴权）。

---

## 3. 排障

### run 卡住不推进（pending 堆积）
1. `queue-stats` 看 `pending` / `oldest_pending_secs`：堆积且老 → worker 没在消费。
2. 查 worker 进程：`pm2 status` / `ps aux | grep arq`。挂了 → 重启。
3. worker 重启 → `on_startup` 自动恢复：`status='running'` 且超 `started_at > 600s` 的卡死 job 重置 `pending` 重投；所有 pending job 重新入队（arq `_job_id` 去重，不重复）。
4. 仍卡 → 看 `/runs/{id}/jobs` 的 `last_error`：凭证失效？LLM 超时？网络？

### stale job 堵队列（老测试 run 残留）
老 smoke/测试 run 的 `pending` job 会被 worker 启动恢复重投、堵队列（直到 max_tries 耗尽）。
```sql
-- 手动清理某个旧 run 的 pending job
UPDATE eval_case_jobs SET status='cancelled', finished_at=NOW()
WHERE run_id = <旧run_id> AND status='pending';
-- 或批量清理所有非活跃 run 的 pending job（谨慎）
```

### 评委/被测模型慢（ReadTimeout）
`chat failed [glm]:` 空错误 = `httpx.ReadTimeout`（响应超时）。glm-4.6 评分延迟方差大。
- 调 `_HTTP_TIMEOUT`（`app/adapters/yunwu.py`，现 150s）—— 注意单 case = 1 生成 + N 维评分，`N × _HTTP_TIMEOUT` 要 < `job_timeout`(900s)。
- 换更快评委模型 / 扩 key 池（多 key/provider，`credentials.max_concurrent`）。
- 401 = 凭证不授权该模型（如 coding-plan key 不含 glm-4-flash）→ 换授权模型或换 key。

### 凭证
`credentials` 表运行时配（**不进代码/seed**）：
- `provider='glm'`：智谱 Coding Plan（`/api/coding/paas/v4`，授权 glm-4.6/glm-4.5）。
- `provider='kimi'`：`api.kimi.com/coding/v1`，模型 `k3`，**temperature 必须 1**。

---

## 4. 数据流（速查）
```
POST /runs → 建 run(pending)+N job+入队 → 立即返回 run_id
worker: job→running → generate(LLM)→score×维(LLM)→写 case_result+scores → job→done → aggregate(原子计数) → run 全终态→completed/failed
POST /runs/{id}/cancel → pending job→cancelled + run→cancelled（在跑的跑完，aggregate 守卫不覆盖 cancelled）
```

---

## 5. 关键表
- `eval_runs`：run 状态机 pending→running→completed/failed/cancelled + 计数。
- `eval_case_jobs`：异步 job（pending→running→done/failed/cancelled），`UNIQUE(run_id,test_case_id)`，`CHECK(status)`。
- `eval_case_results` / `eval_scores`：case 生成结果 + 维度评分。
