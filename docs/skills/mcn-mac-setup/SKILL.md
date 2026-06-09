---
name: mcn-mac-setup
description: 在 Mac 上自动完成 MCN Platform 的本地环境检查、代码获取、依赖安装与启动。当用户说"帮我把 MCN 跑起来""本地启动 MCN""搭建 MCN 环境""MCN 装不上""MCN 跑不起来""Mac 部署 MCN"等时触发。由 Claude Code 在其当前启动目录下自动执行所有检查与命令，用户无需手动敲命令；仅在需要安装依赖、设定密码、启动服务等关键决策点停下来征求用户确认。
---

# MCN Platform Mac 自动搭建（Claude Code 版）

仓库地址：`https://github.com/Aiintalk/New_Mcn_Platform.git`

## 给执行者（Claude Code）的关键约定 — 务必先读

1. **项目目录**：固定为 Claude Code 当前启动目录下的 `New_Mcn_Platform/`。
   由于每个 bash 代码块通常是独立 shell 进程、变量不跨块保留，**本 skill 的每个 bash 块开头都重新定义一次 `PROJECT_DIR`**，请照做，不要假设上一个块的变量还在。
2. **联网前必查代理**：任何 `git clone` / `git fetch` / `brew install` / `npm install` / `pip install` 之前，**都先跑一次「网络连通性检查」**（见阶段二）。不通则停下来提醒用户开 FlClash，不要硬着头皮下载。
3. **失败即停**：任一命令失败（非零退出、报错），**立即停止后续步骤，把错误原样报告用户**，不要在前一步没成功的情况下继续往下跑。
4. **副作用步骤先确认**：只读检查可直接跑；安装依赖、建库、写 .env、启动服务等先汇报、等用户确认。
5. **占位符**：`<DB_PASSWORD>` 表示"用户设定的数据库密码"，执行时替换为真实值；该值必须与 `.env` 的 `DATABASE_URL` 中的密码一致。

确认当前目录：

```bash
PROJECT_DIR="$(pwd)/New_Mcn_Platform"
echo "项目目录：$PROJECT_DIR"
```

---

## 阶段一 — 检查代码仓库与版本一致性（只读，直接执行）

### 1a. 是否已有项目

```bash
PROJECT_DIR="$(pwd)/New_Mcn_Platform"
if [ -d "$PROJECT_DIR/.git" ]; then echo "REPO_EXISTS"; else echo "REPO_MISSING"; fi
```

### 1b. 已存在 → 检查与远程版本是否一致（git fetch 需联网，先确认网络）

```bash
PROJECT_DIR="$(pwd)/New_Mcn_Platform"
cd "$PROJECT_DIR" || { echo "ERR: 进不去项目目录"; exit 1; }
git fetch origin || { echo "ERR: git fetch 失败（检查网络/代理）"; exit 1; }

LOCAL=$(git rev-parse @)
REMOTE=$(git rev-parse @{u} 2>/dev/null)

if [ -z "$REMOTE" ]; then
  echo "NO_UPSTREAM"            # 无跟踪的远程分支，需人工确认
elif [ "$LOCAL" = "$REMOTE" ]; then
  echo "VERSION_SYNCED"         # 已最新
else
  echo "VERSION_BEHIND"         # 落后于远程
fi

# 工作区是否干净（用字符串非空判断，避免误报）
if [ -n "$(git status --porcelain)" ]; then
  echo "HAS_LOCAL_CHANGES"
else
  echo "CLEAN"
fi
```

处理建议：
- `VERSION_SYNCED` → 跳过，进入阶段二。
- `VERSION_BEHIND` 且 `CLEAN` → 征得用户同意后 `git pull` 同步。
- `VERSION_BEHIND` 且 `HAS_LOCAL_CHANGES` → **不要自动 pull**，告知用户本地有未提交改动，询问先 `git stash` 再更新还是保持现状。
- `NO_UPSTREAM` → 告知用户，等待指示。

### 1c. 不存在 → 在阶段四克隆（先过阶段二代理检查）

---

## 阶段二 — 检查本地开发环境

### 环境检查（只读，直接执行）

```bash
git --version 2>/dev/null || echo "GIT_MISSING"
brew --version 2>/dev/null | head -1 || echo "BREW_MISSING"

# Python：3.10 或 3.11 任一即可
( python3.11 --version 2>/dev/null || python3.10 --version 2>/dev/null ) || echo "PYTHON_3.10_OR_3.11_MISSING"

node --version 2>/dev/null || echo "NODE_MISSING"
psql --version 2>/dev/null || echo "PG_MISSING"

# PostgreSQL 服务是否「正在运行」（精确判断 started）
if brew services list 2>/dev/null | grep -i postgresql | grep -q started; then
  echo "PG_SERVICE_RUNNING"
else
  echo "PG_SERVICE_NOT_RUNNING"
fi
```

> Python 判定：有 `python3.10` 或 `python3.11` 任一即通过。建 venv 时优先 3.11，没有用 3.10。

### 网络连通性检查（联网下载前必跑）

> 触发时机：`git clone` / `git fetch` / `brew install` / `npm install` / `pip install` 之前都先跑这段。已具备、无需联网的步骤跳过。
> 用户代理软件为 **FlClash**，端口可能非默认，故用「能否访问外网」判断，不写死端口。

```bash
if curl -sI --max-time 5 https://github.com >/dev/null 2>&1; then
  echo "NET_GITHUB_OK"
else
  echo "NET_GITHUB_BLOCKED"
fi
echo "http_proxy=${http_proxy:-未设置} https_proxy=${https_proxy:-未设置}"
```

处理：
- 通 → 直接下载。
- 不通 → **停下来提醒用户**：

  > 当前无法正常访问 GitHub / 国外源，`git clone`、`brew/pip/npm` 下载会很慢甚至失败。请打开 **FlClash**，确认已开启「系统代理」或 TUN 模式；若开了仍不通，可能需在终端手动设置代理环境变量（见常见问题）。开好后告诉我，我再继续。
  >
  > 预计耗时：开代理后通常几分钟；不开可能十几分钟或失败。也可自己手动下载安装，装完我帮你复查环境。

  用户处理后，重跑本段确认 `NET_GITHUB_OK` 再继续。

> 注：`pip` 走 pythonhosted、`npm` 走 npm registry，同属国外源，同样依赖代理。若用户习惯国内镜像，可改用镜像源（pip：`-i https://pypi.tuna.tsinghua.edu.cn/simple`；npm：`--registry=https://registry.npmmirror.com`），此时可不依赖代理。

---

## 阶段三 — 汇报结果并征求确认

按实际结果填写后汇报：

```
检查完成：

代码仓库（当前目录下 New_Mcn_Platform/）：
  ✅ 已存在且为最新 / ⬇️ 未找到需克隆 / 🔄 已存在但落后于远程建议更新

运行环境：
  ✅ Git / Node.js / Python(3.10或3.11) / PostgreSQL(服务运行中)
  缺失项：❌ <名称>（未安装，约 X 分钟）

网络：
  ✅ 外网可访问（已走代理） / ⚠️ 外网不可达，需先打开 FlClash

预计总耗时：约 X 分钟（受网络影响）

需要我安装缺失依赖 / 克隆代码并继续吗？
```

**等用户确认后再执行阶段四。任一步失败立即停止并报告。**

---

## 阶段四 — 用户确认后执行（仅做缺失的部分，失败即停）

### 4a. 安装缺失依赖（只装缺的；联网前已确认 NET_GITHUB_OK）

```bash
# Homebrew（缺失时）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
  || { echo "ERR: Homebrew 安装失败"; exit 1; }

# 动态把 brew 加入当前会话 PATH（兼容 Apple Silicon /opt/homebrew 与 Intel /usr/local，不依赖 source ~/.zshrc）
if command -v brew >/dev/null 2>&1; then eval "$(brew shellenv)"; \
elif [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)"; \
elif [ -x /usr/local/bin/brew ]; then eval "$(/usr/local/bin/brew shellenv)"; fi

# Python（本机既无 3.10 也无 3.11 时装 3.11）
brew install python@3.11 || { echo "ERR: Python 安装失败"; exit 1; }

# Node.js（缺失时）
brew install node || { echo "ERR: Node 安装失败"; exit 1; }

# PostgreSQL 15（缺失时）
brew install postgresql@15 || { echo "ERR: PostgreSQL 安装失败"; exit 1; }
export PATH="$(brew --prefix postgresql@15 2>/dev/null)/bin:$PATH"
brew services start postgresql@15
```

> 提醒用户：上面 PATH 仅对当前会话生效。永久生效建议把 `eval "$(brew shellenv)"` 与 postgresql@15 的 bin 路径写入 `~/.zshrc`（首次一次即可）。

### 4b. 克隆代码（联网前已确认 NET_GITHUB_OK）

```bash
PROJECT_DIR="$(pwd)/New_Mcn_Platform"
if [ ! -d "$PROJECT_DIR/.git" ]; then
  git clone https://github.com/Aiintalk/New_Mcn_Platform.git "$PROJECT_DIR" \
    || { echo "ERR: git clone 失败（检查网络/代理）"; exit 1; }
  echo "CLONED"
else
  echo "ALREADY_EXISTS（如需更新见阶段一 1b 的 git pull 建议）"
fi
```

### 4c. 配置后端 .env（首次）

```bash
PROJECT_DIR="$(pwd)/New_Mcn_Platform"
cd "$PROJECT_DIR/backend" || { echo "ERR: 无 backend 目录"; exit 1; }
if [ -f .env ]; then
  echo "ENV_EXISTS"
else
  cp .env.example .env && echo "ENV_CREATED"
fi
```

首次创建 `.env` 时提示用户填写：

| 字段 | 说明 |
|------|------|
| `DATABASE_URL` | `postgresql+asyncpg://mcn_user:<DB_PASSWORD>@localhost:5432/mcn_db` |
| `JWT_SECRET` | `openssl rand -hex 32` 生成 |
| `ENCRYPTION_KEY` | `openssl rand -hex 16` 生成 |
| `INITIAL_ADMIN_PASSWORD` | 自定义管理员登录密码（后端首次启动据此创建初始管理员账号） |

`LLM_API_KEY` / `TIKHUB_API_KEY` 可先填 `placeholder`。
**`DATABASE_URL` 里的密码必须与 4d 创建数据库时设定的 `<DB_PASSWORD>` 完全一致。**

### 4d. 数据库（已有则跳过，新建才设密码）

```bash
if psql postgres -tAc "SELECT 1 FROM pg_database WHERE datname='mcn_db'" 2>/dev/null | grep -q 1; then
  echo "DB_EXISTS"   # 跳过创建，不动用户已有数据
else
  echo "DB_MISSING"  # 需创建
fi
```

若 `DB_MISSING`：**先请用户设定数据库密码 `<DB_PASSWORD>`**（并确认已写入 `.env` 的 `DATABASE_URL`），再创建：

```bash
# 把 <DB_PASSWORD> 替换为用户设定的密码
psql postgres << EOF || { echo "ERR: 建库失败"; exit 1; }
CREATE USER mcn_user WITH PASSWORD '<DB_PASSWORD>';
CREATE DATABASE mcn_db OWNER mcn_user;
GRANT ALL PRIVILEGES ON DATABASE mcn_db TO mcn_user;
EOF
echo "DB_CREATED"
```

### 4e. 数据库迁移（首次；动态遍历，失败即停）

```bash
PROJECT_DIR="$(pwd)/New_Mcn_Platform"
cd "$PROJECT_DIR/backend" || { echo "ERR: 无 backend 目录"; exit 1; }
export PGPASSWORD='<DB_PASSWORD>'   # 用户设定的密码
for f in $(ls migrations/*.sql 2>/dev/null | sort); do
  echo "执行 $f ..."
  psql -h localhost -U mcn_user -d mcn_db -f "$f" \
    || { echo "ERR: 迁移失败于 $f，已停止"; unset PGPASSWORD; exit 1; }
done
unset PGPASSWORD
echo "MIGRATIONS_DONE"
```

### 4f. 安装 Python 依赖（首次或 requirements.txt 更新）

```bash
PROJECT_DIR="$(pwd)/New_Mcn_Platform"
cd "$PROJECT_DIR/backend" || { echo "ERR: 无 backend 目录"; exit 1; }

if command -v python3.11 >/dev/null 2>&1; then PYBIN=python3.11
elif command -v python3.10 >/dev/null 2>&1; then PYBIN=python3.10
else echo "ERR: 未找到 python3.10/3.11，请先完成 4a 安装并刷新 PATH"; exit 1; fi

[ -d .venv ] || "$PYBIN" -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt \
  || { echo "ERR: pip 安装失败（可用代理或国内镜像 -i https://pypi.tuna.tsinghua.edu.cn/simple）"; exit 1; }
echo "PY_DEPS_DONE"
```

### 4g. 安装前端依赖（首次或 package.json 更新）

```bash
PROJECT_DIR="$(pwd)/New_Mcn_Platform"
cd "$PROJECT_DIR/frontend" || { echo "ERR: 无 frontend 目录"; exit 1; }
if [ ! -f .env ]; then
  cp .env.example .env 2>/dev/null || true
  echo "VITE_API_BASE_URL=http://localhost:8000" > .env
fi
npm install \
  || { echo "ERR: npm 安装失败（可用代理或国内镜像 --registry=https://registry.npmmirror.com）"; exit 1; }
echo "FE_DEPS_DONE"
```

---

## 阶段五 — 询问是否启动服务

环境与代码就绪后询问：

```
环境准备完毕！是否现在启动服务？
（需要两个终端窗口分别运行后端和前端）
```

用户确认后，**提示用户在两个终端分别执行**（不自动后台执行，避免进程管理问题）。
把 `<项目路径>` 替换为 Claude Code 当前目录的绝对路径。

**终端 1 — 后端：**
```bash
cd <项目路径>/New_Mcn_Platform/backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000
```

**终端 2 — 前端：**
```bash
cd <项目路径>/New_Mcn_Platform/frontend && npm run dev
```

启动后告知用户：浏览器打开 `http://localhost:5173`，用**管理员账号**登录——用户名通常为 `admin`（以项目实际为准），密码为 `.env` 中设定的 `INITIAL_ADMIN_PASSWORD`。

---

## 常见问题

| 问题 | 解法 |
|------|------|
| `psql: command not found` | `eval "$(brew shellenv)"` 后 `export PATH="$(brew --prefix postgresql@15)/bin:$PATH"` |
| PostgreSQL 连接被拒绝 | `brew services start postgresql@15` |
| 下载 GitHub / brew 很慢或失败 | 打开 FlClash 系统代理 / TUN，确认 `curl -sI https://github.com` 能通后重试 |
| 已开 FlClash 但终端仍不通 | 当前终端手动设置：`export https_proxy=http://127.0.0.1:<FlClash端口> http_proxy=http://127.0.0.1:<同端口>`（端口见 FlClash 设置） |
| pip / npm 慢 | 国内镜像：pip `-i https://pypi.tuna.tsinghua.edu.cn/simple`；npm `--registry=https://registry.npmmirror.com` |
| pip install 失败 | 确认已激活虚拟环境：`source .venv/bin/activate` |
| 端口 8000 被占用 | `lsof -i :8000 \| grep LISTEN` 找到 PID 后 `kill <PID>` |
| 数据库密码连不上 | 确认 `.env` 的 `DATABASE_URL` 密码与建库时设定的 `<DB_PASSWORD>` 完全一致 |
| `$PROJECT_DIR` 为空 / 路径错乱 | 每个命令块开头重新执行 `PROJECT_DIR="$(pwd)/New_Mcn_Platform"` |
| Apple Silicon vs Intel | brew 路径：Apple Silicon `/opt/homebrew`，Intel `/usr/local`；用 `brew --prefix` 自动取更稳 |
