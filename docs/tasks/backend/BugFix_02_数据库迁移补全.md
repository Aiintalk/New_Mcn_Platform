# 后端任务单 · BugFix-02 数据库迁移补全

> 发现时间：2026-06-09
> 触发场景：Mac 本地拉取代码后数据库初始化，TikHub 添加报 500 / 添加红人无响应
> 根因：模型代码持续迭代但迁移文件未同步，新表和新字段仅存在于开发环境，新环境执行旧迁移后 schema 不完整
> 负责人：后端
> 优先级：🔴 高（影响新环境初始化，所有人拉代码都会遇到）

---

## 一、问题说明

### 根因拆解

| # | 问题 | 表现 |
|---|------|------|
| 1 | 模型新增字段未同步写迁移 | `kols` 等表字段不完整，后端 INSERT 报列不存在 |
| 2 | 新表完全缺失迁移文件 | `service_credentials` / `outputs` / `files` / `tool_sessions` / `external_service_logs` 等表不存在，访问即 500 |
| 3 | `CREATE TABLE` 无幂等保护 | 重复执行迁移报 "already exists" 错误，掩盖真实 schema 问题 |
| 4 | 无一键初始化脚本 | 新成员不知道要执行哪些文件、按什么顺序执行 |

### 最直接影响（Mac 当前报错）

`service_credentials` 表不存在 → `POST /api/admin/config/credentials` 报 500 → 浏览器收到 500 触发 CORS 报错 → 用户看到「没有响应」

---

## 二、需要补充的表（对比模型 vs 现有迁移）

通过对比 `app/models/*.py` 与 `migrations/001~007.sql`，以下表**在迁移中缺失**：

| 表名 | 对应 Model | 说明 |
|------|-----------|------|
| `service_credentials` | `ServiceCredential` | TikHub / OSS / ASR 等第三方 Key 管理 |
| `outputs` | `Output` | 产出中心记录 |
| `files` | `File` | 文件存储记录 |
| `tool_sessions` | `ToolSession` | 工具会话状态 |
| `external_service_logs` | `ExternalServiceLog` | 第三方服务调用日志 |

---

## 三、修复任务

### 任务 1：新建 `008_schema_catchup.sql`

新建文件 `backend/migrations/008_schema_catchup.sql`，补全所有缺失的表和字段。

使用 **`CREATE TABLE IF NOT EXISTS`** 和 **`ADD COLUMN IF NOT EXISTS`**，保证幂等可重复执行。

**参考 Model 定义，完整 SQL 如下：**

```sql
-- =====================================================================
-- 008_schema_catchup.sql
-- 补全 001~007 迁移中缺失的表和字段
-- 全部使用 IF NOT EXISTS，幂等安全，可重复执行
-- =====================================================================

-- ── 1. service_credentials（TikHub / OSS / ASR 等第三方密钥）──────────
CREATE TABLE IF NOT EXISTS service_credentials (
    id             BIGSERIAL PRIMARY KEY,
    provider       VARCHAR(64)  NOT NULL,
    label          VARCHAR(128) NOT NULL,
    secret_enc     TEXT         NOT NULL,
    secret_tail    VARCHAR(16)  NOT NULL,
    status         VARCHAR(32)  NOT NULL DEFAULT 'enabled',
    weight         INTEGER      NOT NULL DEFAULT 1,
    quota_limit    BIGINT,
    quota_used     BIGINT                DEFAULT 0,
    fail_count     INTEGER      NOT NULL DEFAULT 0,
    cooldown_until TIMESTAMPTZ,
    config         JSONB,
    created_by     BIGINT REFERENCES users(id),
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── 2. outputs（产出中心）────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS outputs (
    id           BIGSERIAL PRIMARY KEY,
    title        VARCHAR(255) NOT NULL,
    tool_code    VARCHAR(64)  NOT NULL,
    tool_name    VARCHAR(128) NOT NULL,
    task_id      BIGINT REFERENCES task_jobs(id),
    content      TEXT,
    content_json JSONB,
    word_count   INTEGER,
    file_id      BIGINT,
    created_by   BIGINT       NOT NULL REFERENCES users(id),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at   TIMESTAMPTZ
);

-- ── 3. files（文件记录）──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS files (
    id           BIGSERIAL PRIMARY KEY,
    filename     VARCHAR(255) NOT NULL,
    file_type    VARCHAR(64),
    file_size    BIGINT,
    oss_key      TEXT         NOT NULL,
    content_type VARCHAR(128),
    output_id    BIGINT REFERENCES outputs(id),
    task_id      BIGINT REFERENCES task_jobs(id),
    created_by   BIGINT       NOT NULL REFERENCES users(id),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at   TIMESTAMPTZ
);

-- ── 4. tool_sessions（工具会话）──────────────────────────────────────
CREATE TABLE IF NOT EXISTS tool_sessions (
    id           BIGSERIAL PRIMARY KEY,
    tool_code    VARCHAR(64)  NOT NULL,
    current_step VARCHAR(64),
    context      JSONB,
    drafts       JSONB,
    messages     JSONB,
    status       VARCHAR(32)  NOT NULL DEFAULT 'draft',
    created_by   BIGINT       NOT NULL REFERENCES users(id),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── 5. external_service_logs（第三方服务调用日志）───────────────────
CREATE TABLE IF NOT EXISTS external_service_logs (
    id            BIGSERIAL PRIMARY KEY,
    service       VARCHAR(64)  NOT NULL,
    action        VARCHAR(128) NOT NULL,
    task_id       BIGINT REFERENCES task_jobs(id),
    credential_id BIGINT REFERENCES service_credentials(id),
    request_body  JSONB,
    response_body JSONB,
    tokens_in     INTEGER,
    tokens_out    INTEGER,
    tokens_used   INTEGER,
    credits       NUMERIC,
    audio_seconds INTEGER,
    duration_ms   INTEGER,
    status        VARCHAR(32)  NOT NULL,
    error_code    VARCHAR(128),
    error_message TEXT,
    request_hash  VARCHAR(128),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── 6. kols 表补字段（001_init.sql 建表时缺少的列）────────────────────
ALTER TABLE kols ADD COLUMN IF NOT EXISTS account_name  VARCHAR(128);
ALTER TABLE kols ADD COLUMN IF NOT EXISTS sec_uid       VARCHAR(128);
ALTER TABLE kols ADD COLUMN IF NOT EXISTS avatar_url    TEXT;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS signature     TEXT;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS follower_count BIGINT;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS video_count   INTEGER;
ALTER TABLE kols ADD COLUMN IF NOT EXISTS owner         VARCHAR(128);
ALTER TABLE kols ADD COLUMN IF NOT EXISTS tikhub_raw    JSONB;

-- ── 7. workspace_tools 补字段 ────────────────────────────────────────
ALTER TABLE workspace_tools ADD COLUMN IF NOT EXISTS config JSONB;

-- ── 完成提示 ──────────────────────────────────────────────────────────
DO $$
BEGIN
  RAISE NOTICE '✅ 008_schema_catchup 执行完成';
END
$$;
```

---

### 任务 2：001~007 加幂等保护

将现有 `001_init.sql` 中所有 `CREATE TABLE` 改为 `CREATE TABLE IF NOT EXISTS`。

其他迁移文件如有同样问题一并修改。

---

### 任务 3：新建 `backend/scripts/init_db.sh`

```bash
#!/bin/bash
# =====================================================================
# MCN Platform — 本地数据库一键初始化
# 用法：bash backend/scripts/init_db.sh
# 前提：本地 PostgreSQL 已启动，mcn_user / mcn_db 已创建
# =====================================================================
set -e

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-mcn_user}"
DB_NAME="${DB_NAME:-mcn_db}"
DB_PASS="${DB_PASS:-mcn_password}"

echo "📦 开始初始化数据库: $DB_NAME"

MIGRATIONS_DIR="$(dirname "$0")/../migrations"

for f in $(ls "$MIGRATIONS_DIR"/*.sql | sort); do
  echo "  → 执行 $(basename $f) ..."
  PGPASSWORD=$DB_PASS psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f "$f" -q
done

# 种子数据（本地开发用，不提交 GitHub）
SEED_FILE="$(dirname "$0")/../seed_local.sql"
if [ -f "$SEED_FILE" ]; then
  echo "  → 执行 seed_local.sql ..."
  PGPASSWORD=$DB_PASS psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f "$SEED_FILE" -q
else
  echo "  ⚠️  seed_local.sql 不存在，跳过种子数据（请参考 seed_local.sql.example）"
fi

echo "✅ 数据库初始化完成"
```

---

### 任务 4：建立迁移规范（写进 CLAUDE.md 或团队 Wiki）

```
【数据库迁移规范】

1. 每次修改 app/models/*.py（新增字段、新增表）
   必须同步新建迁移文件：backend/migrations/XXX_描述.sql

2. 迁移文件命名：三位序号_描述.sql（如 009_add_kol_tags.sql）

3. 迁移 SQL 必须使用幂等写法：
   - 建表：CREATE TABLE IF NOT EXISTS
   - 加列：ALTER TABLE xxx ADD COLUMN IF NOT EXISTS
   - 加索引：CREATE INDEX IF NOT EXISTS

4. 禁止直接手动连库 ALTER TABLE，所有变更必须有对应迁移文件

5. PR 合并 Checklist 新增一项：
   □ 是否有 Model 字段变更？如有，是否对应写了迁移文件？
```

---

## 四、验收标准

- [ ] `008_schema_catchup.sql` 在全新数据库上执行成功，无报错
- [ ] 执行 `bash backend/scripts/init_db.sh` 完成后，Mac 本地可正常添加 TikHub Key
- [ ] 执行后 Mac 本地可正常添加红人
- [ ] `001_init.sql` 的 `CREATE TABLE` 全部改为 `IF NOT EXISTS`，重复执行不报错
- [ ] `init_db.sh` 脚本可在 Mac / Linux 上执行（Windows 用 Git Bash）

---

## 五、后续（非本次范围，记录待做）

- [ ] 后端启动时增加 schema 自动校验：对比 SQLAlchemy 模型 vs 实际 DB，不一致打警告日志
- [ ] 考虑引入 Alembic 做正式的迁移版本管理（M3 阶段评估）
