# MCN Platform

MCN 红人孵化管理平台，支持多用户、多并发场景，集成 AI 能力、TikHub 数据抓取、红人入驻问卷等核心功能模块。

## 技术栈

| 端 | 技术 |
|----|------|
| 后端 | Python 3.10 · FastAPI · SQLAlchemy (asyncpg) · PostgreSQL 15 |
| 前端 | React 18 · Vite · TypeScript · Ant Design 5.x |
| 部署 | Nginx · PM2 · Ubuntu |

## 功能模块

- **用户管理**：管理员 / 运营角色，JWT 鉴权，密码策略
- **红人管理（KOL）**：TikHub 数据抓取，粉丝画像，红人档案
- **AI 服务**：多服务商 Key 池，并发调度，模型管理，使用统计
- **红人入驻问卷**：运营生成分享链接 → 红人填写 24 道题 → AI 生成入驻报告 → 下载 Word/PDF
- **运营首页**：数据概览，产出趋势，常用工具
- **产出中心**：AI 产出记录，入驻报告管理，分享链接管理

## 目录结构

```
mcn-platform/
├── backend/          # FastAPI 后端
│   ├── app/
│   │   ├── routers/  # API 路由
│   │   ├── models/   # 数据库模型
│   │   ├── services/ # 业务逻辑
│   │   ├── adapters/ # 外部服务适配器（AI、TikHub、OSS）
│   │   └── core/     # 配置、数据库、安全
│   ├── migrations/   # SQL 迁移脚本（001~007）
│   └── tests/        # 测试用例
├── frontend/         # React 前端
│   └── src/
│       ├── pages/    # 页面组件
│       ├── api/      # API 调用层
│       ├── store/    # Zustand 状态管理
│       └── types/    # TypeScript 类型定义
├── deploy/           # 部署配置（Nginx）
└── docs/             # 项目文档和任务单
```

## 快速开始

### 环境要求

- Python 3.10+
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

# 执行数据库迁移
psql -U postgres -d mcn_db -f migrations/001_init.sql
# ... 依次执行到 007

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

## 部署

参考 `docs/tasks/deploy/M2_测试服首次部署.md`，支持 PM2 + Nginx 生产部署。

## 测试

```bash
cd backend
source .venv/bin/activate

# 功能测试 + 并发测试
pytest tests/intake/ -v
```

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
