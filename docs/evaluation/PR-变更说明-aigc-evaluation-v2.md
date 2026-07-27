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
