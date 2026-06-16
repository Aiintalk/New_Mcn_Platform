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
│   │   ├── oss.py                     #   对象存储适配器
│   │   ├── asr.py                     #   语音识别适配器
│   │   └── yunwu.py                   #   云雾服务适配器
│   ├── core/                          # 核心基础设施
│   │   ├── config.py                  #   环境配置（读取 .env）
│   │   ├── database.py                #   数据库连接 + Base ORM 类
│   │   ├── security.py                #   JWT 工具 + 密码哈希
│   │   ├── response.py                #   统一响应封装 + ErrorCode
│   │   └── seed.py                    #   初始数据填充
│   ├── middlewares/
│   │   └── auth.py                    #   JWT 鉴权（get_current_user / require_admin）
│   ├── models/                        # SQLAlchemy ORM 模型（15 个）
│   │   ├── user.py                    #   用户表
│   │   ├── kol.py                     #   红人表
│   │   ├── credential.py              #   AI 密钥池表
│   │   ├── workspace.py               #   工作空间 / 工具配置表
│   │   ├── kol_intake.py              #   入驻问卷相关表（5 张）
│   │   ├── tikhub_credential.py       #   TikHub 独立凭证表
│   │   ├── tikhub_call_log.py         #   TikHub 调用日志表
│   │   ├── persona_report.py          #   人格定位报告表
│   │   ├── benchmark.py               #   对标分析配置 + 报告表
│   │   ├── selling_point.py           #   卖点提取配置表
│   │   └── ...                        #   log / file / output / session / task
│   ├── routers/                       # API 路由（按角色分文件，25 个）
│   │   ├── auth.py                    #   POST /api/auth/login、/change-password
│   │   ├── admin_users.py             #   用户管理（admin）
│   │   ├── admin_kols.py              #   红人管理（admin）
│   │   ├── admin_ai.py                #   AI 密钥/模型管理（admin）
│   │   ├── admin_credentials.py       #   凭证管理（admin）
│   │   ├── admin_workspace.py         #   工具配置（admin）
│   │   ├── admin_intake.py            #   入驻问卷管理（admin）
│   │   ├── admin_tikhub.py            #   TikHub 管理（admin）
│   │   ├── admin_logs.py              #   日志管理（admin）
│   │   ├── admin_system.py            #   系统管理（admin）
│   │   ├── admin_benchmark.py         #   对标分析配置（admin）
│   │   ├── admin_selling_point.py     #   卖点提取配置（admin）
│   │   ├── operator_homepage.py       #   运营首页数据
│   │   ├── operator_intake.py         #   入驻问卷（运营端）
│   │   ├── operator_intake_direct.py  #   运营直发对话
│   │   ├── operator_benchmark.py      #   对标分析（运营端）
│   │   ├── operator_tiktok_writer.py  #   TikTok 脚本仿写（运营端）
│   │   ├── operator_selling_point.py  #   卖点提取器（运营端）
│   │   ├── persona.py                 #   人格定位（运营端）
│   │   ├── intake_public.py           #   公开接口（博主填写问卷）
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
│       └── persona_docx.py            #   人格定位报告导出
│
├── docs/                              # ===== 本目录 =====
│   ├── README.md                      #   本文件（架构 + 文档索引）
│   ├── base/                          #   接口契约 + 数据库契约
│   │   ├── MCN_M1_Base_API.md         #     M1 阶段 API 契约
│   │   ├── MCN_M1_Base_Database.md    #     M1 阶段数据库契约
│   │   ├── MCN_M2_Base_API.md         #     M2 阶段 API 契约
│   │   └── MCN_M2_Base_Database.md    #     M2 阶段数据库契约
│   ├── tasks/                         #   任务单 + 验收文档（35 个）
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
│       └── MCN_Integration_Test_Fix_Report_2026-06-11.md  #  集成测试修复报告
│
├── tests/                             # 测试代码
│   ├── unit/                          #   单元测试（Mock DB，不需要 PostgreSQL）
│   │   ├── core/                      #     config / response / security
│   │   ├── middlewares/               #     auth
│   │   └── services/                  #     credential_selector / intake_report
│   ├── integration/                   #   集成测试（需测试数据库 mcn_test）
│   │   ├── test_convention_guard.py   #     规范守卫（AST 扫描红线 #1 #2）
│   │   ├── test_credential_pool.py    #     AI 凭证池并发安全（21 条）
│   │   └── routers/                   #     12 个文件，覆盖全部 router
│   ├── e2e/                           #   端到端测试（待补充）
│   ├── concurrent/                    #   并发隔离测试
│   └── intake/                        #   入驻问卷专项测试
│
├── migrations/                        # SQL 迁移脚本（001 ~ 015）
├── scripts/                           # 工具脚本
│   ├── init_db.sh                     #   一键初始化数据库
│   └── run_coverage.py                #   覆盖率门禁脚本
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
