# M2 Sprint27 后端测试报告：内容分析 Agent 阶段一 v1

> 日期：2026-09-03
> 分支：`codex/content-analysis-agent-dev`（内容分析开发分支）
> 代码对象：`602c2fee0a6dda58f84a459d8f6294068f8b6e48`（本轮代码收口提交）

## 一、结论

内容分析聚焦测试 38/38 通过；在 `backend`（后端目录）执行的单元测试与集成测试最大回归 2051/2051 通过，仓库覆盖率分层门禁退出码为 0。开发侧离线切片可交主产品经理独立审核。

此结论不包含正式数据源、数据库、调度、路由、前端、下游联调、真实项目效果、可读视频完整镜头或真实/付费模型质量。

## 二、环境与隔离

- Python（编程语言）：3.10.9；pytest（Python 测试工具）：9.1.1。
- 数据库只指向本地 `mcn_test`（后端测试库），使用任务指定的 `DATABASE_URL`（数据库连接地址）和 `JWT_SECRET`（测试签名密钥）。
- 未执行生产数据库操作、迁移、外部调用、真实或付费模型调用。
- 覆盖率之外的最大回归显式使用 `--override-ini=addopts=`（清空配置里默认附加参数），避免重复收集覆盖率。

## 三、执行记录

### 1. 内容分析聚焦测试

```bash
env DATABASE_URL=postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test JWT_SECRET=test-secret backend/.venv/bin/python -m pytest backend/tests/unit/services/content_analysis -q --override-ini=addopts=
```

> 中文说明：在仓库根目录运行内容分析专项单元测试，只连接本地测试库，并关闭默认覆盖率参数。

| 通过 | 失败 | 跳过 | 警告 | pytest 计时 | 墙钟计时 | 退出码 |
|---:|---:|---:|---:|---:|---:|---:|
| 38 | 0 | 0 | 0 | 0.05 秒 | 0.91 秒 | 0 |

### 2. 最大回归首轮（保留运行目录失败证据）

```bash
env DATABASE_URL=postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test JWT_SECRET=test-secret backend/.venv/bin/python -m pytest backend/tests/unit backend/tests/integration -q --override-ini=addopts=
```

> 中文说明：按实施计划从仓库根目录运行全部单元测试与集成测试。既有迁移测试用后端目录相对路径读文件，因此在仓库根目录失败。

| 通过 | 失败 | 跳过 | 警告 | pytest 计时 | 墙钟计时 | 退出码 |
|---:|---:|---:|---:|---:|---:|---:|
| 2050 | 1 | 1 | 15 | 421.77 秒 | 423.80 秒 | 1 |

唯一失败：`test_055_is_idempotent_and_preserves_historical_nulls`（验证 055 迁移可重复执行且保留历史空值的测试）从相对路径读取 `migrations/055_kol_persona_profile_unification.sql`（达人档案统一迁移文件），发生 `FileNotFoundError`（找不到文件错误）。这不是内容分析实现失败。

### 3. 最大回归更正运行目录后重跑

```bash
cd backend
env DATABASE_URL=postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test JWT_SECRET=test-secret .venv/bin/python -m pytest tests/unit tests/integration -q --override-ini=addopts=
```

> 中文说明：进入后端目录后，使用相同测试范围、环境和参数重跑，用来区分工作目录问题和真实回归失败。

| 通过 | 失败 | 跳过 | 警告 | pytest 计时 | 墙钟计时 | 退出码 |
|---:|---:|---:|---:|---:|---:|---:|
| 2051 | 0 | 1 | 14 | 417.24 秒 | 419.26 秒 | 0 |

### 4. 覆盖率门禁

```bash
cd backend
env DATABASE_URL=postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test JWT_SECRET=test-secret .venv/bin/python scripts/run_coverage.py --gate
```

> 中文说明：运行仓库规定的覆盖率脚本，同时执行 2052 条测试并检查整体和六个代码分层的最低覆盖率。

| 通过 | 失败 | 跳过 | 警告 | pytest 计时 | 墙钟计时 | 退出码 |
|---:|---:|---:|---:|---:|---:|---:|
| 2051 | 0 | 1 | 14 | 435.90 秒 | 438.68 秒 | 0 |

## 四、覆盖率明细

| 分层 | 实际 | 目标 | 结果 |
|---|---:|---:|---|
| `app/core/`（核心基础设施） | 100.0% | 90% | 通过 |
| `app/models/`（数据模型） | 100.0% | 90% | 通过 |
| `app/services/`（业务服务） | 89.1% | 80% | 通过 |
| `app/routers/`（接口路由） | 73.0% | 70% | 通过 |
| `app/adapters/`（外部服务适配器） | 80.3% | 60% | 通过 |
| `app/middlewares/`（请求中间件） | 100.0% | 90% | 通过 |
| 整体 | 79.7% | 48% | 通过 |

终端覆盖率表将整体四舍五入显示为 80%，门禁脚本按更精确数值报告 79.7%，本报告以门禁值为准。

内容分析内核文件细分覆盖率：

| 文件 | 覆盖率 |
|---|---:|
| `__init__.py`（包导出文件） | 100% |
| `analyzer.py`（分析协议与证据边界） | 95% |
| `deterministic.py`（确定性计算） | 97% |
| `domain.py`（领域对象） | 95% |
| `engine.py`（离线编排引擎） | 98% |

## 五、警告与跳过项

- 14 条警告均来自 `tests/unit/services/test_tikhub_adapter.py`（TikHub 适配器单元测试），对应 `RuntimeWarning`（运行时警告）：模拟的异步调用没有被等待。它们在本轮内容分析目录之外，未做无关修复。
- 首轮仓库根目录运行额外触发 1 条 `DeprecationWarning`（弃用提醒），来自直播复盘测试文档字符串里的 `\s`（正则空白符简写）；更正目录后的最大回归和覆盖率运行未再报这条。
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
