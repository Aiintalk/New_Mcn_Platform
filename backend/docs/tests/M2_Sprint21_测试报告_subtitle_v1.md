# M2 Sprint 21 — 字幕提取异步任务化 测试报告

> **版本**：v1
> **作者**：MCN_PM_Agent
> **日期**：2026-06-27
> **测试对象**：Sprint 21 字幕提取（异步任务化 + 统一历史 + 软删除）
> **测试环境**：Windows 11、Python 3.11、PostgreSQL 18.4、Node.js + Vitest、本地 mcn_m1 库

---

## 一、测试范围

| 范围 | 测试类型 | 文件 |
|------|----------|------|
| 后端 operator_subtitle | 集成（pytest + httpx + 真实 DB） | `tests/integration/routers/test_operator_subtitle.py` |
| 后端 admin_subtitle | 集成（未改动，回归用） | `tests/integration/routers/test_admin_subtitle.py` |
| 后端 tikhub adapter | 单元 | `tests/unit/services/test_tikhub_adapter.py` |
| 前端 SubtitleExtractorPage | 组件（vitest + jsdom） | `src/__tests__/components/pages/SubtitleExtractorPage.test.tsx` |
| 前端 HistoryList | 组件（vitest + jsdom） | `src/__tests__/components/pages/HistoryList.test.tsx` |
| 前端类型 | TypeScript 编译 | `npx tsc --noEmit` |

---

## 二、测试结果汇总

### 后端

| 文件 | 通过 / 总数 | 状态 |
|------|-------------|------|
| `test_operator_subtitle.py` | 30/30 | ✅ PASS |
| `test_admin_subtitle.py` | 11/11 | ✅ PASS（未改动） |
| `test_tikhub_adapter.py`（相关用例） | 全过 | ✅ PASS |
| **全量后端**（排除 tests/intake pre-existing 错误） | 1078 passed / 11 pre-existing failed | ✅ PASS（11 失败均与字幕无关） |

### 前端

| 文件 | 通过 / 总数 | 状态 |
|------|-------------|------|
| `SubtitleExtractorPage.test.tsx` | 5/5 | ✅ PASS |
| `HistoryList.test.tsx` | 6/6 | ✅ PASS |
| **tsc** | clean | ✅ PASS |
| **全量前端** | 233 passed / 7 pre-existing failed | ✅ PASS（7 失败均为 request.test.ts 端口 8000/8001 不匹配，与字幕无关） |

---

## 三、后端测试用例明细

### `test_operator_subtitle.py`（30 个）

#### TestAuth（4 个，未改动）
- test_extract_requires_auth
- test_batch_requires_auth
- test_mindmap_requires_auth
- test_save_output_requires_auth

#### TestExtractAsync（4 个，重写）
- test_extract_returns_job_code_and_creates_job：share_text → 返回 `{job_code, status:'processing'}`，DB 有 kind='single' job + item
- test_extract_with_file_url_skips_tikhub：file_url 模式不调 tikhub
- test_extract_requires_input：空输入 → 400
- test_extract_with_invalid_share_text：tikhub 报错时任务进 failed 状态

#### TestRunSingleExtract（4 个，新建）
- test_run_single_extract_success_share_text：share_text 路径，meta_json 含 play_url/cover_url/nickname/digg_count/aweme_id
- test_run_single_extract_success_file_url：file_url 路径，meta_json 各字段为空字符串
- test_run_single_extract_tikhub_failure：tikhub 失败时 item.status='failed'，error 记录
- test_run_single_extract_asr_failure：ASR 失败时同上

#### TestMindmap（6 个，未改动）

#### TestBatch（2 个，1 个修隔离）
- test_batch_create_success：OperationLog 断言改为 `EXISTS + detail::json->>'job_code' = :jc`（修全量套件污染）
- test_batch_create_empty

#### TestBatchQuery（3 个，未改动）

#### TestBatchesList（4 个，未改动）

#### TestSaveOutput（4 个，未改动）

#### TestDeleteBatch（3 个，新建）
- test_delete_batch_soft_deletes：DELETE 后 deleted_at 非 null，DB 行仍存在
- test_delete_batch_not_found：他人/不存在 job_code → 404
- test_delete_batch_writes_operation_log：OperationLog action=`subtitle_delete` 存在

### `test_admin_subtitle.py`（11 个，未改动）

Sprint 19 完成后未再改动，回归通过。

---

## 四、前端测试用例明细

### `SubtitleExtractorPage.test.tsx`（5 个，重写）

| 用例 | 覆盖点 |
|------|--------|
| renders single-page layout with two sections | 初始渲染（两个 Card + HistoryList） |
| extracts subtitle via async polling and displays video info + cover | extract → 轮询 → 完成后显示封面 + 3 列元信息 + 字幕 |
| shows error message when single extract fails | 任务 failed 时显示 error 文本 |
| switches to mindmap view and shows root title | 切换思维导图视图，SVG 渲染分支 |
| counts pending batch items in textarea | 批量 TextArea 计数 |

### `HistoryList.test.tsx`（6 个，新建）

| 用例 | 覆盖点 |
|------|--------|
| shows empty state when no history | 空列表 Empty 组件 |
| renders unified list of single + batch jobs | 单条 + 批量混合渲染 |
| expands single job to show full transcript and operations | 展开 → 懒加载详情 → 显示 transcript + 复制/思维导图按钮 |
| deletes a job and refreshes list | 删除 → mock deleteHistory 调用 → 列表刷新为空 |
| generates mindmap for a single job | 点生成思维导图 → mock generateMindmap 调用 → MindmapView 渲染 |
| expands batch job to show items list | 批量任务展开 → items list（含 status tag + error） |

---

## 五、踩坑与修复

### 1. OperationLog COUNT 全量套件污染

**现象**：`test_batch_create_success` 单独跑过，全量 pytest 跑时失败
**根因**：`SELECT COUNT(*) FROM operation_logs WHERE action = 'subtitle_batch_create'` 在全量套件里会统计到其他测试用例创建的同 action 日志
**修复**：改为 `EXISTS + detail::json->>'job_code' = :jc` 精确匹配本任务的日志

### 2. 批量 replace_all 漏可选链版本

**现象**：思维导图切换测试失败，`handleToggleMindmap` 提前 return
**根因**：批量做 `replace_all('result.text' → 'result.transcript')` 时漏掉 5 处 `result?.text` 可选链版本
**修复**：单独再做一次 `replace_all('result?.text' → 'result?.transcript')`

### 3. fake timers + userEvent 异步轮询不触发

**现象**：测试卡死或 mock 未被调用
**根因**：默认 fake timers 不推进时间，setInterval 永远不触发
**修复**：`vi.useFakeTimers({ shouldAdvanceTime: true })` + `userEvent.setup({ advanceTimers: vi.advanceTimersByTime })`

### 4. Windows watchfiles 不触发 uvicorn reload

**现象**：改完代码后前端调用 `/extract` 仍走旧逻辑，DB 无写入
**根因**：Windows + watchfiles 在某些情况下不检测变更；uvicorn 跑的还是 17:37 启动的旧代码
**修复**：手动 kill 3 个 python 进程（父 reload 监视器 / worker / multiprocessing 子）后重启

### 5. 后端旧代码 + 新前端联调陷阱

**现象**：前端轮询 `/batch/undefined` 持续 404
**根因**：旧后端 /extract 返回 200 + 旧版响应（无 job_code），新前端代码把 `resp.job_code` 当 undefined，启动了轮询
**修复**：必须前后端同步部署/重启；前端刷新清 state

---

## 六、Pre-existing 失败（与字幕无关）

### 后端 11 个 pre-existing failures

- `tests/concurrent/test_isolation.py` × 4：并发隔离测试（项目老问题）
- `tests/concurrent/test_seeding_writer_isolation.py` × 4：同上
- `tests/unit/services/test_livestream_writer_file_parser.py` × 2：Pages 文件解析（与本功能无关）
- `tests/unit/tools/test_qianchuan_review_prompts.py` × 1：收集错误（与本功能无关）
- `tests/intake/`：conftest.py 非顶层 pytest_plugins（项目老问题）

### 前端 7 个 pre-existing failures

`src/__tests__/unit/api/request.test.ts` × 7：测试硬编码 `http://localhost:8000`，但 `.env.local` 设为 8001。**与字幕模块完全无关。**

---

## 七、覆盖率

- 后端 operator_subtitle.py：47%（路由层，业务逻辑多在 adapter 和后台任务中）
- 后端 admin_subtitle.py：100%（未改动）
- 前端 SubtitleExtractorPage：核心路径全覆盖
- 前端 HistoryList：核心路径全覆盖

---

## 八、人工验收（待用户执行）

代码与自动化测试已通过，**功能正确性需用户在浏览器验证**：

| # | 验收项 | 操作 |
|---|--------|------|
| 1 | 单条异步提取 | 刷新页面（Ctrl+Shift+R）→ 粘贴抖音链接 → 点提取 → 按钮变"解析中… Ns" |
| 2 | 历史记录实时显示 | 提交后历史记录区立刻出现 `single` 标签的 processing 任务 |
| 3 | 切换页面回来 | 切到其他功能页 → 1-3 分钟后回来 → 历史记录里任务变为 completed |
| 4 | 展开查看完整字幕 | 点"详情" → 显示完整 transcript + 复制/思维导图按钮 |
| 5 | 重新生成思维导图 | 点"生成思维导图" → 内联显示 SVG 思维导图 |
| 6 | 软删除 | 点"删除" → 列表移除 → DB 里 deleted_at 非 null（不物理删除） |
| 7 | 批量任务 | TextArea 输入或 Excel 拖拽 → 提交 → 历史记录里出现 `batch` 任务 |
| 8 | 跨用户隔离 | 切换账号后看不到他人的字幕历史 |

---

## 九、结论

- 自动化测试：**41/41 字幕相关用例全过**
- 全量回归：字幕模块 0 失败；11+7 pre-existing 失败均与字幕无关，不阻塞
- 文档落地：契约 §25/§30 + 前后端 README + PM 记忆 + 4 份 Sprint 21 文档（本报告 + 需求 + 后端任务 + 前端任务）齐全
- **建议**：通过自动化测试，准予进入用户浏览器验证环节；用户人工验收 8 项全部通过后即可推送 GitHub。
