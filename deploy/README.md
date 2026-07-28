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

> `deploy/scripts/init-db.sh` 不再内置数据库账号或密码，只读取 `DATABASE_URL` 环境变量或 `backend/.env`。生产/测试服必须使用各自的强凭证，禁止把 `.env` 提交到 Git。

### 迁移步骤

```bash
# 已有 schema_migrations 账本：按顺序执行所有未登记迁移
bash deploy/scripts/init-db.sh

# 既有数据库首次纳管：先备份并核对 049 及之前结构，再登记基线
bash deploy/scripts/init-db.sh --baseline-through 49
```

执行器按“数字前缀 + 完整文件名”排序，以 `schema_migrations` 记录校验和。已登记文件不会重放，因此 migration 内的 seed 不会重复执行。检测到既有业务表但没有账本时，脚本会停止并要求显式基线，禁止猜测。

> 当前历史迁移 031 的 seed 依赖管理端模型 ID 已预先存在，因此空数据库的完整初始化仍需独立梳理，不得把 `--baseline-through` 当成建表工具。本文本轮只批准既有数据库的安全接管与后续增量迁移。

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

# 5. 数据库准备
# 新建空库：按当期首次部署清单准备基础表和模型，再运行迁移。
# 既有库：按 §3.3 备份、核对并纳入迁移账本。

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

# 数据库迁移必须在新代码启动前完成；失败即停，不启动不匹配的新代码
bash ../deploy/scripts/init-db.sh

bash ../deploy/scripts/start.sh

# 前端（如有变更）
cd ../frontend && npm install && npm run build
sudo cp -r dist/* /var/www/mcn/

# 验证
bash ../deploy/scripts/health-check.sh
```

### 3.3 既有生产数据库首次纳管与 050 修复

本步骤只供 PM 批准后的生产变更窗口执行。本开发分支不执行生产命令。

1. 停止写流量或进入维护窗口，记录当前代码提交、数据库版本和接口 500 证据。
2. 使用受控备份目录执行 `pg_dump --format=custom --file=<备份文件> <数据库连接>`，确认命令退出码为 0，并用 `pg_restore --list <备份文件>` 验证备份可读。
3. 只读检查：
   - `kol_references` 表存在；
   - 049 的 `uq_kol_active_products_kol` 唯一约束存在；
   - 050 的 8 个媒体字段当前是否缺失；
   - 053/054 的表或字段是否已经由旧流程人工执行。
4. 根据检查结果组装一次性首次纳管命令：
   - 001–049 已存在：传 `--baseline-through 49`；
   - 053/054 已存在：分别追加 `--adopt-existing 053_eval_core.sql`、`--adopt-existing 054_eval_case_jobs.sql`；
   - 未存在的后续迁移不要登记，由执行器真实执行。
5. 运行 `bash deploy/scripts/init-db.sh ...`。任一迁移失败会回滚该文件并停止，禁止启动新代码。
6. 再运行同一命令：预期“执行 0”，用于证明幂等和 seed 不重放。
7. 启动后端后复验 `/api/health`、素材库列表、至少 4 个红人详情，以及红人 43 的创建、编辑和旧记录读取；页面不再出现 500。

失败处理：

- 迁移失败：保持服务停止，保存完整日志，不手工插入账本，不跳过失败文件。
- 050 未提交前失败：该文件事务已回滚，可修正前置条件后重试。
- 050 已成功但应用复验失败：不要删除 050 新增的可空字段；优先回滚代码并保留兼容字段。若必须恢复整库，使用本次变更前的备份在隔离实例验证后再执行恢复。
- 任何恢复或生产 SQL 都需 PM 单独批准。

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

结构迁移默认采用“向前修复”，不自动删除新增列。生产执行前必须先完成可恢复备份：

```bash
# 备份为 PostgreSQL custom 格式，并验证目录可读
pg_dump --format=custom --file=<备份文件> <数据库连接>
pg_restore --list <备份文件>

# 恢复前先在隔离实例验证；生产恢复需 PM 单独批准
pg_restore --clean --if-exists --dbname=<恢复目标> <备份文件>
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
│   ├── init-db.sh        # 调用账本执行器，顺序执行未登记迁移
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

### 7.5 ERR_TOO_MANY_REDIRECTS（API 尾部斜杠重定向）

**症状**：浏览器报 `net::ERR_TOO_MANY_REDIRECTS`，页面或 API 请求无限重定向。

**根因**：FastAPI 默认 `redirect_slashes=True`，当请求带尾部斜杠（如 `/api/outputs/`）时会 307 重定向到无斜杠路径。但重定向的 `Location` 头使用内部地址 `http://127.0.0.1:8000/api/outputs`，通过 Nginx 反代后浏览器无法连接该内网地址 → 循环。

**修复（已在代码中内置，部署时确认即可）**：

```python
# backend/app/main.py — FastAPI 实例已设置 redirect_slashes=False
app = FastAPI(..., redirect_slashes=False)
```

```nginx
# deploy/nginx/mcn-m1.conf — Nginx 层面 301 去掉尾部斜杠
rewrite ^(/api/.*)/$ $1 permanent;
```

> 两处配合：FastAPI 不再自动重定向，Nginx 在请求进入后端前就去掉尾部斜杠。

### 7.6 AI 对话返回空内容（credentials base_url 缺少路径后缀）

**症状**：AI 功能（卖点提取、TikTok 仿写、千川复盘等）页面显示空白或保存历史报 400，但后端不报错，credentials 表有数据且状态 active。

**根因**：`credentials` 表的 `base_url` 字段缺少 API 路径后缀。例如填了 `https://yunwu.ai` 而非 `https://yunwu.ai/v1`，请求打到服务商的网页前端返回 HTML，AI 响应为空字符串。

**排查**：

```bash
# 检查 credentials 表的 base_url
cd backend && source .venv/bin/activate
python -c "
import asyncio
from app.core.database import AsyncSessionLocal
from sqlalchemy import text
async def check():
    async with AsyncSessionLocal() as s:
        r = await s.execute(text(\"SELECT id, provider, base_url FROM credentials WHERE status='active'\"))
        for row in r: print(row)
asyncio.run(check())
"
```

**修复**：

```sql
-- 确保 base_url 包含 /v1 后缀
UPDATE credentials SET base_url = 'https://yunwu.ai/v1' WHERE provider = 'yunwu';
```

或在管理端「工具配置 → 凭证管理」编辑，`base_url` 填 `https://yunwu.ai/v1`（必须带 `/v1`）。
