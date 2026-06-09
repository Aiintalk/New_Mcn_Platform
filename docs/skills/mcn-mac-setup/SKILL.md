---
name: mcn-mac-setup
description: Mac 本地环境搭建 skill，用于将 MCN Platform（https://github.com/Aiintalk/New_Mcn_Platform）克隆并运行在 Mac 上。当用户提到"Mac 启动"、"本地部署"、"搭建 MCN 环境"、"Mac 跑起来"等时触发。流程：检查环境 → 评估安装时间 → 用户确认 → 执行安装 → 启动服务。
---

# MCN Platform Mac 环境搭建

## 流程概览

**必须按以下顺序执行，不得跳步：**

1. 检查本地环境
2. 输出缺失项 + 预计安装时间，等待用户确认
3. 用户确认后安装缺失依赖
4. 克隆代码（如未克隆）
5. 配置环境变量
6. 执行数据库迁移
7. 启动后端 + 前端

---

## 第 1 步 — 检查本地环境

并行运行以下检查命令，收集结果后一次性汇报：

```bash
# Homebrew
which brew && brew --version | head -1

# Python 3.10+
python3 --version 2>/dev/null || echo "NOT FOUND"
which python3.10 2>/dev/null || echo "python3.10 NOT FOUND"

# Node.js 18+
node --version 2>/dev/null || echo "NOT FOUND"

# PostgreSQL
psql --version 2>/dev/null || echo "NOT FOUND"
brew services list | grep postgresql 2>/dev/null || echo "pg service unknown"

# Git
git --version 2>/dev/null || echo "NOT FOUND"

# 项目目录
ls ~/New_Mcn_Platform 2>/dev/null && echo "REPO EXISTS" || echo "REPO NOT FOUND"
```

---

## 第 2 步 — 评估并告知用户

根据检查结果，生成缺失项清单和预计时间，格式如下：

```
环境检查结果：

已安装：
✅ Git 2.x
✅ Node.js 22.x

需要安装：
❌ Homebrew（约 5 分钟）
❌ Python 3.10（约 3 分钟）
❌ PostgreSQL 15（约 2 分钟）

预计总时间：约 10 分钟
网络状况会影响实际时间。

确认后开始安装？
```

**等待用户明确回复"确认"或"开始"后再继续，不得自动跳过。**

---

## 第 3 步 — 安装缺失依赖

按缺失项逐一安装，安装完成后输出确认：

```bash
# 安装 Homebrew（如缺失）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 安装 Python 3.10（如缺失）
brew install python@3.10

# 安装 Node.js（如缺失）
brew install node

# 安装 PostgreSQL 15（如缺失）
brew install postgresql@15
echo 'export PATH="/opt/homebrew/opt/postgresql@15/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
brew services start postgresql@15
```

---

## 第 4 步 — 克隆代码

```bash
cd ~
git clone https://github.com/Aiintalk/New_Mcn_Platform.git
cd New_Mcn_Platform
```

如目录已存在则跳过克隆，进入目录后执行 `git pull` 更新。

---

## 第 5 步 — 配置后端环境变量

```bash
cd ~/New_Mcn_Platform/backend
cp .env.example .env
```

**提示用户编辑 `.env`，必填项：**

| 字段 | 说明 |
|------|------|
| `DATABASE_URL` | `postgresql+asyncpg://mcn_user:密码@localhost:5432/mcn_db` |
| `JWT_SECRET` | 随机 32 位字符串（可用 `openssl rand -hex 32` 生成） |
| `ENCRYPTION_KEY` | 另一个 32 位字符串 |
| `INITIAL_ADMIN_PASSWORD` | 自定义管理员密码 |

`LLM_API_KEY` 和 `TIKHUB_API_KEY` 可先填 `placeholder`，后台配置。

---

## 第 6 步 — 创建数据库 + 执行迁移

```bash
# 创建数据库用户和库
psql postgres << 'EOF'
CREATE USER mcn_user WITH PASSWORD '与.env一致的密码';
CREATE DATABASE mcn_db OWNER mcn_user;
GRANT ALL PRIVILEGES ON DATABASE mcn_db TO mcn_user;
EOF

# 执行迁移（001~007）
cd ~/New_Mcn_Platform/backend
for f in migrations/001_init.sql \
          migrations/002_kols_add_owner.sql \
          migrations/003_ai_tables.sql \
          migrations/004_credentials_test_fields.sql \
          migrations/005_ai_models_test_fields.sql \
          migrations/006_kol_intake.sql \
          migrations/007_kol_intake_operator_sessions.sql; do
  echo "执行 $f ..."
  PGPASSWORD=密码 psql -h localhost -U mcn_user -d mcn_db -f $f
done
```

---

## 第 7 步 — 启动服务

**后端（终端 1）：**
```bash
cd ~/New_Mcn_Platform/backend
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**前端（终端 2）：**
```bash
cd ~/New_Mcn_Platform/frontend
cp .env.example .env
# .env 内容：VITE_API_BASE_URL=http://localhost:8000
npm install
npm run dev
```

浏览器打开 `http://localhost:5173`，用管理员账号登录。

---

## 常见问题

| 问题 | 解法 |
|------|------|
| `psql: command not found` | `export PATH="/opt/homebrew/opt/postgresql@15/bin:$PATH"` |
| PostgreSQL 连接拒绝 | `brew services start postgresql@15` |
| pip install 失败 | 确认虚拟环境已激活：`source .venv/bin/activate` |
| 端口 8000 被占用 | `lsof -i :8000` 找到进程 kill 掉 |
| Apple Silicon (M1/M2/M3) | Homebrew 路径是 `/opt/homebrew`，Intel 是 `/usr/local` |
