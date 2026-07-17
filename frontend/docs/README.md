# 前端文档目录

> 本目录存放前端相关的所有文档。开发前端时，不出 `frontend/` 目录即可找到全部所需内容。

---

## 前端架构

```
frontend/
├── src/                               # 源码
│   ├── api/                           # API 调用层（36 个模块）
│   ├── components/                    # 可复用组件
│   │   └── OutputHistoryDrawer.tsx    #   产出历史抽屉（按 tool_code 过滤全局 outputs，分页+软删，支持自定义 renderItem）2026-07-01 新增
│   │   ├── request.ts                 #   基础封装（get/post/patch/put/del + 拦截器）
│   │   ├── auth.ts                    #   登录、改密码
│   │   ├── users.ts                   #   用户管理
│   │   ├── kols.ts                    #   红人管理
│   │   ├── credentials.ts             #   凭证池管理（OSS/AI/TikHub/ASR）：CRUD + 启停 + OSS/ASR 连通性测试（通用 /credentials/{id}/test 端点，按 provider 分支）
│   │   ├── workspace.ts              #   工作空间配置
│   │   ├── intake.ts                  #   入驻问卷（运营端）
│   │   ├── intakeDirect.ts            #   入驻问卷（运营直发）
│   │   ├── homepage.ts                #   运营首页数据
│   │   ├── tasks.ts                   #   任务管理
│   │   ├── outputs.ts                 #   产出管理
│   │   ├── files.ts                   #   文件上传下载
│   │   ├── logs.ts                    #   日志查看
│   │   ├── system.ts                  #   系统状态
│   │   ├── ai.ts                      #   AI 服务管理
│   │   ├── tikhub.ts                  #   TikHub 管理
│   │   ├── oss.ts                     #   OSS 统计（stats/operations/users）+ OSS 凭证 CRUD
│   │   ├── asr.ts                     #   ASR 统计（stats/operations/users）+ ASR 凭证 CRUD 类型（实际 CRUD 走通用 credentials.ts）
│   │   ├── persona.ts                 #   人格定位
│   │   ├── benchmark.ts               #   对标分析
│   │   ├── tiktokWriter.ts            #   TikTok 脚本仿写
│   │   ├── sellingPoint.ts            #   产品卖点提取器
│   │   ├── qianchuanReview.ts         #   千川脚本复盘
│   │   ├── qianchuanEditReview.ts     #   千川剪辑预审（chatStream 支持 ai_model_id 参数，2026-07-03 修复 admin 配模型不生效）
│   │   ├── livestreamWriter.ts        #   直播脚本仿写
│   │   ├── livestreamReview.ts        #   直播间脚本复盘
│   │   ├── personaReview.ts           #   人设脚本复盘
│   │   ├── qianchuanPreview.ts        #   千川文案预审（Sprint 11）
│   │   ├── qianchuanCollection.ts     #   千川爆文合集（Sprint 12）
│   │   ├── qianchuanWriter.ts         #   千川文案写作（Sprint 14）
│   │   ├── personaWriter.ts           #   人设脚本仿写（Sprint 15）
│   │   ├── seedingWriter.ts           #   种草内容仿写（Sprint 16）：22 个函数（16 走 request.ts + 4 SSE 流式 + 1 multipart + 1 Blob 下载例外）
│   │   ├── materialLibrary.ts         #   素材库（Sprint 18 迁移）：10 个函数（7 运营端 + 3 管理端），全部走 request.ts
│   │   ├── subtitle.ts                #   字幕提取（Sprint 19 迁移；Sprint 21 异步任务化：extract 返回 job_code，前端轮询；listHistory 统一历史 + deleteHistory 软删除）
│   │   ├── qianchuanProducts.ts       #   千川产品库 CRUD（Sprint 18）
│   │   ├── kolWorkspace.ts            #   红人工作台 API（dashboard/benchmarks/active-products/persona-details，Sprint 18）
│   │   ├── valuesWriter.ts            #   价值观仿写（Sprint 20）：getConfig/updateConfig/extractValues/emotionDirectionStream/writeStream/iterateStream/saveOutput（saveOutput 2026-07-01 补齐）
│   │   ├── filmReview.ts              #   千川成片预审：完整双视频上传、流式报告、保存和办公文档导出（M2 红人工作台还原）
│   │   └── scriptReview.ts            #   千川脚本预审（Sprint 21）：getConfig/updateConfig/submitReview/saveOutput（saveOutput 2026-07-01 补齐）
│   ├── layouts/                       # 布局组件
│   │   ├── AdminLayout.tsx            #   管理端布局（左侧菜单 + 内容区）
│   │   ├── OperatorLayout.tsx         #   运营端布局（左侧菜单 + 内容区）
│   │   └── AuthLayout.tsx             #   登录/注册页布局
│   ├── pages/                         # 页面组件
│   │   ├── admin/                     #   管理端（25 个：14 页面 + 11 ConfigTab）
│   │   │   ├── KolsPage.tsx           #     红人管理
│   │   │   ├── UsersPage.tsx          #     用户管理
│   │   │   ├── AiManagementPage.tsx   #     AI 密钥/模型管理
│   │   │   ├── ServiceConfigPage.tsx  #     工具配置：AI / TikHub / OSS / ASR 凭证池（OSS / ASR Tab 完整对齐 TikHub：4 张统计卡 + 操作分布饼图 + 7 天趋势折线图 + 3 子 Tab 凭证管理/操作统计/用户排行；OSS 表单=AccessKey ID/Secret/Bucket/Endpoint，ASR 表单=AppKey/AccessKey ID/Secret/Region；均含连通性测试）
│   │   │   ├── WorkspaceConfigPage.tsx #    工作空间配置（工具列表 + 配置 Tab：搜索/状态筛选 + 15/页分页；2026-07-01 加「配置」按钮直达对应 Tab + Tabs 受控；含 CONFIG_TAB_KEYS 白名单 + TOOL_CODE_TO_TAB_KEY 例外映射 kol-intake/qianchuan-script-review/selling-point-extractor；4 个预留 Tab 用 PlaceholderConfigTab 占位：persona-positioning/qianchuan-collection/qianchuan分组/review分组）
│   │   │   ├── AdminIntakePage.tsx    #     入驻问卷管理
│   │   │   ├── AdminTasksPage.tsx     #     任务管理
│   │   │   ├── AdminOutputsPage.tsx   #     产出管理
│   │   │   ├── AdminDashboardPage.tsx #     管理端仪表盘
│   │   │   ├── ExternalLogsPage.tsx   #     外部服务日志
│   │   │   ├── OperationLogsPage.tsx  #     操作日志
│   │   │   ├── ServiceStatusPage.tsx  #     服务状态
│   │   │   ├── BenchmarkConfigPage.tsx #    对标分析配置
│   │   │   ├── BenchmarkConfigTab.tsx #     对标分析配置 Tab
│   │   │   ├── SellingPointConfigTab.tsx #  卖点提取配置 Tab
│   │   │   ├── QianchuanReviewConfigTab.tsx # 千川复盘配置 Tab
│   │   │   ├── QianchuanEditReviewConfigTab.tsx # 千川剪辑预审配置 Tab
│   │   │   ├── TiktokWriterConfigTab.tsx # TikTok 仿写配置 Tab
│   │   │   ├── LivestreamWriterConfigTab.tsx # 直播脚本仿写配置 Tab
│   │   │   ├── LivestreamReviewConfigTab.tsx # 直播间脚本复盘配置 Tab（Prompt A/B + 模型）
│   │   │   └── PersonaReviewConfigTab.tsx # 人设脚本复盘配置 Tab
│   │   │   （另有 QianchuanWriterConfigTab.tsx — 千川文案写作配置 Tab，Sprint 14 新增）
│   │   │   （另有 PersonaWriterConfigTab.tsx — 人设脚本仿写配置 Tab，Sprint 15 新增）
│   │   │   （另有 SeedingWriterConfigTab.tsx — 种草内容仿写配置 Tab，Sprint 16 新增：6 个 Prompt + 轻量/重型模型 + 启用开关）
│   │   │   （另有 MaterialLibraryConfigTab.tsx — 素材库配置 Tab，Sprint 18 新增：soul_generator 系统提示词 + 模型选择 + 启用开关）
│   │   │   （另有 SubtitleConfigTab.tsx — 字幕提取配置 Tab，Sprint 19 新增：思维导图 mindmap_prompt + 模型选择 + 启用开关）
│   │   │   （另有 ValuesWriterConfigTab.tsx — 价值观仿写配置 Tab，Sprint 20 新增：4 个 Prompt + 模型 + 启用开关）
│   │   ├── operator/                  #   运营端（23 个页面 + workspace/ 子目录）
│   │   │   ├── HomePage.tsx           #     首页（统计卡片 + 趋势图）
│   │   │   ├── OperatorIntakePage.tsx #     入驻问卷列表
│   │   │   ├── OperatorIntakeChatPage.tsx #  运营直发对话
│   │   │   ├── TasksPage.tsx          #     任务中心
│   │   │   ├── OutputsPage.tsx        #     产出中心
│   │   │   ├── WorkspacePage.tsx      #     创作中心
│   │   │   ├── PersonaPage.tsx        #     人格定位
│   │   │   ├── PersonaWriterPage.tsx  #     人设定位（旧版入口）
│   │   │   ├── BenchmarkPage.tsx      #     对标分析助手
│   │   │   ├── TiktokWriterPage.tsx   #     TikTok 脚本仿写
│   │   │   ├── SellingPointPage.tsx   #     产品卖点提取器
│   │   │   ├── QianchuanReviewPage.tsx #    千川脚本复盘
│   │   │   ├── QianChuanEditReviewPage.tsx # 千川剪辑预审
│   │   │   ├── LivestreamWriterPage.tsx #   直播脚本仿写
│   │   │   ├── LivestreamReviewPage.tsx #   直播间脚本复盘
│   │   │   ├── PersonaReviewPage.tsx  #     人设脚本复盘
│   │   │   ├── KolWorkspacePage.tsx   #     红人工作台 Shell（Sprint 18-20）路由 /kol-workspace/:kol_id，10 个激活导航项；2026-07-12 对齐全站侧栏 UI（190px 深色导航 + 橙色 active）并优化写作工具页布局
│   │   │   └── workspace/             #     工作台子模块（Sprint 18-19）
│   │   │       ├── WorkspaceDashboard.tsx      #  工作台首页（对标账号 + 在售商品）
│   │   │       ├── WorkspacePersona.tsx        #  人物档案 5 分区 inline 编辑器（Sprint 19）
│   │   │       ├── WorkspaceReferences.tsx     #  素材库 6 类管理（Sprint 19）
│   │   │       └── QianchuanProductsModule.tsx #  千川产品库 CRUD
│   │   │   （QianchuanWriterPage/SeedingWriterPage/PersonaWriterPage/LivestreamWriterPage/LivestreamReviewPage 均已拆出 XxxModule 组件供工作台内嵌，Sprint 19；2026-07-12 PersonaWriterModule/SeedingWriterModule 在工作台内启用 workspace-tool-module 紧凑布局，Persona/Seeding/Qianchuan/TikTok 写作步骤卡片统一补 workspace-step-card 内边距）
│   │   │   （另有 ValuesWriterPage.tsx — 价值观仿写，Sprint 20 新增：4 步向导=选价值观+情绪方向+生成内容+迭代优化，同时导出 ValuesWriterModule 供工作台内嵌；2026-07-01 加「保存到历史」按钮 + 历史抽屉，复用 components/OutputHistoryDrawer）
│   │   │   （另有 QianchuanScriptReviewPage.tsx — 千川脚本预审，Sprint 21 新增：直销/价值观双模式，结构化评分（rating/must_fix/suggestions/passed）；2026-07-01 加「保存到历史」按钮 + 历史抽屉（自定义 renderItem 渲染评分 Tag））
│   │   │   （另有 QianchuanWriterPage.tsx — 千川文案写作，Sprint 14 新增）
│   │   │   （另有 PersonaWriterPage.tsx — 人设脚本仿写，Sprint 15 重写 placeholder 上线）
│   │   │   （另有 SeedingWriterPage.tsx — 种草内容仿写，Sprint 16 新增：4 步向导=选达人+产品信息+对标验证+种草仿写）
│   │   │   （另有 MaterialLibraryPage.tsx — 素材库，Sprint 18 新增（迁移自旧架构）：左右分栏=红人列表+4 Tab（人格档案/内容规划/参考素材/入驻信息），支持 AI 从入驻问卷生成 soul.md 初稿）
│   │   │   （另有 SubtitleExtractorPage.tsx — 字幕提取，Sprint 19 新增（迁移自旧架构）：3 Tab（单条提取/思维导图/批量提取），抖音链接→ASR→字幕+AI 思维导图，支持 SRT/Excel/Zip 导出 + 保存到产出中心）
│   │   ├── auth/                      #   登录/改密码
│   │   │   ├── LoginPage.tsx
│   │   │   └── ChangePasswordPage.tsx
│   │   └── intake/                    #   公开页
│   │       └── IntakePage.tsx         #     博主填写问卷
│   ├── routes/                        # 路由守卫
│   │   ├── ProtectedRoute.tsx         #   已登录 + 已改密检查
│   │   └── AdminRoute.tsx             #   admin 角色检查
│   ├── store/                         # Zustand 状态管理
│   │   └── authStore.ts               #   认证状态（token / user / isAuthenticated）
│   ├── styles/                        # 全局样式
│   │   ├── variables.css              #   CSS 变量（品牌色、字号、间距）
│   │   └── admin.css                  #   管理端/运营端共享样式
│   ├── types/                         # TypeScript 类型定义（23 个模块）
│   │   ├── api.ts                     #   ApiResponse<T> / PagedData<T>
│   │   ├── user.ts                    #   UserInfo
│   │   ├── kol.ts                     #   KolInfo
│   │   ├── intake.ts                  #   Intake 相关
│   │   ├── credential.ts             #   凭证相关
│   │   ├── workspace.ts              #   工作空间相关
│   │   ├── persona.ts                 #   人格定位相关
│   │   ├── benchmark.ts               #   对标分析相关
│   │   ├── tiktokWriter.ts            #   TikTok 脚本仿写相关
│   │   ├── sellingPoint.ts            #   卖点提取器相关
│   │   ├── seedingWriter.ts           #   种草内容仿写相关（Sprint 16）
│   │   └── ...                        #   task / output / log / file / system
│   ├── __tests__/                     # 测试代码（180 个用例，全部通过）
│   │   ├── unit/                      #   单元测试
│   │   │   ├── api/                   #     API 层测试（6 个文件）
│   │   │   │   ├── request.test.ts    #       request 封装
│   │   │   │   ├── users.test.ts      #       用户管理 API
│   │   │   │   ├── workspace.test.ts  #       工作空间 API
│   │   │   │   ├── tasks.test.ts      #       任务管理 API
│   │   │   │   ├── outputs.test.ts    #       产出管理 API
│   │   │   │   ├── intake.test.ts     #       入驻问卷 API（18 个用例）
│   │   │   │   └── homepage.test.ts   #       运营首页 API
│   │   │   └── store/authStore.test.ts #      authStore 测试
│   │   └── components/                #   组件测试
│   │       └── pages/                 #     页面组件测试
│   │           ├── LoginPage.test.tsx #       登录页
│   │           └── SeedingWriterPage.test.tsx # 种草仿写（23 个用例：4 步向导全流程 + ConfigTab）
│   ├── test/setup.ts                  # 测试环境 setup（matchMedia mock）
│   ├── App.tsx                        # 路由定义
│   └── main.tsx                       # 入口
│
├── docs/                              # ===== 本目录 =====
│   ├── README.md                      #   本文件（架构 + 文档索引）
│   ├── 前端规范.md                      #   前端唯一规范文档
│   ├── base/                          #   前端基础文档
│   │   └── MCN_M1_Base_Frontend.md    #     前端架构 + 页面 + 路由规范
│   ├── tests/                         #   测试报告
│   │   ├── MCN_Frontend_Test_Task_M1M2.md              #  前端测试任务单
│   │   └── MCN_Frontend_Test_Fix_Report_2026-06-11.md  #  前端测试修复报告
│   └── tasks/                         #   任务单 + 验收文档（46 个）
│       ├── M1_Sprint0.md ~ Sprint4.md           #  M1 各 Sprint
│       ├── M1_Sprint5_TikHub_独立池化.md         #  TikHub 独立池化
│       ├── M2_Sprint1_kol_intake.md             #  入驻问卷主任务
│       ├── M2_Sprint1_kol_intake_*.md           #  入驻问卷系列（14 个）
│       ├── M2_Sprint2_operator_homepage*.md     #  首页系列（3 个）
│       ├── M2_Sprint3_persona_positioning.md    #  人设定位
│       ├── M2_Sprint3_前端任务_benchmark_v2_修复Bug.md  #  对标分析修复
│       ├── M2_Sprint04_前端任务_tiktok-writer_v1.md     #  TikTok 脚本仿写
│       ├── M2_Sprint05_前端任务_selling-point-extractor_v1.md  #  卖点提取器
│       ├── M2_Sprint06_前端任务_qianchuan-review_v1.md  #  千川脚本复盘
│       ├── M2_Sprint07_前端任务_qianchuan-edit-review_v1.md  #  千川剪辑预审
│       └── M2_Sprint07_前端_开发验收_qianchuan-edit-review_v1.md  #  千川剪辑预审验收
│       └── M2_Sprint16_前端任务_seeding-writer.md  #  种草内容仿写（Sprint 16）
│       └── M2_Sprint24_前端任务_红人工作台UI一致性优化_v1.md  #  红人工作台 UI 一致性优化
│       └── M2_Sprint24_前端任务_开发验收_红人工作台UI一致性优化_v1.md  #  红人工作台 UI 一致性优化验收
│
├── vitest.config.ts                   # Vitest 测试配置
├── vite.config.ts                     # Vite 构建配置
├── package.json                       # 依赖 + 脚本
└── tsconfig.json                      # TypeScript 配置
```

---

## 文档存储结构

```
frontend/docs/
├── 前端规范.md    前端唯一规范文档（设计 Token / CSS 组件 / 路由 / 改动纪律）
│                → 所有前端开发开始前必读
├── base/        前端基础文档
│                → MCN_M1_Base_Frontend.md：页面清单、路由结构、组件规范
└── tasks/       任务单 + 验收文档
                 → 新功能、BugFix、优化都放这里
                 → 迭代按 vN 递增新建，不覆盖原文档
                 → 验收文档与任务单同目录，文件名带「开发验收」
```

### 命名规范

```
任务文档：    Mx_Sprintxx_{功能名}[_vN[_迭代类型]]
验收文档：    Mx_Sprintxx_前端任务_开发验收_{功能名}_vN.md
```

- **迭代类型**（v2 起）：`新增功能` / `修改需求` / `修复Bug`
- **版本号**：一条线累加（v1 → v2 → v3），不重复

---

## 关键约定

- 所有 API 调用走 `src/api/request.ts`，禁止裸用 fetch
- 所有样式值引用 CSS 变量，禁止硬编码
- 运营端新功能入口放「创作中心」
- 管理端新配置放「工具配置」→「功能配置」
- 页面组件命名：`XxxPage.tsx`，放 `src/pages/{角色}/`
- 测试运行：`npx vitest run --coverage`

---

## 测试体系

### 单元/组件测试（Vitest）

- **位置**：`src/__tests__/`（与源码同仓，按业务域组织）
- **配置**：`vitest.config.ts`（jsdom + setupFiles=`src/test/setup.ts`）
- **运行**：`npx vitest run --coverage`
- **覆盖**：180 个用例，覆盖所有 page / api / store / hooks

### E2E 测试（Playwright，Sprint 16 v3 引入）

- **位置**：`tests/e2e/`（vitest 通过 `exclude: ['tests/e2e/**']` 不收集）
- **配置**：`playwright.config.ts`
  - `webServer` 自动起 dev server（5175，`strictPort: true`）
  - `channel: 'chrome'` 用系统 Chrome，绕开 Playwright chromium CDN 下载
  - `workers: 1` 串行执行（避免并发污染数据库）
- **helper**：
  - `helpers/auth.ts` — `loginAsAdmin` 走真实 UI 登录（绕过 zustand 模块作用域 init 时序问题）
  - `helpers/api-mock.ts` — mock OSS / 卖点流 / 抖音 / ASR / 结构分析流 / 对话流
- **运行**：需后端 `uvicorn app.main:app --port 8000` 在跑，然后 `npx playwright test`
- **当前覆盖**：smoke 3 个 + seeding-writer 关键路径 6 个 = 9 个

### 端口约定

- **5175**：前端 dev server（`vite.config.ts` 固定 `strictPort`）
- **8000**：后端 API（`backend/.env` 的 `CORS_ORIGINS` 已含 5175）
