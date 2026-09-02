# M2 Sprint27 后端测试报告：内容分析 Agent 阶段一 v1

> 日期：2026-09-03
> 分支：`codex/content-analysis-agent-dev`（内容分析开发分支）
> 代码对象：`3214024b3ad7dec0b3a2c8813f902be5db153883`（本轮最终代码收口提交）

## 一、结论

最终内容分析聚焦测试 63/63 通过，聚焦覆盖率 97%。最新完整覆盖率门禁在 `backend`（后端目录）执行，收集 2077 条，2076 通过、0 失败、1 跳过、14 条警告，退出码为 0。开发侧离线切片可交主产品经理独立审核。

此结论不包含公共 API（应用编程接口）、正式数据源、数据表/迁移、调度、路由、前端、下游联调、真实项目效果、可读视频完整镜头或真实/付费模型质量。

## 二、环境与隔离

- Python（编程语言）：3.10.9；pytest（Python 测试工具）：9.1.1。
- 数据库只指向本地 `mcn_test`（后端测试库），使用任务指定的 `DATABASE_URL`（数据库连接地址）和 `JWT_SECRET`（测试签名密钥）。
- 未执行生产数据库操作、迁移、外部调用、真实或付费模型调用。
- 覆盖率之外的最大回归显式使用 `--override-ini=addopts=`（清空配置里默认附加参数），避免重复收集覆盖率。
- 3 条静态 fixture（测试固定输入）只是匿名合成内容样本，用于字段/隐私形态检查；它们不含项目关系，不经适配层驱动引擎。多项目关系由 `test_engine.py`（离线引擎单元测试）中的独立匿名合成对象验证。

## 三、执行记录

### 1. 最终内容分析聚焦测试

```bash
cd backend
env DATABASE_URL=postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test JWT_SECRET=test-secret .venv/bin/python -m pytest tests/unit/services/content_analysis -q --override-ini=addopts=
```

> 中文说明：在后端目录运行内容分析专项单元测试，只连接本地测试库，并关闭默认覆盖率参数。

- 最终结果：63 通过，0 失败，耗时 0.10 秒，退出码 0。
- 根会话最新专项覆盖率证据：97%。

### 2. 早期错误工作目录失败证据（非最终验证）

> 历史代码对象：`602c2fee0a6dda58f84a459d8f6294068f8b6e48`（早期内容分析收口提交）。

```bash
env DATABASE_URL=postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test JWT_SECRET=test-secret backend/.venv/bin/python -m pytest backend/tests/unit backend/tests/integration -q --override-ini=addopts=
```

> 中文说明：这是较早代码在仓库根目录运行的记录。既有迁移测试用后端目录相对路径读文件，因此在仓库根目录失败；它只用于保留历史失败证据，不是最终验证。

| 通过 | 失败 | 跳过 | 警告 | pytest 计时 | 墙钟计时 | 退出码 |
|---:|---:|---:|---:|---:|---:|---:|
| 2050 | 1 | 1 | 15 | 421.77 秒 | 423.80 秒 | 1 |

唯一失败：`test_055_is_idempotent_and_preserves_historical_nulls`（验证 055 迁移可重复执行且保留历史空值的测试）从相对路径读取 `migrations/055_kol_persona_profile_unification.sql`（达人档案统一迁移文件），发生 `FileNotFoundError`（找不到文件错误）。这不是内容分析实现失败，也不取代下方最新完整门禁结果。

### 3. 最新完整覆盖率门禁（最终证据）

```bash
cd backend
env DATABASE_URL=postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test JWT_SECRET=test-secret .venv/bin/python scripts/run_coverage.py --gate
```

> 中文说明：在正确后端目录运行仓库覆盖率脚本，同时执行单元与集成测试，检查整体和六个代码分层的最低覆盖率。

| 收集 | 通过 | 失败 | 跳过 | 警告 | pytest 计时 | 退出码 |
|---:|---:|---:|---:|---:|---:|---:|
| 2077 | 2076 | 0 | 1 | 14 | 431.51 秒 | 0 |

### 4. 最终新增关键场景

- 每账号独立取最近 3 日千川点赞前 3，接入主引擎后由项目再筛 0—3；第 4 名不回填、不入库。
- 六类封闭价值信号：`early_data_strength`（早期数据强）、`relative_benchmark_outperformance`（相对基准表现更优）、`novel_topic_or_structure`（新选题或新结构）、`clear_traffic_hook`（清晰流量钩子）、`reusable_conversion_structure`（可复用转化结构）、`notable_shot_performance`（值得关注的镜头表现）。
- 结构化适配理由覆盖 `project_persona`（项目人设）、`target_users`（目标用户）、`content_plan`（内容规划）和 `operating_direction`（运营方向）。
- 待入库候选要求视频引用+转写双证据追溯。
- 平台内容编号与外部链接的交叉去重，以及跨账号稳定身份冲突拦截。
- `FAILED`（失败）和近期 `SUCCESS_WITHOUT_CONTENT`（成功且无内容）旧载荷过滤，`PARTIAL_SUCCESS`（部分成功）显式限制。
- 待入库候选自包含结构化项目适配理由和六类价值依据。

## 四、覆盖率明细

| 分层 | 实际 | 目标 | 结果 |
|---|---:|---:|---|
| `app/core/`（核心基础设施） | 100.0% | 90% | 通过 |
| `app/models/`（数据模型） | 100.0% | 90% | 通过 |
| `app/services/`（业务服务） | 89.4% | 80% | 通过 |
| `app/routers/`（接口路由） | 73.0% | 70% | 通过 |
| `app/adapters/`（外部服务适配器） | 80.3% | 60% | 通过 |
| `app/middlewares/`（请求中间件） | 100.0% | 90% | 通过 |
| 整体 | 79.8% | 48% | 通过 |

最新门禁脚本报告整体覆盖率 79.8%，六个分层全部通过。

最新内容分析聚焦覆盖率为 97%；本次不使用早期逐文件数值，避免把旧代码统计当成最终证据。

## 五、警告与跳过项

- 14 条警告均来自 `tests/unit/services/test_tikhub_adapter.py`（TikHub 适配器单元测试），对应 `RuntimeWarning`（运行时警告）：模拟的异步调用没有被等待。它们在本轮内容分析目录之外，未做无关修复。
- 历史根目录运行额外触发 1 条 `DeprecationWarning`（弃用提醒），来自直播复盘测试文档字符串里的 `\s`（正则空白符简写）；最新完整门禁共记录 14 条警告，未包含这条弃用提醒。
- 1 条跳过为 `test_oss_upload_download_delete_round_trip`（对象存储真实上传、下载、删除往返测试），需真实 OSS（对象存储）凭证，不在本轮允许的外部调用范围。

## 六、静态检查与测试副作用

```bash
backend/.venv/bin/python -m compileall -q backend/app/services/content_analysis backend/tests/unit/services/content_analysis
git diff --check
```

> 中文说明：第一条编译内容分析源码和测试，用来发现 Python 语法错误；第二条检查 Git 差异里的空白和冲突格式问题。两者退出码均为 0。

最大回归和覆盖率测试生成了 3 个未跟踪 Word 文件：`questionnaire_template.docx`（问卷模板）、`11_profile.docx`（人格档案报告）、`11_plan.docx`（内容规划报告）。核对时间、路径和测试引用后，已只删除这 3 个测试产物及其空目录，未删除其他文件。

## 七、未验证项

- 未读取或提交飞书 Base（多维表格）原始 2098 条；本会话令牌缺少 `base:table:read`（读取多维表格数据的权限），这不代表数据不存在。
- 未验证正式数据接口、持久化、定时扫描、下游仿写读取、库生命周期或人工入库补标。
- 未验证真实项目的分类与适配质量，也未验证可读视频的完整镜头分析质量。
- 未部署、未上线、未合并主分支。
