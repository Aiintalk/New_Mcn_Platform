# 后端文档目录

> 本目录存放后端相关的所有文档。开发后端时，不出 `backend/` 目录即可找到全部所需内容。

---

## 后端架构

```
backend/
├── app/                               # 源码
│   ├── adapters/                      # 外部服务适配器
│   │   ├── ai.py                      #   AI 服务（多 Key 池、并发调度）
│   │   ├── tikhub.py                  #   TikHub API 适配器
│   │   ├── oss.py                     #   阿里云 OSS 适配器（upload_file / get_download_url / delete_file，真实接通；finally 块写 oss_call_logs 日志）
│   │   ├── asr.py                     #   阿里云 ISI 语音识别适配器（submit_transcription / query_transcription / transcribe，POP RPC + CommonRequest；finally 块写 asr_call_logs 日志）
│   │   └── yunwu.py                   #   多服务商 AI 适配器（yunwu/siliconflow/glm，按 provider 切换；防御空 choices 数组）
│   ├── core/                          # 核心基础设施
│   │   ├── config.py                  #   环境配置（读取 .env）
│   │   ├── database.py                #   数据库连接 + Base ORM 类
│   │   ├── security.py                #   JWT 工具 + 密码哈希
│   │   ├── response.py                #   统一响应封装 + ErrorCode
│   │   └── seed.py                    #   初始数据填充
│   ├── middlewares/
│   │   └── auth.py                    #   JWT 鉴权（get_current_user / require_admin）
│   ├── models/                        # SQLAlchemy ORM 模型（33 个文件）
│   │   ├── user.py                    #   用户表
│   │   ├── kol.py                     #   红人表（Sprint 18 新增 background/experience/relationships/unique_story/extra_notes 5 列）
│   │   ├── credential.py              #   AI 密钥池表
│   │   ├── workspace.py               #   工作空间 / 工具配置表
│   │   ├── kol_intake.py              #   入驻问卷相关表（5 张）
│   │   ├── tikhub_credential.py       #   TikHub 独立凭证表
│   │   ├── tikhub_call_log.py         #   TikHub 调用日志表
│   │   ├── persona_report.py          #   人格定位报告表
│   │   ├── benchmark.py               #   对标分析配置 + 报告表
│   │   ├── selling_point.py           #   卖点提取配置表
│   │   ├── tiktok_writer.py           #   TikTok 脚本仿写配置表
│   │   ├── qianchuan_review.py        #   千川复盘配置表
│   │   ├── qianchuan_edit_review.py   #   千川剪辑预审配置表
│   │   ├── livestream_writer.py       #   直播脚本仿写配置表
│   │   ├── livestream_review.py       #   直播间脚本复盘配置表
│   │   ├── persona_review.py          #   人设脚本复盘配置表
│   │   ├── qianchuan_writer.py        #   千川文案写作配置表（Sprint 14）
│   │   ├── persona_writer.py          #   人设脚本仿写配置表（Sprint 15）
│   │   ├── seeding_writer.py          #   种草内容仿写配置+产品+素材表（Sprint 16）
│   │   ├── qianchuan_product.py       #   千川产品库（Sprint 18）
│   │   ├── kol_benchmark.py           #   达人对标账号（Sprint 18）
│   │   ├── kol_active_product.py      #   达人在售商品关联（Sprint 18）
│   │   └── ...                        #   log / file / output / session / task
│   ├── routers/                       # API 路由（按角色分文件，52 个）
│   │   ├── auth.py                    #   POST /api/auth/login、/change-password
│   │   ├── admin_users.py             #   用户管理（admin）
│   │   ├── admin_kols.py              #   红人管理（admin）
│   │   ├── admin_ai.py                #   AI 密钥/模型管理（admin）
│   │   ├── admin_credentials.py       #   凭证管理（admin）：CRUD + 启停 + 密钥轮换（PATCH api_key）+ OSS/ASR 连通性测试（保存 last_tested_at / last_latency_ms）
│   │   ├── admin_workspace.py         #   工具配置（admin）
│   │   ├── admin_intake.py            #   入驻问卷管理（admin）
│   │   ├── admin_tikhub.py            #   TikHub 管理（admin）
│   │   ├── admin_oss.py               #   OSS 调用统计（admin）：stats / operations / users 三维聚合
│   │   ├── admin_asr.py               #   ASR 调用统计（admin）：stats / operations / users 三维聚合
│   │   ├── admin_logs.py              #   日志管理（admin）
│   │   ├── admin_system.py            #   系统管理（admin）
│   │   ├── admin_benchmark.py         #   对标分析配置（admin）
│   │   ├── admin_selling_point.py     #   卖点提取配置（admin）
│   │   ├── admin_qianchuan_review.py  #   千川复盘配置（admin）
│   │   ├── admin_qianchuan_edit_review.py # 千川剪辑预审配置（admin）
│   │   ├── admin_tiktok_writer.py     #   TikTok 仿写配置（admin）
│   │   ├── admin_livestream_writer.py #   直播脚本仿写配置（admin）
│   │   ├── admin_livestream_review.py #   直播间脚本复盘配置（admin）
│   │   ├── admin_persona_review.py    #   人设脚本复盘配置（admin）
│   │   ├── admin_qianchuan_writer.py  #   千川文案写作配置（admin，Sprint 14）
│   │   ├── admin_persona_writer.py    #   人设脚本仿写配置（admin，Sprint 15）
│   │   ├── admin_seeding_writer.py    #   种草内容仿写配置（admin，Sprint 16）
│   │   ├── operator_homepage.py       #   运营首页数据
│   │   ├── operator_intake.py         #   入驻问卷（运营端）
│   │   ├── operator_intake_direct.py  #   运营直发对话
│   │   ├── operator_benchmark.py      #   对标分析（运营端）
│   │   ├── operator_tiktok_writer.py  #   TikTok 脚本仿写（运营端）
│   │   ├── operator_selling_point.py  #   卖点提取器（运营端）
│   │   ├── operator_qianchuan_review.py #  千川脚本复盘（运营端）
│   │   ├── operator_livestream_writer.py # 直播脚本仿写（运营端）
│   │   ├── operator_livestream_review.py # 直播间脚本复盘（运营端）
│   │   ├── operator_persona_review.py #  人设脚本复盘（运营端）
│   │   ├── operator_qianchuan_writer.py # 千川文案写作（运营端，Sprint 14）
│   │   ├── operator_persona_writer.py #  人设脚本仿写（运营端，Sprint 15）
│   │   ├── operator_seeding_writer.py #  种草内容仿写（运营端，Sprint 16）
│   │   ├── operator_qianchuan_products.py # 千川产品库 CRUD（运营端，Sprint 18）
│   │   ├── operator_workspace.py      #   红人工作台（首页/对标/在售商品，Sprint 18）
│   │   ├── admin_kols.py + _operator_router # 红人管理（admin）+ persona-details（operator，Sprint 18）
│   │   ├── persona.py                 #   人格定位（运营端）
│   │   ├── intake_public.py           #   公开接口（博主填写问卷）
│   │   ├── tool_chat_stream.py        #   工具：AI 流式对话
│   │   ├── tool_export_word.py        #   工具：Word 导出
│   │   ├── tool_extract_frames.py     #   工具：视频抽帧
│   │   ├── tool_qianchuan_edit_review.py # 工具：千川剪辑预审
│   │   ├── tool_transcribe.py         #   工具：语音转文字
│   │   ├── health.py                  #   健康检查
│   │   ├── files.py                   #   文件上传下载
│   │   ├── outputs.py                 #   产出管理
│   │   ├── tasks.py                   #   任务管理
│   │   └── workspace.py               #   工作空间
│   ├── schemas/                       # Pydantic schema（当前为空，定义在 router 内）
│   └── services/                      # 业务逻辑
│       ├── credential_selector.py     #   密钥池轮转选择器
│       ├── intake_report.py           #   入驻报告生成（PDF/DOCX）
│       ├── kol_scheduler.py           #   红人数据定时任务
│       ├── kol_tikhub.py              #   TikHub 数据抓取
│       ├── file_parser.py             #   文件解析（.docx/.pdf/.txt/.md/.pages）
│       ├── word_export.py             #   Word 文档导出
│       ├── benchmark_report.py        #   对标分析报告生成
│       ├── qianchuan_review_service.py #  千川复盘业务服务
│       ├── persona_docx.py            #   人格定位报告导出
│       ├── seeding_writer_prompt.py   #   种草仿写 Prompt 模板渲染（14 占位符）
│       └── document_parser.py         #   文档解析（PDF/DOCX/XLSX/PPTX/TXT）
│
├── docs/                              # ===== 本目录 =====
│   ├── README.md                      #   本文件（架构 + 文档索引）
│   ├── base/                          #   接口契约 + 数据库契约
│   │   ├── MCN_M1_Base_API.md         #     M1 阶段 API 契约
│   │   ├── MCN_M1_Base_Database.md    #     M1 阶段数据库契约
│   │   ├── MCN_M2_Base_API.md         #     M2 阶段 API 契约
│   │   └── MCN_M2_Base_Database.md    #     M2 阶段数据库契约
│   ├── tasks/                         #   任务单 + 验收文档（43 个）
│   │   ├── M1_Sprint0.md ~ Sprint4.md          #  M1 各 Sprint
│   │   ├── M1_Sprint5_TikHub_独立池化.md        #  TikHub 独立池化
│   │   ├── M2_Sprint1_kol_intake.md            #  入驻问卷主任务
│   │   ├── M2_Sprint1_kol_intake_*.md          #  入驻问卷系列补充（10 个）
│   │   ├── M2_Sprint2_operator_homepage*.md    #  首页系列（3 个）
│   │   ├── M2_Sprint3_persona_positioning*.md  #  人设定位 + v2 修复
│   │   ├── M2_Sprint04_后端任务_tiktok-writer*.md     #  TikTok 脚本仿写 v1 + v2 修复
│   │   ├── M2_Sprint05_后端任务_selling-point-extractor*.md  #  卖点提取器 v1 + v2 修复
│   │   ├── M2_Sprint06_后端任务_qianchuan-review_v1.md       #  千川脚本复盘 v1
│   │   ├── M2_Sprint07_后端任务_qianchuan-edit-review_v1.md  #  千川剪辑预审 v1
│   │   ├── M2_Sprint07_后端_开发验收_qianchuan-edit-review_v1.md  #  千川剪辑预审验收
│   │   └── BugFix_*.md                         #  BugFix（3 个）
│   └── tests/                         #   测试报告 + 测试任务
│       ├── MCN_M1_Test_Task.md                        #  M1 测试任务
│       ├── MCN_M1_Test_Report_Chapter1.md             #  M1 测试报告
│       ├── MCN_M1_Concurrent_Test_Report.md           #  M1 并发测试报告
│       ├── M2_Sprint1_kol_intake_测试任务单.md          #  M2 Sprint1 测试任务
│       ├── M2_Sprint2_homepage_测试任务单.md            #  M2 Sprint2 测试任务
│       ├── M2_Sprint3_测试报告.md                       #  M2 Sprint3 测试报告（persona + TikHub）
│       ├── M2_Sprint04_测试报告_tiktok-writer_v1.md     #  M2 Sprint4 测试报告
│       ├── M2_Sprint05_测试报告_selling-point-extractor_v1.md  #  M2 Sprint5 测试报告
│       ├── M2_Sprint06_测试报告_qianchuan-review_v1.md  #  M2 Sprint6 测试报告
│       ├── M2_Sprint07_测试报告_qianchuan-edit-review_v1.md  #  M2 Sprint7 测试报告
│       ├── M2_Sprint08_测试报告_livestream-writer_v1.md  #  M2 Sprint8 测试报告（34/34）
│       ├── M2_Sprint09_测试报告_livestream-review_v1.md  #  M2 Sprint9 测试报告（58/58）
│       ├── M2_Sprint10_测试报告_persona-review_v1.md     #  M2 Sprint10 测试报告（54/54）
│       ├── M2_Sprint11_测试报告_qianchuan-preview_v1.md  #  M2 Sprint11 测试报告（25/25）
│       ├── M2_Sprint11_测试报告_oss-adapter_v1.md        #  M2 Sprint11 OSS 测试报告
│       ├── M2_Sprint12_测试报告_qianchuan-collection_v1.md  #  M2 Sprint12 测试报告
│       ├── M2_Sprint15_测试报告_persona-writer_v2_修复Bug.md  #  M2 Sprint15 Bug修复测试报告
│       └── MCN_Integration_Test_Fix_Report_2026-06-11.md  #  集成测试修复报告
│
├── tests/                             # 测试代码
│   ├── unit/                          #   单元测试（Mock DB，不需要 PostgreSQL）
│   │   ├── core/                      #     config / response / security
│   │   ├── middlewares/               #     auth
│   │   └── services/                  #     credential_selector / intake_report
│   ├── integration/                   #   集成测试（需测试数据库 mcn_test）
│   │   ├── test_convention_guard.py   #     规范守卫（AST 扫描红线 #1 #2 #6 #7）
│   │   ├── test_credential_pool.py    #     AI 凭证池并发安全（21 条）
│   │   └── routers/                   #     20 个文件，覆盖全部 router
│   ├── e2e/                           #   端到端测试（待补充）
│   ├── concurrent/                    #   并发隔离测试
│   └── intake/                        #   入驻问卷专项测试
│
├── migrations/                        # SQL 迁移脚本（001 ~ 034）
├── scripts/                           # 工具脚本
│   ├── init_db.sh                     #   一键初始化数据库
│   ├── run_coverage.py                #   覆盖率门禁脚本
│   ├── migrate_qianchuan_reports.py   #   旧千川复盘数据迁移
│   └── migrate_material_library.py    #   旧素材库（soul.md/content-plan.md）迁移
├── requirements.txt                   # Python 依赖
├── seed_local.sql                     # 本地种子数据
└── pytest.ini                         # pytest 配置
```

---

## 文档存储结构

```
backend/docs/
├── base/          接口契约 + 数据库契约（唯一事实源）
│                  → 接口变更必须先更新 Base_API，再改代码
│                  → 表结构变更必须先更新 Base_Database，再写迁移
├── tasks/         任务单 + 验收文档
│                  → 新功能、BugFix、优化都放这里
│                  → 迭代按 vN 递增新建，不覆盖原文档
│                  → 验收文档与任务单同目录，文件名带「开发验收」
└── tests/         测试报告 + 测试任务
                   → 测试代码在 backend/tests/，测试文档在这里
                   → 每个 Sprint 测试完成后出具测试报告
```

### 命名规范

```
任务文档：    Mx_Sprintxx_{功能名}[_vN[_迭代类型]]
验收文档：    Mx_Sprintxx_后端任务_开发验收_{功能名}_vN.md
BugFix：      BugFix_{序号}_{描述}.md
测试报告：    MCN_Mx_{测试类型}_Test_Report.md
```

- **迭代类型**（v2 起）：`新增功能` / `修改需求` / `修复Bug`
- **版本号**：一条线累加（v1 → v2 → v3），不重复

---

## 关键约定

- 所有接口响应走 `success_response()` / `error_response()`
- 所有错误码注册在 `app/core/response.py` 的 `ErrorCode`
- 改 Model 必须同步写 migrations 迁移文件
- 改接口必须先更新 `docs/base/Base_API.md`
- 测试运行（单元 + 集成）：`pytest tests/unit/ tests/integration/ -v --cov=app`
- 覆盖率门禁：`python scripts/run_coverage.py --gate`
- intake/ 和 concurrent/ 是 E2E 级测试，需要真实服务器，不纳入门禁统计

---

## 工具列表

| 工具标识 | 功能描述 | 主要路由文件 | 引入 Sprint |
|---------|---------|------------|------------|
| tiktok-writer | TikTok脚本仿写 | operator_tiktok_writer.py / admin_tiktok_writer.py | Sprint 4 |
| selling-point-extractor | 产品卖点提取器 | operator_selling_point.py / admin_selling_point.py | Sprint 5 |
| qianchuan-review | 千川脚本复盘 | operator_qianchuan_review.py | Sprint 6 |
| qianchuan-edit-review | 千川剪辑预审 | tool_qianchuan_edit_review.py | Sprint 7 |
| livestream-writer | 直播脚本仿写 | operator_livestream_writer.py / admin_livestream_writer.py | Sprint 8 |
| livestream-review | 直播间脚本复盘 | operator_livestream_review.py / admin_livestream_review.py | Sprint 9 |
| persona-review | 人设脚本复盘 | operator_persona_review.py / admin_persona_review.py | Sprint 10 |
| qianchuan-preview | 千川文案预审 | operator_qianchuan_preview.py / admin_qianchuan_preview.py | Sprint 11 |
| qianchuan-collection | 千川爆文合集 | operator_qianchuan_collection.py | Sprint 12 |
| tiktok-review | TT内容复盘 | operator_tiktok_review.py / admin_tiktok_review.py | Sprint 13 |
| persona-writer | 人设脚本仿写 | operator_persona_writer.py / admin_persona_writer.py | Sprint 15 |
| seeding-writer | 种草内容仿写 | operator_seeding_writer.py / admin_seeding_writer.py | Sprint 16 |
| material-library | 素材库（红人素材中枢） | operator_material_library.py / admin_material_library.py | Sprint 18（迁移） |
| subtitle | 字幕提取（单条异步+批量+思维导图+统一历史+软删除） | operator_subtitle.py / admin_subtitle.py | Sprint 19（迁移）；Sprint 21（异步任务化+软删除） |
| values-writer | 价值观仿写（4步向导 + save-output 历史） | operator_values_writer.py / admin_values_writer.py | Sprint 20；历史功能 2026-07-01 补齐 |
| qianchuan-script-review | 千川脚本预审（直销/价值观双模式 + save-output 历史） | operator_script_review.py / admin_script_review.py | Sprint 21；历史功能 2026-07-01 补齐 |
| retrospective | 复盘（工作台子模块，多维材料+AI分析+导出） | operator_retrospective.py / admin_retrospective.py | Sprint 22 |

---

## 最近改动

### 2026-07-07 PR #18 修复 Bug #12-17 系统反馈问题

**背景**：飞书 wiki 集中反馈的 6 个用户体验 Bug，由外部贡献者 `chongzhang258-star` 提交 PR，PM 本地 rebase main 解决冲突后合并（保留 PR #19 的 provider 修复 + 叠加 PR #18 的重试逻辑）。

**修复内容**（按 Bug 编号）：

| Bug # | 模块 | 问题 | 修复 |
|-------|------|------|------|
| #12 | 字幕提取 - 批量历史 | transcript 截断 120 字 + 缺「复制文本」按钮 | `subtitle/HistoryList.tsx`：完整展示（滚动 200px）+ 复制按钮 |
| #13 | 红人工作台 - 对标账号 | 纯数字抖音号报「uid 找不到」 | `adapters/tikhub.py` `resolve_sec_user_id`：纯数字输入优先按 uid 查，无结果自动 fallback 到 unique_id |
| #14 | 人设仿写 - 开始评估 | 报错无法进入下一步 | `api/personaWriter.ts`：错误消息提取 `err.detail.message` → `err.message`（根因同 Bug #2，依赖 migration 048）|
| #15 | 千川仿写 - 产品卖点 | 截断 400 字 | `QianchuanWriterPage.tsx`：完整展示（滚动 300px）|
| #16/#17 | 直播仿写 / 直播复盘 | 无法生成 / 报错 | 根因同 Bug #2（migration 048 已在 main），前端错误消息提取修正 |

**额外改进**（commit 2，selling-point 容错）：
- `routers/operator_selling_point.py`：`_RETRY_DELAYS=[2,4]` 503/502/429/timeout 自动重试最多 3 次（**保留 PR #19 的 `provider=provider` 不变**）
- `pages/operator/SellingPointPage.tsx`：流结束后检测 `[ERROR]` 标记，转为友好提示，错误文本不再污染分析报告区域
- `tests/integration/routers/test_tool_extract_frames.py`：补 `shutil.which` ffmpeg mock + 新增 503 测试用例

**测试**：
- 后端核心 50 passed（含 selling_point + workspace + extract_frames）
- 后端 tikhub adapter 12 failed（**预存失败**，main 同样失败，mock 路径 `report_failure` vs `_report_failure`，与本次改动无关）
- 前端 HistoryList 6/6 + QianchuanWriterPage 10/11（1 失败为预存，main 同样失败）

**依赖**：Bug #14/#16/#17 依赖 migration 048（`048_external_service_logs_tokens_used.sql`，PR #17 已合并到 main，2026-07-02 起）。

**关键不变量验证**（rebase 后保留）：
- ✅ `provider=provider` 在 `chat_stream` 调用（line 134，PR #19 修复）
- ✅ `_resolve_model` 返回 `(model_id, provider)` 二元组（PR #19）
- ✅ `_RETRY_DELAYS` 重试循环结构（PR #18）

### 2026-07-07 PR #18 测试补漏 + tikhub adapter 预存失败修复

**背景**：PR #18 合并后审计发现 — 4 处关键改动完全无测试覆盖 + tikhub adapter 12 个预存失败（mock 路径 `report_failure` 与实际 `_report_failure` 不一致）+ 2 处前端测试断言不完整。本 PR 单独成支补漏，不动生产代码。

**补漏内容**（按 PR #18 改动点）：

| 改动点 | 补漏前 | 补漏后 |
|-------|--------|--------|
| `tikhub.resolve_sec_user_id` 纯数字 fallback | 无 fallback 测试 | 2 个：纯数字 uid 命中走快捷路径 + uid 无果 fallback 到 unique_id |
| tikhub adapter 12 预存失败 | mock 路径错误 | 全部改为 `_report_success`/`_report_failure`，重写 douyin_id 测试，12/12 通过 |
| `operator_selling_point` 503 重试 | 仅 1 个 error marker 测试 | +2 个：503 重试后成功 + 重试耗尽仍 yield [ERROR]（patch asyncio.sleep 跳过真实等待） |
| `personaWriter.ts` 3 处错误消息提取 | 完全无测试 | 新建 `__tests__/unit/api/personaWriter.test.ts`（6 个：3 函数主路径 + 3 状态码回退） |
| `SellingPointPage.tsx` [ERROR] 标记处理 | 完全无测试 | 新建 `__tests__/components/pages/SellingPointPage.test.tsx`（2 个：标记清理 + 友好提示 / 健康流） |
| `HistoryList.tsx` 批量任务复制按钮 | 展开测试无复制按钮断言 | 加 `expect(screen.getByText('复制文本'))` |
| `QianchuanWriterPage.tsx` 长 Brief 不截断 | 完全无测试 | +1 个：500 字 Brief 含尾部标记，验证标记完整展示（不走旧 `slice(0, 400)` 截断） |

**全量回归**：后端 1123 passed / 1 skipped / 2 failed（livestream Pages 解析，预存）/ 8 errors（concurrent 并发测试，需特殊基础设施）；前端 265 passed / 2 failed（KolWorkspace / QianchuanWriterPage 各 1，均为预存）。

**测试原则贯彻**：本 PR 不修改任何生产代码，纯补漏 + 修测试代码本身。生产代码全量回归通过，覆盖率不退化。

### 2026-07-03 修复 AI 多服务商切换不生效 + siliconflow list index out of range

**背景**：管理端切换厂商模型后调用 AI 不生效（仍走默认 yunwu 网关）；用户切到 siliconflow 后报 `[siliconflow]: list index out of range`。

**根因**：
1. **provider 传递缺失（架构缺陷）**：13 个 router 的 `chat_stream` 调用未传 `provider` 参数，adapter 默认 `provider="yunwu"`，导致配置的厂商永不生效。
2. **空 choices 防御缺失**：`yunwu.py:303/179` 当上游返回 `choices:[]`（siliconflow 等结尾帧仅含 usage）时，`[][0]` 抛 IndexError。

**修复内容**：
- `app/adapters/yunwu.py` L303（流式）+ L179（非流式）：先判空再取 `[0]`
- 13 个 router 加 `_resolve_model` 返回 `(model_id, provider)` 二元组，调用 chat/chat_stream 时传 `provider=provider`：
  - `operator_selling_point.py`、`operator_retrospective.py`
  - `operator_persona_writer.py`（3处）、`operator_seeding_writer.py`（5处）
  - `operator_values_writer.py`（4处，含非流式 chat）
  - `operator_qianchuan_writer.py`、`operator_qianchuan_preview.py`
  - `operator_tiktok_review.py`、`operator_benchmark.py`
  - `operator_livestream_writer.py`、`operator_tiktok_writer`（body.model 默认 yunwu）
- 新增单测：`tests/unit/services/test_yunwu_adapter.py`（空 choices 防御 2 用例）
- 扩展单测：`test_operator_selling_point.py` 加 provider 路由 2 用例

**验证**：
- 后端单测 31 个相关用例全过
- 端到端 curl：默认 yunwu 配置流式输出正常，ai_call_logs 记录 success
- SQL 验证：DB `ai_models.provider` 字段可正确 JOIN 读取，`_pick_and_lock` 按 provider 过滤 credentials 工作正常

**使用方法**：管理员在「工具配置 → 卖点提取（或其他工具）」选择不同厂商的模型后，请求会路由到对应服务商的凭证池（credentials 表 `provider` 字段过滤）。

### 2026-07-03 补修补：tool_chat_stream.py 漏传 provider + qianchuan-edit-review 配模型无效

**背景**：上一轮修复漏了 1 个共享 router `tool_chat_stream.py`（`POST /api/tools/chat-stream`，目前仅供千川剪辑预审使用）；同时发现 qianchuan-edit-review 工具的运营端 `getConfig()` 拉到了 `ai_model_id` 但完全没用，`analyze()` 仍硬编码 `'gpt-4o'`，**admin 配模型等于白配**。

**修复内容**：
- `app/routers/tool_chat_stream.py`：
  - `ChatStreamRequest` 加 `ai_model_id: int | None = None`
  - 加 `_resolve_model(ai_model_id, db)` → `(model_id, provider)`（参照 operator_selling_point.py:77，但接受 id 而非 config 对象，保持共享 router 通用性）
  - 加 `DEFAULT_MODEL="gpt-4o"` / `DEFAULT_PROVIDER="yunwu"` 常量
  - `generate()` 内 `yunwu_adapter.chat_stream(...)` 调用显式传 `provider=provider`
- `tests/integration/routers/test_tool_chat_stream.py`：加 2 用例（`test_passes_default_provider_when_no_ai_model_id` / `test_passes_provider_from_ai_model_id`）；原 `fake_stream` 签名加 `**kwargs` 兼容
- 前端 `api/qianchuanEditReview.ts`：`chatStream` 加 `aiModelId?: number | null`，仅非空时放进 body
- 前端 `pages/operator/QianChuanEditReviewPage.tsx`：加 `activeModelId` state，`useEffect` 从 `getConfig()` 读取，`analyze()` 传给 `chatStream`

**验证**：后端 6/6 测试通过（含 2 新用例）；前端 tsc 0 错误；其他 19 个相关测试回归全过
