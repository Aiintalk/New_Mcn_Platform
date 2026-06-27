# M2 Sprint 21 — 字幕提取异步任务化 + 统一历史 + 软删除 需求文档

> **版本**：v1
> **作者**：MCN_PM_Agent
> **日期**：2026-06-27
> **基线**：基于 Sprint 19 字幕提取（main，已合并）的迭代
> **迁移源**：旧架构 `Ai_Toolbox/subtitle-extractor-web/app/page.tsx`（历史记录 + 异步轮询模式）

---

## 一、定位

针对 Sprint 19 字幕提取的三大缺陷做异步化 + 体验迭代：

1. **单条 extract 异步任务化**：原同步阻塞 1-3 分钟，前端无法切换页面 → 改为创建 `kind='single'` 任务后立即返回 `job_code`，前端轮询
2. **统一历史记录**：单条 + 批量在同一列表展示，支持查看完整字幕 / 重新生成思维导图 / 复制 / 软删除
3. **软删除**：用户主动删除历史记录（不物理删除，保留审计能力）

附加：`subtitle_items.meta_json` 存视频元信息（cover_url/nickname/digg_count/aweme_id/play_url/audio_url），API 响应里扁平化到顶层。

---

## 二、需求来源

用户反馈（2026-06-27）：
> "在解析过程中我切换了其他功能页面回来后可以查看历史记录嘛"

具体场景：
- 单条 ASR 解析需 1-3 分钟，用户在此期间想切换到其他工具页面做事
- 切换回来后期望能看到刚才提取的进度 / 结果
- 当前的"我的批量任务"列表只显示批量任务，单条提取切换页面后丢失

---

## 三、迁移红线对照

| 红线 | 本功能如何满足 |
|------|--------------|
| #1 标准信封 | 异步 extract 返回 `{success, code, message, data:{job_code, status}}`，DELETE 软删除同样返回标准信封 |
| #2 写操作写 OperationLog | POST /extract（action=`subtitle_extract`）、POST /batch（action=`subtitle_batch_create`）、DELETE /batch/{job_code}（action=`subtitle_delete`，**新增**）|
| #3 前端走 request.ts | `extractSubtitle` / `listHistory` / `deleteHistory` 等均走 `api/subtitle.ts` 封装 |
| #4 改契约先回报 | 已更新 Base_API §25（异步 extract + DELETE）+ Base_Database §30（kind/deleted_at/meta_json）|
| #5 AiCallLog 由 adapter 写 | 本次未新增 AI 调用路径，沿用 Sprint 19 yunwu/asr adapter 日志链路 |
| #6 AsyncSessionLocal 已注册 | Sprint 19 已将 `app.routers.operator_subtitle.AsyncSessionLocal` 加入 conftest patch 列表，本次复用 |
| #7 列表必须分页 | GET /batches 保留分页（page/page_size），不回归 |
| #8 严禁物理删除 | DELETE 软删除实现 `deleted_at = now()`，不删 row |

---

## 四、关键技术决策

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| 1 | 任务表统一 | 复用 `subtitle_jobs` 加 `kind` 字段（single/batch） | 避免新建表；与批量任务共用 `_run_*` 后台模式 |
| 2 | 软删除 | `deleted_at TIMESTAMPTZ`，过滤 `IS NULL` | 保留审计；与项目其他表（products/references）一致 |
| 3 | 视频元信息存储 | `subtitle_items.meta_json TEXT`（JSON） | 专用字段比 hack `job.phase` 干净；API 响应扁平化到顶层方便前端使用 |
| 4 | 异步执行模式 | `asyncio.create_task(_run_single_extract())` | 与 Sprint 19 `_run_batch` 同模式；不引入 Celery |
| 5 | 前端轮询 | 单条：3s 间隔；历史列表：5s 间隔（仅当有 processing 任务） | ASR 1-3 分钟，SSE 不合适；批量原已用轮询 |
| 6 | 历史记录组件 | 新建 `HistoryList.tsx` 自包含组件 | 单一职责；自动轮询；不污染主页面状态 |
| 7 | Migration 编号 | 044（kind/soft_delete）+ 045（meta_json） | 当前最高 043（values_writer）|
| 8 | API 重命名 | `listMyBatches` → `listHistory`（保留别名）+ 新增 `deleteHistory` | 反映"统一历史"语义；别名避免破坏旧调用方 |
| 9 | 历史操作集 | 单条：查看完整字幕 + 重新生成思维导图 + 复制 + 删除；批量：查看 items + 删除 | 用户确认（AskUserQuestion） |

---

## 五、不在本次范围

1. **思维导图持久化**：用户在历史记录里"重新生成思维导图"的结果当前只缓存在前端 state，刷新后丢失。未来如需持久化，需要新建 `subtitle_mindmaps` 表或在 `subtitle_items` 加 `mindmap_json` 字段
2. **批量任务的"重新生成思维导图"**：批量任务每条 item 都有独立 transcript，本次只在单条任务支持重生成；批量任务的思维导图仍走原路径（在主页面结果区生成）
3. **WebSocket 推送**：仍用轮询，不引入 WS
4. **历史记录搜索/筛选**：本次只支持分页倒序，不支持按状态/关键词筛选
5. **批量任务的批量删除**：本次只支持单条删除

---

## 六、验收标准（8 项）

1. ✅ POST /extract 异步返回 `{job_code, status:'processing'}`，前端拿到后开始轮询
2. ✅ _run_single_extract 后台执行：tikhub + asr（share_text 模式）或纯 asr（file_url 模式），结果存 `subtitle_items.meta_json` + `transcript`
3. ✅ DELETE /batch/{job_code} 软删除（设置 `deleted_at`），后续列表/详情查询过滤掉
4. ✅ GET /batches 返回单条+批量统一历史（按 created_at 倒序，过滤 deleted_at IS NULL，分页）
5. ✅ 前端 SubtitleExtractorPage 单条提取改为轮询模式：创建 job → 每 3s 轮询 → 完成显示结果
6. ✅ 前端 HistoryList 组件：展开详情懒加载；单条支持复制/重生成思维导图/删除；批量支持查看 items/删除；processing 任务自动 5s 轮询
7. ✅ 所有测试通过（后端 pytest + 前端 vitest + tsc）
8. ✅ 契约（Base_API §25 + Base_Database §30）+ 前后端 README + PM 记忆 同步

---

## 七、实施记录

| 阶段 | 状态 | 产物 |
|------|------|------|
| Phase 1 后端模型 + migration | ✅ | migration 044 + 045 + ORM 加字段 |
| Phase 2 后端 /extract 改异步 | ✅ | _run_single_extract + job_code 立即返回 |
| Phase 3 后端 DELETE + GET /batches 软删除过滤 | ✅ | DELETE /batch/{job_code} + deleted_at IS NULL 过滤 |
| Phase 4 前端 API + 单条轮询 | ✅ | api/subtitle.ts 重命名 + SubtitleExtractorPage 改轮询 |
| Phase 5 前端 HistoryList 组件 | ✅ | pages/operator/subtitle/HistoryList.tsx 新建 |
| 测试 + 文档 | ✅ | 30+11 后端 + 5+6 前端 + 契约 + README + PM 记忆 |

---

## 八、踩坑记录

1. **OperationLog COUNT 全量套件污染**：测试 `WHERE action = 'subtitle_xxx'` 在全量 suite 跑时其他用例污染计数 → 改用 `EXISTS + detail::json->>'job_code' = :jc` 精确匹配
2. **批量 replace_all 漏 `result?.text` 可选链版本**：`replace_all('result.text' → 'result.transcript')` 漏掉 5 处 `result?.text`，单独再做一次 `replace_all('result?.text' → 'result?.transcript')`
3. **fake timers + userEvent 异步轮询测试**：必须 `vi.useFakeTimers({ shouldAdvanceTime: true })` + `userEvent.setup({ advanceTimers: vi.advanceTimersByTime })`，否则 setInterval 不触发
4. **Windows watchfiles 不触发 uvicorn reload**：改完代码后必须手动重启 uvicorn（kill 父+子+multiprocessing 孙三个进程），不能依赖 --reload 自动加载
5. **后端旧代码 + 新前端联调踩坑**：前端调用旧后端 /extract 时，旧后端返回的是 200 + 旧版响应（无 job_code），新前端代码把 `resp.job_code` 当成 undefined，导致轮询 `/batch/undefined` 永远 404 —— 部署/重启时必须前后端同步

---

## 九、测试统计

- 后端 `test_operator_subtitle.py` 30/30 ✅
- 后端 `test_admin_subtitle.py` 11/11 ✅（未改动）
- 前端 `SubtitleExtractorPage.test.tsx` 5/5 ✅（重写）
- 前端 `HistoryList.test.tsx` 6/6 ✅（新建）
- 前端 tsc：clean
- 全量后端 1078 passed（pre-existing 11 failures 与字幕无关）
- 全量前端 233 passed（pre-existing 7 port-mismatch failures 与字幕无关）
