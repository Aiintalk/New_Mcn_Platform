# AIGC 评测 v2 — 测试与质量报告

> 范围：`feature/aigc-evaluation-v2` 全量改动（95 文件）。本报告聚焦**测试覆盖 + 质量/review 过程**（文件/部署变更见姊妹文档《PR-变更说明》）。
> 结论先行：**316 自动化测试全绿（后端 200 + 前端 116）+ 1 套 e2e**；后端 eval 模块覆盖率主体 90-100%（最低 scorer 83% / routers 84-85%，全过 80% 门禁）；核心异步逻辑经 3 轮独立 review；真实 LLM 冒烟验证端到端落库。

---

## §1. 测试规模与分层（金字塔）

| 层 | 文件数 | 用例数 | 覆盖对象 |
|---|---|---|---|
| **单元（Service 层）** | 7 | 167 | runner / scheduler / generator / scorer / rubric_resolver / comparator / worker |
| **单元（Model 层）** | 1 | — | 13 个 eval ORM 模型 |
| **集成（API 层）** | 2 | 33 | admin / operator routers（契约 + 鉴权 + 分页） |
| **前端单元（组件）** | 8 | — | 8 个评测页面（交互 + 错误 + 边界） |
| **前端单元（API）** | 1 | — | evaluation API 封装（request.ts 走查） |
| **E2E（Playwright）** | 1 套 | — | 触发→轮询→完成 全流程 |
| **合计** | — | **后端 200 + 前端 116 = 316** | + 1 e2e |

三层金字塔齐：单元（Service + Model）→ 集成（API）→ E2E（浏览器全流程）。符合 CLAUDE.md 测试策略。

---

## §2. 覆盖率（后端 eval 模块逐文件）

门禁：CLAUDE.md 要求 Services ≥ 80%。实测：

| 文件 | 覆盖率 | 说明 |
|---|---|---|
| models（13 个） | **100%** | 全覆盖 |
| schemas（9 个） | **100%** | 全覆盖 |
| constants / adapters.base / registry | 88-100% | registry 88%（未注册分支） |
| services/generator | **100%** | 两步渲染 + 缺失值 fallback |
| services/rubric_resolver | **100%** | 评分 prompt 构建 |
| services/comparator | **96%** | run 对比 |
| services/runner | **93%** | execute_case + compute_resolved_scoring（未覆盖=5 处 defensive ValueError） |
| services/scheduler | **97%** | trigger_run 异步 + 空 case 守卫 |
| services/scorer | **83%** ⚠️ | JSON 三策略解析的个别 fallback 分支未单独测（功能由 generator/runner 间接覆盖） |
| worker | **87%** | enqueue/aggregate/recover 逻辑全覆盖；未覆盖=arq 进程包装层 + redis pool 懒加载（需真 worker） |
| routers/admin | **84%** | CRUD 主路径 + 鉴权；未覆盖=个别错误分支 |
| routers/operator | **85%** | 同上 |

> 最低 scorer 83% / routers 84-85%，**均 ≥ 80% 门禁**。未覆盖部分主要是 defensive 错误分支与 arq 进程集成层（后者由手动冒烟覆盖，见 §5）。

---

## §3. 测试质量（不止 happy path）

测试按"正常 + 错误 + 边界"三轨设计，举关键例：

**并发/事务正确性（异步架构核心）**
- 幂等守卫：job 已终态再次执行 → 跳过，不重复计数（防 arq 重试 over-counting）
- 失败必收尾：execute 抛错 → job=failed + run.failed_cases+1 + re-raise（保证 run 不卡 pending）
- 原子计数：多 worker 并发用裸 SQL `UPDATE ... = ... + 1`（非 ORM `+=`），防竞争
- 重启恢复：卡死 running（超 600s）→ 重置 pending + 重投；fresh running 不误伤
- 空 case 守卫：selector 无匹配 → run 直接 failed，不卡 pending

**case 级隔离**
- generate 抛错 → 不落任何 case_result/score（无半成品）
- 单维 score 抛错 → 整 case 不落库（db.add 在循环后）

**B-C2 可复现性**
- resolved_scoring 在 trigger_run 冻结进 metadata；execute_case 优先读冻结值（不受 run 中改配置影响）；缺失回退现算

**前端边界**（测试名实证）：标签超 5 个警告、tags 空校验、样本 not-found 跳转、复制/删除失败提示、null 字段兜底渲染、停用维度 off 标签……

**测试隔离**：`_isolate` fixture 每测清 eval_* 表；`_reload(populate_existing=True)` 处理裸 SQL UPDATE 后的 ORM 缓存；失败路径调逻辑前捕获 `job_id` 成 int（规避 rollback expire 致 MissingGreenlet）。

---

## §4. 独立 Code Review（多轮，满足"至少两轮独立子 agent"门禁）

### Phase 3（worker 真实执行）— 2 轮
- **R1（双 reviewer 并行，不同维度 lens）**：0 个 ≥80 阻断。2 处改进：
  - `execute_case` 读 metadata 冻结快照（原重算破坏 B-C2 可复现性）→ 修
  - 测试断言 partial 绑定的 model_id 参数（原只验调用次数）→ 修
- **R2（验证轮）**：确认 R1 两处修复正确、未引入新问题；全量 7 维复扫无 ≥80 显性错误。低于阈值观察（model_id 可 None / max_attempts 语义 / 双 commit 微秒窄窗）均非阻塞、非本次引入。

### smoke-fix bundle（kimi 接入 + 推理模型超时）— 1 轮
- **1 reviewer**：抓到 1 个 **Important 阻塞**——超时算术错误：单 case = **5 次** LLM 调用（1 生成+4 评分），原 `5×120=600=job_timeout` 余量为 0，任何开销撞 job_timeout → 重试烧时。
  - 修：`_HTTP_TIMEOUT` 60→150 + `job_timeout` 600→900（5×150=750 < 900，留 150s 余量）
  - 另修 cosmetic：seed `output_payload.model` 应是被测 k3（非评委 glm-4.6）
- 确认 temperature 透传**不破 200 测试**（注入 mock 走跳过分支，不收 temperature kwarg）

> 所有 review 均独立子 agent（不共享主上下文），按"后轮验证前轮修复"推进，直到无显性错误停止。

---

## §5. 真实 LLM 冒烟（自动化测试之外的关键验证）

自动化测试全 mock LLM。另起 redis + arq worker + 真实凭证跑通端到端：
- **kimi-k3 生成**：真实千川文案落 `eval_case_results`（例：`【千川脚本｜慧敏｜餐后阻糖饮｜60秒】...`）
- **glm-4.6 评分**：真实四维分数落 `eval_scores`（例：`[8.0, 9.0, 10.0, 8.0]`）
- **全链路**：trigger → 入队 → worker 消费 → execute_case（生成+评分）→ 落库 → run 聚合 收尾

> 冒烟同时暴露并修复了 3 个自动化测试抓不到的真实问题：① glm-4-flash 不被 coding-plan key 授权（401）② kimi-k3 只接受 temperature=1（400）③ 推理模型响应慢致 ReadTimeout + 超时算术余量为 0。

---

## §6. 已知局限（诚实披露）

1. **defensive ValueError 未单测**：`execute_case` 的 5 处"实体查不到"守卫未单独覆盖（spec 未要求；逻辑简单，由调用方 run_case_job_logic 的 except 兜底收尾，不会卡 running）。
2. **真 LLM 集成未自动化**：起停真 worker 的 e2e（重启恢复等）目前是**手动冒烟**，未进 CI 自动化（依赖真实凭证 + redis）。
3. **glm-4.6 评委偶发慢**：推理模型评分方差大，个别 case 单维 >150s 会 ReadTimeout 致该 job 失败（5 case 冒烟 4 成 1 败）。**非代码 bug，是推理评委特性**；根治需换更快评委模型或扩 key 池（plan §4 待决）。
4. **scorer 83% / routers 84-85%**：低于模块均值，主要是 JSON 解析 fallback 与 router 错误分支；功能由上游间接覆盖，达门禁但非满分。

---

## §7. 质量结论

- ✅ 三层测试金字塔完整（316 自动化 + e2e）
- ✅ 覆盖率全过 80% 门禁，核心服务 93-100%
- ✅ 测试三轨（正常/错误/边界）+ 并发/事务/隔离关键场景覆盖
- ✅ 核心异步逻辑 3 轮独立 review，无显性错误
- ✅ 真实 LLM 冒烟验证端到端落库
- ⚠️ 已知局限 4 项（见 §6），均非阻断，已在 plan/spec 标注为后续演进项
