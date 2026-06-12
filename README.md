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
- **AI 服务**：多服务商 Key 池（云雾/硅基流动/GLM），并发调度，僵尸锁自动清理，模型管理，使用统计
- **TikHub 管理**：独立 Key 池，端点统计，用户排行，调用日志
- **红人入驻问卷**：运营生成分享链接 → 红人填写 24 道题 → AI 生成入驻报告 → 下载 Word/PDF
- **人格定位**：抖音号解析 + 文件上传 → AI 生成人格档案 + 内容规划 → 导出 Word → 历史管理
- **对标分析助手**：抖音号解析 → 自动抓取 TOP10/近30天视频 → AI 生成人格档案 + 内容规划 → 导出 Word → 历史管理
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
│   │   ├── models/                    #     SQLAlchemy ORM 模型（14 个文件，21 个模型类）
│   │   ├── routers/                   #     API 路由（按角色分文件，23 个）
│   │   ├── schemas/                   #     Pydantic schema
│   │   └── services/                  #     业务逻辑服务
│   ├── docs/                          #   后端文档
│   │   ├── README.md                  #     架构说明 + 文档索引
│   │   ├── base/                      #     接口契约 + 数据库契约
│   │   ├── tasks/                     #     任务单 + 验收文档（22 个）
│   │   └── tests/                     #     测试报告 + 测试任务
│   ├── tests/                         #   测试代码
│   │   ├── unit/                      #     单元测试
│   │   ├── integration/               #     集成测试
│   │   ├── e2e/                       #     端到端测试
│   │   ├── concurrent/                #     并发隔离测试
│   │   └── intake/                    #     入驻问卷专项测试
│   ├── migrations/                    #   SQL 迁移脚本（001 ~ 013）
│   └── scripts/                       #   工具脚本（init_db.sh、init_test_db.sh、run_coverage.py）
│
├── frontend/                          ← 前端（React + Vite）
│   ├── src/                           #   源码
│   │   ├── api/                       #     API 调用层（18 个模块）
│   │   ├── layouts/                   #     布局组件（Admin / Operator / Auth）
│   │   ├── pages/                     #     页面组件（admin 14 个 / operator 9 个 / auth 2 个 / intake 1 个）
│   │   ├── routes/                    #     路由守卫
│   │   ├── store/                     #     Zustand 状态管理
│   │   ├── styles/                    #     CSS 变量 + 全局样式
│   │   ├── types/                     #     TypeScript 类型定义（13 个模块）
│   │   └── __tests__/                 #     前端测试
│   ├── docs/                          #   前端文档
│   │   ├── README.md                  #     架构说明 + 文档索引
│   │   ├── 前端规范.md                  #     前端唯一规范文档
│   │   ├── base/                      #     前端基础文档
│   │   └── tasks/                     #     任务单 + 验收文档（24 个）
│   ├── vitest.config.ts               #   Vitest 测试配置
│   └── vite.config.ts                 #   Vite 构建配置
│
├── deploy/                            ← 运维部署
│   ├── docs/                          #   运维文档
│   │   ├── README.md                  #     部署架构说明 + 文档索引
│   │   └── tasks/                     #     任务单 + 验收文档（6 个）
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

# 一键初始化数据库（Mac/Linux）
bash scripts/init_db.sh   # 默认 postgres/admin123/mcn_m1

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

参考 `deploy/docs/tasks/M2_测试服首次部署.md`，支持 PM2 + Nginx 生产部署。

## 环境变量说明

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | PostgreSQL 连接串，格式：`postgresql+asyncpg://user:pass@host/db` |
| `JWT_SECRET` | JWT 签名密钥，建议 32 位以上随机字符串 |
| `ENCRYPTION_KEY` | 数据加密密钥，32 位随机字符串 |
| `INITIAL_ADMIN_USERNAME` | 初始管理员账号（首次启动自动创建） |
| `INITIAL_ADMIN_PASSWORD` | 初始管理员密码 |
| `LLM_API_KEY` | AI 服务 API Key（也可在管理后台配置 Key Pool） |
| `TIKHUB_API_KEY` | TikHub API Key |
