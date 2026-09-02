# 评测策略与评分规则动态化 — 需求设计文档

> 分支：`feature/eval-real-testcases`（迭代收尾 PR 之后的下一个功能）
> 日期：2026-08-27
> 状态：✅ 六项需求已由 PM 拍板（见《迭代收尾-待确认事项与改动说明》上篇），本文为落地设计
> 依据：0717 周会（张翀：维度/标准按业务差异化）· 0720 v2 设计稿 §2.8 策略层 · 安雅 0726 评分标准初稿（已入库并逐字校验）· PM 0827 六项裁决

---

## 〇、一句话目标

把已预留但未启用的**策略层**激活：让不同业务（护肤/食品/剧情号…）可以用**各自的套餐**——不同的测试例子集、不同的 rubric 场景变体、不同的维度权重、不同的评委配置——跑各自的评测；同一 run 内规则严格统一（PM 裁决③：case 彼此可比是第一性原则）；规则变更可追溯（轻量快照）。

## 一、已拍板的六项裁决（设计约束）

| # | 裁决 | 设计含义 |
|---|---|---|
| ① | 四维度定稿（安雅 0726 初稿） | 维度表不动，`scoring-alignment-anya.md` 等旧文档标注过时 |
| ② | **套餐制起步** | 策略 = 套餐；一期只建业务级策略（4-8 种），不做 per-红人配置 UI；`strategy.kol_id` 字段保留但一期不用 |
| ③ | **策略统一挑**（run 内一套标准） | rubric 变体在策略里按维度选定；runner 不做 per-case 匹配 |
| ④ | **轻量版本化** | run 创建时把规则快照写进 metadata；对比报告标注规则差异；不做重放 |
| ⑤ | 安雅标准已到位 | rubric 内容零变更启动；品类变体（美妆/减肥）由内容方后续在 UI 里补 |
| ⑥ | 入口可达 | 运营侧边栏加「维度与评分标准」直达；RunDetail 徽章 d4→维度显示名 |

## 二、用户故事（谁用这套东西）

- **张翀/安雅（业务评测方）**：在管理端建「护肤套餐」策略——从 23 条测试例选护肤相关的子集、钩子力 rubric 用护肤变体（暂无则 default）、权重调成 0.4/0.25/0.2/0.15——之后每次迭代提示词都跑这个套餐，分数纵向可比。
- **安雅（标准维护）**：给种草力维度补一套「美妆变体」rubric（10/8/6/4/2 五档文本），不启用任何策略也能先存着（超集理念：细则在池子里，策略负责挑）。
- **PM（对比决策）**：版本对比页看 v1.3 vs v1.4，两 run 若规则版本不同，页面显著提示"规则已变更，对比仅供参考"。

## 三、功能范围（本 PR 做/不做）

**做**：

1. **策略管理 CRUD**（admin 端点 + 管理页）：创建/编辑/启停/软删策略；配置四件套——①测试例选择器（按标签/按 ID 列表）②rubric 变体选择（每维度选一个 scenario_tag，default 兜底）③维度权重覆盖（合计校验=1.00）④评委三件套覆盖（model/provider/adapter，可留空走版本快照）
2. **运行绑定策略**：新建运行时选策略（默认 default）；`trigger_run` 接受 `strategy_id`
3. **runner 激活变体选择**：`_get_default_rubrics` → 按 `strategy.rubric_selector[dim_id]` 取对应 scenario_tag 的 rubric 行，无该变体或未配置时回退 default（**回退规则固定：选了但变体缺失 → 用 default 并在 run metadata 记录 fallback 明细，不静默**）
4. **轻量规则快照（④）**：run 创建时把 `resolved_rules`（维度集+最终权重+每维度实际使用的 rubric 变体 tag+各档 criteria 摘要哈希）写进 `run.metadata_`；对比页两 run 的 `resolved_rules` 哈希不同 → 顶部黄条警示
5. **入口修复（⑥）**：运营侧边栏（admin 可见评测组）+「维度与评分标准」；RunDetail 维度徽章显示 `开头钩子力 9.0`（悬停 tooltip 显示维度说明），对比页同理
6. **rubric 变体管理增强**：维度管理页的 rubric 编辑支持按 scenario_tag 分组维护（现在只有 default 一组）

**不做**（明确出界）：

- per-红人策略配置 UI（`kol_id` 字段留位）
- 运行时 per-case rubric 匹配（裁决③排除）
- 规则重放/历史重算（裁决④只要轻量）
- 定时策略调度消费（`eval_schedule_policies` 表已有，绑定策略的调度放下一个 PR）
- 安雅的品类变体内容（她的输入，机制就绪后她在 UI 填）

## 四、数据模型（零新表）

全部复用现有表，无迁移（或仅一条轻量迁移给 seed 数据）：

```
eval_strategies（已有 7 个配置字段，一期填 default 之外新增业务策略行）
eval_rubrics.scenario_tag（已有列，从"仅标记"变为"策略可选项"）
eval_runs.metadata_.resolved_rules（新增 JSONB 键，无 DDL）
eval_runs.strategy_id（已有列，一期恒 default → 变为可选）
```

**策略示例**（「护肤套餐」）：
```json
{
  "name": "护肤套餐",
  "business_type": "skincare",
  "test_case_selector": { "tags": ["真实数据", "美妆"] },
  "dimension_weight_overrides": { "4": 0.40, "5": 0.25, "6": 0.20, "7": 0.15 },
  "rubric_selector": { "4": "skincare", "5": "default", "6": "default", "7": "default" },
  "scoring_model_override": null,  // 留空 = 用版本快照里的评委配置
}
```

**test_case_selector 语义**（对齐 `runner.resolve_test_cases` 现有实现，零改动）：
- `{"all": true}`：全部启用样本
- `{"tags": [...]}`：任一命中（runner 已实现 tags overlap，用于「真实数据」这类标签筛业务子集）
- `{"ids": [...]}`：显式 ID 列表（精细拼套餐）
- 组合时 ids ∪ tags（现有实现为 if/elif 优先级，本 PR 不改其解析顺序，前端表单约束只填一种）

**resolved_rules 快照示例**（写入 run.metadata_）：
```json
{
  "strategy_id": 3, "strategy_name": "护肤套餐",
  "dimensions": [
    {"id": 4, "name": "hook_strength", "weight": 0.40,
     "rubric_scenario": "skincare", "rubric_fallback_from": null, "rubric_hash": "a1b2c3"}
  ],
  "rules_version_hash": "9f8e7d"
}
```

## 五、接口设计（admin 端点 + operator 微调）

**策略 CRUD**（`admin_evaluation.py`，require_admin，信封+OperationLog 照红线）：
- `GET    /admin/evaluation/strategies`（分页 + tool_code 筛选）
- `POST   /admin/evaluation/strategies`（校验：权重覆盖合计=1.00（若提供）；rubric_selector 引用的 dimension 存在且 active）
- `PUT    /admin/evaluation/strategies/{id}`（同校验；软删唯一约束 (tool_code,name) 已有）
- `DELETE /admin/evaluation/strategies/{id}`（软删；被 run 引用过的不物理删——run 存的是快照，删策略不影响历史）
- `GET    /admin/evaluation/strategies/{id}/preview`：**保存前预览**——解析选择器返回将命中的测试例列表 + 每维度将实际使用的 rubric 变体（含 fallback 预告）。你 8/19 要的"开始运行前看到选中多少 case"在这里一并实现（运行抽屉选策略后实时调 preview）

**运行侧**（`operator_evaluation.py`）：
- `POST /runs` body 增 `strategy_id`（缺省 default）；校验策略 active
- 前端运行抽屉：加「评测策略」下拉（default + 业务策略），选中非 default 策略时显示 preview（N 条样本 · 权重 · 变体）

**对比侧**：
- `GET /compare` 响应增 `rules_compatible: bool`（两 run resolved_rules 哈希比对）；前端据此渲染黄条

## 六、runner 改造（核心一处）

`runner.py::_get_default_rubrics(db, dim_id)` → `_get_rubrics_for_strategy(db, dim_id, scenario_tag)`：
```python
# 伪码
if scenario_tag and scenario_tag != "default":
    rows = fetch(dim_id, scenario_tag=scenario_tag, active)
    if rows: return rows            # 策略选的变体
    fallback = "default"            # 变体缺失 → 回退并记录
else:
    fallback = None
return fetch(dim_id, scenario_tag=None, active)  # default 变体
```
- execute_case 按维度传入 `strategy.rubric_selector.get(str(dim.id))`
- `resolved_rules` 快照在 `scheduler.trigger_run` 时一次算好写入（run 级，非 per-case，符合裁决③）

## 七、前端页面

1. **管理端新页「评测策略」**（`/admin/evaluation/strategies`，挂"评测配置"组）：列表（名称/业务类型/样本数预览/权重/状态）+ 编辑抽屉（四件套分区：样本范围[radios 全部/按标签/按ID]+权重滑条+rubric 变体下拉[每行一个维度，选项=default+该维度已有变体]+评委覆盖[留空提示走版本]）+ preview 面板
2. **维度管理页增强**：rubric 编辑区按 scenario_tag 分 tab（default 恒在 + 已有变体），新增变体 = 输入 tag 名开新 tab 填五档
3. **运行抽屉**：策略下拉 + preview（样本数/权重/变体一览）
4. **入口（⑥）**：OperatorLayout 评测组加「维度与评分标准」（adminOnly）→ 跳 `/admin/evaluation/dimensions`（AdminLayout 内）；RunDetail/Compare 维度徽章 d4→「开头钩子力」

## 八、错误处理

| 场景 | 行为 |
|---|---|
| 策略选的 rubric 变体不存在 | 回退 default + resolved_rules 记 `rubric_fallback_from` + run 详情页展示"本 run 实际使用规则" |
| 权重覆盖合计 ≠ 1.00 | 创建/编辑策略时 400（Validation） |
| 运行引用的策略被停用 | 触发 run 时 409 提示（历史 run 不受影响，读快照） |
| 变体只有部分档位（如只有 10/8） | 保存 rubric 时校验必须 5 档齐全，否则 400 |
| strategy_id 不存在/非 active | 404/409 |

## 九、测试计划

- **unit**：策略 CRUD 校验（权重合计/维度存在性/rubric 5 档）；`_get_rubrics_for_strategy` 三分支（选中/回退/default）；selector 三语义（all/tags_any/ids）；resolved_rules 哈希稳定性（同规则同哈希）
- **integration**：策略 CRUD 端点（含 401/403/信封）；trigger_run 带 strategy_id → run 绑定 + 快照正确；fallback 场景端到端；compare 的 rules_compatible
- **前端**：策略页（表单校验/preview 交互）、运行抽屉策略选择+样本数显示、徽章显示名、入口可见性（admin 见/运营不见）
- **回归**：全量套件 + 覆盖率门禁（routers/services 不跌破线）

## 十、实施拆分（建议 2 个 commit）

1. `feat(eval): 策略管理 CRUD + runner 变体选择 + 规则快照`（后端全量 + 单测/集成测试）
2. `feat(eval): 策略管理页 + 运行抽屉策略选择 + 入口/徽章修复`（前端 + 对比黄条）

## 十一、风险与依赖

- run.metadata_ 快照体积：20 档 criteria 全文约 4-6KB/run，可接受（只存哈希+档位数，全文不存——需要看全文时按 hash 反查 rubric 表）
- default 策略的 test_case_selector 现为 `{"all": true}`——迁移 057 已停用 demo，真实数据 10 条即"全部启用样本"，语义不变
- 无外部依赖（不装 pgvector、不引入新组件）
