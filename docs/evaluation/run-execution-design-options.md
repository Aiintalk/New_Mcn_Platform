# AIGC 评测 — Run 执行架构选型评估报告

> 2026-07-24 · PM 草拟 · 待选型确认后进入 spec/实施
>
> 背景：当前 `POST /runs` 同步 `await scheduler.trigger_run(...)`，5 case × 4 次 LLM 调用 ≈ 4 分钟，
> 请求阻塞直到 run 跑完才返回 → HTTP 超时、浏览器转圈、无法管理。需重新设计为**离线后台执行 + web 端 run 管理**。

---

## 0. 目标与非目标

**必须满足**
- 触发即返回（POST 立即拿到 run_id），**浏览器关闭/刷新不影响 run 继续**。
- web 端可管理 run：列表、详情、状态、（可选）取消。
- run 状态可查、可轮询（前端展示进度）。

**应满足（强烈建议）**
- **进程重启不丢 run**（PM2 reload / 崩溃 / 部署时，进行中的 run 能恢复或重跑，不白烧 LLM token）。

**非目标（一期）**
- 高并发/高吞吐（eval run 是低频手工/定时批，非线上高 QPS）。
- 多机水平扩展（单机 PM2 即可）。

---

## 1. 现状盘点

| 项 | 现状 |
|---|---|
| 触发方式 | `await scheduler.trigger_run()` 同步阻塞请求（router L397） |
| 已有异步手段 | `asyncio.create_task`（字幕批处理）、`BackgroundTasks`（intake/persona）——**全是进程内、重启即丢** |
| 外部队列/worker | **无**（无 Redis、无 Celery/arq/RQ） |
| 部署 | 单 Ubuntu、PM2 管进程、Postgres 18 |
| run 状态机 | `eval_runs.status`：pending→running→completed/failed（字段已具备） |
| run 列表接口 | **缺**（`GET /runs` 列表未实现，前端用 localStorage 兜底 → frontend-issues.md #1） |

关键：**执行模型本身要换**（同步→异步离线），不止加个 list 接口。

---

## 2. 候选方案

### 方案 A：进程内后台任务（`asyncio.create_task`）
**做法**：router 建 run 行（status=pending）+ commit → 立即返回 run_id → `asyncio.create_task(runner.execute_run(run_id))` 在 FastAPI 事件循环里跑。与现有字幕批处理一致。

### 方案 B：DB 驱动 + 进程内 worker 循环（持久化）
**做法**：run 全部是 DB 行（status=pending）。一个在 `lifespan` 启动的常驻 asyncio worker 循环：轮询 `eval_runs WHERE status='pending'` → 取一条置 running → 执行 → 写 completed/failed。**启动时恢复**：把上次崩在 `running` 的（无 finished_at 且超时）重置回 pending。

### 方案 C：独立 worker 进程 + 任务队列（arq + Redis）
**做法**：FastAPI 把 run_id 投到 Redis 队列（arq/Celery/RQ）→ 独立 worker 进程消费执行 → 回写 DB 状态。web 与 worker 进程分离。

### 方案 D（备选）：subprocess/systemd per-run
每次触发 spawn 一个 `python -m app.evaluation.worker <run_id>` 子进程。隔离彻底，但进程管理/监控/背压都难，异步栈里不自然。**不推荐**，仅列出。

### 方案 E（备选）：Postgres LISTEN/NOTIFY
PG 当队列（worker LISTEN 通道，触发 NOTIFY）。免 Redis，但 NOTIFY 是即发即弃（worker 挂了就丢）→ 仍需轮询兜底，复杂度高于 B。**不推荐**。

---

## 3. 对比矩阵

| 维度 | A. create_task | B. DB+worker循环 | C. arq+Redis |
|---|---|---|---|
| 浏览器关闭后继续 | ✅ | ✅ | ✅ |
| **进程重启后继续/恢复** | ❌ 丢 | ✅ 恢复 | ✅ |
| 进程隔离（web 崩≠run 崩） | ❌ 同进程 | ❌ 同进程 | ✅ 独立 worker |
| 并发/并行 | 受限（共享事件循环，建议串行） | 受限（单 worker，可限并发 N） | ✅ 多 worker 扩展 |
| 新基础设施 | 无 | 无 | **需引入 Redis** |
| 运维成本 | 低 | 低 | 中-高（broker+worker 进程+监控） |
| 开发量 | **小** | 中 | 大 |
| 与现有栈契合 | 高（沿用字幕批处理模式） | 高（FastAPI async + PG） | 中（新增 Redis + worker 部署） |
| 失败/中断恢复 | 无 | DB 重置 stuck→pending | 队列重投 |
| run 可观测 | DB status | DB status + worker 日志 | 队列 + DB |

---

## 4. 推荐与理由

### 🏆 推荐：**方案 B（DB 驱动 + 进程内 worker 循环 + 启动恢复）**

**为什么不是 A**：A 不满足"进程重启不丢"。eval run 一次 4 分钟、烧真金白银的 LLM token，PM2 reload 部署 / 崩溃时丢一条 = 浪费。用户明确要"离线、稳健"。

**为什么不是 C**：引入 Redis + 独立 worker 是为"高并发/水平扩展"付费，但 eval run 是**低频批**（手工 + 定时），单 worker 完全够用。当前项目零 Redis 基建，C 的运维/开发成本与收益不匹配——属于"将来 run 量级上去 / 要 web-worker 物理隔离"时再升级的路径。

**B 的核心收益**：
- **持久**：run 是 DB 行，重启后启动恢复逻辑把 stuck 的 running 重置 pending 重跑。
- **零新基建**：复用 Postgres + FastAPI lifespan，不引入 Redis。
- **契合栈**：FastAPI async + 已有 `eval_runs.status` 状态机，worker 循环天然异步（run 是 IO 密集——等 LLM，不抢 CPU）。
- **够用**：低频批，单 worker 顺序执行（或限并发 1~2）即可；要扩时再上 C。

**B 的代价/风险**：
- 单 worker → 多 run 排队（可接受，低频）。
- worker 与 web 共进程 → 一个 run 里若抛未捕获异常需兜底（已有 case 级隔离，再加 run 级 try）。
- 轮询间隔 trade-off（建议 3~5s，run 低频无压力）。

### 何时升级到 C
- run 频率显著上升（如几十个 KOL 并发定时回归）。
- 需要 web 与 worker **物理隔离**（web 挂了 run 仍跑）。
- 要多机扩展。

---

## 5. 选定 B 后的实施轮廓（确认选型后再细化成 spec）

### 5.1 数据流
```
浏览器 POST /runs ──► router: 建 eval_runs(status=pending) + commit ──► 立即返回 run_id
                                       │
                  (lifespan 常驻) worker_loop 每 ~4s:
                       SELECT pending run (LIMIT 1, FOR UPDATE SKIP LOCKED)
                       → status=running, started_at
                       → runner.execute_run(run_id)  # 复用现有 runner（已修事务/role）
                       → status=completed/failed, finished_at
浏览器 GET /runs（列表）/ GET /runs/{id}（详情+进度） ◄─ 轮询 status
```

### 5.2 改动清单（预估）
1. **scheduler/runner**：`trigger_run` 拆成"建 run(pending) + commit + return id"，**不再 await execute_run**。
2. **worker_loop**（新）：`app/evaluation/services/worker.py`，lifespan 启动；含启动恢复（running 且 started_at 超时 → pending）。
3. **router**：`POST /runs` 改为返回 pending run；新增 `GET /runs` 分页列表（补 frontend-issues #1）。
4. **main.py lifespan**：启动 worker_loop（asyncio.create_task），优雅关闭（shutdown 取消）。
5. **前端 Runs 页**：列表接 `GET /runs`（去掉 localStorage 兜底）；详情轮询 status 直到 completed/failed。
6. **并发限制**：worker 同时跑 1（或配置 N），避免凭证 active_requests 抢占。

### 5.3 测试 + e2e 计划
- **单测**：worker_loop 的"取 pending / 启动恢复 / 状态流转 / 异常兜底"。
- **集成**：触发后立即返回 pending → 轮询到 completed → 评分落库。
- **重启恢复 e2e**：run 卡 running → 重启 worker → 自动重置 pending 重跑（这条是 B 区别于 A 的关键，必须有测试）。
- **web e2e**（Playwright，需后端栈起来）：列表/详情/触发/进度轮询。

---

## 6. 待你拍板
1. **执行架构选 A / B / C？**（推荐 B）
2. worker **并发度**：1（顺序，最稳）还是 2~3？
3. **取消 run**（web 端中止进行中的 run）一期要不要？（B 下可做：加 status=cancelling，worker 每轮检查）
4. 选定后我走 spec（数据流 + 改动清单细化 + DDL 变更）→ brainstorm review → TDD 实现。
