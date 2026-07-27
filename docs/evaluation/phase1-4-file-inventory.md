# AIGC 评测体系 — Phase 1-4 文件清单（vs main 主干）

> **分支**：`feature/aigc-evaluation-v2`  
> **对比基准**：`main`（PR #33 尚未合并）  
> **生成时间**：2026-07-22  
> **测试**：177 passed, 0 failed，覆盖率全部门禁达标

---

## 一、后端代码 — 评测模块（全部新增，`backend/app/evaluation/`）

| 文件 | 模块 | 功能 | 行数 |
|------|------|------|------|
| `constants.py` | 常量 | tool_code / 枚举 / 默认值 | 36 |
| `adapters/__init__.py` | 适配器 | 包标记 | 15 |
| `adapters/base.py` | 适配器 | LLMAdapter Protocol 接口 | 33 |
| `adapters/registry.py` | 适配器 | adapter_registry（一期 yunwu） | 30 |
| `adapters/yunwu.py` | 适配器 | YunwuAdapter 委托现有 yunwu | 43 |
| `models/__init__.py` | 数据模型 | 汇总 import 11 个 ORM 类 | 30 |
| `models/dimension.py` | 数据模型 | eval_dimensions 评分维度 | 38 |
| `models/rubric.py` | 数据模型 | eval_rubrics 评分细则 | 54 |
| `models/test_case.py` | 数据模型 | eval_test_cases 测试集 | 38 |
| `models/version.py` | 数据模型 | eval_versions 版本快照 | 50 |
| `models/run.py` | 数据模型 | eval_runs 评测运行 | 51 |
| `models/case_result.py` | 数据模型 | eval_case_results 生成结果 | 44 |
| `models/score.py` | 数据模型 | eval_scores 维度评分 | 50 |
| `models/human_label.py` | 数据模型 | eval_human_labels 人工校准 | 37 |
| `models/schedule_policy.py` | 数据模型 | eval_schedule_policies 调度策略 | 42 |
| `models/strategy.py` | 数据模型 | eval_strategies 评测策略（三件套 override） | 63 |
| `models/judge_model.py` | 数据模型 | eval_judge_models 评委候选池 | 51 |
| `services/__init__.py` | 核心服务 | 包标记 | 0 |
| `services/rubric_resolver.py` | 核心服务 | rubric → 评分 prompt 渲染 | 69 |
| `services/generator.py` | 核心服务 | 两步 prompt 渲染 + 生成 | 86 |
| `services/scorer.py` | 核心服务 | JSON 解析三策略 + 评分 | 155 |
| `services/comparator.py` | 核心服务 | 版本对比（test_case_id 对齐） | 209 |
| `services/runner.py` | 运行编排 | run 编排 + resolved_scoring + case 隔离 | 321 |
| `services/scheduler.py` | 运行编排 | 手动 / 自动触发入口 | 112 |
| `schemas/__init__.py` | API Schema | Pydantic 汇总 | 59 |
| `schemas/dimension.py` | API Schema | 维度请求 / 响应 | 57 |
| `schemas/rubric.py` | API Schema | rubric 整批替换 | 40 |
| `schemas/test_case.py` | API Schema | 测试集请求 / 响应 | 54 |
| `schemas/version.py` | API Schema | 版本创建 / clone（含 source_kol_id） | 81 |
| `schemas/run.py` | API Schema | 运行触发 / 状态 | 47 |
| `schemas/score.py` | API Schema | 评分响应 / 人工校准 | 41 |
| `schemas/schedule_policy.py` | API Schema | 调度策略请求 / 响应 | 47 |
| `schemas/compare.py` | API Schema | 对比报告响应 | 36 |
| `routers/__init__.py` | API 路由 | 包标记 | 7 |
| `routers/admin_evaluation.py` | API 路由 | admin 端 15 个接口（维度 / rubric / 版本 / 调度） | 746 |
| `routers/operator_evaluation.py` | API 路由 | operator 端 10 个接口（测试集 / 运行 / 校准 / 对比） | 569 |
| **小计** | | **35 个文件** | **~4,234** |

---

## 二、数据库迁移（新增）

| 文件 | 功能 | 行数 |
|------|------|------|
| `migrations/053_eval_core.sql` | 11 张 CREATE TABLE + 索引 + 3 条部分唯一索引 + seed（3 维度 + 15 rubric + 1 default 策略） | 338 |

---

## 三、现有文件变更（最小侵入，仅追加）

| 文件 | 变更内容 | 增 / 删 | 说明 |
|------|---------|---------|------|
| `app/main.py` | 追加 2 行 import + 2 行 include_router | +4 / -0 | 注册 eval 两个 router |
| `app/models/__init__.py` | 追加 11 个 eval model import + `__all__` | +24 / -0 | 跨包注册触发 metadata.create_all |
| `requirements.txt` | 追加 `croniter>=1.4.0` | +1 / -0 | cron 校验新依赖 |
| `tests/conftest.py` | `_SESSION_LOCAL_PATCH_TARGETS` 追加 2 行 | +3 / -0 | runner / scheduler patch（红线 #7） |

---

## 四、测试文件（全部新增）

| 文件 | 测试内容 | 用例数 | 行数 |
|------|---------|--------|------|
| `unit/models/test_eval_models.py` | ORM 建表 + CRUD + 唯一约束 + 级联 | 20 | 464 |
| `unit/services/test_eval_rubric_resolver.py` | 占位符渲染 + rubric 拼接 | 14 | 171 |
| `unit/services/test_eval_generator.py` | 两步渲染 + soul←persona + mock | 17 | 222 |
| `unit/services/test_eval_scorer.py` | JSON 三策略 + clamp + mock | 31 | 278 |
| `unit/services/test_eval_comparator.py` | 跨 run 对齐 + diff + ↑↓→ | 13 | 428 |
| `unit/services/test_eval_runner.py` | resolved_scoring + case 隔离 + 权重三级 | 12 | 694 |
| `unit/services/test_eval_scheduler.py` | 手动触发 + default 策略绑定 | 4 | 252 |
| `integration/routers/test_admin_evaluation.py` | admin 15 端点 + 关联维护 + croniter + 鉴权 | 39 | 930 |
| `integration/routers/test_operator_evaluation.py` | operator 10 端点 + 人工校准事务 + 对比 | 27 | 814 |
| **小计** | | **177** | **~4,253** |

---

## 五、文档（全部新增，v1 保留不动）

| 文件 | 用途 | 行数 |
|------|------|------|
| `specs/2026-07-20-aigc-evaluation-system-design.md` | v2 完整技术设计（14 章） | 1,598 |
| `plans/2026-07-20-aigc-evaluation.md` | v2 分阶段实施计划（6 Phase） | 272 |
| `evaluation/weekly-alignment-summary-v2.md` | 白话概要（安雅 / 周会讲述用） | 215 |
| `evaluation/scoring-alignment-anya.md` | 安雅评分填表模板（维度 / 权重 / rubric） | 158 |
| `evaluation/data-model-diagram-v2.html` | 11 张表关系图（浏览器可开） | 174 |
| `evaluation/weekly-alignment-summary.md` | v1 概要（仅追加 v2 指针，+5 行） | +5 |

---

## 六、汇总

| 类别 | 文件数 | 行数 | 说明 |
|------|--------|------|------|
| 后端代码 | 35 | ~4,234 | 全部在 `app/evaluation/`，独立模块 |
| 数据库迁移 | 1 | 338 | 053_eval_core.sql |
| 现有文件变更 | 4 | +32 / -0 | main.py / models/__init__ / requirements / conftest（追加，不改逻辑） |
| 测试 | 9 | ~4,253 | 177 个用例，全绿 |
| 文档 | 6 | ~2,422 | spec / plan / 概要 / 填表 / 图 |
| **合计** | **55** | **~11,279** | |

---

## 关键设计落地确认

| 设计点 | 状态 | 验证方式 |
|--------|------|---------|
| 模块独立（不动现有代码） | ✅ | 现有文件仅 +32 行追加，零逻辑改动 |
| 权限分离（admin / operator） | ✅ | admin 路由 require_admin，operator 路由 require_operator |
| 适配器方案 B（registry 归 runner） | ✅ | generator/scorer 纯函数收 callable，不经 registry |
| resolved_scoring 持久化 | ✅ | run.metadata['resolved_scoring'] 写入 + 测试断言 |
| 版本快照关联维护 | ✅ | resolve_prompt/kol_context 三步 + source_kol_id |
| 评委三件套覆盖 | ✅ | scoring_model/provider/adapter override |
| eval_rubrics UNIQUE | ✅ | NULLS NOT DISTINCT + 测试 IntegrityError |
| convention_guard | ✅ | 6/6 通过 |
| 不读 ai_models/credentials | ✅ | model_id 字符串自管，adapter 内部处理凭证 |
| case 级错误隔离 | ✅ | savepoint 回滚单 case，不影响其他 |
| 权重三级覆盖 | ✅ | strategy > version > dimension default |
