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

## 改存量文件（19，全 eval 内部 + 2 接线）

**后端 eval 内部**：`constants.py` / `admin_evaluation.py` / `operator_evaluation.py` / `worker.py` + 对应测试
**前端 eval 内部**：`api/index.ts` / `types/index.ts` / `primitives.tsx` / `RunDetail.tsx` / `Runs.tsx` / `TestCaseEdit.tsx` + 测试
**前端接线**：`App.tsx`（+Observability 路由）/ `AdminLayout.tsx`（+评测监控 菜单项）

> **无共享/核心文件**（`yunwu.py`/`main.py`/`models/__init__`/`requirements`/`conftest` 均在 PR #34 已合并，本分支未再动）。

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
