# MCN_PM_Agent — 项目记忆与当前状态（M2）

> 最后更新：2026-06-18（Sprint 11 OSS adapter 接入完成：3 函数真实接通 + 8 单元测试 + 连通性测试 + 文档落地，等用户配凭证跑 live test）
> 更新角色：MCN_PM_Agent
> 上一份文档：`docs/pm/PM_记忆与状态.md`（M1 阶段，已归档）

---

## 一、项目基本信息

- **项目名**：MCN Information System Platform
- **当前阶段**：M2 阶段 — Sprint 11 OSS adapter 后端接通完成（feature/oss-adapter 待 push），下一个 Sprint 候选：files router 接入 OSS / ASR / 管理端 OSS 面板 UI
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

### M2 工作项 — 阿里云 OSS Adapter 后端接通 ✅ 完成（待 push）

**核心定位**：把 `app/adapters/oss.py` 从 M1 起的 Mock 占位（`get_download_url` 返回假 URL，`upload_file` 抛 NotImplementedError）替换为真实接通阿里云 OSS 的实现。**仅后端接通，凭证由用户后续配置**，files router 上传接口、管理端 OSS 面板、存储统计等留后续。

| 端 | 状态 | 备注 |
|----|------|------|
| OSS adapter 重写 | ✅ 完成 | `app/adapters/oss.py`：3 公开函数（`upload_file` / `get_download_url` / `delete_file`）+ 2 内部 helper（`_get_oss_credential` / `_make_bucket`） |
| 单元测试 | ✅ 8/8 | `tests/unit/services/test_oss_adapter.py`（纯 mock），覆盖率 **89%**（adapter 门禁 ≥ 60%） |
| 连通性测试 | ✅ 已就位（默认跳过） | `tests/integration/test_oss_live.py`（`pytestmark = skipif(not OSS_LIVE_TEST)`），用户配凭证后启用 |
| pytest.ini | ✅ 加 markers | `live: tests requiring real external services` |
| 文档 | ✅ 落地 | 任务单 + 测试报告 + README 更新 + PM 记忆（本文） |
| 凭证配置 | ⏳ 待用户配 | `service_credentials` 表插 `provider='oss'` 记录，详见任务单 §7 |

**关键设计点：**
- `oss2` 是同步库 → 全部 `asyncio.to_thread` 包装，不阻塞事件循环
- `_get_oss_credential` 在 try **外**调用（凭证缺失 / config 缺字段时直接抛 KeyError，不 report_failure 因为没 cred_id）
- oss2 操作在 try **内**（失败 → report_failure + 包装为 RuntimeError 传播）
- 凭证字段映射：`label`=AccessKey ID，`secret_enc`=Secret，`config.bucket`/`config.endpoint` 从 JSONB 读

**全量回归**：4 failed + 4 errors 全是预存技术债（5 个其他 router 缺 OperationLog / snappy 模块缺失 / intake conftest pytest_plugins 位置），OSS 改动**零回归**。

**不在本次范围（留后续）：**
- 管理端 OSS 面板 UI（凭证 CRUD + 存储统计展示）
- `files.py` router 补 upload 接口（真正存 OSS，目前 router 仍写本地）
- 存储统计（基于 files 表 + 阿里云计量 API）
- outputs 产出迁移到 OSS
- ASR 服务接入

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


### 基础文档

| 文件 | 说明 |
|------|------|
| `backend/docs/base/MCN_M2_Base_API.md` | M2 API 接口规范（含 Sprint1~3） |
| `backend/docs/base/MCN_M2_Base_Database.md` | M2 数据库契约（含 Sprint1~3） |
| `backend/docs/后端开发约定.md` | 后端开发唯一事实源 |
| `frontend/docs/前端规范.md` | 前端开发唯一事实源 |
