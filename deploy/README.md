# MCN 内容工作台 M1 — 运维部署手册

> 维护者：MCN_DevOps_Agent  
> 最后更新：2026-06-05  
> 对应版本：M1 Sprint 1

---

## 目录

- [1. 环境要求](#1-环境要求)
- [2. 本地开发启动步骤](#2-本地开发启动步骤)
- [2.5 数据库环境（本地开发）](#25-数据库环境本地开发)
- [3. 测试服部署步骤](#3-测试服部署步骤预留)
- [4. 健康检查](#4-健康检查)
- [5. 回滚方式](#5-回滚方式)
- [6. 目录结构说明](#6-目录结构说明)
- [7. 常见问题排查](#7-常见问题排查)

---

## 1. 环境要求

| 组件 | 版本要求 | 说明 |
|---|---|---|
| Python | 3.11+ | 后端运行时 |
| Node.js | 20.x (LTS) | 前端构建 & PM2 |
| PostgreSQL | 14+ | 主数据库，仅绑 127.0.0.1 |
| Nginx | 1.18+ | 反代 & 静态资源 |
| PM2 | latest | 后端进程守护 |
| Redis | 6+ | 可选，任务队列扩容时启用 |

> **注意：** PostgreSQL 必须仅绑定 `127.0.0.1`，禁止对外暴露。

### 1.1 安装基础依赖（Ubuntu 22.04）

```bash
sudo apt update && sudo apt install -y nginx postgresql redis-server python3.11 python3.11-venv
sudo npm i -g pm2
```

### 1.2 PostgreSQL 内存收敛（小内存服务器关键）

编辑 `/etc/postgresql/<version>/main/postgresql.conf`：

```conf
shared_buffers = 256MB          # 测试服 256MB；正式服独立 PG 可用 512MB~1G
effective_cache_size = 1GB
work_mem = 8MB
maintenance_work_mem = 64MB
max_connections = 40
```

```bash
sudo systemctl restart postgresql
```

---

## 2. 本地开发启动步骤

### 2.1 克隆仓库并准备环境变量

```bash
git clone <repo_url> mcn-platform
cd mcn-platform
```

**后端环境变量：**

```bash
cp backend/.env.example backend/.env
# 编辑 backend/.env，填写：
#   DATABASE_URL=postgresql://user:pass@127.0.0.1:5432/mcn_db
#   JWT_SECRET=<随机字符串，至少 32 位>
#   CORS_ORIGINS=http://localhost:5173   ← 前端实际访问地址（逗号分隔多个）
#   AI_API_KEY=<第三方 AI 密钥>
#   OSS_ACCESS_KEY=...
#   OSS_SECRET_KEY=...

> ⚠️ **CORS_ORIGINS 必须与前端实际访问地址一致**，否则浏览器登录请求会被拦截（详见 [第 7 节：常见问题排查](#7-常见问题排查)）。
```

> ⚠️  `.env` 文件已列入 `.gitignore`，**禁止提交**。

### 2.2 启动后端

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 开发模式（热重载）：
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 生产模式（nohup 后台 + 日志轮转，推荐用部署脚本）：
bash ../deploy/scripts/start.sh
```

> **进程管理说明：** 生产环境使用 `nohup` 后台运行（见 `start.sh`），配合 logrotate 日志轮转（见 2.6）。如需进程守护自动重启，可改用 PM2：`pm2 start "uvicorn app.main:app --host 127.0.0.1 --port 8000" --name mcn-api`。

后端默认监听 `127.0.0.1:8000`。

### 2.3 启动前端（开发模式）

```bash
cd frontend
npm install
npm run dev
# 前端默认 http://localhost:5173
```

### 2.4 配置本地 Nginx（可选）

```bash
sudo cp deploy/nginx/mcn-m1.conf /etc/nginx/sites-available/mcn-m1
sudo ln -s /etc/nginx/sites-available/mcn-m1 /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## 2.5 数据库环境（本地开发）

| 项目 | 值 |
|---|---|
| 版本 | PostgreSQL 14+（本地开发实测 18.4）|
| 地址 | localhost:5432 |
| 用户 | postgres |
| 密码 | 见 `backend/.env` 中 `DATABASE_URL`（⚠️ 不入 git）|
| M1 开发库 | mcn_m1（已创建）|
| 旧系统库 | mcn_platform（保留，不操作）|
| psql 路径（Windows）| `D:\ProtgreSQL\bin\psql.exe` |

> ⚠️ 默认密码（`admin123`）仅供本地开发参考，**不得用于任何服务器环境**。  
> 服务器部署时必须在 `backend/.env` 中设置强密码，由 `DB_PASSWORD` 环境变量传入脚本。
>
> ⚠️ 生产/测试服部署时必须通过环境变量覆盖默认密码（`export DB_PASSWORD=<强密码>`），切勿使用默认值 `admin123`。

### 建表步骤

```bash
# 执行建表脚本（由后端 Sprint 1 生成，路径相对于项目根目录）
bash deploy/scripts/init-db.sh

# 或手动执行（Windows）：
# D:\ProtgreSQL\bin\psql.exe -U postgres -h localhost -d mcn_m1 -f backend/migrations/001_init.sql

# 验证（应看到 11 张表）
# D:\ProtgreSQL\bin\psql.exe -U postgres -h localhost -d mcn_m1 -c "\dt"
```

---

## 3. 测试服 / 生产服部署步骤

### 3.1 首次部署

```bash
# 1. SSH 登入服务器
ssh deploy@<server-ip>

# 2. 克隆代码
cd /opt
git clone <repo_url> mcn-platform
cd mcn-platform

# 3. 后端环境
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. 配置环境变量（务必修改 JWT_SECRET / DATABASE_URL / 密码为强值）
cp .env.example .env
vim .env

# 5. 初始化数据库（建表 + 迁移）
bash ../deploy/scripts/init-db.sh

# 6. 启动后端
bash ../deploy/scripts/start.sh

# 7. 前端构建 + 部署静态文件
cd ../frontend
npm install
npm run build
sudo mkdir -p /var/www/mcn
sudo cp -r dist/* /var/www/mcn/

# 8. 配置 Nginx（修改 server_name + SSL 证书路径后）
sudo cp ../deploy/nginx/mcn-m1.conf /etc/nginx/sites-available/mcn
sudo ln -sf /etc/nginx/sites-available/mcn /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 9. 配置 SSL 证书（Let's Encrypt）
sudo certbot --nginx -d <your-domain>

# 10. 安装日志轮转
sudo cp ../deploy/scripts/logrotate-mcn.conf /etc/logrotate.d/mcn-backend
# 编辑路径，改为实际部署路径
sudo vim /etc/logrotate.d/mcn-backend

# 11. 健康检查
bash ../deploy/scripts/health-check.sh
```

### 3.2 后续更新部署

```bash
cd /opt/mcn-platform
git pull origin main

# 后端
cd backend && source .venv/bin/activate
pip install -r requirements.txt  # 如有新依赖
bash ../deploy/scripts/stop.sh
bash ../deploy/scripts/start.sh

# 前端（如有变更）
cd ../frontend && npm install && npm run build
sudo cp -r dist/* /var/www/mcn/

# 数据库迁移（如有新 migration）
# bash ../deploy/scripts/init-db.sh  或手动执行新迁移

# 验证
bash ../deploy/scripts/health-check.sh
```

---

## 4. 健康检查

```bash
bash deploy/scripts/health-check.sh
```

预期输出：

```json
{
    "success": true,
    "code": "OK",
    "message": "success",
    "data": {
        "status": "ok",
        "db": "ok",
        "version": "1.0.0"
    }
}
OK: service is healthy
```

返回码 `0` 代表健康；非 `0` 代表异常，需检查后端日志。

查看后端日志：

```bash
tail -f deploy/logs/backend.log
```

---

## 5. 回滚方式

### 5.1 代码回滚

```bash
# 查看最近 10 个 commit
git log --oneline -10

# 回滚到指定 commit（先确保服务已停止）
bash deploy/scripts/stop.sh
git checkout <commit_hash>
bash deploy/scripts/start.sh
bash deploy/scripts/health-check.sh
```

### 5.2 数据库回滚

> Sprint 1 及以后通过迁移脚本管理 schema，届时补充回滚命令。

目前可通过 PostgreSQL 备份还原：

```bash
# 备份（在部署前执行）
pg_dump mcn_db > /tmp/mcn_db_backup_$(date +%Y%m%d_%H%M%S).sql

# 还原
psql mcn_db < /tmp/mcn_db_backup_<timestamp>.sql
```

---

## 6. 目录结构说明

```
deploy/
├── nginx/
│   └── mcn-m1.conf      # Nginx 配置（HTTPS + SSE proxy_buffering off + 安全头）
├── scripts/
│   ├── start.sh          # 启动后端（uvicorn + nohup）+ 重载 Nginx
│   ├── stop.sh           # 停止后端进程
│   ├── health-check.sh   # 调用 /api/health 验证服务状态
│   ├── init-db.sh        # 执行建表迁移脚本
│   └── logrotate-mcn.conf # 日志轮转配置（copytruncate，14天保留）
├── logs/                 # uvicorn 运行日志（自动创建，不入 git，logrotate 管理）
├── pids/                 # 进程 PID 文件（自动创建，不入 git）
├── sql/                  # 数据库迁移脚本预留目录
└── README.md             # 本文件
```

---

## 附：关键配置约束（勿改）

| 约束 | 说明 |
|---|---|
| 密钥不硬编码 | 全部通过环境变量，`.env` 不入 git |
| PostgreSQL 不对外暴露 | 仅绑 `127.0.0.1` |
| SSE 必须关闭 buffering | Nginx `proxy_buffering off` |
| 视频不落本地盘 | 一律 OSS 前端签名直传 |
| CORS_ORIGINS 与前端地址一致 | `.env` 中配置，前端端口/域名变更时必须同步更新 |
| 生产强制 HTTPS | Nginx HTTP 80 → HTTPS 443 重定向，HSTS 证书验证后启用 |
| 日志轮转必须配置 | logrotate copytruncate + maxsize 100M + 14 天保留 |

---

## 7. 常见问题排查

### 7.1 前端登录失败（CORS 拦截）

**症状**：浏览器 Console 报 `Access to fetch at 'http://...' from origin 'http://...' has been blocked by CORS policy`。

**根因**：前端实际访问地址（Origin）不在后端 `CORS_ORIGINS` 白名单中。

**排查步骤**：

```bash
# 1. 确认前端实际跑在哪个端口/域名
#    Vite 默认 5173，被占用时自动切到 5174/5175…

# 2. 检查后端 CORS 配置
grep CORS_ORIGINS backend/.env
# 应包含前端实际地址，例如：
#   CORS_ORIGINS=http://localhost:5173,http://localhost:5174

# 3. 验证 CORS 预检是否放行
curl -s -i -X OPTIONS http://127.0.0.1:8000/api/auth/login \
  -H "Origin: http://localhost:5174" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type"
# 预期：HTTP 200 + access-control-allow-origin: http://localhost:5174
# 若返回 400 "Disallowed CORS origin" → 配置未生效
```

**修复**：

```bash
# 编辑 .env，加入前端实际地址
vim backend/.env
#   CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174

# 重启后端（.env 变更不会被 --reload 热加载，必须重启进程）
bash deploy/scripts/stop.sh && bash deploy/scripts/start.sh
```

> ⚠️ **生产环境**：`CORS_ORIGINS` 应设为实际域名（如 `https://mcn.example.com`），不要用 localhost。

### 7.2 后端重启后端口仍被占用（stale socket）

**症状**：杀掉后端进程后重启，报 `Address already in use` 或新进程启动了但请求仍打到旧配置。

**根因**：进程被强杀后，操作系统内核仍持有 LISTEN socket（Windows 尤其常见，Linux 偶发）。

**排查**：

```bash
# Linux
sudo lsof -i :8000        # 找到占用进程
sudo kill -9 <PID>
# 若进程不存在但端口仍 LISTEN → 等待内核回收（通常 < 30s），或换端口

# Windows
netstat -ano | findstr :8000
taskkill //F //PID <PID>
# stale socket 需等待几秒后重试
```

**预防**：始终用 `deploy/scripts/stop.sh` 优雅关闭，避免 `kill -9`。

### 7.3 后端启动成功但请求 502

**症状**：Nginx 返回 502 Bad Gateway，但 `curl http://127.0.0.1:8000/api/health` 正常。

**根因**：Nginx 反代目标是 `127.0.0.1:8000`，但后端监听的是 `0.0.0.0:8000` 或其他地址。

**排查**：

```bash
# 1. 确认后端监听地址
grep -n "host" deploy/scripts/start.sh
# 应为 --host 127.0.0.1（与 Nginx proxy_pass 一致）

# 2. 确认 Nginx 反代目标
grep proxy_pass deploy/nginx/mcn-m1.conf
# 应为 http://127.0.0.1:8000

# 3. Nginx 自身配置是否有语法错误
sudo nginx -t
```

### 7.4 前端构建失败（antd / React 版本冲突）

**症状**：`npm run build` 报 antd 相关类型错误或运行时 `findDOMNode` 警告。

**根因**：antd v5 官方仅支持 React 16~18，React 19 需要兼容补丁。

**确认**：

```bash
# 检查是否已安装补丁
grep "v5-patch-for-react-19" frontend/package.json
# 检查 main.tsx 是否在最顶部导入
head -1 frontend/src/main.tsx
# 应为：import '@ant-design/v5-patch-for-react-19';
```

**修复**：

```bash
cd frontend
npm install @ant-design/v5-patch-for-react-19
# 确保 main.tsx 第 1 行（所有 antd import 之前）有：
#   import '@ant-design/v5-patch-for-react-19';
npm run build
```
