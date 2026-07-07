# MCN_PM_Agent — 项目记忆与当前状态（M2）

> 最后更新：2026-07-07（**PR #18 测试补漏 PR**：分支 `test/pr18-followup-tests`，PM 审计 PR #18 合并后发现 4 处改动完全无测试 + tikhub adapter 12 个预存失败（mock 路径 `report_failure` vs `_report_failure`）+ 2 处前端断言不完整，开 followup PR 单独补漏。补漏：tikhub fallback 测试 2 个 + tikhub 12 个失败全修 + operator_selling_point 503 重试测试 2 个 + personaWriter.test.ts 6 个 + SellingPointPage.test.tsx 2 个 + HistoryList 复制按钮断言 + QianchuanWriterPage 长 Brief 不截断；后端 1123 passed、前端 265 passed，2+2 失败均为预存非回归；不动生产代码，仅补测试 + 文档。上一个：同日稍早 PR #18 合并到 main（Bug #12-17 修复）。再上一个：2026-07-03 qianchuan-edit-review provider 切换 + ai_model_id 解析彻底修复（PR #20 已合并 main）。再上一个：同日稍早完成 AI 多服务商切换不生效修复（13 个 router 的 chat_stream 调用补传 `provider` 参数 + yunwu.py 防御空 choices 数组，PR #19）。再上一个：2026-07-01（**管理端配置页 UX 完善**：`/admin/workspace` 工具列表操作列加「配置」按钮直达对应 Tab + 4 个预留 Tab 占位 + 修 selling-point-extractor 映射 bug；同日稍早完成 values-writer + script-review 补历史记录功能 P0 #2）。再上一个：2026-06-30（**PR #13 红人工作台 Sprint 18-23 合并到 main**：merge commit `b9d50c6`，含 Sprint 22 复盘 + Sprint 21 千川脚本预审 + Sprint 23 工作台配置 + Sprint 18-20 工作台主体；feature/kol-workspace 分支保留持续开发。再上一个：2026-06-28 旧架构数据全量迁移到新架构 — 12 服务 260 文件 → 8 业务表，272 INSERT + 20 UPDATE + 32 KOL，迁移工具 `backend/scripts/migrate_legacy_data.py` + 迁移记录文档仍在工作区待提交）

> **🚧 当前状态**：main 上最新合并 = PR #18（Bug #12-17 系统反馈问题，2026-07-07）+ PR #20（qianchuan-edit-review provider 修复，2026-07-03）+ PR #19（AI 多服务商切换，2026-07-03）。`test/pr18-followup-tests` 分支待开 PR（PR #18 测试补漏 + tikhub adapter 12 预存失败修复）。`feature/kol-workspace` 分支保留持续开发。下一步候选：legacy 迁移工具归档（4 个 untracked 文件）/ KolWorkspacePage 测试失败修复 / Sprint 17 backlog。

> **📋 Sprint 17 backlog**（已写需求文档，待开工）：管理端调用日志扩展（用户列 + 功能列）—— `docs/pm/M2_Sprint17_管理端调用日志扩展_需求文档.md`

> 更新角色：MCN_PM_Agent
> 上一份文档：`docs/pm/PM_记忆与状态.md`（M1 阶段，已归档）

---

## 一、项目基本信息

- **项目名**：MCN Information System Platform
- **当前阶段**：M2 阶段 — **迁移收尾 + 日志链路修复 + 文档补遗**（PR #8 日志修复+文档 / PR #9 ConfigTab，待 E2E 合并），上一个：Sprint 16 种草内容仿写（PR #7 已合并），最近已合并：Sprint 14 千川文案写作（PR #5）。**迁移进度：19 个旧工具中 16 个已迁移完成且 online**，剩余约 4 个未迁移（字幕提取/素材库/人格预览/涛然写作）。下一个候选：tool_transcribe 切到 ASR / TikHub 日志 bug 修复 / 凭证加密 / 4 个未迁移工具
- **GitHub**：https://github.com/Aiintalk/New_Mcn_Platform
- **工作目录**：`D:\2026年工作\AI相关\AI工具箱新架构方案\mcn-platform`（Windows 本地）
- **后端**：`backend/`（FastAPI + PostgreSQL）
- **前端**：`frontend/`（React + Vite + TypeScript + Ant Design 5.x）

### 环境信息

- **数据库**：PostgreSQL 18.4 @ localhost:5432（Windows 本地），postgres 密码 `postgres2026`（2026-06-17 起，原 `admin123`），主库 `mcn_m1` / 测试库 `mcn_test`（账号 `mcn_user/admin123`，仅 conftest.py 用）
- **psql 路径**：`D:\ProtgreSQL\bin\psql.exe`
- **后端地址**：`http://localhost:8000`（uvicorn）
- **前端地址**：`http://localhost:5175`（Vite，5173/5174 被旧项目占用）
- **测试账号**：admin / Admin@123456

---

## 二、M2 阶段（当前）

> **Sprint 编号说明**：main 与 feature/kol-workspace 两分支并行开发期间各自用了 Sprint 18/19 编号，内容不同（main = 素材库/字幕；feature = 红人工作台）。合并后按"保留双方记录、时间序"原则记录如下，最新在前。

### M2 工作项 — PR #18 修复 Bug #12-17 系统反馈问题 ✅ 完成（main，2026-07-07）

**背景**：飞书 wiki 集中反馈的 6 个用户体验 Bug，由外部贡献者 `chongzhang258-star`（2026-07-02 提交 PR）。PR 创建后 main 又合并了 PR #19（AI 多服务商切换，2026-07-03）+ PR #20（qianchuan-edit-review provider 修复，2026-07-03），导致 `operator_selling_point.py` 冲突。PM 本地 rebase main 解决冲突 + 跑回归测试 + 补文档落地后合并。

**修复的 6 个 Bug**（飞书 wiki 编号 #12-17）：

| # | 模块 | 问题 | 修复 |
|---|------|------|------|
| 12 | 字幕提取 - 批量历史 | transcript 截断 120 字 + 缺「复制文本」按钮 | `subtitle/HistoryList.tsx` 完整展示（滚动 200px）+ 复制按钮 |
| 13 | 红人工作台 - 对标账号 | 纯数字抖音号报"uid 找不到" | `tikhub.py resolve_sec_user_id` uid 查无果自动 fallback 到 unique_id |
| 14 | 人设仿写 - 开始评估 | 报错无法继续 | `personaWriter.ts` 错误消息提取 `err.detail.message` → `err.message`（根因同 Bug #2，依赖 migration 048）|
| 15 | 千川仿写 - 产品卖点 | 截断 400 字 | `QianchuanWriterPage.tsx` 完整展示（滚动 300px）|
| 16/17 | 直播仿写 / 直播复盘 | 无法生成 / 报错 | 根因同 Bug #2（migration 048 已在 main），前端错误消息提取修正 |

**额外改进**（commit 2，selling-point 容错）：
- `operator_selling_point.py` `_RETRY_DELAYS=[2,4]`：503/502/429/timeout 自动重试最多 3 次（**保留 PR #19 的 `provider=provider` 不变**）
- `SellingPointPage.tsx`：流结束后检测 `[ERROR]` 标记转友好提示，错误文本不再污染分析报告
- `test_tool_extract_frames.py`：补 `shutil.which` ffmpeg mock + 503 测试用例

**冲突解决**（`operator_selling_point.py` 单文件冲突）：
- 冲突 1（常量区）：保留 PR #19 的 `DEFAULT_PROVIDER="yunwu"` + PR #18 的 `_RETRY_DELAYS=[2,4]`
- 冲突 2（generate 函数）：采用 PR #18 重试循环结构 + 保留 PR #19 的 `provider=provider` 参数
- 关键不变量验证：`provider=provider` 在 line 134、`_resolve_model` 返回二元组、`_RETRY_DELAYS` 全部保留

**验证**：
- 后端核心 50 passed（operator_selling_point + operator_workspace + tool_extract_frames）
- 后端 tikhub adapter 12 failed（**预存失败**，main 同样失败，mock 路径 `report_failure` vs `_report_failure`，与本次改动无关）
- 前端 HistoryList 6/6 通过 + QianchuanWriterPage 10/11（1 失败预存，main 同样失败）

**依赖**：Bug #14/#16/#17 依赖 migration 048（`048_external_service_logs_tokens_used.sql`，PR #17 已合并 main，2026-07-02 起）。

**红线合规**：
- ✅ #1 标准信封：未改 router 返回结构
- ✅ #3 前端走 request.ts：personaWriter.ts 是 SSE 流式（readPlainStream），属例外
- ✅ #4 契约同步：纯 bugfix，无契约变更
- ✅ #5 改后端 README：本 PR 自带 backend/docs/README.md "最近改动"段更新

**重要教训**：
1. **外部贡献者 PR 合并前必须 rebase main + 跑回归测试**：PR 创建后 main 合并的新 PR（本例 PR #19）可能改了同一文件，直接 merge 会丢失关键修复（本例 PR #19 的 provider 修复）。AI review 必须列出冲突文件 + 验证关键不变量保留。
2. **预存失败测试要区分**：tikhub adapter 12 个 + QianchuanWriterPage 1 个失败都是 main 上预存的（与 MEMORY.md 记录一致），不算 PR #18 回归。合并前要切 main baseline 跑同样测试确认。

**产物**（PR #18 自带）：
- 代码：7 文件 +143/-52
- 文档：backend/docs/README.md "最近改动"段 + 本节
- 待补（untracked，合并后补）：docs/pm/BUG修复登记.md BUG-033~038

---

### M2 工作项 — PR #18 测试补漏 + tikhub adapter 修复 🚧 进行中（分支 `test/pr18-followup-tests`，待发 PR）

**背景**：PR #18 合并后 PM 审计发现：4 处关键改动完全无测试覆盖 + tikhub adapter 12 个预存失败（mock 路径与实际函数名不一致）+ 2 处前端测试断言不完整。开 followup PR 单独补漏，**不动生产代码**（仅测试代码本身）。

**补漏清单**：

| # | 改动点 | 补漏前状态 | 补漏后 |
|---|--------|-----------|--------|
| 1 | `tikhub.resolve_sec_user_id` 纯数字 fallback | 无 fallback 路径测试 | +2 个：纯数字 uid 命中走快捷路径 + uid 无果 fallback 到 unique_id（patch `_get_key_and_url`/`get_user_profile`） |
| 2 | tikhub adapter 12 预存失败 | mock 路径 `report_failure`（无下划线）不存在 | 全改 `_report_success`/`_report_failure`，重写 douyin_id 测试（原测试与代码语义已脱节），12/12 通过 |
| 3 | `operator_selling_point` 503 重试 | 仅 1 个 error marker 测试 | +2 个：503 重试后成功（1 次失败 + 1 次成功）+ 重试耗尽仍 yield [ERROR]（patch asyncio.sleep 跳过真实等待，验证 call_count=3） |
| 4 | `personaWriter.ts` 3 处错误消息提取 | 完全无测试 | 新建 `__tests__/unit/api/personaWriter.test.ts`：6 个（3 函数主路径 throw err.message + 3 状态码回退 throw `失败: ${status}`） |
| 5 | `SellingPointPage.tsx` [ERROR] 标记处理 | 完全无测试 | 新建 `__tests__/components/pages/SellingPointPage.test.tsx`：2 个（标记清理 + 友好提示 / 健康流） |
| 6 | `HistoryList.tsx` 批量任务复制按钮 | 展开测试无复制按钮断言 | +1 行：`expect(screen.getByText('复制文本')).toBeInTheDocument()` |
| 7 | `QianchuanWriterPage.tsx` 长 Brief 不截断 | 完全无测试 | +1 个：500 字 Brief 含尾部唯一标记，验证标记完整展示（旧逻辑 `slice(0, 400)` 会丢失） |

**全量回归**：
- 后端 1123 passed / 1 skipped / 2 failed（`test_livestream_writer_file_parser` Pages 解析，预存）/ 8 errors（`tests/concurrent` 并发测试，需特殊基础设施）
- 前端 265 passed / 2 failed（KolWorkspacePage Test benchmark modal + QianchuanWriterPage Test 2 人物预览，均为预存）

**红线合规**：
- ✅ 测试 PR 不改契约、不改 router 结构、不改前端业务代码
- ✅ #5 改后端 README：backend/docs/README.md "最近改动" 段加测试补漏子段
- ✅ 全量回归通过，覆盖率不退化（66.47% 后端）

**重要教训**：
1. **PR 合并后审计 ≠ 跑通测试就过**：必须 diff 检查 PR 的每个改动点是否都有对应测试覆盖，4 处漏测在 PR review 时未被发现。
2. **预存失败不能忽视**：12 个 tikhub adapter 失败虽是预存，但根因是测试代码与生产代码脱节（mock 路径错 + 测试语义错），既然在改这个文件就一并修掉，不能让"预存失败"成为永久借口。

**产物**：
- 测试代码：4 文件新增（personaWriter.test.ts / SellingPointPage.test.tsx）+ 修改 + 3 文件修改（test_tikhub_adapter / test_operator_selling_point / HistoryList.test / QianchuanWriterPage.test）
- 文档：backend/docs/README.md "最近改动"段加测试补漏子段 + 本节

---

### M2 工作项 — qianchuan-edit-review provider 切换 + ai_model_id 解析彻底修复 ✅ 完成（main，2026-07-03，PR #20 已合并）

**背景**：用户问「qianchuan-edit-review 功能逻辑」，梳理时发现两个 bug：(1) PR #19 漏修了共享 router `tool_chat_stream.py`（同样漏传 `provider=`）；(2) 前端 `QianChuanEditReviewPage` 的 `useEffect` 拿到 `ai_model_id` 后完全没用，`analyze()` 硬编码 `'gpt-4o'`，admin 配模型等于白配。

**根因**：
1. **共享 router 漏传 provider**：`tool_chat_stream.py:59` 调 `yunwu_adapter.chat_stream()` 没传 provider，落入默认 `provider="yunwu"`（与同日早些时候 PR #19 修复的 13 个 router 是同一个坑）
2. **前端硬编码 model**：`api/qianchuanEditReview.ts` 的 `chatStream` 只接受 `model` 字符串；page 把 admin 配的 `ai_model_id` 拿到 state 但没传到后端；后端也没字段接收

**改动**：
- **后端 `backend/app/routers/tool_chat_stream.py`**：
  - `ChatStreamRequest` 加 `ai_model_id: int | None = None`
  - 加 `_resolve_model(ai_model_id, db)` → `(model_id, provider)`（参照 `operator_selling_point.py:77` 同款 pattern，但接受 `int | None` 而非 config 对象——保留共享 router 通用性）
  - 加 `DEFAULT_MODEL="gpt-4o"` / `DEFAULT_PROVIDER="yunwu"` 常量
  - 函数签名加 `db: AsyncSession = Depends(get_db)`（解析 ai_model_id 用）；`generate()` 内仍用独立 `AsyncSessionLocal`（流式 session）
  - `yunwu_adapter.chat_stream(...)` 调用显式传 `provider=provider`
- **测试 `tests/integration/routers/test_tool_chat_stream.py`**：加 2 用例（默认 provider + siliconflow 切换）；原 `fake_stream` 签名加 `**kwargs` 兼容
- **前端 `api/qianchuanEditReview.ts`**：`chatStream` 加 `aiModelId?: number | null` 参数，仅非空时放进 body
- **前端 `pages/operator/QianChuanEditReviewPage.tsx`**：加 `activeModelId` state，`useEffect` 从 `getConfig()` 读取，`analyze()` 传给 `chatStream`
- **文档**：Base_API §chat-stream 加 `ai_model_id` 字段说明；backend/docs/README.md 加补修补条目；frontend/docs/README.md 标注

**验证**：
- 后端单测 6/6 通过（含 2 个新增）
- 后端 19 个相关测试回归全过（qianchuan-edit-review / chat_stream / export_word / transcribe）
- 前端 tsc --noEmit 0 错误
- 端到端 curl 待跑

**红线合规**：
- ✅ #1 标准信封：chat-stream 是流式例外，不改
- ✅ #3 前端走 request.ts：chatStream 是 SSE 流式例外（裸 fetch + getReader），合规
- ✅ #4 改接口同步契约：Base_API §chat-stream 已更新
- ✅ #5 改后端/前端 README：双 README 均已更新

**重要教训**：「同款 pattern 修复」必须列出**全部调用方清单**核对，PR #19 当时只查了 `operator_*` 系列，漏掉了 `tool_*` 系列里的共享 router。后续修复同类问题时 grep 范围要覆盖 `app/routers/` 全部，而非按命名前缀过滤。

### M2 工作项 — AI 多服务商切换不生效 + siliconflow list index out of range 修复 ✅ 完成（main，2026-07-03）

**用户反馈**：selling-point-extractor 在服务器上调用 yunwu 报 503，用户切换厂商到 siliconflow 不生效，强制切后报 `[siliconflow]: list index out of range`。本地正常。

**根因**：
1. **provider 传递缺失（架构缺陷）**：13 个 router 的 `chat_stream` 调用未传 `provider` 参数，adapter 默认 `provider="yunwu"`，导致管理端配置的厂商永不生效。
2. **空 choices 防御缺失**：`yunwu.py` L303（流式）/ L179（非流式）当上游返回 `choices:[]`（siliconflow 等结尾帧仅含 usage）时，`[][0]` 抛 IndexError。

**改动**：
- **`backend/app/adapters/yunwu.py`**：先判空再取 `[0]`，空数组在流式场景 `continue`、非流式抛 `RuntimeError("chat failed [{provider}]: empty choices...")`。
- **13 个 router 加 `_resolve_model` 返回 `(model_id, provider)` 二元组**，调用 chat/chat_stream 时传 `provider=provider`：
  - `operator_selling_point.py`、`operator_retrospective.py`、`operator_qianchuan_writer.py`、`operator_qianchuan_preview.py`、`operator_tiktok_review.py`、`operator_benchmark.py`
  - `operator_persona_writer.py`（3 处）、`operator_seeding_writer.py`（5 处）、`operator_values_writer.py`（4 处含非流式 chat）
  - `operator_livestream_writer.py`、`operator_tiktok_writer.py`（用 body.model，默认 yunwu）
- **新单测**：`tests/unit/services/test_yunwu_adapter.py`（流式+非流式空 choices 防御 2 用例）
- **扩展单测**：`tests/integration/routers/test_operator_selling_point.py` 加 provider 路由 2 用例（默认 yunwu + 读 ai_models.provider）

**验证**：
- 后端单测 31 个相关用例全过（含 4 个新增）
- 端到端 curl：默认 yunwu 配置流式输出正常，ai_call_logs 记录 `success` 8.2s
- SQL 验证：`ai_models.provider` 字段可正确 JOIN 读取，`_pick_and_lock` 按 provider 过滤 credentials 工作正常

**红线合规**：
- ✅ #1 标准信封：未改
- ✅ #2 写操作写 OperationLog：未改
- ✅ #3 前端走 request.ts：未改
- ✅ #4 改接口同步契约：本次未改接口契约（adapter 内部参数变化，对外契约不变）
- ✅ #5 改后端更新 README：backend/docs/README.md 已加「最近改动」段

**重要经验**：adapter 函数签名里 `provider` 是**默认参数**而非显式必传时，新调用点极易漏传。后续可考虑加 lint 检查或让 provider 成为必传参数（破坏性改动，待评估）。

### M2 工作项 — 管理端工具配置页 UX 完善（配置按钮 + 预留 Tab）✅ 完成（main，2026-07-01）

**背景**：`/admin/workspace` 工具列表原本只有「编辑 / 停用」操作，23 个工具的配置入口只能靠管理员手动在 Tab 栏找。用户要求把「配置」按钮加到操作列，且对所有工具都预留入口（包括分组占位与未做配置页的）。

**改动**（`frontend/src/pages/admin/WorkspaceConfigPage.tsx` 单文件）：

| # | 事项 | 结果 |
|---|------|------|
| 1 | Tabs 受控化 | 加 `activeKey` state + `onChange`，让外部按钮能切 Tab |
| 2 | CONFIG_TAB_KEYS 白名单 | 23 个 tool_code 全部纳入（含 4 个预留占位）|
| 3 | TOOL_CODE_TO_TAB_KEY 例外映射 | 3 条：`kol-intake→intake` / `qianchuan-script-review→script-review` / `selling-point-extractor→selling-point`（**最后一条是修 bug**，原本漏了导致卖点提取器无配置按钮）|
| 4 | PlaceholderConfigTab 占位组件 | 4 个未做独立配置页的工具（persona-positioning / qianchuan-collection / qianchuan 分组 / review 分组）显示「暂未提供独立配置项」|
| 5 | 操作列加「配置」按钮 | 放在「编辑」之前，按 CONFIG_TAB_KEYS 判断显隐 |
| 6 | 顺手修 selling-point-extractor 映射 bug | 该 tool_code 与 Tab key（selling-point）不一致，原本漏映射 → 现在卖点提取器也有「配置」按钮 |

**关键决策**：
- 4 个预留 Tab 的 label 带「（预留）」后缀，管理员一眼能看出哪些还没做
- 以后补真实配置：新建 `XxxConfigTab.tsx` → 替换 children → 去掉「（预留）」后缀即可

**遗留**：4 个预留位以后逐个补真实配置页（persona-positioning / qianchuan-collection 优先，qianchuan+review 分组可能永远是占位）。

---

### M2 工作项 — values-writer + script-review 补历史记录功能（P0 #2）✅ 完成（main，2026-07-01）

**问题定位**：PR #13 上线的 values-writer（价值观仿写）和 qianchuan-script-review（千川脚本预审）两个工具**完全没有历史记录功能** — 用户调用完成后无 INSERT 落 `outputs` 表，刷新页面或离开后结果丢失。同期工具 persona-writer / seeding-writer 早已用共享 `outputs` 表 + save-output 模式实现历史，是现成可复制范式。

**修复方案**：参照 persona-writer:525-570 的 `save_output` 实现，两个工具各加 `POST /save-output`；前端两页加「保存到历史」按钮 + 页内历史抽屉（首次抽出可复用组件 `OutputHistoryDrawer`）。

| # | 事项 | 结果 |
|---|------|------|
| 1 | `routers/operator_values_writer.py` | 加 TOOL_CODE/TOOL_NAME + `SaveOutputRequest` + POST /save-output（content+title+topic，写 OperationLog） |
| 2 | `routers/operator_script_review.py` | 加 POST /save-output（content+content_json+title，JSONB 存结构化评分） |
| 3 | `components/OutputHistoryDrawer.tsx` | **新增可复用组件**：Ant Design Drawer + List，按 tool_code 过滤全局 `/api/outputs`，分页 + 软删 + 可选 renderItem |
| 4 | `ValuesWriterPage.tsx` | 加「保存到历史」+「历史记录」按钮 + `<OutputHistoryDrawer>` |
| 5 | `QianchuanScriptReviewPage.tsx` | 加保存按钮 + 历史抽屉（renderItem 自定义渲染评分 Tag） |
| 6 | `api/valuesWriter.ts` + `api/scriptReview.ts` | 加 `saveOutput()` 函数 |
| 7 | `types/valuesWriter.ts` + `types/scriptReview.ts` | 加 `SaveOutputRequest` 类型 |
| 8 | 后端测试 | 每工具 4 个 save-output 用例（success / empty_content / writes_operation_log / account_isolation），28/28 通过 |
| 9 | 契约文档 | Base_API §26 加 26.x POST /save-output；§27 加同款 endpoint |
| 10 | README | backend + frontend 标注新功能；新增 `components/` 目录说明 |
| 11 | 端到端 curl | dev 服实测两个 save-output success；GET /outputs?tool_code=X 正确过滤；OperationLog 2 条 |

**关键设计**：
- **复用全局 GET /outputs?tool_code=X + DELETE /outputs/{id}**，不在工具 router 里重复 list/delete endpoint
- **script-review 用 outputs.content_json JSONB** 存 ReviewResult 结构化评分，content 存仿写脚本原文
- **首次建可复用组件** `components/OutputHistoryDrawer`（前端原本无 components/ 目录）— 未来 persona-writer / seeding-writer 加 UI 也可复用
- **不需要 migration** — outputs 表已含 content + content_json 双字段

**红线合规**：#1 标准信封 / #2 写 OperationLog / #3 走 request.ts / #4 契约同步 / #5 双 README / #8 软删（全 outputs.py 已是软删）。

**未来增量**：persona-writer / seeding-writer 也有 save-output API 但前端没接入 UI（只有 API 没人调）— 后续可统一接入 `OutputHistoryDrawer` 组件。

---

### M2 工作项 — 启用 TikHubCallLog 写入（修复长期 bug）✅ 完成（main，2026-07-01）

**问题定位**：`tikhub_call_logs` 表 + ORM 早已设计好，`admin_tikhub /stats /operations /users` 三个聚合接口也基于此表 —— 但全 backend 没有任何代码在写它。实测表 0 行，admin_tikhub /stats 返回全空。PR #13 红人工作台的「添加对标账号验证」也调 TikHub 但不写日志 → TikHub 调用长期处于"成本不可监控、Key 故障不可定位、用户行为不可追溯"状态。

**修复方案**：参考已有先例 `yunwu.py` 的 AiCallLog finally 写法（红线 #6 同款），把同样模式套到 `tikhub.py`。

| # | 事项 | 结果 |
|---|------|------|
| 1 | `adapters/tikhub.py` | 加 `_log_call` helper + 6 个公开 async 函数（`resolve_sec_user_id` / `get_user_profile` / `get_user_fans_info` / `get_live_room_products` / `fetch_user_videos` / `fetch_video_by_share_url`）try/finally 写 `TikHubCallLog` |
| 2 | `routers/operator_workspace.py` | 2 处调用（validate benchmark 路径）传 `user_id=current_user.id` |
| 3 | `tests/integration/routers/test_operator_workspace.py` | 加 3 个 validate 测试（含 avatar_in_resolve / fallback_profile / tikhub_error 三个分支） |
| 4 | 后端开发约定 | `§4.2 外部服务 Service` 加"禁止裸 httpx 调 TikHub"小节；新增 `§7.4 TikHubCallLog` 字段说明 |
| 5 | 端到端验证 | dev 服实测 `/operator/workspace/3/benchmarks/validate` → `tikhub_call_logs` 新增 2 行（get_user_profile + resolve_sec_user_id，user_id=1 admin）；admin_tikhub /stats 从空变 `total_calls=2` |
| 6 | 全量回归 | 1075 passed，14 failed（**全部预先存在**：12 个 tikhub_adapter 测试 mock 路径 `report_failure`→应为 `_report_failure`、2 个 pages_extracts） |

**字段映射**：credential_id（凭证池返回）/ user_id（None=系统调用如 kol_scheduler）/ platform（固定 `"douyin"`）/ endpoint（函数名，与 admin_tikhub SQL GROUP BY 对齐）/ status (`success`/`error`) / latency_ms (`int((time.monotonic()-start)*1000)`)。

**API 兼容**：6 函数 `user_id` 默认 None → 10+ 现有调用点零破坏（admin_system / operator_benchmark / operator_persona_writer / operator_seeding_writer / operator_subtitle / kol_scheduler）。

**未来增量**：其余调用点后续逐步补 `user_id=current_user.id`（日志照常写，只是 user_id=NULL）。

---

### M2 工作项 — Sprint 22 复盘（retrospective）✅ 完成（feature/kol-workspace，PR #13 已合并 2026-06-30）

**核心定位**：红人工作台复盘子模块。支持多维材料录入（直播数据/素材数据/评价文字/直播脚本/素材脚本），AI 流式生成复盘报告，支持历史管理和 Word 导出。不设 workspace_tools 注册（属 KolWorkspace 内嵌模块，非独立工作台工具）。

| # | 事项 | 结果 |
|---|------|------|
| 1 | Migration 045 | `retrospective_sessions` + `retrospective_configs` 两张表 |
| 2 | ORM 模型 2 个 | `RetrospectiveSession`、`RetrospectiveConfig` |
| 3 | 后端接口 9 个 | admin GET/PUT config（2）+ operator list/create/delete/parse-files/analyze（SSE）/export-word（7） |
| 4 | conftest.py 更新 | `operator_retrospective.AsyncSessionLocal` 加入 patch 列表 |
| 5 | 前端 | `types/retrospective.ts` + `api/retrospective.ts` + `WorkspaceRetrospective.tsx`（三视图）+ `RetrospectiveConfigTab.tsx` |
| 6 | 工作台接入 | `KolWorkspacePage.tsx` 加 `retrospective` 导航项 + `WorkspaceConfigPage` 注册 ConfigTab |
| 7 | 后端集成测试 | 13 / 13 通过 |
| 8 | 前端组件测试 | 6 / 6 通过 |
| 9 | 契约文档 | `Base_API §28` + `Base_Database §34-35` 已更新 |
| 10 | 测试报告 | `backend/docs/tests/M2_Sprint22_测试报告_复盘_v1.md` |

**关键设计点**：
- **三视图模式**：列表视图（历史）→ 编辑视图（录入材料 + 分析）→ 详情视图（查看报告）
- **材料多维输入**：直播数据/素材数据/评价文字 支持文件解析（parse-files 接口），直播脚本/素材脚本支持粘贴
- **analyze 自动保存**：SSE 流完成后后台 AsyncSessionLocal 写 result + status='done'，前端无需手动保存
- **物理删除**：复盘记录允许物理删除（业务决策，非软删）

**不在范围**：
- 多用户共享复盘（当前按 created_by 隔离）
- 复盘历史版本管理
- 复盘模板功能

---

### M2 工作项 — 旧架构数据全量迁移到新架构 ✅ 完成（2026-06-28，本地 mcn_m1 已导入；迁移工具 + 记录文档待提交）

**背景**：旧架构 15 个服务的备份数据（`D:\2026年工作\AI相关\Arya姐\backups\all-services-data-backup-20260627`，JSON + Markdown 混合存储）需迁移到新架构 PostgreSQL，让历史数据在新架构功能里可见、可查询、可继续使用。

**执行结果**（272 INSERT + 20 UPDATE + 32 新 KOL，单一 transaction）：

| Phase | 服务 | 数据形态 | 目标表 | 新增 |
|-------|------|---------|--------|------|
| A.1 | benchmark-analyzer | 34 JSON | `benchmark_analyses` | 34 |
| A.2 | kol-intake | 6 JSON | `kol_intake_links` + `kol_intake_submissions` | 6+6 |
| A.3 | persona-positioning | 10 JSON | `persona_reports` | 10 |
| A.4 | selling-point-extractor | 37 JSON | `outputs`（tool_code='selling-point-extractor'） | 37 |
| B | 6 服务 personas/ 目录 | soul.md + content-plan.md | `kols.persona` / `kols.content_plan` | 32 新 KOL + 12 persona + 8 plan |
| C.1 | qianchuan-collection/global/scripts | 68 .md | `qianchuan_collection_scripts`（pool='global'） | 68 |
| C.2 | qianchuan-collection/personas.bak | 33 .md | `qianchuan_collection_scripts`（pool='persona'） | 33 |
| C.3 | material-library/\<name\>/scripts | 24 .md | `kol_references`（type='红人爆款文案'） | 24 |

**关键设计**：
- 脚本 `backend/scripts/migrate_legacy_data.py`（~580 行，参考 `migrate_material_library.py`）
- CLI：`--backup-dir --admin-id 1 --dry-run/--no-dry-run --phase=A|B|C|all --service=<name> --overwrite`
- 幂等：benchmark 按 (sec_user_id, created_at)、kol-intake 按 token UNIQUE、persona-report 按 (operator_id, influencer_name, created_at)、selling-point 按 content_json.legacy_id、Phase B 按 name+NULL、Phase C 按 (pool, title)/(kol_id, title)
- 事务：A+B+C 同一 AsyncSessionLocal，任一异常全 rollback（第一轮失败已验证 rollback 干净）
- 身份：所有 created_by/operator_id/owner_id = user_id=1 (admin)
- 踩坑1：Windows 控制台 GBK 遇 emoji 报 UnicodeEncodeError → 入口 `sys.stdout.reconfigure(encoding='utf-8')`
- 踩坑2：PostgreSQL 拒绝 `\u0000`（DOCX/PDF base64 二进制含此字符）→ `_strip_nulls` 递归清洗所有 Text/JSONB 字段
- 踩坑3：dry-run 跨服务同名 KOL 误报"新建 39"（实际 32）→ 进程内 `_KOL_CACHE` 解决 + Phase C 找不到 KOL 问题

**未迁 4 个**：taoran-writer（products 表不存在）/ huimin-studio + taoran-studio（studio 表不存在）/ anya-agent（空数组）。详见迁移记录文档"未迁服务"章节。

**产物**（仍在工作区待提交）：
- 脚本：`backend/scripts/migrate_legacy_data.py`
- 服务器导出脚本：`backend/scripts/export_legacy_for_server.py`（生成 `legacy_for_server_*.sql`，20MB，含真实业务数据，已加 .gitignore）
- 前置检查 SQL：`deploy/scripts/preflight_legacy_migration.sql`
- 迁移记录：`docs/pm/M2_数据迁移记录_legacy_to_new.md`（含字段映射、count 对比、抽样核查、回滚预案、合规检查）

---

### M2 工作项 — Sprint 21 字幕异步任务化 + 统一历史 + 软删除 ✅ 完成（main，PR #15 已合并）

**背景**：用户反馈"解析过程中切换页面回来后看不到历史记录"，且单条 ASR 解析需 1-3 分钟同步阻塞前端不合理。基于 Sprint 19 字幕提取（main，PR #14 已合并）做异步化迭代。

**实施记录**：

| # | 事项 | 结果 |
|---|------|------|
| 1 | Migration 044 + 045 | `subtitle_jobs.kind`（single/batch）+ `deleted_at`（软删除）+ `(kind, deleted_at)` 索引；`subtitle_items.meta_json`（单条任务的视频元信息 JSON） |
| 2 | POST /extract 异步任务化 | 改为创建 `SubtitleJob(kind='single', total=1)` + 后台 `asyncio.create_task(_run_single_extract())`，立即返回 `{job_code, status:'processing'}`；前端拿 job_code 轮询 |
| 3 | 新增 DELETE /batch/{job_code} | 软删除（设置 `deleted_at = now()`），写 OperationLog（action=`subtitle_delete`） |
| 4 | GET /batches 改语义 | 单条+批量统一历史列表（过滤 `deleted_at IS NULL`），原"我的批量任务"语义被替换 |
| 5 | 前端 HistoryList 组件 | `pages/operator/subtitle/HistoryList.tsx`（新建）：自包含，展开详情/复制/重新生成思维导图/删除/自动轮询 processing 任务 |
| 6 | 前端 API 重命名 | `listMyBatches` → `listHistory`（保留别名），新增 `deleteHistory`；SubtitleExtractorPage 单条区改轮询模式（创建 job → 每 3s 轮询 → 完成显示） |
| 7 | _item_to_dict 扁平化 | meta_json 里的 play_url/cover_url/nickname/digg_count/aweme_id 扁平到 API 响应顶层 |
| 8 | 测试 | 后端 `test_operator_subtitle.py` 30/30 ✅ + `test_admin_subtitle.py` 11/11 ✅；前端 `SubtitleExtractorPage.test.tsx` 5/5 ✅ + `HistoryList.test.tsx` 6/6 ✅ |
| 9 | 文档 | 契约 Base_API §25 + Base_Database §30 + 前后端 README + 需求文档 + 前后端任务单 + 测试报告 + 前后端开发验收 均已落地 |

**踩坑记录**：
1. **OperationLog COUNT 全量套件污染**：测试 `WHERE action = 'subtitle_xxx'` 在全量 suite 跑时其他用例污染计数，改用 `EXISTS + detail::json->>'job_code' = :jc` 精确匹配
2. **批量 replace_all 漏 `result?.text` 可选链版本**：`replace_all('result.text' → 'result.transcript')` 漏掉 5 处 `result?.text`，单独再做一次 `replace_all('result?.text' → 'result?.transcript')`
3. **fake timers + userEvent 异步轮询测试**：必须 `vi.useFakeTimers({ shouldAdvanceTime: true })` + `userEvent.setup({ advanceTimers: vi.advanceTimersByTime })`，否则 setInterval 不触发
4. **Windows watchfiles 不触发 uvicorn reload**：改完代码后必须手动重启 uvicorn（kill 父+子+multiprocessing 孙三个进程），不能依赖 --reload 自动加载

**不在本次范围**：思维导图持久化（仍只缓存前端 state）、批量任务的"重新生成思维导图"（仅单条支持）、WebSocket 推送（仍轮询）、历史记录搜索/筛选、批量任务的批量删除。

---

### M2 工作项 — Sprint 21 千川脚本预审（qianchuan-script-review）✅ 完成（feature/kol-workspace）

**核心定位**：工作台独立工具页，对千川脚本进行 AI 预审。支持「千川直销模式」（检查产品名/价格/卖点替换）和「价值观模式」（评估情绪强度/信息差）两种预审类型，返回结构化结论（rating/must_fix/suggestions/passed）。

| # | 事项 | 结果 |
|---|------|------|
| 1 | Migration 044 | `qianchuan_script_review_configs` 表 + 默认配置种子 |
| 2 | 后端接口 3 个 | admin GET/PUT config（2）+ operator POST review（1，非流式） |
| 3 | conftest.py 更新 | `operator_script_review.AsyncSessionLocal` 加入 patch 列表 |
| 4 | 前端 | `types/scriptReview.ts` + `api/scriptReview.ts` + `QianchuanScriptReviewPage.tsx`（双栏布局）+ `ScriptReviewConfigTab.tsx` |
| 5 | 路由注册 | `App.tsx` 加 `/workspace/qianchuan-script-review` lazy 路由 |
| 6 | 后端集成测试 | 8 / 8 通过 |
| 7 | 前端组件测试 | 7 / 7 通过 |
| 8 | 契约文档 | `Base_API §27` + `Base_Database §33`（已存在）已更新 |
| 9 | 测试报告 | `backend/docs/tests/M2_Sprint21_测试报告_qianchuan-script-review_v1.md` |

**关键设计点**：
- **非流式预审**：AI 返回完整 JSON，前端等待结果（不走 SSE），适合短脚本快速判定
- **两 Prompt 合一配置**：`direct_prompt` + `value_prompt` 同存一条 `config_key='default'` 配置行
- **JSON 容错解析**：AI 返回 markdown fence 包裹 JSON 时自动提取，解析失败返回 error_response
- **rating 三档**：`pass`（可上线）/ `minor`（小改可上线）/ `fail`（需大改）

---

### M2 工作项 — Sprint 20 价值观仿写 ✅ 完成（feature/kol-workspace，PR #13）

| # | 事项 | 结果 |
|---|------|------|
| 1 | Migration 043（原 038） | `values_writer_configs` 表 + 默认配置种子 |
| 2 | 后端接口 6 个 | 管理端 GET/PUT config + 运营端 extract-values（非流式）+ emotion-direction/write/iterate（SSE 流式） |
| 3 | 前端 ValuesWriterPage | 4 步向导（选价值观→情绪方向→生成内容→迭代），同时导出 ValuesWriterModule 供工作台内嵌 |
| 4 | 工作台接入 | `values-writer` 导航项激活，点击直接进 Step 2（达人已锁定） |
| 5 | 管理端配置 | ValuesWriterConfigTab（4 Prompt + 模型 + 启用开关） |
| 6 | 测试 | 后端 1017/1017 通过，前端 203/203 通过 |

---

### M2 工作项 — Sprint 19 红人工作台扩展（feature 分支）✅ 完成（feature/kol-workspace，PR #13）

**背景**：Sprint 18 建立了工作台框架，Sprint 19 补全达人相关的内容模块，并让工具以 Module 方式内嵌进工作台。

| # | 事项 | 结果 |
|---|------|------|
| 1 | WorkspacePersona | 5 分区人物档案 inline 编辑（background/experience/relationships/unique_story/extra_notes） |
| 2 | WorkspaceReferences | 素材库 6 类管理（人设/千川各 3 类，折叠列表 + Popconfirm 删除） |
| 3 | 5 个工具页拆 Module | QianchuanWriterModule / SeedingWriterModule / PersonaWriterModule / LivestreamWriterModule / LivestreamReviewModule |
| 4 | KolWorkspacePage 接入 | 9 个导航项激活（含新增 seeding-writer/persona-writer/livestream-writer/livestream-review） |
| 5 | 测试 | 198/198 全通过（含修复 Sprint 16 预存失败） |

---

### M2 工作项 — Sprint 19 字幕提取（subtitle-extractor）迁移（main 分支）✅ 完成

**背景**：旧架构 `Ai_Toolbox/subtitle-extractor-web/` 全量迁移。Sprint 3 起即有 `tool_transcribe.py`（云雾 Whisper，Sprint 3 债务），本次新建 `operator_subtitle.py` + `admin_subtitle.py`，与 tool_transcribe.py 不冲突。ASR adapter 已在 Sprint 4+ 就绪可调用。

**实施记录**（8 步全部完成）：

| 步骤 | 状态 | 产物 |
|------|------|------|
| Step 1 分支 + 数据库 | ✅ | migration 035（3 表 + seed + workspace_tools subtitle online/140）+ 3 ORM（SubtitleJob/Item/Config）|
| Step 2 单条字幕提取 | ✅ | POST /extract（share_text/file_url 路径）+ 5 tests + 前端 Tab 1 |
| Step 3 思维导图 + admin 配置 | ✅ | POST /mindmap（yunwu + JSON 解析含 markdown fence 清理）+ 6 tests + admin 2 端点 + 8 tests + SubtitleConfigTab + WorkspaceConfigPage 注册 |
| Step 4 批量字幕提取 | ✅ | POST /batch + _run_batch（AsyncSessionLocal 后台任务）+ GET /batch/{job_code}（含 items 进度）+ 前端批量 Tab + conftest `_SESSION_LOCAL_PATCH_TARGETS` 加 `app.routers.operator_subtitle.AsyncSessionLocal`（红线 #7）|
| Step 5 导出 + 产出接入 | ✅ | POST /save-output（写共享 outputs 表 tool_code='subtitle'）+ 4 tests + 前端 SRT/Excel/Zip 导出按钮（xlsx + jszip）+ 保存到产出中心按钮 |
| Step 6 workspace_tools online + 文档 | ✅ | workspace_tools.subtitle online/140（migration 035 内 UPDATE）+ Base_API §25 + Base_Database §30 + 前后端 README + M2_Sprint19 需求文档 |
| Step 7 全量回归 + PR | 🔄 待 PR | 测试 25+8 全过，待 commit + push + PR |
| Step 8 移除 access_code 改用 created_by | ✅ | 旧架构无用户系统的产物（`access_code` 8 位跨设备查询码）改为 JWT + `created_by` 绑定；migration 035 删字段、3 个端点重做（删 by-access、加 /batches 运营端、加 /admin/subtitle/batches 管理端）、operator 25→28 tests + admin 8→11 tests、前端批量 Tab 用「我的批量任务」列表替代 access_code 输入框 |

**关键技术决策**：
1. **批量后台执行**：`asyncio.create_task(_run_batch())`，用 AsyncSessionLocal 独立 session 脱离请求生命周期；conftest patch 列表已加。
2. **思维导图**：默认模型 `claude-haiku-4-5-20251001`（mindmap_model_id 配置缺失或失效时回退）；yunwu_adapter.chat() 非流式调用。
3. **JSON 解析容错**：`re.sub(r"^```(?:json)?\s*\n?", "", raw, flags=re.MULTILINE)` 清理 markdown fence 后再 json.loads。
4. **产出接入复用全局路由**：`POST /save-output` 写共享 outputs 表，列表/详情/删除走全局 `/api/outputs?tool_code=subtitle`，不重复。
5. **批量任务身份绑定改用 created_by**（Step 8 决策，覆盖原 access_code 方案）：新架构 JWT 已足够；任务通过 `subtitle_jobs.created_by` 绑定用户身份，`GET /batch/{job_code}` 加 `created_by == current_user.id` 过滤，`GET /batches` 列表只看自己；管理员通过 `GET /admin/subtitle/batches` 跨用户查询。原 access_code 字段、`_gen_access_code` helper、`GET /batch/by-access` 端点、前端「跨设备查询」输入框全部删除。

**测试统计**（Step 8 后）：
- `test_operator_subtitle.py` 28/28 ✅（TestAuth 4 + TestExtract 5 + TestMindmap 6 + TestBatch 2 + TestBatchQuery 3 + TestBatchesList 4 + TestSaveOutput 4）
- `test_admin_subtitle.py` 11/11 ✅（TestAuth 4 + TestGetConfigs 1 + TestUpdateConfigs 3 + TestAdminBatches 3）

**不在本次范围**：
- tool_transcribe.py 改造（Sprint 3 债务，继续云雾 Whisper）
- 批量任务多进程（Celery/RQ）
- 字幕翻译 / 字幕时间轴对齐（旧架构也没做）
- access_code 跨设备查询模式（Step 8 已废弃，新架构 JWT + created_by 替代）

---

### M2 工作项 — Sprint 18 红人工作台基础架构（feature 分支）✅ 完成（feature/kol-workspace，PR #13）

**背景**：huimin-studio 全量迁移需求确认，以达人为中心建立「红人工作台」，本 Sprint 建立数据层 + Shell + 首页 Dashboard + 千川产品库 Module。

| # | 事项 | 结果 | 归属 |
|---|------|------|------|
| 1 | Migration 039-042（原 034-037） | kols+5列 + qianchuan_products + kol_benchmarks + kol_active_products | 本地 DB |
| 2 | ORM 模型 3 个 + kol.py 扩展 | QianchuanProduct / KolBenchmark / KolActiveProduct | 后端 |
| 3 | 后端接口 13 个 | 千川产品库(4) + 工作台首页(1) + 对标账号(4) + 在售商品(2) + 人物档案(2) | 后端 |
| 4 | 前端工作台框架 | KolWorkspacePage Shell + WorkspaceDashboard + QianchuanProductsModule | 前端 |
| 5 | 路由 + 入口 | /kol-workspace/:kol_id 路由 + KolsPage「进入工作台」按钮 | 前端 |
| 6 | 测试 | 后端 32 个集成测试全通过（1006/1006）；前端 18 个单元测试全通过 | 测试 |

**待办**：PR 创建 + CI 通过 + 人工验收（访问 http://localhost:5175，从红人列表进入工作台验证）

---

### M2 工作项 — Sprint 18 素材库迁移（main 分支）✅ 完成

迁移自旧架构 `Ai_Toolbox/material-library-web/`。后端 migration 034 + 2 张新表（kol_references + material_library_configs）+ 9 个 API（7 运营 + 2 管理）+ 22 个后端测试通过 + 6/6 convention_guard；前端 MaterialLibraryPage（左右分栏 4 Tab：人格档案/内容规划/参考素材/入驻信息）+ MaterialLibraryConfigTab + 18 个前端测试通过。关键决策：人格档案/内容规划复用 kols.persona + kols.content_plan（**不新建 profile 表**）。契约文档同步：Base_API §24 + Base_Database §28-29 + 前后端 README + 根 README。

---

### M2 工作项 — 2026-06-24 迁移收尾 + 日志链路修复 + 文档补遗 ✅ 完成（PR #8 + #9 待合并）

**背景**：Sprint 16 后核查发现 5 个工具（livestream-writer/review、persona-review、qianchuan-preview/collection）的 migration 021-025 未执行到数据库，workspace_tools 停在 14 条；同时 AI 调用日志链路有断层（管理员端不可见）；多个 Sprint 缺需求文档/测试报告。

| # | 事项 | 结果 | 归属 |
|---|------|------|------|
| 1 | migration 021-025 执行 | workspace_tools 14→19 条，5 工具全部注册 | 本地 DB |
| 2 | persona-review + livestream-review 设 online | 16 工具全部上线，运营端可用 | 本地 DB |
| 3 | 日志链路修复 | yunwu adapter `chat()`/`chat_stream()` 双写 ExternalServiceLog（service="ai"），管理员「外部服务日志」页可见 AI 调用 | PR #8 |
| 4 | Sprint 8/9/10 文档补遗 | persona-review 需求文档 + 3 份测试报告（34/58/54 passed）+ 前后端 README 补登 | PR #8 |
| 5 | LivestreamReviewConfigTab 补建 | livestream-review 前端配置页（复刻 PersonaReviewConfigTab），5 工具管理员配置页全部对齐 | PR #9 |

**日志链路修复详情**：
- 问题：`ai_call_logs`（yunwu adapter 写）与 `external_service_logs`（管理员 ExternalLogsPage 读）是两张独立表，AI 调用只写前者 → 管理员端不可见
- 修复：yunwu adapter finally 块增加 ExternalServiceLog 双写（service="ai"），与 AiCallLog 并行
- 测试：test_credential_pool.py 新增 `_count_external_logs` helper + 双写断言，27 passed

**5 工具管理员配置能力（修复后全部对齐）**：

| 工具 | 后端 API | 前端 ConfigTab | 状态 |
|------|:---:|:---:|:---:|
| livestream-writer | ✅ | ✅ | online |
| livestream-review | ✅ | ✅ PR #9 补建 | online |
| persona-review | ✅ | ✅ | online |
| qianchuan-preview | ✅ | ✅ | online |
| qianchuan-collection | N/A（脚本库不调 AI） | N/A | online |

**迁移进度统计**：19 个旧工具中 **16 个已迁移完成且 online**（14 原 online + 2 新上线）；3 个 workspace_tools 遗留占位（qianchuan/review/subtitle，无完整代码）；剩余约 4 个旧工具未迁移。

**待办（不影响本批 PR）**：
- stash@{0}：Sprint 3 补遗文档 + Sprint 17 需求文档，需独立 PR
- 技术债务：`secret_enc` 明文加密 / TikHub 日志 bug / 软删改造
- 新功能：ASR 完整方案（有 plan 未开工）/ 4 个未迁移工具（字幕提取/素材库/人格预览/涛然写作）

---

### M2 工作项 — Sprint 14 千川文案写作迁移（qianchuan-writer）✅ 完成（已合并到 main，PR #5 merge commit cc9d665）

**核心定位**：旧架构 `Ai_Toolbox/qianchuan-writer-web` 整体迁移到新架构。4 步向导业务逻辑 100% 保留（选达人→加载产品→输入脚本→生成仿写），Prompt 模板化（占位符从旧版 `${var}` 改为新架构 `{{var}}`），AI 模型可配，产出与账号绑定入库可查历史。参照样板：`tiktok-writer`（Prompt 表 + ConfigTab + operator 向导页）。

**分支**：`migrate/qianchuan-writer`（从 main 拉新分支，PR #4 合并后开始）

| 端 | 状态 | 备注 |
|----|------|------|
| Migration 030 | ✅ 完成 | `qianchuan_writer_configs` 表（config_key/system_prompt/ai_model_id/is_active）+ 种子 Prompt（含 `{{name}}`/`{{soul}}`/`{{content_plan}}` 占位符）+ `workspace_tools` 注册（status='dev'）|
| ORM 模型 | ✅ 完成 | `QianchuanWriterConfig`（参照 TiktokWriterConfig 结构）|
| Prompt 渲染 service | ✅ 完成 | `app/services/qianchuan_writer_prompt.py::render_system_prompt`，正则一次性替换 `{{name}}`/`{{soul}}`/`{{content_plan}}`（避免 soul 内含 `{{name}}` 文本时二次替换）|
| operator router（6 接口）| ✅ 完成 | `operator_qianchuan_writer.py`：GET /kols/personas（JOIN users 拿 creator_name 标签）+ POST /parse-file（复用 file_parser）+ POST /chat（yunwu_adapter SSE 流式）+ POST /save-output（写 outputs 账号绑定）+ POST /export-word（docx StreamingResponse）+ GET /outputs（账号隔离分页）|
| admin router（2 接口）| ✅ 完成 | `admin_qianchuan_writer.py`：GET/PUT /configs（参照 TiktokWriterConfigTab 模式）|
| Router 注册 | ✅ 完成 | `app/main.py` include 两个 router；`conftest.py` patch 列表加 operator_qianchuan_writer（用 AsyncSessionLocal 流式）|
| 前端 types | ✅ 完成 | `frontend/src/types/qianchuanWriter.ts`（8 接口请求/响应类型）|
| 前端 API 层 | ✅ 完成 | `frontend/src/api/qianchuanWriter.ts`（8 函数，6 operator + 2 admin）|
| 前端 4 步向导页面 | ✅ 完成 | `QianchuanWriterPage.tsx`（选达人 + 加载产品 6 格式 + 输入脚本实时字数 + 流式仿写 + 多轮追问 + 保存历史 + 导出 .txt/.docx）|
| 前端 ConfigTab | ✅ 完成 | `QianchuanWriterConfigTab.tsx`（system_prompt/ai_model_id/is_active，参照 TiktokWriterConfigTab）|
| 前端路由 + Tab 注册 | ✅ 完成 | `App.tsx` React.lazy + Route `/workspace/qianchuan-writer`；`WorkspaceConfigPage.tsx` 注册 ConfigTab |
| 单元测试 | ✅ 8/8 | `test_qianchuan_writer_prompt.py`：4 占位符替换 + 2 缺失 fallback + 1 多次出现 + 1 真实模板 |
| operator 集成测试 | ✅ 20/20 | 4 鉴权 + 3 personas + 3 parse-file + 4 chat + 3 save-output + 2 export-word + 2 outputs（账号隔离）|
| admin 集成测试 | ✅ 9/9 | 4 鉴权 + 1 GET configs + 4 PUT configs（Prompt/ai_model_id/OperationLog/config_key 不存在）|
| 前端组件测试 | ✅ 11/11 | 4 步向导渲染 + 各 Step 交互 + 流式输出 mock + 多轮追问 + 保存/导出 3 按钮 + ConfigTab 渲染与提交 |
| 全量回归 | ✅ 后端 805 passed / 前端 138 passed | 后端 2 failed 为预存 snappy 问题（`test_livestream_writer_file_parser` .pages 解析），已 git stash 验证非本次引入 |
| 契约同步 | ✅ 完成 | `MCN_M2_Base_API.md` 加 §21（6 运营端 + 2 管理端接口）；`MCN_M2_Base_Database.md` 加 §25 qianchuan_writer_configs（含种子 Prompt 模板）；前后端 README 计数同步（models 28/routers 50/migrations 030/api 31/types 21/tasks 42-43）|

**关键设计点：**
- **Prompt 模板化**：旧版 `${var}` 前端拼接 → 新版 DB 存 `{{name}}`/`{{soul}}`/`{{content_plan}}`，后端 `render_system_prompt()` 正则一次性替换
- **三接口分离**：chat / save-output / export-word 各自独立（比 tiktok-writer 合并写库更清晰，前端两按钮独立调用）
- **达人列表 creator_name 标签**：`LEFT JOIN users ON kols.created_by = users.id`，系统预设返回 `'系统预设'`，用户自建返回用户名（为后续「A 用户私享」预留）
- **账号隔离**：outputs 查询 `WHERE created_by=current_user.id AND deleted_at IS NULL`
- **导出文件名 URL 编码**：后端 `Content-Disposition: filename*=UTF-8''<encoded>`（支持中文）
- **page_size 白名单**：仅允许 10/20/50，其他值 fallback 到 20
- **流式 429 重试**：delays `[2, 4, 6]` 秒（最多 3 次）
- **默认 AI 模型**：`ai_model_id` 留空或失效走 `claude-opus-4-6-thinking`
- **三接口命中三层日志**：chat 写 ai_call_logs（adapter 自动）+ operation_logs（router BackgroundTask）+ save-output 写 outputs（历史）

**技术决策（实施过程）：**
1. React 19 + AntD 5 TextArea 受控组件在 jsdom 中 `user.type` 可工作，但需"下一步"按钮点击触发 Step 切换
2. AntD Button 自动在两个字符按钮文本间加空格（"确认"→"确 认"），测试用 `/确\s*认/` 正则匹配
3. jsdom 不支持 `Element.scrollIntoView`，测试文件顶部 mock
4. `.txt` 前端 Blob 下载（不走后端）；`.docx` 调 `/export-word` 返回 StreamingResponse

**不在本次范围（留作后续独立任务）：**
- **workspace_tools 改 status='online'**：测试通过后管理端手动改（或后续脚本批量改）
- **persona 数据补全**：旧架构本地仅 2 个 persona（孙知羽 v6.0 + 陶然 v2.0），新架构 kols 表 4 活跃但 persona=NULL，需要业务侧手工录入
- **A 用户私享达人**：本次达人对全部公开，后续若需要"A 用户添加的达人 A 用户只能使用"需要改查询 SQL 加 `OR kols.created_by = current_user.id` 过滤
- **其余 5 个"已迁移但未注册 workspace_tools"工具**：livestream-review / persona-review / qianchuan-collection / qianchuan-preview / seeding-writer 待迁移

---

### M2 工作项 — Sprint 15 人设脚本仿写迁移（persona-writer）✅ 完成（待 PM 签收 + 推 PR #6）

**核心定位**：旧架构 `Ai_Toolbox/persona-writer-web`（Next.js 14）整体迁移到新架构。3 步向导业务逻辑 100% 忠实旧版（加载风格 → 对标验证 → 仿写创作），4 个 Prompt + 2 个 AI 模型（light / heavy）admin 全部可配。Step 2 含抖音链接解析（TikHub）+ 点赞门槛硬编码（≥10万）+ AI 开头评估；Step 3 含 AI 结构拆解 + 双选题（💡我有想法 / 🤖我没想法）+ 多轮追问（含图片）+ 终稿编辑（手动复制对标原文）。参照样板：`qianchuan-writer`（Sprint 14）。

**分支**：`migrate/persona-writer`（从 main 拉新分支，PR #5 合并后开始）

| 端 | 状态 | 备注 |
|----|------|------|
| Migration 031 | ✅ 完成 | `persona_writer_configs` 表（4 Prompt 字段 + light/heavy_model_id + is_active）+ 种子 4 Prompt（从旧版 page.tsx 提取）+ `workspace_tools` UPSERT（status='online' 直接上线）|
| ORM 模型 | ✅ 完成 | `PersonaWriterConfig`（参照 QianchuanWriterConfig 扩展为 4 Prompt + 2 模型）|
| Prompt 渲染 service | ✅ 完成 | `app/services/persona_writer_prompt.py::render_prompt`，7 占位符 + `{{is_custom}}...{{/is_custom}}` / `{{!is_custom}}...{{/!is_custom}}` 块语法（双模式分支）+ 正则一次性替换防二次替换 |
| tikhub adapter 扩展 | ✅ 完成 | `fetch_video_by_share_url(share_url, db)`，调 `GET /api/v1/douyin/web/fetch_one_video_by_share_url`，finally 写 TikHubCallLog |
| operator router（8 接口）| ✅ 完成 | `operator_persona_writer.py`：GET /kols/personas + POST /fetch-video（含 likes_pass 门槛判定）+ POST /evaluate-opening（流式 light）+ POST /analyze-structure（流式 light）+ POST /chat（流式 heavy，scene=writing/iteration 双场景）+ POST /save-output + POST /export-word + GET /outputs |
| admin router（2 接口）| ✅ 完成 | `admin_persona_writer.py`：GET/PUT /configs（4 Prompt + 2 模型 + is_active）|
| Router 注册 | ✅ 完成 | `app/main.py` include 2 router；`conftest.py` patch 列表加 operator_persona_writer |
| 前端 types | ✅ 完成 | `frontend/src/types/personaWriter.ts`（含 ChatRequest scene/topic_mode 双字段）|
| 前端 API 层 | ✅ 完成 | `frontend/src/api/personaWriter.ts`（10 函数：8 operator + 2 admin；3 流式 + 1 Blob 例外）|
| 前端 3 步向导页面 | ✅ 完成 | `PersonaWriterPage.tsx`（重写 placeholder）：Step 1 选达人预览 → Step 2 链接解析+点赞门槛+文案+AI 评估+质量门 → Step 3 结构拆解+双选题+写作+多轮追问+图片上传+终稿编辑+导出 |
| 前端 ConfigTab | ✅ 完成 | `PersonaWriterConfigTab.tsx`（4 Prompt TextArea + 2 模型 Select + is_active Switch）|
| 前端路由 + Tab 注册 | ✅ 完成 | `App.tsx` Route `/workspace/persona-writer`（已存在）；`WorkspaceConfigPage.tsx` 注册 ConfigTab |
| 单元测试 | ✅ 16/16 | `test_persona_writer_prompt.py`：7 占位符替换 + 块语法 is_custom + fallback + 多次出现 + 真实模板 + 防二次替换 |
| tikhub 单测扩展 | ✅ +3 | `test_tikhub_adapter.py` 扩展：fetch_video_by_share_url 成功/失败/URL 解析 |
| operator 集成测试 | ✅ 30/30 | 鉴权 4 + personas 3 + fetch-video 5 + evaluate 3 + analyze 3 + chat 5 + save 3 + export 2 + outputs 2 |
| admin 集成测试 | ✅ 9/9 | 鉴权 4 + GET 1 + PUT 4 |
| 前端组件测试 | ✅ 19/19 | 3 步向导渲染 + Step 1/2/3 各环节 + 双选题切换 + 图片上传 mock + 多轮追问 + 终稿提示 + 保存/导出 + ConfigTab |
| 全量回归 | ✅ 后端 863 passed / 前端 157 passed | 后端基线 805 → 863（+58）；前端基线 138 → 157（+19）；后端 2 failed 仍为预存 snappy 问题 |
| 契约同步 | ✅ 完成 | `MCN_M2_Base_API.md` 加 §22（8 运营端 + 2 管理端）；`MCN_M2_Base_Database.md` 加 §26 persona_writer_configs（含 7 占位符 + 块语法）；前后端 README 计数同步（models 29/routers 52/migrations 031/api 32/types 22/tasks 43-44）|

**关键设计点：**
- **4 Prompt + 2 模型 admin 可配**：评估/拆解用 light（claude-haiku-4-5-20251001）；写作/追问用 heavy（claude-opus-4-6）。旧版 qwen-flash 在新架构 ai_models 表未注册，改用 claude-haiku-4-5 替代
- **`{{is_custom}}` 块语法**：双选题（💡我有想法 / 🤖我没想法）Prompt 合并到 1 个 writing_prompt，用 `{{is_custom}}...{{/is_custom}}` 和 `{{!is_custom}}...{{/!is_custom}}` 块语法区分。比简单替换为 'true'/'false' 更优雅（AI 不需要理解 if-else 逻辑）
- **图片追问复用 /api/files**：不新增专用上传接口，运营端 API 总数维持 8 个（决策 #15）
- **点赞门槛硬编码 100000**：业务铁律（对标必须 ≥10 万赞），不让 admin 改（避免降标）
- **质量门判定**：`likes_pass AND (评估含"通过"且不含"不通过") AND user_agree` 三件套全 ✅ 才能进 Step 3
- **流式 429 重试**：delays `[2, 4, 6]` 秒（同 qianchuan-writer）
- **5 张日志表全覆盖**：ai_call_logs（yunwu finally）+ tikhub_call_logs（tikhub finally）+ operation_logs（router 显式写 fetch-video/save-output/PUT configs/chat create_job）+ outputs（save-output 写）+ task_jobs（chat create_job=true 写）
- **workspace_tools status='online' 直接上线**：已通过 E2E 测试，不需后续手动改

**关键技术决策（实施过程）：**
1. **subagent 派工模式**：PM 派 2 个 subagent（后端 + 前端）按需求文档 + qianchuan-writer 样板自主开发，PM 只做需求确认 + 验收 + 文档收尾。后端 subagent 86/86 测试全绿；前端 subagent 19/19 测试全绿
2. **`{{is_custom}}` 块语法**（subagent 创新）：原需求文档设计是替换为 'true'/'false' 让 AI 理解 if-else；subagent 改为块语法，渲染阶段就移除/保留整段，AI 拿到的是单一确定 Prompt，更稳定
3. **3.5 终稿编辑纯前端**：用户手动改 textarea + 复制对标原文前 2-3 句，无后端交互（业务铁律保留）
4. **流式 API 设计**（前端 subagent）：3 个流式函数（evaluateOpeningStream / analyzeStructureStream / chatStream）接收 `onChunk` 回调，内部封装 `readPlainStream` helper
5. **双分支顺序开发**：先后端 subagent 完成契约稳定，再派前端 subagent（避免并行契约漂移）

**不在本次范围（留作后续独立任务）：**
- **tool_transcribe 改造**：继续用云雾 Whisper（Sprint 3 债务）
- **service_credentials.secret_enc 加密**：Sprint 3 债务
- **TikHub adapter 日志写入 bug**：Sprint 11 发现，独立修复
- **persona 数据补全**：旧架构本地仅 2 个 persona（孙静 + 陶然），新架构已通过 `_e2e_seed_personas.py` 一次性脚本补到 kols 表（脚本本身不进 git，保留工作区）
- **ASR 业务集成**：把 tool_transcribe 调用方切到 ASR
- **其余 5 个工具迁移**：livestream-review / persona-review / qianchuan-collection / qianchuan-preview / ~~seeding-writer~~（✅ Sprint 16 已迁移）

---

### M2 工作项 — Sprint 16 种草内容仿写迁移（seeding-writer）✅ 完成（待 PM 签收 + 推 PR #7）

**核心定位**：旧架构 `Ai_Toolbox/seeding-writer-web` 整体迁移到新架构。4 步向导（选达人+素材库 → 产品信息 → 对标验证 → 种草仿写）业务逻辑 100% 保留。新增产品库 + 素材库公司共享（对齐 kols/references 语义），6 个 Prompt 模板（14 占位符）+ 双模型可配（light=haiku 默认 / heavy=opus 默认）。首次完整集成 4 个外部 adapter（yunwu AI / tikhub 视频解析 / oss 文档转 URL / asr 录音转录）。参照样板：`persona-writer`（Prompt 表 + ConfigTab + 4 步向导）。

**分支**：`migrate/seeding-writer`（从 main 拉新分支）

| 端 | 状态 | 备注 |
|----|------|------|
| Migration 033 | ✅ 完成 | 3 表（`seeding_writer_configs` / `seeding_writer_products` / `seeding_writer_references`）+ 6 seed Prompt（从旧版提取）+ `workspace_tools` UPSERT；dollar quoting `$PROMPT_SP$` 处理 Prompt 内单引号 |
| 3 ORM 模型 | ✅ 完成 | `models/seeding_writer.py`：SeedingWriterConfig / SeedingWriterProduct / SeedingWriterReference |
| Prompt 渲染 service | ✅ 完成 | `services/seeding_writer_prompt.py::render_prompt`，14 占位符 + `{{name}}...{{/name}}` 块循环（多产品字段）+ 正则一次性替换防二次替换 |
| 文档解析 service | ✅ 完成 | `services/document_parser.py`：PDF（pypdf）/ DOCX（python-docx）/ XLSX（openpyxl）/ PPTX（python-pptx）/ TXT / MD，统一返回 7 字段 + `_rawText` |
| operator router（20 接口）| ✅ 完成 | `operator_seeding_writer.py` ~780 行： personas/references/products CRUD + 文档解析 + 卖点流式 + 视频解析 + ASR submit/poll + 结构拆解流式 + AI 推荐 + 写作/迭代流式 + 保存/导出/历史 |
| admin router（2 接口）| ✅ 完成 | `admin_seeding_writer.py`：GET/PUT /configs（6 Prompt + 2 模型 + is_active）|
| Router 注册 | ✅ 完成 | `app/main.py` include 2 router；`conftest.py` patch 列表加 operator_seeding_writer（admin 不直接 import AsyncSessionLocal 无需 patch）|
| 依赖 | ✅ 完成 | `requirements.txt` 加 `openpyxl` + `python-pptx` |
| 前端 types | ✅ 完成 | `types/seedingWriter.ts` 200 行 |
| 前端 API | ✅ 完成 | `api/seedingWriter.ts` 320 行 22 函数（16 走 request.ts + 4 SSE + 1 multipart + 1 Blob 例外）|
| 前端 4 步向导 | ✅ 完成 | `pages/operator/SeedingWriterPage.tsx` 1412 行：Step 1 达人下拉+素材库（粘贴/抖音导入/删除）/ Step 2 产品库+文档 AI 解析+卖点流式讨论+6 字段表单 / Step 3 抖音解析+ASR 5s 轮询+结构拆解流式 / Step 4 三选题模式+写作流式+多轮迭代+保存+.txt/.docx 导出 |
| 前端 ConfigTab | ✅ 完成 | `pages/admin/SeedingWriterConfigTab.tsx` 283 行：6 Prompt 卡片状态（字数/未设置）+ 编辑 Modal（8 字段：6 Prompt + light/heavy 模型 + 启用 Switch）|
| 前端路由 + Tab 注册 | ✅ 完成 | `App.tsx` Route `/workspace/seeding-writer`；`WorkspaceConfigPage.tsx` 注册 ConfigTab；`HomePage.tsx` + `WorkspacePage.tsx` 加 navigate 分支 |
| 后端单元测试 | ✅ 完成 | `test_seeding_writer_prompt.py`（14 占位符 + 块循环 + 防二次替换）+ `test_document_parser.py`（5 格式 + 异常路径）|
| 后端集成测试 | ✅ 完成 | `test_operator_seeding_writer.py`（20 接口完整覆盖 + 鉴权 + SSE）+ `test_admin_seeding_writer.py`（2 接口 + 鉴权）|
| 前端组件测试 | ✅ 23/23 | `SeedingWriterPage.test.tsx`：4 步向导全流程 + ConfigTab；ASR 测试用 `vi.setConfig({ testTimeout: 30000 })` 应对 5s 轮询；AntD 中文字间空格用正则匹配 |
| 测试报告 | ✅ 完成 | `docs/tests/M2_Sprint16_seeding-writer_测试报告.md`：后端 970/973（2 预存在 livestream 失败无关）+ 前端 180/180 |
| 契约同步 | ✅ 完成 | `MCN_M2_Base_API.md` 加 §23（20 运营端 + 2 管理端）；`MCN_M2_Base_Database.md` 加 §27（3 表 schema + 14 占位符说明）；3 README 计数同步（models 30/routers 54/migrations 033/api 33/types 23/tests 180）|

**关键设计点：**
- **产品库 + 素材库公司共享**：与 kols 一致——非用户隔离，所有运营共用一池。决策依据：旧架构已是公司共享，迁移保留语义；表字段含 `created_by` 但不强制隔离
- **ASR submit + poll 分离**：避免长连接超时。`submit_transcribe` 立即返回 task_id；前端轮询 `poll_transcribe` 每 5s 一次（最多 60 次 = 5 分钟）。adapter 不锁连接
- **6 Prompt + 14 占位符**：sp_system / parse_product / structure_analysis / ai_recommend / writing / iteration；占位符含 `{{name}}...{{/name}}` 块循环（多字段组），正则一次性替换防 `{{xx}}` 嵌套二次替换
- **双模型策略**：light（结构拆解/AI 推荐）默认 claude-haiku-4-5；heavy（卖点/写作/迭代）默认 claude-opus-4-6。ConfigTab 可改
- **文档解析后端 Python**：不用前端 JS 解析（DOCX/XLSX/PPTX 在 JS 生态依赖笨重）。pypdf/python-docx/openpyxl/python-pptx 各司其职，multipart 上传到后端 → 解析 → 返回结构化 JSON
- **4 adapter 首次齐集**：本次是 4 个外部 adapter（yunwu/tikhub/oss/asr）首次在一个功能里全部调用——OSS 用于文档 URL（ASR 需要公网 URL），ASR 用于音频转录，tikhub 用于抖音视频解析，yunwu 用于所有 AI 流式
- **测试 4 大坑（AntD 5 + Vitest 3）**：① 中文字符串按钮被 AntD 加空格（`保存`→`保 存`）→ 用正则 `/^保\s*存$/`；② `vi.setConfig({ testTimeout })` 在 `beforeEach` 里无效，必须在 `describe` 顶部；③ 多个 step 同时 in DOM 时 `openSelectAndPick` 要传 `selectIndex`；④ 列表+Modal 同文案冲突 → 用更精确的正则

**不在本次范围（留作后续独立任务）：**
- **tool_transcribe 切到 ASR**：现在继续用云雾 Whisper。本次 ASR 仅用于 seeding-writer 内部
- **service_credentials.secret_enc 加密**：Sprint 3 债务。本次 OSS/ASR AK 仍明文（继承债务）
- **service_credentials 软删改造**：Sprint 3 债务
- **预存在 livestream `.pages` 解析 2 个失败**：与本任务无关，独立修复
- **旧架构 `Ai_Toolbox/seeding-writer-web` 下线**：等用户切换 + 数据迁移完成后

---

### M2 工作项 — Sprint 16 v2 种草内容仿写 E2E 验收期 Bug 修复 🔄 进行中（v1 PR #7 同分支内集中修复）

**核心定位**：v1 主体（PR #7）已发后用户浏览器 E2E 走查发现，并入同分支 `migrate/seeding-writer` 集中修复，不开新分支。对齐 Sprint 15 v2 模式。

| 端 | 状态 | 备注 |
|----|------|------|
| ASR 采样率适配（BUG-032）| ✅ 代码修复 + 单测 | Step 3 对标验证抖音链接报 `41050008 UNSUPPORTED_SAMPLE_RATE`；根因：旧架构 `subtitle-extractor-web/lib/aliyun-asr.ts:51` 有 `enable_sample_rate_adaptive: true`，新架构 `asr.py` 迁移时漏了。修复：提取 `_build_task_dict()` 函数 + 加参数 + 单测 `test_build_task_dict_includes_sample_rate_adaptive`；17/17 通过 |
| 用户浏览器验证 | 🔄 进行中 | 用户在 Step 3 实际跑通 ASR 链路验证中 |
| BUG 登记补齐 | ✅ 完成 | `docs/pm/BUG修复登记.md` §十 |
| 测试报告补齐 | ✅ 完成 | `docs/tests/M2_Sprint16_seeding-writer_测试报告.md` §4.3 |

**关键设计点：**
- **1 行修复覆盖全量**：新架构所有 ASR 调用都走 `app/adapters/asr.py::submit_transcription`，提取 `_build_task_dict` 后该参数对所有调用点（seeding-writer Step 3 + 后续 tool_transcribe 切换）统一生效
- **迁移漏参数模式**：从旧架构抄实现时只看了核心字段（appkey/file_link/version），漏了"看似可选实则必需"的容错参数（`enable_sample_rate_adaptive`）。教训：迁移前应通读旧实现完整 task/参数字典，不能只看 happy path
- **与 Sprint 15 v2 模式对齐**：v1 主体完成后 E2E 走查发现的 bug 并入同分支修复；不开新分支；文档侧在 v1 章节后开 v2 子章节

**不在本次范围（留作后续独立任务）：**
- ~~**并发测试** `tests/concurrent/test_seeding_writer_isolation.py`~~：✅ Sprint 16 v3 已补
- ~~**Playwright E2E 基础设施**~~：✅ Sprint 16 v3 已补

---

### M2 工作项 — Sprint 16 v3 种草内容仿写 并发测试 + E2E 测试补齐 ✅ 完成（待 PM 签收 + 推 PR #7）

**核心定位**：v2 BUG-032 修复后用户要求"并发测试完成 + E2E 测试完成再推 PR"。v3 在同分支 `migrate/seeding-writer` 内补齐两类测试基础设施，不开新分支。

| 端 | 状态 | 备注 |
|----|------|------|
| 并发隔离测试 SW-ISO-001~004 | ✅ 完成 | `backend/tests/concurrent/test_seeding_writer_isolation.py`：20 op 并发写入隔离 / 跨工具隔离 / 60 条压力；4/4 通过（38.31s） |
| Playwright 基础设施 | ✅ 完成 | `playwright.config.ts`（webServer 自动起 dev / channel:'chrome' 用系统 Chrome 绕开 CDN / workers=1） |
| E2E 用例 9 个 | ✅ 完成 | smoke 3 + seeding-writer 关键路径 6（4 步向导 / Step 1 初始 / Step 1→2 切换 / Step 2 校验 / Step 3 抖音输入框 / ConfigTab）；9/9 通过（33.5s） |
| auth helper | ✅ 完成 | `helpers/auth.ts` 走真实 UI 登录（绕开 zustand 模块作用域 init 时序问题） |
| api-mock helper | ✅ 完成 | `helpers/api-mock.ts` mock OSS / 卖点流 / 抖音 / ASR / 结构分析流 / 对话流 |
| CORS 补 5175 | ✅ 完成 | `backend/.env` `CORS_ORIGINS` 加 `http://localhost:5175`（前端 dev 端口，不进 git） |
| vitest exclude E2E | ✅ 完成 | `vitest.config.ts` 加 `exclude: ['tests/e2e/**']` 防止 vitest 误收集 Playwright spec |
| 测试报告补齐 | ✅ 完成 | `docs/tests/M2_Sprint16_seeding-writer_测试报告.md` §4.4（并发）+ §4.5（E2E）+ §一总览 + §七命令 |
| 前端 README | ✅ 完成 | `frontend/docs/README.md` 加「测试体系」章节（Vitest + Playwright 双轨 + 端口约定） |

**关键设计点：**
- **channel:'chrome' 替代 Playwright chromium**：国内 Playwright CDN 1228 下载困难，改用系统已装的 Chrome（`C:/Program Files/Google/Chrome/Application/chrome.exe`），配置一行 `channel: 'chrome'` 解决
- **UI 登录替代 storageState/addInitScript/evaluate 注入**：zustand store 是模块作用域单例，`request.ts::buildHeaders()` 用 `useAuthStore.getState().token` 而非 localStorage 直读。store init 时序在 React app 模块加载那一刻固化，后续 localStorage 写入不会同步到 store state。改走 `/login` 页填表单 → 点登录 → `waitForURL(/^(?!.*\/login).+$/)` 最稳，React app 走正常流程会调 `setAuth()` 正确填充 store
- **复用 M1 并发测试基础设施**：op_users fixture（20 operator session 级）/ asyncpg + httpx 直调 API / TestResult reporter；新加 spec 文件 import 即用，不重写基础设施
- **vitest vs playwright 分工**：vitest 跑组件/单测（src/__tests__/），playwright 跑浏览器 E2E（tests/e2e/）。`vitest.config.ts` 加 exclude 防止 vitest 把 e2e spec 当 vitest 测试误收集报 `test.describe() not expected here`
- **5175 端口选择**：5173/5174 历史被旧项目占用，`vite.config.ts` 用 `strictPort: true` 锁定 5175，避免 vite 静默切换到 5176 导致 E2E webServer 探活失败

**踩坑记录（E2E 调试期 6 个 debug spec 已删）：**
1. **`.env` 改了 CORS 但 uvicorn --reload 不监听 .env**：Windows multiprocessing spawn 模式下 .env 变化不触发 reload，必须 kill 主+子进程重启（taskkill //F //PID 主 //PID 子）。本次 kill 了 40820/36220 重启生效
2. **storageState LocalStorage 一直空**：debug2-7.spec.ts 排查发现 zustand store init 早于 evaluate-set localStorage，最终改走 UI 登录解决
3. **`getByText('选达人')` strict mode violation**：page-desc 也有"选达人 · 产品信息..."文本，加 `{ exact: true }` 或换更精确选择器（heading role）
4. **Step 1 实际是"选达人"不是"加素材"**：spec v1 基于猜测写 `getByText('上传种草爆款文案')`，实际页面没有；改为基于 error-context.md 的 page snapshot 重写为"Step 1 初始状态"测试
5. **bash taskkill /F 被当路径**：git bash 下 `/F` 会被转换，必须用 `//F`（双斜杠转义）
6. **concurrent conftest 默认密码错**：`DB_URL` 默认 admin123，实际是 postgres2026；测试必须传 `TEST_DB_URL` 环境变量

**不在本次范围（留作后续独立任务）：**
- 后端预存在 2 failed（`test_livestream_writer_file_parser.py`）+ 542 errors（`test_credential_pool.py / test_workspace.py` 的 fixture 问题）：Sprint 11 之前历史债，独立修复
- **tool_transcribe 切换到 ASR**：现在继续用云雾 Whisper，独立任务

---

### M2 工作项 — Sprint 15 v2 人设脚本仿写 E2E 验收期 Bug 集中修复 ✅ 完成（待 PM 签收 + 推 PR #6）

**核心定位**：v1 主体完成后 E2E 验收发现 7 个 Bug（4 P1 + 3 P2），集中修复 + 配套契约同步 + 数据修复。不涉及新功能，全部为补齐与修复。

**分支**：`migrate/persona-writer`（继承 v1，未切新分支）

| 端 | 状态 | 备注 |
|----|------|------|
| TikHub URL 清洗（BUG-025）| ✅ 完成 | `app/adapters/tikhub.py` 新增 `_clean_share_url`（urlsplit + urlunsplit 丢 query/fragment）。单测 +5（30/30 全过）|
| 4 writer SQL 统一（BUG-026）| ✅ 完成 | 4 个 `operator_*_writer.py` 统一 `status IN ('signed','pending_renewal')`；4 个测试 fixture 改 `'active'` → `'signed'`（10 处）|
| kols 唯一索引 + 预检查（BUG-028）| ✅ 完成 | Migration 032 部分唯一索引（douyin_id + sec_uid）+ `admin_kols.py` 加预检查 + `response.py` 加 `RESOURCE_ALREADY_EXISTS`（409）+ `test_admin_kols.py` 新建 7 用例全过 |
| kols.status 默认值修复（BUG-027）| ✅ 完成 | ORM `kol.py:27` default `'active'` → `'signed'`；前端 Form initialValue='signed'；数据修复现有 `'active'` → `'signed'` |
| 数据污染清理（BUG-029）| ✅ 完成 | id=3（孙静/原搭搭）、id=4（陶然/原小A）软删；用户通过 UI 重建 |
| ConfigTab 描述清理（BUG-030）| ✅ 完成 | `PersonaWriterConfigTab.tsx` + `QianchuanWriterConfigTab.tsx` 删除开发风格描述 div |
| KolsPage content_plan UI（BUG-031）| ✅ 完成 | `KolsPage.tsx` 详情抽屉加内容规划编辑卡片 + 新建表单加 Form.Item；`types/kol.ts` 补 content_plan 字段 |
| 契约同步 | ✅ 完成 | M1_Base_Database §6.2（status 修正）+ §6.3（索引说明，新建）+ M1_Base_API §3（错误码表加 RESOURCE_ALREADY_EXISTS）+ M2_Base_API §13.4/§16.3/§21.1/§22.1（4 writer SQL 统一）+ backend README migrations 031→032 |
| 任务文档 v2 | ✅ 完成 | 后端 `M2_Sprint15_后端任务_persona-writer_v2_修复Bug.md` + 前端 `M2_Sprint15_前端任务_persona-writer_v2_修复Bug.md` |
| 测试报告 v2 | ✅ 完成 | `backend/docs/tests/M2_Sprint15_测试报告_persona-writer_v2_修复Bug.md` |
| 开发验收 v2 | ✅ 完成 | `backend/docs/tasks/M2_Sprint15_后端_开发验收_persona-writer_v2_修复Bug.md` |
| BUG 登记 | ✅ 完成 | BUG-025 ~ BUG-031 共 7 条（`docs/pm/BUG修复登记.md` §九）|

**关键设计点：**
- **TikHub URL 清洗**：用 `urlsplit` + `urlunsplit` 丢弃所有 query/fragment，只留 scheme/netloc/path。在 `_resolve_short_url` 之后调用，确保脏 URL（含 share_sign/ts/from_aid 等 14 个 tracking 参数）被清洗
- **部分唯一索引**（partial index）：参照 `001_init.sql:28 idx_users_username` 模式，`WHERE deleted_at IS NULL AND douyin_id IS NOT NULL AND douyin_id <> ''`，允许软删后用相同 douyin_id 重建
- **预检查 + DB 索引双保险**：前端友好错误（预检查）+ DB 兜底（并发竞态 IntegrityError）
- **ORM default 三层修复**：ORM default（后端兜底）+ Form initialValue（前端默认）+ 数据修复（现有 active → signed）
- **数据修复不入 migration**：migration 只管 schema；数据修复用一次性 SQL（asyncpg 直连）

**不在本次范围（留作后续独立任务）：**
- **admin/kols 完整 API 章节契约**：M1_Base_API 缺整章（历史债务），独立任务
- **运营添加红人权限**：当前仅 admin；运营走 kol-intake 问卷流程。若需运营直接添加，独立任务
- **DB 唯一索引测试库验证**：测试库 metadata.create_all 不跑 migration，索引兜底未自动化覆盖；生产已应用，后续加 e2e 或 migration 验证脚本

---

### M2 工作项 — Sprint 18 素材库（material-library）迁移 ✅ 完成（分支 `migrate/material-library`，待 PR）

**核心定位**：迁移自旧架构 `Ai_Toolbox/material-library-web/`。红人素材中枢 —— 管理每位红人的人格档案（soul.md）+ 内容规划（content-plan.md）+ 6 类参考素材（红人爆款/红人喜欢/风格参考/千川爆款/千川喜欢/千川风格），支持 AI 从入驻问卷数据生成 soul.md 初稿。

**关键决策**：人格档案、内容规划**复用 kols.persona + kols.content_plan**（kols 表已有 Text 字段），**不新建 profile 表**（避免字段重复、保持单一事实源）。

| 端 | 状态 | 备注 |
|----|------|------|
| Migration 034 | ✅ 完成 | 2 张新表（kol_references + material_library_configs）+ 4 个索引 + soul_generator 种子配置（默认 ai_model_id=3 claude-sonnet-4-6）+ workspace_tools 注册（tool_code='material-library', status='dev'） |
| ORM 模型 | ✅ 完成 | `KolReference` + `MaterialLibraryConfig`（新建 `app/models/material_library.py`），注册到 `__init__.py` |
| 后端运营 API | ✅ 完成 | `app/routers/operator_material_library.py`（7 接口）：kols 列表/详情、profile 更新、references CRUD、intake 查询、generate-soul（yunwu adapter，占位符 `{{kol_name}} {{intake_answers}} {{intake_report}}`） |
| 后端管理 API | ✅ 完成 | `app/routers/admin_material_library.py`（2 接口）：GET / PUT /configs |
| 旧数据迁移脚本 | ✅ 完成 | `scripts/migrate_material_library.py`：扫描旧 personas 目录 → soul.md / content-plan.md → UPDATE kols（仅填 NULL，--overwrite 覆盖）；编码容错（GBK/UTF-8）；dry-run 验证 OK |
| 后端测试 | ✅ 完成 | 22 个测试通过（test_operator_material_library 14 + test_admin_material_library 8）；convention_guard 6/6 |
| 前端 API | ✅ 完成 | `api/materialLibrary.ts`（10 函数 = 7 运营 + 3 管理，全部走 request.ts） |
| 前端运营页 | ✅ 完成 | `pages/operator/MaterialLibraryPage.tsx`（左右分栏：280px 红人列表 + 4 Tab） |
| 前端管理 Tab | ✅ 完成 | `pages/admin/MaterialLibraryConfigTab.tsx`（soul_generator Prompt + 模型 + 启用开关） |
| 路由/Tab 注册 | ✅ 完成 | App.tsx 加 `/workspace/material-library`；WorkspaceConfigPage 加 'material-library' Tab |
| 前端测试 | ✅ 完成 | 18 个测试通过（MaterialLibraryPage 12 + MaterialLibraryConfigTab 6）；vitest 全量 198/198 |
| 契约文档 | ✅ 完成 | Base_API §24（7+2 接口）+ Base_Database §28-29（2 张表）+ 前后端 README + 根 README |
| TypeScript | ✅ 通过 | `tsc --noEmit` clean |

**踩坑**：① AntD Tabs 测试切换需用 `getByRole('tab', { name })`，`getByText` 在 tab label + tab content 同时存在时会匹配多个元素；② AntD Popconfirm / Modal.confirm 默认 OK 按钮文本是 **英文 "OK"**（无 ConfigProvider + zhCN 时）；③ AntD v5 `Modal.confirm()` 静态方法在测试环境无法挂载到 DOM（设计限制），需测直调分支绕过。

---

### M2 工作项 — ASR 完整方案（阿里云智能语音交互）✅ 完成（已合并到 main，PR #4 merge commit 7fb84a7）

**核心定位**：ASR（录音文件识别）完整方案，完全复刻 OSS Tab 的架构与 UI 范式。服务商：阿里云智能语音交互（`filetrans.cn-shanghai.aliyuncs.com`，POP RPC 风格）。`tool_transcribe.py` **不改**（继续用云雾 Whisper），ASR 作为独立功能模块。

| 端 | 状态 | 备注 |
|----|------|------|
| Migration 029 | ✅ 完成 | `asr_call_logs` 表（credential_id / user_id / operation=submit/query / status / latency_ms / task_id / audio_url / error_message）+ 5 个索引 |
| ORM 模型 | ✅ 完成 | `AsrCallLog`（新建）；同时补注册 `OssCallLog`（之前 __init__.py 漏了）|
| ASR adapter | ✅ 完成 | `app/adapters/asr.py`：3 公开函数（submit_transcription / query_transcription / transcribe）+ 5 内部 helper（_make_domain / _make_client / _build_submit_request / _build_query_request / _get_asr_credential）；POP RPC + CommonRequest；transcribe 内部轮询（10s × 600s）|
| 后端统计接口 | ✅ 完成 | `app/routers/admin_asr.py`：GET /stats + /operations + /users，参照 admin_oss.py |
| 测试端点扩展 | ✅ 完成 | `admin_credentials.py::test_credential` 加 ASR 分支：调 `GetTaskResult` 用固定 probe TaskId（必返回 41050010 TASK_EXPIRED，只要不抛认证异常即连通 OK）；不依赖测试音频；提取 `_record_test_outcome` 辅助函数消除重复 |
| Router 注册 | ✅ 完成 | `app/main.py` include admin_asr_router |
| 依赖 | ✅ 完成 | `requirements.txt` 加 `aliyun-python-sdk-core>=2.13.12`（与 oss2 兼容下限）|
| 前端 API 模块 | ✅ 完成 | `frontend/src/api/asr.ts`：3 统计函数 + 类型定义（实际 CRUD 走通用 credentials.ts）|
| 前端 ASR Tab | ✅ 完成 | `ServiceConfigPage.tsx` 中 AsrConfigTab 完整组件：4 紫色统计卡 + AsrDonutChart + AsrLineChart + 3 子 Tab + AppKey/AccessKey ID/AccessKey Secret/Region 表单（紫色 #722ED1 与 OSS 蓝区分）|
| 前端通用 Modal 剥离 | ✅ 完成 | 通用"新增 Key"Modal 去掉 ASR Option（与 OSS 一样走独立 Tab）|
| 单元测试 | ✅ 16/16 | `test_asr_adapter.py`：4 submit + 2 query + 4 transcribe + 3 日志写入 + 3 凭证解析边界 |
| 集成测试 | ✅ 10/10 | `test_admin_asr.py`：4 权限 + 2 stats + 2 operations + 2 users |
| 凭证测试 | ✅ 4/4 | `test_credentials.py::TestTestCredential` 加 ASR 分支：ok / failure / missing_app_key / invalid_secret_format |
| 前端测试 | ✅ 12/12 | `AsrConfigTab.test.tsx`：4 卡渲染、统计值显示、饼图、折线图、3 子 Tab、子 Tab 切换加载、AppKey 脱敏、新增表单字段、api_key 拼接（id\nsecret）、测试按钮 |
| 文档同步 | ✅ 完成 | `MCN_M2_Base_API.md` 加 §10B ASR；`MCN_M2_Base_Database.md` 加 §24 asr_call_logs；前后端 README 同步 |

**关键设计点：**
- ASR `secret_enc` 格式：`"access_key_id\naccess_key_secret"`（两行，与 OSS 单一 secret 不同）
- ASR `config` 字段：`{app_key, region}`（region 默认 `cn-shanghai`，支持 `cn-beijing` / `cn-shenzhen`）
- `operation` 分类：`submit`（提交任务）/ `query`（查询结果）—— 每次完整 ASR 调用产生 2 条日志
- `transcribe()` 不写日志（它只是 submit + query 的组合；由两个子调用各自写）
- 测试端点不调 SubmitTask（避免依赖测试音频文件），改调 `GetTaskResult` 用固定 probe TaskId——简单可靠
- 前端 AsrConfigTab 用通用 credentials.ts 做 CRUD，只在测试按钮上动态 import testOssCredential（后端该端点已按 provider 分支）
- 前端表格列：AppKey 前 8 位 + `****` 脱敏
- 前端紫色主题（#722ED1）与 OSS 蓝色（#1890FF）视觉区分

**不在本次范围（留后续独立任务）：**
- **tool_transcribe 改造**：现在继续用云雾 Whisper。改造为 ASR（或凭证池路由）作为后续任务
- **TikHub adapter 日志写入 bug**：Sprint 11 OSS 任务时发现的，独立修复
- **service_credentials.secret_enc 加密**：Sprint 3 债务。ASR 的 `access_key_id\naccess_key_secret` 同样明文（继承债务）
- **service_credentials 软删改造**：Sprint 3 债务
- **ASR 业务集成**：把 tool_transcribe 调用方（千川剪辑预审、TT 复盘）切到 ASR

---

### M2 工作项 — OSS 使用显示完整对齐 TikHub ✅ 完成（已合并到 main，PR #3）

**核心定位**：让 OSS Tab 的"使用显示"完全对齐 TikHub Tab——4 张统计卡片 + 2 张图表 + 3 个子 Tab + 凭证列表含使用数据。**关键发现**：OSS adapter 此前无任何 router 调用（统计永远是 0），必须造调用场景（改造 files.py）；TikHub adapter 自身也有 bug 不写日志（统计数字也不准，留作独立任务）。

| 端 | 状态 | 备注 |
|----|------|------|
| Migration 027 | ✅ 完成 | `oss_call_logs` 表（credential_id / user_id / operation / status / latency_ms / oss_key / error_message）+ 5 个索引 |
| Migration 028 | ✅ 完成 | `service_credentials` 加 `last_tested_at` / `last_latency_ms` 字段（通用，ASR/AI 也能用）|
| ORM 模型 | ✅ 完成 | `OssCallLog`（新建）+ `ServiceCredential` 扩 2 字段 |
| OSS adapter | ✅ 完成 | 3 函数（upload_file/get_download_url/delete_file）finally 块写 OssCallLog + commit，支持 user_id 参数 |
| 后端统计接口 | ✅ 完成 | `app/routers/admin_oss.py`：GET /stats + /operations + /users，参照 admin_tikhub.py，SQL 字段名 endpoint→operation，无 platform 维度 |
| 测试端点扩展 | ✅ 完成 | `admin_credentials.py::test_credential` 保存 last_tested_at + last_latency_ms（成功/失败都写）|
| 造调用场景 | ✅ 完成 | `app/routers/files.py`：新增 POST /files 上传到 OSS（50MB 限制，oss_key 命名 uploads/{user_id}/{yyyymmdd}/{uuid}.{ext}）；GET /download-url 改真（调 adapter）；DELETE 改软删+OSS 清理 |
| Router 注册 | ✅ 完成 | `app/main.py` include admin_oss_router |
| 前端 API 模块 | ✅ 完成 | `frontend/src/api/oss.ts`（getOssStats/getOssOperations/getOssUsers + 类型定义）|
| 前端 OSS Tab 改造 | ✅ 完成 | `ServiceConfigPage.tsx` 中 OssConfigTab 完整重写：4 卡 + 2 图（OssDonutChart/OssLineChart）+ 3 子 Tab（凭证管理/操作统计/用户排行）+ 凭证列表加"上次测试"列 |
| 前端类型 | ✅ 完成 | `frontend/src/types/credential.ts` ServiceCredential 加 last_tested_at/last_latency_ms |
| 单元测试 | ✅ 14/14 | `test_oss_adapter.py` 加 5 个新用例：upload/delete/download 成功写日志、upload 失败写日志、user_id=None |
| 集成测试 | ✅ 10/10 | `test_admin_oss.py`（新建）：4 个权限校验 + 2 个 stats + 2 个 operations + 2 个 users |
| 前端测试 | ✅ 12/12 | `OssConfigTab.test.tsx`：4 卡渲染、统计值显示、饼图、折线图、3 子 Tab、子 Tab 切换加载、凭证 CRUD（原有）|
| 文档同步 | ✅ 完成 | `MCN_M2_Base_API.md` 加 §10A OSS 接口；`MCN_M2_Base_Database.md` 加 §21 oss_call_logs + §22 service_credentials 扩展字段；前后端 README 同步 |

**关键设计点：**
- OSS 日志写入位置在 adapter `finally` 块（仿 yunwu.py AiCallLog 模式），router 不重复写
- `oss_call_logs.operation` 取值 upload/download/delete（短字符串，16 位以内）
- `service_credentials.last_tested_at/last_latency_ms` 字段**通用**（不限定 provider='oss'），将来 ASR/AI 测试端点可复用
- 前端 OssDonutChart/OssLineChart 复制自 TikHub 版本改名，字段差异：endpoint→operation（line chart 完全一致）
- 子 Tab 切换用 click handler 触发懒加载（不用 useEffect 触发，便于测试）
- POST /files 大小校验用流式读取（64KB chunk），避免一次性加载到内存
- DELETE /files OSS 清理失败**不阻塞软删除**（已软删，失败仅日志记录）

**不在本次范围（留后续独立任务）：**
- **TikHub adapter 日志写入 bug**：TikHub adapter 调用时不写 `tikhub_call_logs`，导致 TikHub Tab 统计数字不准。修复涉及 tikhub.py 所有方法，规模大，作为独立任务
- service_credentials.secret_enc 仍明文存储（Sprint 3 债务）
- service_credentials 物理删除（一票否决级债务，应改软删）
- ASR Tab 独立组件（ASR 仍走通用配置分支）

---

### M2 工作项 — OSS 配置前端 UI 完善 ✅ 完成（已合并到 main，PR #3）

**核心定位**：补齐 OSS 配置的端到端能力。后端 adapter 早已接通，但前端 OSS Tab 此前套用通用凭证模型（缺 AccessKey ID/Bucket/Endpoint 字段、测试按钮误调 AI Key 接口、编辑表单只能改 label/weight），本次参照 TikHub Tab 模式做独立组件 + 后端连通性测试端点。

| 端 | 状态 | 备注 |
|----|------|------|
| 前端 OssConfigTab | ✅ 完成 | `frontend/src/pages/admin/ServiceConfigPage.tsx` 新增独立组件：列表（含 bucket/endpoint/AccessKey ID 脱敏）+ 新增/编辑表单（OSS 专属 7 字段）+ 测试按钮（调真后端接口）|
| 前端测试 | ✅ 5/5 | `frontend/src/__tests__/components/pages/OssConfigTab.test.tsx`：渲染空数据 / 渲染列表 / Modal 打开 / 表单提交拼装 / 测试按钮调用 |
| 后端测试端点 | ✅ 完成 | `POST /api/admin/config/credentials/{id}/test`（admin_credentials.py）：仅 OSS，调 `_make_bucket().get_bucket_info()` 最轻量验证，OperationLog 记录 |
| 后端 Update 扩展 | ✅ 完成 | `UpdateCredentialRequest` 加 `api_key: str \| None`，支持密钥轮换（同步更新 secret_enc + secret_tail）|
| 后端契约文档 | ✅ 补全 | `MCN_M1_Base_API.md` 第 12 节补 PATCH/DELETE/test 三个端点契约 |
| 后端测试 | ✅ 8/8 新增 | `test_credentials.py` 新增 TestTestCredential（6 条）+ TestUpdateCredential 加 api_key 用例（2 条）|
| 守卫违规修复 | ✅ 5/5 | 既有债务：admin_livestream_review.update_config / admin_persona_review.update_config / operator_livestream_review.generate / operator_livestream_writer.chat / operator_persona_review.generate 全部补 OperationLog |

**关键设计点：**
- 测试端点响应**业务失败也走 success 信封**（参照 TikHub 模式），状态在 `data.status`，避免前端 try/catch 误判
- OSS 测试用 `bucket.get_bucket_info()` 而非 `list_objects`——验证 ak/sk/bucket/endpoint 全套且开销最小
- 前端 Endpoint 用 HTML5 `<datalist>` 提供常用区域预设（华东1杭州/华东2上海/华北2北京等 9 个）+ 自由输入，避免 Select+自定义输入的复杂交互
- 编辑表单的 AccessKey Secret 留空表示不改（密钥轮换为可选操作）
- 5 个守卫违规都是 M2 Sprint 9/10 遗留债务，本次一并清理（用户批准扩大范围）

**不在本次范围（留后续）：**
- service_credentials 凭证加密（Fernet，独立 PR）
- DELETE 改软删（一票否决级债务）
- list_credentials 的 `len(all())` 性能优化
- OSS adapter 接入业务（files router / outputs 迁移 / ASR）

---

### M2 工作项 — 阿里云 OSS Adapter 后端接通 ✅ 完成（已合并到 main，PR #3）

**核心定位**：把 `app/adapters/oss.py` 从 M1 起的 Mock 占位（`get_download_url` 返回假 URL，`upload_file` 抛 NotImplementedError）替换为真实接通阿里云 OSS 的实现。**仅后端接通，凭证由用户后续配置**，files router 上传接口、管理端 OSS 面板、存储统计等留后续。

| 端 | 状态 | 备注 |
|----|------|------|
| OSS adapter 重写 | ✅ 完成 | `app/adapters/oss.py`：3 公开函数（`upload_file` / `get_download_url` / `delete_file`）+ 2 内部 helper（`_get_oss_credential` / `_make_bucket`） |
| 单元测试 | ✅ 9/9 | `tests/unit/services/test_oss_adapter.py`（纯 mock），覆盖率 **89%**（adapter 门禁 ≥ 60%） |
| 连通性测试 | ✅ PASSED | `tests/integration/test_oss_live.py`（env var 注入凭证），2026-06-18 真实阿里云 OSS 验证通过（bucket=`aitoolboxte`，6.97s） |
| pytest.ini | ✅ 加 markers | `live: tests requiring real external services` |
| 文档 | ✅ 落地 | 任务单 + 测试报告 + README 更新 + PM 记忆（本文） |
| 凭证配置 | ✅ 验证通过 | env var 方式（OSS_LIVE_TEST=1 + AK_ID/SECRET/BUCKET）；后续 UI 接通用 API |

**关键设计点：**
- `oss2` 是同步库 → 全部 `asyncio.to_thread` 包装，不阻塞事件循环
- `_get_oss_credential` 在 try **外**调用（凭证缺失 / config 缺字段时直接抛 KeyError，不 report_failure 因为没 cred_id）
- oss2 操作在 try **内**（失败 → report_failure + 包装为 RuntimeError 传播）
- **字段映射与通用 API 对齐**：`label`=备注名 / `secret_enc`=Secret / `config.access_key_id`=AK ID / `config.bucket`+`endpoint`+`region` 从 JSONB 读（不在 label 里）

**全量回归**：4 failed + 4 errors 全是预存技术债（5 个其他 router 缺 OperationLog / snappy 模块缺失 / intake conftest pytest_plugins 位置），OSS 改动**零回归**。

**不在本次范围（留后续）：**
- 管理端 OSS 面板 UI（凭证 CRUD + 存储统计展示）
- `files.py` router 补 upload 接口（真正存 OSS，目前 router 仍写本地）
- 存储统计（基于 files 表 + 阿里云计量 API）
- outputs 产出迁移到 OSS
- ASR 服务接入
- **service_credentials 凭证加密（Fernet）**：2026-06-18 摸过现状后决定**延后**。
  - 现状：`secret_enc` 字段明文存储（admin_credentials.py:116），3 个 adapter 直接读明文（ai.py:54 / tikhub.py:24 / oss.py:62）
  - 历史遗留：`mcn_m1` 库 id=1、2 两条 ai 凭证（label=openai-main / openai-test）的 `secret_enc` 已是 Fernet 密文格式（`gAAAAABq...`），但代码无解密逻辑 → 这两条实际是坏的（adapter 拿密文字符串当 api_key 必然 401）。**建议用户手动删除或重建**
  - 改造影响面：1 写入点 + 3 读取点 + 新增 `app/utils/crypto.py` + requirements.txt 加 `cryptography` + 数据迁移脚本（5 条明文 → 加密）
  - 改造决策：复用 `.env.example` 已有的 `ENCRYPTION_KEY`（HKDF 派生 Fernet key，用户无需改 .env 格式），独立 PR `feature/credential-encryption`
  - 触发时机：生产部署前再做（当前本地开发明文风险可控）

---

### M2 Sprint 12 — 千川爆文合集（qianchuan-collection）✅ 完成

**核心定位**：纯手工脚本收集库，无 AI 调用。全网爆款池（41 条种子数据）+ 达人爆款池（按达人分组管理）。

| 端 | 状态 | 备注 |
|----|------|------|
| 数据库迁移 025 | ✅ 已执行 | `qianchuan_collection_personas` + `qianchuan_collection_scripts` 表 + workspace_tools 注册（status=online）+ 41 条种子数据 |
| 后端 7 个接口 | ✅ 完成 | `operator_qianchuan_collection.py`（personas CRUD + scripts CRUD + parse-file） |
| SQLAlchemy 模型 | ✅ 完成 | `app/models/qianchuan_collection.py` |
| main.py 注册 | ✅ 完成 | router 已 include |
| 自动化测试 | ✅ 31/31 | 集成测试 31 条 + 前端单元测试 8 条 |
| 前端页面 | ✅ 完成 | `QianchuanCollectionPage.tsx`，路由 `/workspace/qianchuan-collection` |
| 功能验证 | ✅ 通过 | 12 项验证全 PASS，2026-06-18 |
| 契约文档 | ✅ 已更新 | Base_API §19、Base_Database §19-20 迁移 025 已登记 |

**架构特点（与其他工具差异）：**
- 无 AI 调用 → 无 yunwu adapter、无 AiCallLog、无 Prompt 配置、无管理端专属 Tab
- 无 AsyncSessionLocal 直接导入 → 无需注册 conftest.py
- 软删除（is_deleted）贯穿达人和脚本，级联软删靠 UPDATE 实现（不靠 FK CASCADE）
- 种子数据 41 条通过 migration 025 INSERT，frontmatter 解析自旧工具 .md 文件

**覆盖率：**
- `operator_qianchuan_collection.py`：72% ✅（目标 ≥ 70%）

---

### M2 Sprint 13 — TT内容复盘（tiktok-review）✅ 完成

**核心定位**：迁移旧工具，两侧视频文案对比 + AI 7维度分析 + 产出中心 + 导出Word + 管理端Prompt配置。

| 端 | 状态 | 备注 |
|----|------|------|
| 数据库迁移 026 | ✅ 已执行 | `tiktok_review_configs` 表 + workspace_tools 注册（status=dev）+ 默认Prompt |
| 后端运营端 4 个接口 | ✅ 完成 | `operator_tiktok_review.py`（generate/save/outputs/export-word） |
| 后端管理端 2 个接口 | ✅ 完成 | `admin_tiktok_review.py`（configs GET/PUT） |
| SQLAlchemy 模型 | ✅ 完成 | `app/models/tiktok_review.py` |
| main.py 注册 | ✅ 完成 | 两个 router 已 include |
| 后端集成测试 | ✅ 通过 | 18 条，覆盖率 72% |
| 前端 API 层 | ✅ 完成 | `tiktokReview.ts`，前端单元测试 8 条通过 |
| 前端运营端页面 | ✅ 完成 | `TiktokReviewPage.tsx`，路由 `/workspace/tiktok-review` |
| 前端管理端 Tab | ✅ 完成 | `TiktokReviewConfigTab.tsx`，WorkspaceConfigPage 已注册 |
| 契约文档 | ✅ 已更新 | Base_API §20、Base_Database §21、迁移 026 |
| 全量回归 | ✅ 通过 | 后端 402 passed，前端 103 passed |

**架构特点**：
- 转录走公共接口 `/api/tools/transcribe`（语言固定 ko），不新建专属接口
- Word 导出复用 `app/services/word_export.py`
- 一个配置项（`config_key='default'`），管理端可改 Prompt + 模型
- 产出保存到 outputs 表，支持历史列表查询

---

### M2 Sprint 11 — 千川文案预审（qianchuan-preview）✅ 完成

**核心流程：** 上传/粘贴两段文案（原版爆款 + 我方文案）→ AI 流式对比分析 → 生成预审报告 → 导出 Word / 复制

| 端 | 状态 | 备注 |
|----|------|------|
| 数据库迁移 024 | ✅ 已执行 | `qianchuan_preview_configs` 表 + workspace_tools 注册（status=online） |
| 后端 5 个接口 | ✅ 完成 | `operator_qianchuan_preview.py`（parse-file/generate/export-word）+ `admin_qianchuan_preview.py`（GET/PUT configs） |
| System Prompt | ✅ 完成 | `tools/qianchuan_preview/prompts.py`，DB 管理端可配置 |
| SQLAlchemy 模型 | ✅ 完成 | `app/models/qianchuan_preview.py` |
| main.py 注册 | ✅ 完成 | 两个 router 已 include |
| 自动化测试 | ✅ 25/25 | 单元 7 + 集成 18 |
| 前端页面 | ✅ 完成 | `QianchuanPreviewPage.tsx`，路由 `/workspace/qianchuan-preview` |
| 管理端 Tab | ✅ 完成 | `QianchuanPreviewConfigTab.tsx` |
| 功能验证 | ✅ 通过 | 5 项验证全 PASS，2026-06-18 |
| 契约文档 | ✅ 已更新 | Base_API §18、Base_Database 迁移 024 已登记 |

**关键修复（功能验证时）：**
- generate 接口原版 `yunwu_adapter.chat_stream()` 使用了不存在的 `system_prompt=` 参数，修正为将 system_prompt 放入 messages 列表首位 `{"role":"system","content":...}`，并补传 `db`/`user_id`/`feature`

**与同类工具差异：**
- 无历史记录（轻量工具，不保存报告）
- 无 parse-file 的日历噪声过滤（复用 `parse_qianchuan_review_file` 但文案类文件通常不含日历噪声）
- 工具状态直接 `online`（旧工具已上线，无 dev 阶段）

**覆盖率：**
- `operator_qianchuan_preview.py`：40%（流式路径已知缺口）
- `admin_qianchuan_preview.py`：83% ✅
- `tools/qianchuan_preview/prompts.py`：100% ✅

---

### M2 Sprint 1 — 红人入驻问卷（kol-intake） ✅ 完成

**核心流程：** 运营生成链接 → 博主打开链接 → AI 多轮对话（24 道题）→ 生成报告 → 下载 docx/PDF

| 端 | 状态 | 备注 |
|----|------|------|
| 后端 | ✅ 完成 | 23 个接口 |
| 运维 | ✅ 完成 | 006+007 迁移已执行 |
| 前端 | ✅ 完成 | 入驻问卷+运营直发+报告展示+下载 |

---

### M2 Sprint 2 — 运营端首页重设计 ✅ 完成

| 端 | 状态 |
|----|------|
| 后端 | ✅ 完成 |
| 前端 | ✅ 完成（recharts 折线图 + 环形图 + 常用工具） |

---

### M2 Sprint 3 — 人格定位（persona-positioning） ✅ 完成

**核心流程：** 抖音号解析/文件上传 → 选择对标达人 → AI 生成人格档案+内容规划 → 导出 Word → 历史管理

| 端 | 状态 | 备注 |
|----|------|------|
| 后端 10 个接口 | ✅ 完成 | `app/routers/persona.py` |
| TikHub 管理端 10 个接口 | ✅ 完成 | `app/routers/admin_tikhub.py` |
| 前端三步向导 | ✅ 完成 | `PersonaPage.tsx` |
| TikHub 管理页面 | ✅ 完成 | `ServiceConfigPage.tsx` TikHubConfigTab |
| AI 流式适配器 | ✅ 完成 | 僵尸锁自动清理（360s） |
| 自动化测试 | ✅ 221/221 + 71/71 | |
| 手工测试 | ✅ 完成 | 6 个 Bug 全部修复并验证 |
| 代码提交 | ✅ 已推送 | 6 个 commit → GitHub main |

**新增数据库表（3张）：**
- `persona_reports` — 人格定位报告（迁移 009）
- `tikhub_credentials` — TikHub 独立 Key 池（迁移 010）
- `tikhub_call_logs` — TikHub 调用日志（迁移 011）

**Bug 修复记录（6 个）：**
1. 抖音分享链接解析失败（URL提取+短链+TikHub响应格式）
2. 前端下载地址错误（API vs FETCH_BASE 路径拆分）
3. 历史记录抽屉不渲染（移到组件最外层）
4. SSE 断连空报告标 ready（空内容保护）
5. 历史记录点击无反应（loadHistoryDetail 加 setStep(3)）
6. 产出中心预览为空（调详情接口获取 content）

**文档补遗（2026-06-24）：** CLAUDE.md 功能完成链核查发现 Sprint 3 仅有任务单（v1/v2），缺 PM 视角的需求文档与测试报告。已补齐：
- `docs/pm/M2_Sprint3_persona-positioning_需求文档.md`（695 行，整合 v1/v2 + 契约 + 产出双写 + 10 个决策点）
- `docs/tests/M2_Sprint3_persona-positioning_测试报告.md`（339 行，221+71 测试详情 + 6 Bug 修复记录 + 15 步手工 E2E 走查）

---

### M2 Sprint 10 — 人设脚本复盘（persona-review）✅ 完成

**核心流程：** 上传人设脚本（txt，多视频）→ 可选上传运营 Excel → AI 流式生成复盘报告（内容质量/投放效率）→ 保存/历史管理

| 端 | 状态 | 备注 |
|----|------|------|
| 数据库迁移 023 | ✅ 已执行 | `persona_review_configs` 表 + workspace_tools 注册（status=dev） |
| 后端 5 个接口 | ✅ 完成 | `operator_persona_review.py`（generate/save/outputs）+ `admin_persona_review.py`（GET/PUT configs） |
| System Prompt | ✅ 完成 | `tools/persona_review/prompts.py`，with_excel/without_excel 两版，DB 管理端可配置 |
| 服务层 | ✅ 完成 | `service.py`：merge/hasExcel/build_user_message/generate_review_stream |
| SQLAlchemy 模型 | ✅ 补建 | `app/models/persona_review.py`（PersonaReviewConfig），注册到 Base.metadata |
| main.py 注册 | ✅ 完成 | 两个 router 已 include |
| conftest.py 注册 | ✅ 完成 | `operator_persona_review.AsyncSessionLocal` 已在 patch 列表 |
| 自动化测试 | ✅ 54/54 通过 | Prompt 精确比对(16) + service 单元(16) + 集成(22) |
| 契约文档 | ✅ 已更新 | Base_API §17、Base_Database 迁移 023 已登记 |
| 人工验证 | ✅ 通过 | 2026-06-17 |
| 前端配置页 | ✅ 完成 | `PersonaReviewConfigTab.tsx` 对齐标准模式（empty-state/色标/destroyOnHidden） |

**关键修复（本次会话）：**
1. 补建 `app/models/persona_review.py`：原先缺失 SQLAlchemy 模型，测试库 `create_all` 无法建表，集成测试全 ERROR
2. service.py 排序 bug：旧代码先追加未匹配 Excel 行再全局排序，导致高点赞未匹配行排到最前；修复为先排有脚本内容的行，再追加未匹配行到末尾（符合需求文档）
3. 测试用例修正：`test_title_replaced_by_video_theme_on_match` 原数据不满足匹配条件（旧版"通过"是排序副作用假阳性），修正为前6字相同的真实匹配数据

**差异点（与 livestream-review）：**
- 无 parse-file 接口（txt 前端直读）
- 匹配字段：`video_theme`（非 `live_theme`）
- 未匹配 Excel 行追加末尾且不参与排序（livestream-review 不追加）
- 内容截断 2000 字（非 3000）
- hasExcel 判断：`completion_rate | ad_spend | likes`

**覆盖率：**
- `operator_persona_review.py`：84% ✅
- `admin_persona_review.py`：85% ✅
- `service.py`：92% ✅

**部署注意：**
- 工具当前状态 `dev`，上线前管理端改为 `online`

---

### M2 Sprint 9 — 直播间脚本复盘（livestream-review）✅ 完成

**核心流程：** 上传直播脚本（多场）→ 上传直播数据 Excel（可选）→ AI 流式生成复盘报告（话术效果 + 留人转化）→ 保存/导出/复制

| 端 | 状态 | 备注 |
|----|------|------|
| 数据库迁移 020 | ✅ 完成 | `livestream_review_configs` 表 + workspace_tools 注册（status=dev） |
| 后端 6 个接口 | ✅ 完成 | `operator_livestream_review.py`（parse-file/generate/save/outputs）+ `admin_livestream_review.py`（GET/PUT configs） |
| System Prompt | ✅ 完成 | `tools/livestream_review/prompts.py`，A/B 两版逐字保留，�� DB 管理端可配置 |
| 服务层 | ✅ 完成 | `service.py`：merge/detect_has_excel/build_user_message/generate_review_stream |
| 前端三步向导 | ✅ 完成 | `LivestreamReviewPage.tsx`，路由 `/workspace/livestream-review` |
| 自动化测试 | ✅ 58/58 通过 | Prompt 精确比对(16) + service 单元(22) + 集成(20) |
| 人工验证 | ✅ 通过 | 2026-06-16 |

**关键决策：**
- Prompt 遵迁移红线 #4 存 DB（with_excel / without_excel 两条）
- hasExcel：后端合并后检查是否含 gmv/peak_viewers/conversions，非简单判断 excel_data 非空
- 未匹配 Excel 行不追加给 AI（只发有脚本内容的场次）

**覆盖率：**
- `operator_livestream_review.py`：86% ✅
- `admin_livestream_review.py`：86% ✅
- `service.py`：72%（流式路径已知缺口）

**部署注意：**
- 工具当前状态 `dev`，上线前管理端改为 `online`
- 旧产品数据（线上 data/ 目录）本次未迁移，待确认

---

### M2 部署阶段修复（2026-06-17）✅ 完成

测试服（120.26.111.136 Ubuntu + Nginx）部署后集中发现的 4 个问题，**不归特定 Sprint，归部署阶段**：

| # | 问题 | 修复 | 文档 |
|---|------|------|------|
| 1 | 前端 JS 包 2.2MB，首屏慢 | `App.tsx` 28 个页面改 `React.lazy()`，按路由拆分；首屏 ~2.2MB → ~90KB（gzip） | `frontend/docs/tasks/M2_Sprint09_前端任务_路由懒加载与TS修复_v1.md` |
| 2 | `npm run build` 暴露 3 个预存 TS 错误（dev 用 esbuild 不查类型） | 删未用变量/属性/import（`LivestreamReviewPage`/`LivestreamWriterPage`） | 同上 |
| 3 | 测试服 PDF 中文显示黑块（服务器无中文字体，回退 Helvetica） | `intake_report.py` 字体注册加 Linux/macOS 路径；服务器需 `apt install fonts-wqy-microhei` | `backend/docs/tasks/M2_Sprint1_kol_intake_PDF跨平台字体_v1_修复Bug.md` |
| 4 | kol-intake 对话页：回车发送后输入框失焦；报告页无重新采集按钮 | `OperatorIntakeChatPage.tsx` 加 `inputRef + useEffect` focus；抽 `initSession()`；报告页加重新采集按钮 | `frontend/docs/tasks/M2_Sprint1_kol_intake_对话页UX修复_v1_修复Bug.md` |

**构建产物对比**（路由懒加载）：

| 场景 | 改造前 | 改造后（gzip） |
|------|--------|--------------|
| 单 bundle | ~2.2MB（一个文件） | 60+ chunks（按页面） |
| 登录页首屏 | ~2.2MB | **~90 KB** |

**测试**：87/87 前端测试通过；`npm run build` 15.43s 成功。

**部署侧已配套修复（前后会话）**：
- `redirect_slashes=False`（FastAPI）+ Nginx `rewrite ^(/api/.*)/$ $1 permanent` 解决 `ERR_TOO_MANY_REDIRECTS`
- Nginx `gzip_types` 加 `application/javascript`
- `credentials.base_url` 必须带 `/v1` 后缀（已加 `deploy/README.md` §7.6）
- 详见 `deploy/README.md` §7 常见问题排查（6 个 case）

---

### M2 Sprint 8 — 直播脚本仿写（livestream-writer）✅ 完成

**核心流程：** 选达人 → 上传产品卖点卡 → 上传对标直播间文案 → AI 流式生成7模块开播方案 → 多轮迭代修改 → 导出 .txt

| 端 | 状态 | 备注 |
|----|------|------|
| 后端 6 个接口 | ✅ 完成 | `operator_livestream_writer.py` / `admin_livestream_writer.py` |
| 数据库迁移 | ✅ 已执行 | `021_livestream_writer.sql`：`livestream_writer_configs` 表 + workspace_tools 注册 |
| 自动测试 | ✅ 34/34 通过 | 单元 11 + 集成 23，覆盖率 operator 72% / admin 83% |
| 前端 API/Types | ✅ 完成 | `livestreamWriter.ts` / `types/livestreamWriter.ts` |
| 前端页面 | ✅ 完成 | `LivestreamWriterPage.tsx`，路由 `/workspace/livestream-writer` |
| 管理端配置 Tab | ✅ 完成 | `LivestreamWriterConfigTab.tsx`，挂载到 WorkspaceConfigPage |
| 人工验证 | ✅ 通过 | 2026-06-16 |

**技术要点：**
- System Prompt 实时从后端 `livestream_writer_configs` 表拉取（GET /config），管理端可修改后前端自动生效
- 重试策略：429 最多 5 次，退避 5/10/15/20/25s（比 tiktok-writer 更激进，适配 thinking 模式慢速）
- `parse_livestream_writer_file`：不支持 .pdf（原工具边界），含日历噪音过滤（复用 `_parse_pages_qianchuan_review`）
- BackgroundTask 积累完整 chunks，生成结束后一次性写 `task_jobs` + `outputs`
- kols 查询条件：`content_plan IS NOT NULL AND persona IS NOT NULL`（两个字段均需有内容）
- autoTrimIfTooLong：前端生成结束后自动检查讲解脚本字数，超出则自动追加压缩请求

---

### M2 Sprint 7 — 千川剪辑预审（qianchuan-edit-review）✅ 完成

**核心流程：** 上传原版爆款视频 + 我方成片 → 截帧（ffmpeg）+ 转录（Whisper）→ 多模态 SSE 流式预审（看画面+文案）→ 导出 Word / 保存报告

| 端 | 状态 | 备注 |
|----|------|------|
| 后端 5 个接口 | ✅ 完成 | `tool_extract_frames.py` / `tool_transcribe.py` / `tool_chat_stream.py` / `tool_export_word.py` / `tool_qianchuan_edit_review.py` |
| 数据库迁移 | ✅ 完成 | 019_qianchuan_edit_review.sql，workspace_tools 已注册 status=online |
| 前端 API 模块 | ✅ 完成 | `qianchuanEditReview.ts`，5 个封装（FormData/SSE/Blob 均有例外标注，红线 #3 合规）|
| 前端页面 | ✅ 完成 | `QianChuanEditReviewPage.tsx`，路由 `/workspace/qianchuan-edit-review` |
| 集成测试 | ✅ 21/21 通过 | 5 个路由各 3-5 个测试 |
| 功能测试 | ✅ PASS | 9 项接口验证（鉴权/截帧/转录/Word 导出/保存报告/输入校验），DB 审计日志确认 |

**技术要点：**
- `tool_chat_stream.py` 使用 `AsyncSessionLocal` 后台写 AiCallLog，已注册 conftest.py `_SESSION_LOCAL_PATCH_TARGETS`
- 所有新接口返回标准信封 `success_response(data=...)`（红线 #1 合规）
- `tool_export_word.py` 返回 `StreamingResponse`（文件流例外，不包信封）
- Content-Disposition 文件名用 `filename*=UTF-8''url_encoded` 格式，前端需 `decodeURIComponent` 解码
- `_RETRY_DELAYS = [3, 6]`（共 3 次尝试），单次重试上限对齐测试断言
- pytz 新增依赖，已写入 requirements.txt

**覆盖率（新增文件）：**
- `tool_transcribe.py`：100% ✅
- `tool_qianchuan_edit_review.py`：86% ✅
- `tool_export_word.py`：87% ✅
- `tool_chat_stream.py`：81% ✅
- `tool_extract_frames.py`：34%（ffmpeg subprocess 路径无法在集成测试中真实执行）

**功能测试发现（2026-06-14）：**
- 运行后端需用新路径 `/Users/zhangchong/Desktop/mcn_platform/New_Mcn_Platform/backend`；旧路径 `/Users/zhangchong/ai_intalk/New_Mcn_Platform/` 的 uvicorn 进程也在 8000 端口，启动前须先 kill 旧进程
- 新 operator 账户 `password_changed_at` 须设为非 NULL 才能通过 `require_password_changed` 鉴权

---

### M2 Sprint 6 — 千川脚本复盘（qianchuan-review）✅ 完成

**核心流程：** 上传千川脚本（文件/粘贴）→ 上传投放数据 Excel（可选）→ AI 流式生成复盘报告 → 保存/导出/复制

| 端 | 状态 | 备注 |
|----|------|------|
| 后端 4 个接口 | ✅ 完成 | `operator_qianchuan_review.py`（parse-file/generate/save/outputs）|
| System Prompt 常量 | ✅ 完成 | `tools/qianchuan_review/prompts.py`，A/B 两版本逐字保留 |
| 合并服务层 | ✅ 完成 | `qianchuan_review_service.py`（merge/sort/build_user_message/stream）|
| file_parser 扩展 | ✅ 完成 | 新增 `parse_qianchuan_review_file()` 含日历噪声过滤 |
| 前端三步页面 | ✅ 完成 | `QianchuanReviewPage.tsx`，XLSX.js 前端解析 Excel |
| 旧数据迁移脚本 | ✅ 完成 | `scripts/migrate_qianchuan_reports.py`，支持 --dry-run |
| 运维任务单 | ✅ 完成 | `deploy/docs/tasks/M2_Sprint6_运维端任务_qianchuan-review_v1.md` |
| 自动化测试 | ✅ 57/57 后端 | prompts(17) + service(13) + file_parser(14) + integration(13) |
| 功能测试 | ✅ PASS | 12 项端到端验证全通过，修复 xlsx 依赖缺失 |
| 工具状态 | ✅ online | 创作中心可见可用（016 迁移已执行）|

**技术要点：**
- CORS 新增 `expose_headers=["X-Task-Id"]`，前端从响应头读 task_id
- task_job 生命周期：流前 processing → 流后 success（独立 AsyncSessionLocal background task）
- outputs 分页：一次全量有序查询后内存切片，避免双查询

**覆盖率：**
- `prompts.py`：100% ✅
- `qianchuan_review_service.py`：86%（目标≥80%）✅
- `operator_qianchuan_review.py`：73%（目标≥70%）✅
- `file_parser.py`（新增函数）：82%（目标≥90%）⚠️

**验收后修复（2026-06-13）：**
- `xlsx` npm 包漏写 `package.json`：前端 Vite 编译报 `Failed to resolve import "xlsx"`，`tsc --noEmit` 未能检出（类型通过，运行时缺包）。修复：`npm install xlsx --save`（commit `ca50de6`）
- `workspace_tools` 漏 INSERT：`016_qianchuan_review.sql` 迁移未在开发阶段执行，工具 status 停留在 dev，管理端看不到入口。修复：补写迁移文件并执行（commit `9969176`）
- 前端 CSS 失效：页面全部使用 Tailwind class，项目未安装 Tailwind，样式无效。修复：全部改为 `var(--brand)` / `card` / `btn` 等项目 CSS 变量体系（commit `7cff76e`）

---

### M2 Sprint 5 — 产品卖点提取器（selling-point-extractor）✅ 完成

**核心流程：** 上传产品Brief + 达人文案 → AI 流式生成极致卖点卡（机制/背书/口碑/产品力）→ 多轮追问 → 下载 .md → 历史记录管理

| 端 | 状态 | 备注 |
|----|------|------|
| 后端 admin 2 个接口 | ✅ 完成 | `admin_selling_point.py`，GET/PUT selling_point_configs |
| 后端 operator 5 个接口 | ✅ 完成 | `operator_selling_point.py`，chat 从 DB 读 Prompt+模型 |
| file_parser 扩展 | ✅ 完成 | 新增 `.pages`/`.doc`/pdfplumber 支持，独立函数 |
| 前端运营端页面 | ✅ 完成 | `SellingPointPage.tsx`，无 SYSTEM_PROMPT 硬编码 |
| 前端管理端配置 Tab | ✅ 完成 | `SellingPointConfigTab.tsx`（工具配置页） |
| 自动化测试 | ✅ 43/43 后端 + 86/86 前端 | |
| 数据库迁移 | ✅ 015 已执行 | selling_point_configs 表 + workspace_tools 注册 |
| 工具状态 | ✅ online | 创作中心可见可用 |

**红线合规**：6 条迁移红线全部满足，含红线 4（Prompt+模型管理端可配置）

**迭代修复（验收后）：**
- CSS 重写：初版使用 Tailwind（项目未安装），重写为 `card`/`btn`/CSS 变量体系，页面布局正常
- 拖拽上传：Step 1/2 上传框支持拖拽文件，`briefDragOver`/`scriptDragOver` state 控制高亮

**覆盖率：**
- `operator_selling_point.py`：71%（目标≥70%）✅
- `admin_selling_point.py`：71%（目标≥70%）✅
- `file_parser.py`（含旧测试）：82%（目标≥80%）✅

---

### M2 Sprint 4 — TikTok 脚本仿写（tiktok-writer）✅ 完成

**核心流程：** 粘贴文案 + 点赞数（≥10万）→ AI 评估 Opening Hook → AI 分析结构锁定 Opening → AI 仿写 Body（直写 / 提供方向 / 多轮迭代）→ 导出 Word

| 端 | 状态 | 备注 |
|----|------|------|
| 后端 3 个接口 | ✅ 完成 | `app/routers/operator_tiktok_writer.py` |
| 共用 Word 导出服务 | ✅ 完成 | `app/services/word_export.py`（可被其他工具复用） |
| 前端 5 步页面 | ✅ 完成 | `TiktokWriterPage.tsx` |
| 前端路由接入 | ✅ 完成 | App.tsx + WorkspacePage.tsx |
| 自动化测试 | ✅ 317/317 后端 + 69/69 前端 | |
| 数据库迁移 | ✅ 014 已执行 | workspace_tools 注册 |
| 工具状态 | ✅ online | 创作中心可见可用 |

**已知遗留：**
- `persona.test.ts` 和 `authStore.test.ts` 为预存失败，与本 Sprint 无关
- router 覆盖率 41%（streaming generator 路径），后续补充单元测试

---

### M2 Sprint 3 — 对标分析助手（benchmark） ✅ 完成

**核心流程：** 抖音号解析 → 自动抓取 TOP10 + 近30天视频 → AI 流式生成人格档案 + 内容规划 → 导出 Word → 历史管理

| 端 | 状态 | 备注 |
|----|------|------|
| 后端 operator 4 个接口 | ✅ 完成 | `app/routers/operator_benchmark.py` |
| 后端 admin 3 个接口 | ✅ 完成 | `app/routers/admin_benchmark.py` |
| TikHub 适配器扩展 | ✅ 完成 | `resolve_sec_user_id` + `fetch_user_videos` |
| Word 报告生成 | ✅ 完成 | `app/services/benchmark_report.py` |
| 前端对标分析页面 | ✅ 完成 | `BenchmarkPage.tsx`（输入/结果双模式 + SSE 流式） |
| 前端管理配置页 | ✅ 完成 | `BenchmarkConfigTab.tsx`（嵌入工作台配置） |
| 自动化测试 | ✅ 371/371 | 后端 289 + 前端 82，全部通过 |
| 前端 UI 修复 | ✅ 完成 | 复制按钮可见性 + antd 废弃 API 修复 |

**新增数据库表（2张）：**
- `benchmark_configs` — 对标分析配置（迁移 007）
- `benchmark_analyses` — 对标分析结果（迁移 007）

**前端修复记录（本次会话）：**
1. 复制按钮颜色过灰（改为 primary 色调）
2. `destroyOnClose` 废弃警告（6 处改为 `destroyOnHidden`）
3. antd `message` 静态方法缺 context（改用 `App.useApp()` hook）
4. tab 按钮 border 属性冲突（拆分为独立属性）
5. `window.matchMedia` 测试环境缺失（setup.ts 添加 mock）
6. 模型注册缺失导致集成测试失败（`__init__.py` 补全 Sprint 3 模型）

---

## 三、跨 Sprint 通用问题记录（经验教训）

每次新工具迁移必须检查以下事项，避免重复踩坑：

| # | 问题 | 首次出现 | 处理方式 |
|---|------|---------|---------|
| 1 | **前端 CSS 用了 Tailwind**：项目未安装 Tailwind，所有 `bg-*`/`text-*`/`rounded-*` 等 class 全部无效，页面裸奔 | Sprint 5、Sprint 6 均出现 | 全部改为 `var(--brand)` / `card` / `btn-primary` 等项目 CSS 变量体系；前端规范已注明禁止使用 Tailwind |
| 2 | **npm 包引用未声明**：代码 `import * as XLSX from 'xlsx'` 但 `package.json` 未写 `xlsx`，`tsc --noEmit` 不报错（类型解析走 node_modules），Vite 运行时才爆 `Failed to resolve import` | Sprint 6 | 新增第三方包必须同步 `npm install --save`；功能测试阶段 curl Vite 模块可发现 |
| 3 | **workspace_tools INSERT 漏执行**：迁移 SQL 文件写了但没有执行，工具 status 停留在 dev，运营端入口不显示 | Sprint 6 | 每次迁移完成后验收清单必须包含 `psql` 查 workspace_tools 确认 status=online |
| 4 | **文档落地遗漏**：代码全部完成后未补写需求文档/任务单/测试报告，PM 记忆停留在上一个 Sprint | Sprint 6 | CLAUDE.md 第十二节已增加「C 文档落地」强制闸门 |
| 5 | **功能测试缺失**：只跑 pytest，未在真实服务上验证接口和页面 | Sprint 6（首次发现） | CLAUDE.md 第十三节已增加「必须调用 Skill: verify」规则 |
| 6 | **旧后端进程残留**：旧路径 uvicorn 占用 8000 端口，新路由不生效，功能测试全 404 | Sprint 7 | 功能测试前先 `curl /openapi.json` 确认新路由存在，否则 kill 旧进程重启新后端 |
| 7 | **operator 首次登录鉴权**：新建 operator 的 `password_changed_at` 为 NULL，`require_password_changed` 拦截所有请求 | Sprint 7 | 测试账号创建后用 `psql UPDATE users SET password_changed_at=NOW() WHERE username='...'` |
| 8 | **文档欠账跨 Sprint 累积**：代码 commit 后只更新 PM 记忆，未将任务单/验收文档/测试报告就近归位，契约文档（Base_API/Base_Database）也未同步，导致 Sprint 6/7 共欠 9 份文档，在 Sprint 7 结束后才集中补写 | Sprint 7（根因回顾）| **每次 Sprint commit 前先过 CLAUDE.md §五交付物清单，逐项核对，缺一项不得声明完成；契约文档随接口/表变更当次同步，不攒到 Sprint 末尾**。失误根因：把「代码完成」等同于「任务完成」，跳过了节点 A（需求文档确认）和节点 B 归位签收两个闸门 |
| 9 | **路由懒加载缺失**：单 bundle 2.2MB，首屏慢；新项目首日就应在 `App.tsx` 用 `React.lazy()` 拆路由 | 部署阶段（2026-06-17） | 前端规范应补「新增页面默认 lazy」约定；Layout/守卫保持静态（壳子每路由都用） |
| 10 | **跨平台本地资源路径**：字体/文件路径代码只写一套（Windows），部署到 Linux 服务器后失效；dev 模式测不出来 | 部署阶段（2026-06-17） | 涉及本地资源的代码必须列 Win/Linux/macOS 三套路径；CI 应在 Linux 跑 |
| 11 | **`tsc -b` 强类型检查缺失**：dev 用 esbuild 不查类型，预存 TS 错误（未用变量、重复属性）攒到 `npm run build` 才爆 | 部署阶段（2026-06-17） | CI 跑 `tsc -b`（强校验）而非只 `tsc --noEmit`；commit 前推荐 `npm run build` |
| 12 | **测试服部署后才发现问题**：本地 dev 全绿，部署到测试服（Ubuntu + Nginx + 真实链路）才暴露 redirect loop / 字体缺失 / gzip 配置等部署侧问题 | 部署阶段（2026-06-17） | M2 收尾阶段必须有「部署 + 真实链路测试」环节，不能只靠本地 dev 通过就声明完成 |

---

## 四、当前卡点与下一步

| 卡点 | 处理方式 |
|------|---------|
| 并发测试 4/4 失败 | 本地环境问题，需在测试服验证 |
| antd `message` 静态方法警告 | 仅 BenchmarkPage 已修复，其余 25 个文件待批量迁移 |
| Sprint 9/10 convention_guard OperationLog 违规（5处） | 预存问题，admin PUT 接口未写 OperationLog，待后续统一修复 |

**下一步优先级：**
1. ✅ 已完成：Sprint 12 qianchuan-collection 迁移
2. push commits 到 GitHub（Sprint 12 代码 + 文档落地）
3. 确认下一个待迁移工具（参考 `Ai_Toolbox_new/` 目录）
4. 批量修复 antd `message` 静态方法 → `App.useApp()` hook（25 个文件）
5. 测试服部署并验证并发测试

### 产品 backlog（待开工，按需排期）

| # | 需求 | 背景 | 倾向方案 | 影响面 |
|---|------|------|---------|--------|
| P1 | PDF 图片内容识别 | 卖点提取器等工具上传图文 PDF 时，`pdfplumber` 只提文本层，图片里的产品图/成分表/卖点图全部丢失，AI 拿不到完整 Brief | 多模态 AI 看图：`pdf2image` 把每页转图片（依赖 poppler）+ yunwu adapter 支持图片 messages（Claude Vision/GPT-4V）+ Prompt 调整 | **通用**：所有走 PDF 解析的工具都会受益（卖点提取 / 对标分析 / 千川脚本复盘 / 字幕提取等） |
| P2 | 卖点提取器文件大小显示 | `SellingPointPage.tsx` 上传文件列表只显示文件名，没显示大小 | 前端 `handleFilesUpload` 保留 `f.size`，列表渲染加格式化大小 | 单页 |

**记录**：2026-07-03（卖点提取器业务逻辑梳理时发现）

---

## 五、文档索引

### 任务单（已迁移至各端 docs/ 下）

| 文件 | 说明 | 状态 |
|------|------|------|
| `docs/pm/M2_Sprint11_qianchuan-preview_需求文档.md` | Sprint 11 需求文档 | ✅ 已完成 |
| `backend/docs/tasks/M2_Sprint11_后端任务_qianchuan-preview_v1.md` | Sprint 11 后端任务单 | ✅ 已完成 |
| `frontend/docs/tasks/M2_Sprint11_前端任务_qianchuan-preview_v1.md` | Sprint 11 前端任务单 | ✅ 已完成 |
| `docs/pm/M2_Sprint12_qianchuan-collection_需求文档.md` | Sprint 12 需求文档 | ✅ 已完成 |
| `backend/docs/tasks/M2_Sprint12_后端任务_qianchuan-collection_v1.md` | Sprint 12 后端任务单 | ✅ 已完成 |
| `frontend/docs/tasks/M2_Sprint12_前端任务_qianchuan-collection_v1.md` | Sprint 12 前端任务单 | ✅ 已完成 |

| `docs/pm/M2_Sprint09_livestream-review_需求文档.md` | Sprint 9 需求文档 | ✅ 已完成 |
| `backend/docs/tasks/M2_Sprint10_后端任务_persona-review_v1.md` | Sprint 10 后端任务单 | ✅ 已执行 |
| `frontend/docs/tasks/M2_Sprint10_前端任务_persona-review_v1.md` | Sprint 10 前端任务单 | 🔄 待执行 |
| `frontend/docs/tasks/M2_Sprint09_前端任务_路由懒加载与TS修复_v1.md` | 部署阶段：路由懒加载 + 3 个 TS 修复（首屏 2.2MB→90KB） | ✅ 已完成（2026-06-17） |
| `frontend/docs/tasks/M2_Sprint1_kol_intake_对话页UX修复_v1_修复Bug.md` | kol-intake 对话页 focus + 重新采集按钮 | ✅ 已完成（2026-06-17） |
| `backend/docs/tasks/M2_Sprint1_kol_intake_PDF跨平台字体_v1_修复Bug.md` | PDF 跨平台字体（修复测试服黑块） | ✅ 已完成（2026-06-17） |
| `docs/pm/M2_Sprint06_qianchuan-review_需求文档.md` | Sprint 6 需求文档 | ✅ 已完成 |
| `backend/docs/tasks/M2_Sprint06_后端任务_qianchuan-review_v1.md` | Sprint 6 后端任务单 | ✅ 已执行 |
| `frontend/docs/tasks/M2_Sprint06_前端任务_qianchuan-review_v1.md` | Sprint 6 前端任务单 | ✅ 已执行 |
| `deploy/docs/tasks/M2_Sprint6_运维端任务_qianchuan-review_v1.md` | Sprint 6 运维任务单 | ✅ 已完成 |
| `docs/superpowers/plans/2026-06-14-qianchuan-edit-review.md` | Sprint 7 实现计划（10 Task）| ✅ 已执行 |
| `docs/superpowers/specs/2026-06-14-qianchuan-edit-review-design.md` | Sprint 7 设计文档 | ✅ 已完成 |
| `frontend/docs/tasks/M2_Sprint05_前端任务_selling-point-extractor_v1.md` | Sprint 5 前端任务单 | ✅ 已执行 |
| `backend/docs/tasks/M2_Sprint04_后端任务_tiktok-writer_v1.md` | tiktok-writer 后端任务单 | ✅ 已执行 |
| `frontend/docs/tasks/M2_Sprint04_前端任务_tiktok-writer_v1.md` | tiktok-writer 前端任务单 | ✅ 已执行 |
| `backend/docs/tasks/M2_Sprint3_persona_positioning.md` | 人格定位后端任务单 | ✅ 已执行 |
| `backend/docs/tasks/M2_Sprint3_后端任务_persona_positioning_v2_修复Bug.md` | 6 个 Bug 修复 | ✅ 已执行 |
| `frontend/docs/tasks/M2_Sprint3_persona_positioning.md` | 人格定位前端任务单 | ✅ 已执行 |
| `docs/tasks/backend/M2_Sprint3_benchmark.md` | 对标分析后端任务单 | ✅ 已执行 |
| `docs/tasks/frontend/M2_Sprint3_benchmark.md` | 对标分析前端任务单 | ✅ 已执行 |
| `docs/tasks/deploy/M2_Sprint3_benchmark.md` | 对标分析运维任务单 | ✅ 已执行 |
| `frontend/docs/tasks/M2_Sprint3_前端任务_benchmark_v2_修复Bug.md` | benchmark 前端 + 测试修复（6 个 Bug） | ✅ 已执行 |

### 测试报告

| 文件 | 说明 | 状态 |
|------|------|------|
| `backend/docs/tests/M2_Sprint11_测试报告_qianchuan-preview_v1.md` | Sprint 11 测试报告（25/25 自动化 + 5 项功能验证）| ✅ 已完成 |
| `backend/docs/tests/M2_Sprint12_测试报告_qianchuan-collection_v1.md` | Sprint 12 测试报告（31/31 集成 + 8/8 前端 + 12 项功能验证）| ✅ 已完成 |
| `backend/docs/tests/M2_Sprint07_测试报告_qianchuan-edit-review_v1.md` | Sprint 7 测试报告（21/21 集成测试 + 9 项功能验证）| ✅ 已完成 |
| `backend/docs/tests/M2_Sprint06_测试报告_qianchuan-review_v1.md` | Sprint 6 测试报告（57/57 后端，verify PASS）| ✅ 已完成 |
| `backend/docs/tests/M2_Sprint05_测试报告_selling-point-extractor_v1.md` | Sprint 5 测试报告（43/43 后端 + 86/86 前端）| ✅ 已完成 |
| `backend/docs/tests/M2_Sprint04_测试报告_tiktok-writer_v1.md` | Sprint 4 测试报告（317/317 后端）| ✅ 已完成 |
| `backend/docs/tests/M2_Sprint3_测试报告.md` | Sprint 3 测试报告（371/371） | ✅ 已完成 |
| `docs/pm/M2_Sprint3_persona-positioning_需求文档.md` | Sprint 3 人格定位 PM 需求文档补遗（2026-06-24） | ✅ 已完成 |
| `docs/tests/M2_Sprint3_persona-positioning_测试报告.md` | Sprint 3 人格定位测试报告补遗（2026-06-24） | ✅ 已完成 |


### 基础文档

| 文件 | 说明 |
|------|------|
| `backend/docs/base/MCN_M2_Base_API.md` | M2 API 接口规范（含 Sprint1~3） |
| `backend/docs/base/MCN_M2_Base_Database.md` | M2 数据库契约（含 Sprint1~3） |
| `backend/docs/后端开发约定.md` | 后端开发唯一事实源 |
| `frontend/docs/前端规范.md` | 前端开发唯一事实源 |
