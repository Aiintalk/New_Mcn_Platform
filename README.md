# MCN Platform

MCN 红人孵化管理平台，支持多用户、多并发场景，集成 AI 能力、TikHub 数据抓取、红人入驻问卷、人格定位等核心功能模块。

## 技术栈

| 端 | 技术 |
|----|------|
| 后端 | Python 3.11 · FastAPI · SQLAlchemy (asyncpg) · PostgreSQL 15 |
| 前端 | React 19 · Vite 8 · TypeScript 6 · Ant Design 5.x · Zustand 5 |
| 部署 | Nginx · PM2 · Ubuntu |

## 功能模块

- **用户管理**：管理员 / 运营角色，JWT 鉴权，密码策略
- **红人管理（KOL）**：TikHub 数据抓取，粉丝画像，红人档案
- **外部 KOL 只读 API**：`/api/external/kols` 通过 `X-API-Key` 只读开放红人列表与详情，给其它项目读取 `kols` 表数据，不暴露数据库端口或账号
- **外部录屏主播同步 API**：`/api/external/recording-anchors` 合并开放红人主播与直播对标主播清单，用 `source_type` 区分「红人主播」和「直播对标主播」，内容对标不进入远程录屏系统
- **AI 服务**：多服务商 Key 池（云雾/硅基流动/GLM），并发调度，僵尸锁自动清理，模型管理，使用统计
- **内容分析 Agent 阶段一 + v1.8 飞书适配**：已有内存项目隔离离线内核，以及可注入的飞书只读客户端合同、字段映射、完整分页校验和无内容日报；飞书只提供内容，项目范围/上下文/关系仍由任务配置与正式数据库后续交付。当前无公共 API（应用编程接口）、数据表/迁移、调度、前端、真实飞书凭据联调或真实模型
- **TikHub 管理**：独立 Key 池，端点统计，用户排行，调用日志
- **OSS 对象存储**：阿里云 OSS adapter（上传/下载/删除），独立凭证池，4 张统计卡 + 操作分布饼图 + 7 天趋势折线图 + 3 子 Tab（凭证管理 / 操作统计 / 用户排行）+ 连通性测试
- **ASR 语音识别**：阿里云智能语音交互（录音文件识别 - 异步 API），独立凭证池（AppKey + AccessKey + Region），submit/query 双操作统计，紫色主题 Tab 复刻 OSS 架构，连通性测试用 GetTaskResult probe TaskId（不依赖测试音频）
- **红人入驻问卷**：运营生成分享链接 → 红人填写 24 道题 → AI 生成入驻报告 → 下载 Word/PDF
- **人格定位**：选择正式达人（`kols.id`）+ 当前运营关联入驻资料或上传文件 → AI 生成人格档案 + 内容规划 → 字段级同步确认 → 导出 Word → 按达人保留历史
- **对标分析助手**：抖音号解析 → 自动抓取 TOP10/近30天视频 → AI 生成对标分析报告 → 导出 Word → 历史管理
- **TikTok 脚本仿写**：达人人设 + TikTok 链接 → AI 流式仿写脚本 → 导出 Word
- **产品卖点提取器**：上传产品 Brief + 达人文案 → AI 提炼机制/背书/口碑/产品力四板块极致卖点卡 → 多轮追问 → 历史管理
- **千川脚本复盘**：上传千川脚本（文件/粘贴）+ 投放数据 Excel → AI 流式生成复盘报告 → 保存/导出/复制
- **千川剪辑预审**：上传原版爆款视频 + 我方成片 → 截帧 + 转录 → 多模态 SSE 流式预审 → 导出 Word / 保存报告
- **直播脚本仿写**：选达人 + 上传产品卖点卡 + 对标直播间文案 → AI 流式生成 7 模块开播方案 → 多轮迭代 → 导出 .txt
- **直播间脚本复盘**：上传直播脚本（多场）+ 直播数据 Excel → AI 流式生成复盘报告（话术效果 + 留人转化）→ 保存/导出/复制
- **人设脚本复盘**：上传人设脚本（多视频）+ 可选运营 Excel → AI 流式生成复盘报告（内容质量 / 投放效率）→ 保存/历史管理
- **种草内容仿写**：4 步向导（选达人 + 素材库 / 产品信息 / 对标验证 / 种草仿写）→ 抖音链接 ASR 转录 + 结构拆解 → AI 多轮迭代生成种草脚本 → 保存/导出 .txt/.docx。产品库 + 素材库公司共享，6 个 Prompt + 双模型可配置（Sprint 16）
- **素材库**：红人参考素材中枢（迁移自旧架构 Ai_Toolbox/material-library-web），保留 6 类参考素材和档案只读摘要；人格档案、内容规划的正式编辑统一跳转红人工作台（Sprint 25）
- **红人工作台**：运营端红人统一入口（`/kol-hub`）。每个正式达人以 `kols.id` 进入独立工作台；“人物档案”统一编辑人格档案、内容规划、基本身份、真实经历、关系网、独家经历和其他补充七项内容，供文案、直播、复盘等下游复用（Sprint 25）
- **红人工作台旧版核心流程还原**：保留新版视觉和额外工具，恢复千川仿写闭环、价值观四步仿写、直播脚本上下文、六类素材文档/视频、逐份复盘，以及原片与剪辑成片的完整视频预审；TikTok 工具不在本轮范围。完整视频预审使用统一配置中的 Gemini（谷歌视频模型）能力，未配置时明确失败、不降级为关键帧。
- **数据库迁移链路**：既有数据库通过 `schema_migrations` 账本按文件顺序执行未完成迁移；包含校验和、单文件事务和并发锁，已执行 seed 不重放。首次接管旧库必须先备份并显式核对基线。
- **运营首页**：数据概览，产出趋势，常用工具
- **产出中心**：AI 产出记录，入驻报告管理，分享链接管理

## 目录结构

> 原则：文档跟着代码走（就近原则）。开发某端时，不出该端目录即可找到所有相关文档。

```
mcn-platform/
├── CLAUDE.md                          ← Claude Code 项目规范（自动加载）
├── README.md                          ← 本文件
│
├── backend/                           ← 后端（FastAPI）
│   ├── app/                           #   源码
│   │   ├── adapters/                  #     外部服务适配器（AI、TikHub、OSS、ASR）
│   │   ├── core/                      #     配置、数据库、安全、响应封装
│   │   ├── middlewares/               #     JWT 鉴权中间件
│   │   ├── models/                    #     SQLAlchemy ORM 模型（38 个文件）
│   │   ├── routers/                   #     API 路由（按角色分文件，67 个）
│   │   ├── schemas/                   #     Pydantic schema
│   │   └── services/                  #     业务逻辑服务
│   │       └── content_analysis/      #       内容分析 Agent 阶段一离线内核与飞书只读适配
│   ├── docs/                          #   后端文档
│   │   ├── README.md                  #     架构说明 + 文档索引
│   │   ├── base/                      #     接口契约 + 数据库契约
│   │   ├── tasks/                     #     任务单 + 验收文档（62 个）
│   │   └── tests/                     #     测试报告 + 测试任务
│   ├── tests/                         #   测试代码
│   │   ├── unit/                      #     单元测试
│   │   ├── integration/               #     集成测试
│   │   ├── e2e/                       #     端到端测试
│   │   ├── concurrent/                #     并发隔离测试
│   │   └── intake/                    #     入驻问卷专项测试
│   ├── migrations/                    #   SQL 迁移脚本（53 个）
│   └── scripts/                       #   工具脚本（init_db.sh、init_test_db.sh、run_coverage.py）
│
├── frontend/                          ← 前端（React + Vite）
│   ├── src/                           #   源码
│   │   ├── api/                       #     API 调用层（33 个模块）
│   │   ├── layouts/                   #     布局组件（Admin / Operator / Auth）
│   │   ├── pages/                     #     页面组件（admin 22 个 / operator 19 个 / auth 2 个 / intake 1 个）
│   │   ├── routes/                    #     路由守卫
│   │   ├── store/                     #     Zustand 状态管理
│   │   ├── styles/                    #     CSS 变量 + 全局样式
│   │   ├── types/                     #     TypeScript 类型定义（23 个模块）
│   │   └── __tests__/                 #     前端测试
│   ├── docs/                          #   前端文档
│   │   ├── README.md                  #     架构说明 + 文档索引
│   │   ├── 前端规范.md                  #     前端唯一规范文档
│   │   ├── base/                      #     前端基础文档
│   │   └── tasks/                     #     任务单 + 验收文档（44 个）
│   ├── vitest.config.ts               #   Vitest 测试配置
│   └── vite.config.ts                 #   Vite 构建配置
│
├── deploy/                            ← 运维部署
│   ├── docs/                          #   运维文档
│   │   ├── README.md                  #     部署架构说明 + 文档索引
│   │   └── tasks/                     #     任务单 + 验收文档（8 个）
│   ├── scripts/                       #   启停脚本、健康检查
│   └── nginx/                         #   Nginx 配置
│
└── docs/                              ← 跨端共享文档
    ├── design/                        #   设计方案（系统设计、UI 规范、部署评估）
    ├── standards/                     #   编码标准、测试策略、Code Review 标准
    ├── base/                          #   跨端契约（验收标准、权限定义）
    ├── pm/                            #   PM 状态文档
    └── tests/                         #   跨端测试报告
```

### 文档组织规则

| 目录 | 内容 | 说明 |
|------|------|------|
| `backend/docs/` | 后端全部文档 | 接口契约、数据库契约、任务单、测试报告 |
| `frontend/docs/` | 前端全部文档 | 前端规范、任务单 |
| `deploy/docs/` | 运维全部文档 | 部署任务单 |
| `docs/` | 跨端共享 | 设计方案、编码标准、PM 状态 |

每个端的 `docs/README.md` 都有该端完整的架构说明和文档索引。

## 最近改动

- **2026-09-03 · Sprint27**：内容分析 Agent 阶段一离线内核返修后专项测试 313 通过，专项覆盖率 92.2%；最新完整门禁 2326 通过、1 跳过、0 失败、0 错误，整体覆盖率 80.4%。阶段一纯离线切片已通过主产品经理第二轮审核和用户产品验收，并获授权封存到独立开发分支；未形成可用的生产入口。

## 快速开始

### 环境要求

- Python 3.11+（asyncpg 在 Windows 上需要 3.11，不支持 3.14+）
- Node.js 18+
- PostgreSQL 15+

### 后端

```bash
cd backend

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，填写数据库连接、JWT_SECRET 等

# 按账本执行数据库迁移（Mac/Linux）
# 既有库首次纳管必须先按 deploy/README.md 备份、核对并登记基线
bash ../deploy/scripts/init-db.sh

# 一键初始化测试数据库（只需创建空库，表由 conftest.py 自动建删）
bash scripts/init_test_db.sh   # 默认 postgres/admin123/mcn_test

# 启动服务
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd frontend

# 安装依赖
npm install

# 配置环境变量
cp .env.example .env
# 编辑 .env，设置 VITE_API_BASE_URL

# 开发模式
npm run dev

# 构建生产版本
npm run build
```

## 测试

### 后端测试

```bash
cd backend
source .venv/bin/activate  # Windows: .venv311\Scripts\activate

# 只跑单元测试（不需要数据库）
pytest tests/unit/ -v

# 只跑集成测试（需要 PostgreSQL mcn_test 库）
pytest tests/integration/ -v

# 单元 + 集成（覆盖率门禁范围）
pytest tests/unit/ tests/integration/ -v --cov=app --cov-report=term-missing

# 覆盖率门禁（分层达标检查）
python scripts/run_coverage.py --gate
```

> **注意**：`tests/intake/` 和 `tests/concurrent/` 是 E2E 级别测试，需要真实运行的服务器，不纳入 CI 覆盖率统计。

### 前端测试

```bash
cd frontend

# 运行测试
npx vitest run

# 运行测试 + 覆盖率
npx vitest run --coverage

# 监听模式
npx vitest
```

## 部署

参考 `deploy/README.md`（部署架构 + §7 常见问题排查 6 个案例：CORS / 端口占用 / 502 / antd React 19 / ERR_TOO_MANY_REDIRECTS / AI 返回空）和 `deploy/docs/tasks/M2_测试服首次部署.md`，支持 PM2 + Nginx 生产部署。

### 部署侧关键优化（M2 阶段）

- 前端路由懒加载（`React.lazy()`），首屏 JS 从 ~2.2MB 降到 ~90KB（gzip）
- Nginx `gzip_types` 含 `application/javascript`，传输再压缩 60-80%
- FastAPI `redirect_slashes=False` + Nginx rewrite 解决 `ERR_TOO_MANY_REDIRECTS`
- PDF 生成跨平台字体（Linux 需 `apt install fonts-wqy-microhei`）

## 环境变量说明

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | PostgreSQL 连接串，格式：`postgresql+asyncpg://user:pass@host/db` |
| `JWT_SECRET` | JWT 签名密钥，建议 32 位以上随机字符串 |
| `ENCRYPTION_KEY` | 数据加密密钥，32 位随机字符串 |
| `INITIAL_ADMIN_USERNAME` | 初始管理员账号（首次启动自动创建） |
| `INITIAL_ADMIN_PASSWORD` | 初始管理员密码 |
| `EXTERNAL_KOLS_API_KEY` | 外部 KOL 只读 API / 外部录屏主播同步 API 密钥，用于 `X-API-Key` 鉴权 |
| `LLM_API_KEY` | AI 服务 API Key（也可在管理后台配置 Key Pool） |
| `TIKHUB_API_KEY` | TikHub API Key |
