---
name: mcn-mac-setup
description: 自动完成 MCN Platform 的 Mac 本地环境搭建与启动。当用户说"帮我把 MCN 跑起来"、"本地启动 MCN"、"搭建 MCN 环境"、"Mac 部署"等时触发。AI 自动执行所有检查和安装步骤，无需用户手动运行命令。
---

# MCN Platform Mac 自动搭建

仓库地址：https://github.com/Aiintalk/New_Mcn_Platform.git
本地目录：`~/New_Mcn_Platform`

---

## 执行流程

### 阶段一 — 并行检查所有环境（立即执行，无需询问）

同时运行以下所有检查：

```bash
# 1. 代码仓库
ls ~/New_Mcn_Platform 2>/dev/null && echo "REPO_EXISTS" || echo "REPO_MISSING"

# 2. Homebrew
brew --version 2>/dev/null | head -1 || echo "BREW_MISSING"

# 3. Python
python3.10 --version 2>/dev/null || python3 --version 2>/dev/null || echo "PYTHON_MISSING"

# 4. Node.js
node --version 2>/dev/null || echo "NODE_MISSING"

# 5. PostgreSQL
psql --version 2>/dev/null || echo "PG_MISSING"
brew services list 2>/dev/null | grep postgresql || echo "PG_SERVICE_UNKNOWN"

# 6. Git
git --version 2>/dev/null || echo "GIT_MISSING"
```

---

### 阶段二 — 汇报检查结果，评估下载时间

根据检查结果，按以下格式向用户汇报：

```
环境检查完成：

代码仓库：
  ✅ 已存在 ~/New_Mcn_Platform（无需下载）
  或
  ⬇️ 未找到，需要从 GitHub 克隆（网络正常约 1-2 分钟）

运行环境：
  ✅ Git 2.x
  ✅ Node.js 22.x
  ✅ Python 3.11
  ✅ PostgreSQL 15（服务运行中）
  或对缺失项显示：
  ❌ Homebrew（未安装，约 5 分钟）
  ❌ Python 3.10（未安装，约 3 分钟）
  ❌ PostgreSQL 15（未安装，约 2 分钟）

预计总耗时：约 X 分钟（网络状况会影响实际时间）
全部就绪，无需安装任何依赖。（如果全部已装）

需要安装缺失依赖并启动服务吗？
```

**等待用户确认后再继续。**

---

### 阶段三 — 用户确认后执行（按需）

#### 3a. 安装缺失依赖（只安装缺失的，已有的跳过）

```bash
# Homebrew（缺失时）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Python 3.10（缺失时）
brew install python@3.10

# Node.js（缺失时）
brew install node

# PostgreSQL 15（缺失时）
brew install postgresql@15
echo 'export PATH="/opt/homebrew/opt/postgresql@15/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
brew services start postgresql@15
```

#### 3b. 克隆代码（仓库不存在时）

```bash
cd ~
git clone https://github.com/Aiintalk/New_Mcn_Platform.git
```

仓库已存在时执行：
```bash
cd ~/New_Mcn_Platform
git pull
```

#### 3c. 检查并配置 .env（首次）

```bash
cd ~/New_Mcn_Platform/backend
[ -f .env ] && echo "ENV_EXISTS" || cp .env.example .env && echo "ENV_CREATED"
```

如果是首次创建 `.env`，提示用户填写以下必填项后再继续：

| 字段 | 说明 |
|------|------|
| `DATABASE_URL` | `postgresql+asyncpg://mcn_user:密码@localhost:5432/mcn_db` |
| `JWT_SECRET` | `openssl rand -hex 32` 生成 |
| `ENCRYPTION_KEY` | `openssl rand -hex 16` 生成 |
| `INITIAL_ADMIN_PASSWORD` | 自定义管理员密码 |

`LLM_API_KEY` / `TIKHUB_API_KEY` 可先填 `placeholder`。

#### 3d. 创建数据库（首次，库不存在时）

```bash
psql postgres -c "\l" | grep mcn_db || psql postgres << 'EOF'
CREATE USER mcn_user WITH PASSWORD 'mcn_password';
CREATE DATABASE mcn_db OWNER mcn_user;
GRANT ALL PRIVILEGES ON DATABASE mcn_db TO mcn_user;
EOF
```

#### 3e. 执行数据库迁移（首次）

```bash
cd ~/New_Mcn_Platform/backend
for f in migrations/001_init.sql \
          migrations/002_kols_add_owner.sql \
          migrations/003_ai_tables.sql \
          migrations/004_credentials_test_fields.sql \
          migrations/005_ai_models_test_fields.sql \
          migrations/006_kol_intake.sql \
          migrations/007_kol_intake_operator_sessions.sql; do
  echo "执行 $f ..."
  PGPASSWORD=mcn_password psql -h localhost -U mcn_user -d mcn_db -f $f
done
```

#### 3f. 安装 Python 依赖（首次或 requirements.txt 有更新）

```bash
cd ~/New_Mcn_Platform/backend
[ -d .venv ] || python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### 3g. 安装前端依赖（首次或 package.json 有更新）

```bash
cd ~/New_Mcn_Platform/frontend
[ -f .env ] || (cp .env.example .env && echo "VITE_API_BASE_URL=http://localhost:8000" > .env)
npm install
```

---

### 阶段四 — 询问是否启动服务

完成所有安装后询问：

```
环境准备完毕！是否现在启动服务？
（需要两个终端窗口分别运行后端和前端）
```

用户确认后输出启动命令，**提示用户在两个终端分别执行**（不要自动后台执行，避免进程管理问题）：

**终端 1 — 后端：**
```bash
cd ~/New_Mcn_Platform/backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000
```

**终端 2 — 前端：**
```bash
cd ~/New_Mcn_Platform/frontend && npm run dev
```

启动后告知：浏览器打开 `http://localhost:5173`，用管理员账号登录。

---

## 常见问题

| 问题 | 解法 |
|------|------|
| `psql: command not found` | `export PATH="/opt/homebrew/opt/postgresql@15/bin:$PATH"` |
| PostgreSQL 连接被拒绝 | `brew services start postgresql@15` |
| pip install 失败 | 确认已激活虚拟环境：`source .venv/bin/activate` |
| 端口 8000 被占用 | `lsof -i :8000 \| grep LISTEN` 找到 PID 后 `kill <PID>` |
| Apple Silicon (M1/M2/M3) | Homebrew 路径是 `/opt/homebrew`，Intel 是 `/usr/local` |
