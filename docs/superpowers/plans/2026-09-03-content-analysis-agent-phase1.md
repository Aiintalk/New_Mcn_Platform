# 内容分析 Agent 阶段一实施计划

> **执行要求：** 使用 `superpowers:subagent-driven-development`（子任务驱动开发）逐项实施，并在每项后做独立规格与质量复审。

**目标：** 在不新增接口、数据表、迁移、调度或真实模型调用的前提下，交付一套数据源和分析器均可替换的离线内容分析内核，覆盖 v1.6 阶段一授权范围中的确定性计算、项目隔离、结构化分析边界和离线结果。

**架构：** 新能力放在 `backend/app/services/content_analysis/`，使用不可变领域对象承接标准业务语义；`deterministic.py` 只负责时区、去重、统计和排序；`analyzer.py` 定义可注入的异步分析协议及结果边界；`engine.py` 编排共享基础分析、项目独立适配、日报、内容库候选和跨项目候选。测试数据只保留匿名、合成后的最小边界样本，通过测试适配器映射到标准输入，生产包不读取飞书、日期表名或本地网页。

**技术栈：** Python 3.10、标准库 `dataclasses` / `enum` / `statistics` / `zoneinfo`、`pytest`、`pytest-asyncio`。不新增第三方依赖。

**正式规格：** `/Users/zhangchong/Desktop/codex_workspace/aiintalk_pm/docs/New_Mcn_Platform_Agents/M2_对标内容分析智能体_需求文档.md` v1.6。

**全局约束：**

- 只做冻结测试数据的离线分析切片；不接正式数据源、路由、数据库、调度或前端。
- 不调用任何真实或付费模型；离线引擎必须显式注入分析器，测试只用模拟实现。
- 不把播放量 0 当有效播放量，不计算播放互动率、逐日增量、增长速度或趋势。
- 项目上下文、机会、日报和内容库候选必须按项目隔离；来源限定信息不能变成当前项目商品事实。
- 没有可读画面时不得保留确定镜头或第一画面结论。
- 外部 PM 文档及线上/本地测试数据源只读，不纳入仓库。

---

## Task 1：标准输入与确定性计算内核

**文件：**

- 新建：`backend/app/services/content_analysis/__init__.py`
- 新建：`backend/app/services/content_analysis/domain.py`
- 新建：`backend/app/services/content_analysis/deterministic.py`
- 新建：`backend/tests/unit/services/content_analysis/__init__.py`
- 新建：`backend/tests/unit/services/content_analysis/test_deterministic.py`
- 新建：`backend/tests/fixtures/content_analysis/phase1_anonymized.json`
- 新建：`backend/tests/fixtures/content_analysis/README.md`

### 第 1 步：先写失败测试

测试必须覆盖：

- 运行时先转中国时区，再推导刚结束报告日、最近 3 个完整自然日和最近 30 个完整自然日；验证日界前后边界。
- 相同平台作品编号或相同外部链接去重，保留采集时间更新的记录；两者均缺失时不按文案合并。
- 播放字段为 0 时标准输入记为不可用，互动统计只包含点赞、评论、分享、收藏。
- 人设 30 日点赞均值、中位数、样本数、最高、最低。
- 每账号最近 3 日千川内容按当前点赞排序取前 3，边界外内容和第 4 名不入池。
- 冻结样本数量受限、编号匿名、无本地绝对路径、无长篇转写或真实个人信息。

运行：

```bash
env DATABASE_URL=postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test JWT_SECRET=test-secret backend/.venv/bin/python -m pytest backend/tests/unit/services/content_analysis/test_deterministic.py -q --override-ini=addopts=
```

预期：因生产模块或行为尚不存在而失败，记录失败原因。

### 第 2 步：实现最小领域模型

`domain.py` 只声明阶段一需要的业务语义：

- 内容来源、稳定身份、发布时间/采集时间、最新互动值、转写、可选视频引用和更新状态。
- 项目—账号关系与项目上下文版本。
- 三种主分类、同步状态、可信程度、开头标注状态、业务状态。
- 基础分析、项目判断、统计、日报及候选所需的不可变对象。

所有带时间的输入要求时区明确；互动值允许缺失，不用 0 代替缺失。

### 第 3 步：实现确定性函数

`deterministic.py` 提供：

- `derive_windows(run_at)`：返回中国时区下的报告日期、3 日和 30 日半开区间。
- `deduplicate_contents(contents)`：只按链接或平台作品编号合并，选择最新采集记录。
- `persona_like_baseline(...)`：按账号计算 30 日人设点赞五项统计。
- `qianchuan_top_three(...)`：按账号计算 3 日高点赞千川前 3。
- `normalize_play_count(...)`：0 或负数视为不可用，不派生播放率。

### 第 4 步：运行聚焦测试并提交

预期：任务 1 全部测试通过、没有新增警告；仅提交任务 1 文件。

---

## Task 2：可注入智能分析边界与项目隔离离线引擎

**文件：**

- 新建：`backend/app/services/content_analysis/analyzer.py`
- 新建：`backend/app/services/content_analysis/engine.py`
- 修改：`backend/app/services/content_analysis/__init__.py`
- 新建：`backend/tests/unit/services/content_analysis/test_engine.py`

### 第 1 步：先写失败测试

测试必须覆盖：

- 分析器通过异步协议注入；共享内容只做一次基础分析，同账号关联两个项目时分别适配，且上下文和结果不串项目。
- 明确种草、使用流程、卖点证明、成交促单等转化内容由模拟分析器归千川；证据不足保留“无法判断”及原因。
- 缺字幕仍继续；视频不可读时清除确定镜头和第一画面结论，并增加限制说明。
- 成功有内容、成功无内容、部分成功和失败分别输出；只有成功无内容设置空日报。
- 关系账号无法与同步结果匹配时输出关系缺失，不把内容分配给错误项目。
- 每项目人设机会和千川机会分别为 0—3 条；千川内容库候选把正文对标、开头状态、开头片段或不可用原因绑定在同一记录。
- 来源商品说法只进入来源限定信息，不形成当前项目商品事实；输出明确区分事实、判断、假设、限制与可信程度。
- 前两天内容只在已保存业务状态变化时重新进入日报；没有旧状态或只有互动值变化时不算变化。
- 跨项目候选只聚合已进入两个项目库的共同可复用方法，不携带来源限定信息，也不自动写入其他项目库。

运行：

```bash
env DATABASE_URL=postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test JWT_SECRET=test-secret backend/.venv/bin/python -m pytest backend/tests/unit/services/content_analysis/test_engine.py -q --override-ini=addopts=
```

预期：因分析协议和引擎尚不存在而失败，记录失败原因。

### 第 2 步：实现分析器协议与边界保护

`analyzer.py` 定义无默认实现的异步 `ContentAnalyzer` 协议：基础内容分析可跨项目复用，项目适配必须逐项目调用。加入确定性边界清理：

- 分类只能为人设、千川、无法判断；无法判断必须有原因。
- 视频不可读时移除确定镜头/第一画面结论并写明限制。
- 来源商品和达人专属信息只保存在来源限定信息。
- 结构化结果保留选题、开头、结构、转化说服链、镜头、互动、项目适配、可复用方法、事实/判断/假设/限制和可信程度。

### 第 3 步：实现离线编排

`engine.py` 完成：

- 对 30 日范围内容去重并缓存基础分析。
- 精确映射稳定账号关系，按项目单独调用适配判断。
- 生成项目独立日报、当日分类/互动概览、前两天业务状态变化、0—3 条两类机会、内容库候选和跨项目候选。
- 明确同步状态、缺失账号/资料、低可信程度和关系问题；只在成功确认无内容时生成空日报。
- 使用最新互动值做当前统计和排序，不构造历史互动序列或趋势。

### 第 4 步：运行任务 1+2 聚焦测试并提交

预期：内容分析目录全部测试通过、没有新增警告；仅提交任务 2 文件。

---

## Task 3：控制器验收、文档与完整验证

**文件：**

- 新建：`backend/docs/tasks/M2_Sprint27_后端任务_内容分析Agent阶段一_v1.md`
- 新建：`backend/docs/tasks/M2_Sprint27_后端任务_开发验收_内容分析Agent阶段一_v1.md`
- 新建：`backend/docs/tests/M2_Sprint27_测试报告_内容分析Agent阶段一_v1.md`
- 修改：`backend/docs/README.md`
- 修改：`README.md`
- 修改：`docs/pm/PM_记忆与状态_M2.md`

### 第 1 步：独立复审整个分支

按任务 1、任务 2 的规格复审结论完成必要的受控返修；不修复与本轮无关的历史问题。

### 第 2 步：执行验证

依次运行：

```bash
env DATABASE_URL=postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test JWT_SECRET=test-secret backend/.venv/bin/python -m pytest backend/tests/unit/services/content_analysis -q --override-ini=addopts=
env DATABASE_URL=postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test JWT_SECRET=test-secret backend/.venv/bin/python -m pytest backend/tests/unit backend/tests/integration -q --override-ini=addopts=
cd backend && env DATABASE_URL=postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test JWT_SECRET=test-secret .venv/bin/python scripts/run_coverage.py --gate
```

如既有门禁失败，保留完整失败证据并区分本轮新增测试结果，不用无关改动稀释范围。

### 第 3 步：落档与提交

- 任务、验收、测试报告和 README 明确阶段一仅为离线切片，不代表生产接口、定时运行、真实项目效果或完整镜头分析通过。
- PM 状态新增本轮事实；保留并注明 `origin/main` 已存在的历史冲突标记，不擅自清理。
- 记录 CA-01 至 CA-23 的“已覆盖 / 部分覆盖 / 阶段二依赖 / 本轮不适用”矩阵。
- 本地提交文档与必要返修；禁止推送、建 PR、合并或部署。
