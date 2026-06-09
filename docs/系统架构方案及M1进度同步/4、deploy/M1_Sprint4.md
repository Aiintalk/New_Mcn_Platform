# MCN_DevOps_Agent — M1 Sprint 4 部署指令

> 角色：MCN_DevOps_Agent（运维 Claude）  
> 工作目录：`deploy/`  
> 文档生成时间：2026-06-07  
> 前置条件：测试服基础环境已就绪（Nginx / Python 3.11 / PostgreSQL / uvicorn）

---

## 一、数据库迁移文件清单

| 顺序 | 文件 | 操作内容 | 状态 |
|---|---|---|---|
| 1 | `backend/migrations/003_ai_tables.sql` | 新建 `credentials`、`ai_models`、`ai_call_logs` 三张表及索引 | 本地已执行 |
| 2 | `backend/migrations/004_credentials_test_fields.sql` | `credentials` 表新增 `last_tested_at`、`last_latency_ms` 字段 | 本地已执行 |
| 3 | `backend/migrations/005_ai_models_test_fields.sql` | `ai_models` 表新增 `last_tested_at`、`last_latency_ms` 字段 | 本地已执行 |

> **注意**：001/002 迁移为 M1 基础表结构，应已在更早阶段执行。本次仅需执行 003～005。

---

## 二、迁移执行顺序与命令

**必须按顺序执行**，003 → 004 → 005（004/005 依赖 003 创建的表）。

```bash
# 切换到项目根目录
cd /path/to/mcn-platform

# 003：AI 管理模块建表（credentials / ai_models / ai_call_logs）
PGPASSWORD=$DB_PASSWORD psql -U postgres -h 127.0.0.1 -d mcn_m1 \
  -f backend/migrations/003_ai_tables.sql

# 004：credentials 表加测试结果字段
PGPASSWORD=$DB_PASSWORD psql -U postgres -h 127.0.0.1 -d mcn_m1 \
  -f backend/migrations/004_credentials_test_fields.sql

# 005：ai_models 表加测试结果字段
PGPASSWORD=$DB_PASSWORD psql -U postgres -h 127.0.0.1 -d mcn_m1 \
  -f backend/migrations/005_ai_models_test_fields.sql
```

**验证（执行完毕后确认表结构）**：

```bash
PGPASSWORD=$DB_PASSWORD psql -U postgres -h 127.0.0.1 -d mcn_m1 -c "\dt"
# 应看到 credentials、ai_models、ai_call_logs 三张表

PGPASSWORD=$DB_PASSWORD psql -U postgres -h 127.0.0.1 -d mcn_m1 \
  -c "\d credentials"
# last_tested_at / last_latency_ms 字段应存在

PGPASSWORD=$DB_PASSWORD psql -U postgres -h 127.0.0.1 -d mcn_m1 \
  -c "\d ai_models"
# last_tested_at / last_latency_ms 字段应存在
```

---

## 三、服务重启注意事项

### 3.1 重启流程

```bash
# 1. 停止旧进程
bash deploy/scripts/stop.sh

# 2. 确认端口已释放
# Linux:
fuser 8000/tcp   # 无输出表示端口已空闲

# 3. 启动新进程
bash deploy/scripts/start.sh

# 4. 等待 3 秒后健康检查
sleep 3 && bash deploy/scripts/health-check.sh
```

### 3.2 重要注意事项

| 事项 | 说明 |
|---|---|
| **迁移先于重启** | 必须数据库迁移全部成功后再启动后端，否则后端启动时会因字段缺失报错 |
| **不要跳过健康检查** | 启动后务必执行 `health-check.sh`，确认 `database: ok` |
| **日志路径** | `deploy/logs/backend.log`，启动异常时首先查此文件 |
| **PID 文件** | `deploy/pids/backend.pid`，`stop.sh` 依赖此文件终止进程 |
| **端口占用** | 若 `stop.sh` 无法终止（权限不足），需手动 `kill` 或通过启动该进程的终端 `Ctrl+C` |

### 3.3 回滚

```bash
# 停服
bash deploy/scripts/stop.sh

# 代码回滚
git checkout <上一个稳定 commit>

# 若迁移需要回滚，手动执行反向 ALTER（DROP COLUMN）
# PGPASSWORD=$DB_PASSWORD psql -U postgres -d mcn_m1 -c \
#   "ALTER TABLE credentials DROP COLUMN IF EXISTS last_tested_at, DROP COLUMN IF EXISTS last_latency_ms;"
# PGPASSWORD=$DB_PASSWORD psql -U postgres -d mcn_m1 -c \
#   "ALTER TABLE ai_models DROP COLUMN IF EXISTS last_tested_at, DROP COLUMN IF EXISTS last_latency_ms;"

# 重启
bash deploy/scripts/start.sh && bash deploy/scripts/health-check.sh
```

---

## 四、环境变量说明

### 4.1 必填项（上线前必须替换占位值）

| 变量 | 说明 | 示例/要求 |
|---|---|---|
| `DATABASE_URL` | PostgreSQL 连接串 | `postgresql+asyncpg://user:pass@127.0.0.1:5432/mcn_m1` |
| `JWT_SECRET` | JWT 签名密钥 | **随机字符串，至少 32 位**，`change-me-in-production` 不可用于生产 |
| `ENCRYPTION_KEY` | 数据加密密钥 | **恰好 32 字符**，`change-me-32-chars-...` 不可用于生产 |
| `INITIAL_ADMIN_PASSWORD` | 首次启动创建管理员的密码 | 强密码，仅首次启动生效 |

### 4.2 AI 服务商配置（base_url）

后端支持两层配置，**数据库优先**：

```
优先级：DB service_credentials 表 > .env 环境变量
```

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LLM_API_BASE` | `https://yunwu.ai/v1` | AI 服务商 base_url，兼容 OpenAI 格式的中转地址 |
| `LLM_API_KEY` | —（必填）| AI 服务商 API Key |
| `LLM_MODEL` | `claude-haiku-4-5-20251001` | 默认模型 ID |

**通过数据库管理多 Key 池**（推荐生产环境）：

```sql
-- 查看当前已配置的 AI 凭证
SELECT id, provider, label, secret_tail, status, weight FROM service_credentials
WHERE provider = 'ai';

-- 新增 Key（secret_enc 字段存储完整 Key，由后端加密写入，勿直接 INSERT 明文）
-- 建议通过管理后台 /api/admin/credentials 接口写入
```

| `service_credentials` 关键字段 | 说明 |
|---|---|
| `provider` | 服务商标识，AI 填 `ai`，TikHub 填 `tikhub` |
| `label` | 备注名，便于区分多个 Key |
| `base_url`（config jsonb）| 覆盖 `.env` 的 `LLM_API_BASE`，格式：`{"base_url": "https://yunwu.ai/v1"}` |
| `weight` | 轮询权重，数值越大越优先 |
| `status` | `enabled` / `disabled` |

### 4.3 TikHub 配置

| 变量 | 说明 |
|---|---|
| `TIKHUB_API_KEY` | TikHub API Key（也可通过 `service_credentials` 表管理）|
| `TIKHUB_BASE_URL` | 默认 `https://api.tikhub.io` |

### 4.4 OSS 配置（Sprint 4 补充）

```bash
OSS_ACCESS_KEY_ID=your_access_key_id
OSS_ACCESS_KEY_SECRET=your_access_key_secret
OSS_BUCKET=your-bucket-name
OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
OSS_REGION=cn-hangzhou
```

> 视频及文件上传必须走 OSS 前端签名直传，**严禁落本地磁盘**（详见 `project_docs/MCN_M1_部署与容量评估.md` 第四节）。
