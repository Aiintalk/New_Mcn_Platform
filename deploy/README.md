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
#   AI_API_KEY=<第三方 AI 密钥>
#   OSS_ACCESS_KEY=...
#   OSS_SECRET_KEY=...
```

> ⚠️  `.env` 文件已列入 `.gitignore`，**禁止提交**。

### 2.2 启动后端

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
# 或使用 PM2：
# pm2 start app.py --name mcn-api --interpreter python3.11
```

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

## 3. 测试服部署步骤（预留）

> **Sprint 4 补充此章节。**

步骤概要（待补全）：
1. SSH 登入测试服
2. 拉取最新代码
3. 配置环境变量
4. 运行 `bash deploy/scripts/start.sh`
5. 运行健康检查确认上线

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
│   └── mcn-m1.conf      # Nginx 反代配置（含 SSE proxy_buffering off）
├── scripts/
│   ├── start.sh          # 启动后端（uvicorn）+ 重载 Nginx
│   ├── stop.sh           # 停止后端进程
│   ├── health-check.sh   # 调用 /api/health 验证服务状态
│   └── init-db.sh        # 执行建表迁移脚本
├── logs/                 # uvicorn 运行日志（自动创建，不入 git）
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
