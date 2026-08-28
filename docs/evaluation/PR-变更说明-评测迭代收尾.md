# 评测模块迭代收尾（真实测试集 + 打磨清单 P0-P3）— PR 变更说明

> 给：项目负责人 + 仓库管理员（郜郜）。
> 范围：`feature/eval-real-testcases` vs `main`（main = `cb3f4ca` = PR #44 合并点）。**20 commits，35 文件，+2420 / −459**。
> 一句话：接入张翀第一批 **10 条真实测试集**（方案 A 纯业务数据），修复验收发现的 **8 个 bug + 编辑页数据破坏隐患**，完成打磨清单 **P0-P3**（评分可信度/体验/失败重跑/系统性测试）+ PM 验收追加项（场景变体 UI 隐藏）。**业务代码改动收敛在评测模块 5 个文件**；全部测试经两轮独立 review（scorer 4 项 + tc 7 项，全修闭环）。

郜郜重点关注：**§1 改了哪些已有文件（5 个后端 + 12 个前端）**、**§4 部署（有 DB 迁移 057）**。

---

## §1. 改了哪些「已有文件」

### 后端生产代码（5 个，全部在 `app/evaluation/` 模块内，不碰主工程）

| 文件 | 改了什么 | 为什么 | 风险 |
|---|---|---|---|
| `services/scorer.py` | 评分 prompt 首尾加 JSON 格式守卫；解析失败自动纠错重评 1 次；两次均失败**抛错走 case 失败路径**（不再落兜底 1 分污染数据） | run21 实测 20 条评分 4 条 parse 失败落假 1 分进对比均值 | ⚠️ 行为变化：双失败 case 现在标 failed（可重跑）而非落 1 分——**这是有意的数据可信度修复**。经独立 review 4 项修正（含"重试 prompt 尾守卫"） |
| `services/scheduler.py` | `trigger_run` 透传用户自定义运行名（此前硬编码丢弃） | 用户填的运行名表单必填却不入库 | 低（加参数，不传行为不变） |
| `routers/operator_evaluation.py` | ① 分数/权重 Decimal→float（白屏根因）② 运行名透传 ③ scores 带 `dimension_name`（徽章显示名）④ 新增 `POST /runs/{id}/jobs/{job_id}/retry` + `GET /runs/{id}/jobs`（失败重跑） | 全部来自 PM 验收报的 bug | 低（新增端点不影响存量；Decimal 修复让 API 返回真数字） |
| `routers/admin_evaluation.py` | 维度 `default_weight` Decimal→float（同白屏根因） | 同上 | 低 |
| `worker.py` | `retry_failed_job`（手动重跑逻辑）+ `retry_delay=60s`（429 限流退避） | run20 有 5 case 因 kimi 429 失败，arq 默认 0s 立即重试继续撞限流 | 低（worker 独立进程，重启生效） |

### 前端（12 个，全部 `evaluation/` + 1 个布局）

| 文件 | 改了什么 | 风险 |
|---|---|---|
| `pages/TestCases.tsx` | 标签筛选接线到后端（此前纯摆设）+ 筛选中下拉选项冻结 | 低 |
| `pages/TestCaseEdit.tsx` | **整页重写**：旧表单四件套（selling_points/messages）→ 方案 A 四业务字段（达人/人设/产品信息/参考脚本）。旧表单回填全空且**保存会破坏真实数据** | ⚠️ 行为变化：编辑页字段布局变了（对齐数据契约，用户已实测确认） |
| `pages/Runs.tsx` | "进行中" = pending+running；新建抽屉标签命中数实时预览（"将命中 N 条"） | 低 |
| `pages/RunDetail.tsx` | d4 徽章→维度显示名（雷达图/校准弹窗同步）；失败 case 行显示错误+「重跑」按钮；行聚合并入"生成即失败"的 job 行 | 低 |
| `pages/Compare.tsx` | 手输 run id → 下拉选择（名称/状态/日期，默认预选最近两次完成）；**顺带修存量 bug：direction 枚举错位**（后端 up/down/same vs 前端 improve/worsen/flat，方向判断从未生效） | 低 |
| `layouts/OperatorLayout.tsx` + `App.tsx` | 侧边栏加「评分标准」直达入口（路由双挂载） | 低 |
| `pages/Dimensions.tsx` | 隐藏「场景变体」UI（预留机制未启用造成困惑，PM 拍板隐藏；数据逻辑保留） | 低 |
| `types/index.ts` / `api/index.ts` | 类型与 API 函数同步（dimension_name/job 字段/retryJob/listRunJobs） | 低 |
| 5 个测试文件 | 适配上述交互 + 新增回归用例 | 仅测试 |

> **0 改动**：CI/`.github`、CLAUDE.md/AGENTS.md、依赖、conftest、主工程任何路由。

---

## §2. 新增文件（18 个）

**后端（3）**
- `scripts/seed_eval_testcases_real.py` — 张翀 10 条真实测试例（纯业务 input_payload，幂等 upsert，`真实数据` 溯源 tag）
- `migrations/057_eval_testcases_real_data.sql` — 剥离全库 `input_payload.messages` 死字段（generator 从不读）+ 停用 13 条 demo 占位例
- `tests/unit/evaluation/test_seed_eval_testcases_real.py` — 8 个数据契约测试

**文档（5）**
- `docs/evaluation/张翀真实测试集-集成方案说明.md`（方案 A/B/C 对比与 PM 拍板存档）
- `docs/evaluation/测试报告-真实测试集集成.md`
- `docs/evaluation/迭代收尾-待确认事项与改动说明.md`（六项需求裁决 + 本 PR 改动明细）
- `docs/evaluation/评分维度动态化-需求确认清单.md`（六轮讨论考古）
- `docs/superpowers/specs/2026-08-27-eval-scoring-strategy-design.md`（策略层设计，**只存档不实施**——PM 决定保持单一标准）
- `docs/evaluation/评测后续迭代路线图.md`（PM 0828 裁决落档：近期 3 项/中期 3 项/远期 4 项）

**其余**：前端测试重写/新增（TestCaseEdit 7 用例等）

---

## §3. 交付内容明细（按 commit 时间序）

| 阶段 | 内容 | 关键验证 |
|---|---|---|
| **真实测试集** `483c56e` | 10 条真实例（羊羊×3/暖暖×3/姜周周×2/可可×2）；demo 全停用；messages 死字段全库清理 | 契约测试 8/8；dev 库迁移前后对比；全量 1994 passed 门禁全绿 |
| **验收 bug 修复** `8f22778`/`b5e7479`/`0d6c4e3`/`2822328` | 标签筛选失效 / "进行中"漏 pending run / 详情页白屏（Decimal→字符串）/ 运行名被丢弃 | 每个三层验证：单测回归 + tsc + Playwright 浏览器实测 |
| **P0 评分可信度** `4f74dae`+`e104763` | JSON 首尾守卫 + 解析失败重评 1 次 + 双失败抛错（宁重跑不落污染分） | 49 单测 + **独立 review（REQUEST_CHANGES 4 项全修）** + run55 E2E 10/10 真实模型全链路 |
| **P1 体验** `9ca053d` | 对比下拉选 run / 标签命中预览 / 评分标准入口 + 维度徽章显示名 / direction 枚举修复 | 98 前端测试 + 浏览器五点实测（对比 8.20→8.78 方向 7/2/1） |
| **P2 稳定性** `a94187c` | 失败 case 单独重跑（端点+按钮+计数修正）/ 429 退避 60s / 失败行可见 | 64 后端 + 99 前端 + **E2E：run20 job62 点重跑→done，failed 5→4** |
| **P3 系统性测试** `9fea7cb` | 三模块全部提交类操作接口测试 13/13；**修复编辑页字段错位**（保存即毁数据的隐性 bug） | 接口 13/13 + 编辑页 7/7 + 浏览器实测 case22 四字段全回填 |
| **PM 验收追加** `955df12` | 隐藏维度页「场景变体」UI（预留机制未启用造成困惑，PM 拍板 B；数据逻辑保留，策略层启动时放开） | Dimensions 17/17 + 全量 93/93 + 浏览器实测无残留 |
| **覆盖率劣化补测** `1af05a6` | P3 的 13 项 curl 实测转 pytest 集成测试（retry 四路负路径/jobs/cancel/case_results 附 job 字段/scores 附维度名）计入覆盖 | operator_evaluation 覆盖 65%→71%；全量 2014 passed |
| **tc 独立 review** `873edb3` | reviewer 7 项发现全修：🔴固定命名 flake（实证复现）/弱化重复测试删除/id(self)→uuid/补 503+OperationLog 断言/FE 死代码+label 歧义/seed 注释对齐实现 | operator_evaluation 53/53 + worker 19/19 + seed 8/8 + 全量 2013 passed / 0 failed |

---

## §4. 部署（郜郜必读）

1. **DB 迁移**：`bash backend/scripts/run_migrations.py`（或按序执行 `057_eval_testcases_real_data.sql`）——幂等可重跑
2. **灌真实测试集**：`cd backend && python scripts/seed_eval_testcases_real.py`（幂等 upsert；**dev 库已执行过**，生产首次执行会插入 10 条 + 停用 demo）
3. **重启 worker**：`arq` 进程需重启（retry_delay / retry_failed_job 生效）：`pkill -f "arq app.evaluation" && REDIS_URL=... arq app.evaluation.worker.WorkerSettings`
4. **重启 web**：uvicorn 正常发布（无新 env、无新依赖）
5. **前端**：正常构建发布

**无新增**：依赖 / env 变量 / 新进程 / 新表（057 只是数据修正，无 DDL）。

---

## §5. 风险与回滚

- 业务代码改动**全部收敛在 `app/evaluation/`**（5 文件）+ 前端 `evaluation/`（11 文件）——主工程零改动
- 回滚：revert PR 即可；DB 侧 demo 停用/messages 清理不影响历史 run 读取（快照在 case_result.input_snapshot）
- 两处**有意的行为变化**（见 §1 ⚠️）：双 parse 失败改抛错（数据可信度）、编辑页表单重写（对齐契约）——均有 PM 实测确认

---

## §6. 质量数据

- 后端：`tests/unit + tests/integration` = **2013 passed / 0 failed**（新增 ~80 用例），覆盖率门禁 6 目录全 PASS（对比 #44 基线无实质劣化：services +0.2 / routers −0.1 波动 / adapters −0.7 为非本 PR 的测量波动）
- 前端：evaluation 页面 **93 passed** + tsc 0 错
- E2E：run55（评分守卫 10/10 真实模型）、run20（重跑闭环 failed 5→4）、case22（编辑页回填）
- 独立 review ×2：P0 scorer 修复 4 项全修；测试代码 7 项全修（含实证复现的 flake）
- P3 接口实测 13/13（三模块全部提交类操作）
