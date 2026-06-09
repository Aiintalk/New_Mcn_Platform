# MCN_Backend_Agent — M1 Sprint 1 任务指令

> 角色：MCN_Backend_Agent（后端开发 Claude）  
> 工作目录：`backend/`（项目根目录下）  
> PM 生成时间：2026-06-05  
> 前置条件：`tasks/M1_Sprint0.md` 验收通过，`backend/app/` 目录已初始化  
> 完成后：回传 PM，等待 Sprint 2 指令

---

## 必读文档（执行前请先阅读，路径相对于项目根目录）

1. `../MCN_M1_Base_基层文档包/MCN_M1_Base_API_utf8_bom.md` ← **最高优先级，接口契约**
2. `../MCN_M1_Base_基层文档包/MCN_M1_Base_Database_utf8_bom.md` ← 数据库权威文档
3. `../MCN_M1_Base_基层文档包/MCN_M1_Base_Permission_utf8_bom.md` ← 权限规则

---

## 数据库环境（已由 PM 确认）

| 项目 | 值 |
|---|---|
| 版本 | PostgreSQL 18.4 |
| 地址 | localhost:5432 |
| 用户 | postgres |
| 密码 | admin123 |
| 目标库 | mcn_m1（已创建，空库） |
| psql 路径 | `D:\ProtgreSQL\bin\psql.exe` |

> ⚠️ 旧库 `mcn_platform` 保持不动，不要操作

---

## Step 1：执行建表脚本

将以下 SQL 保存为 `backend/migrations/001_init.sql`，然后执行：

```bash
D:\ProtgreSQL\bin\psql.exe -U postgres -h localhost -d mcn_m1 -f migrations/001_init.sql
```

**建表 SQL（Base_Database.md 权威版，PM 已校对）：**

```sql
-- =====================================================================
-- MCN Information System Platform M1 — 建表脚本
-- 数据库：mcn_m1
-- =====================================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

-- 1. users
CREATE TABLE users (
  id                  BIGSERIAL PRIMARY KEY,
  username            VARCHAR(64)   NOT NULL,
  real_name           VARCHAR(64)   NOT NULL,
  password_hash       TEXT          NOT NULL,
  role                VARCHAR(32)   NOT NULL DEFAULT 'operator',
  status              VARCHAR(32)   NOT NULL DEFAULT 'enabled',
  password_changed_at TIMESTAMPTZ,
  token_version       INT           NOT NULL DEFAULT 0,
  last_login_at       TIMESTAMPTZ,
  last_active_at      TIMESTAMPTZ,
  created_by          BIGINT,
  created_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
  deleted_at          TIMESTAMPTZ
);
CREATE UNIQUE INDEX idx_users_username ON users(username) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_role_status ON users(role, status);
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 2. workspace_tools
CREATE TABLE workspace_tools (
  id          BIGSERIAL PRIMARY KEY,
  tool_code   VARCHAR(64)   NOT NULL,
  tool_name   VARCHAR(128)  NOT NULL,
  category    VARCHAR(64),
  description TEXT,
  status      VARCHAR(32)   NOT NULL DEFAULT 'dev',
  tags        JSONB,
  config      JSONB,
  sort_order  INT           NOT NULL DEFAULT 0,
  created_at  TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX idx_workspace_tools_code ON workspace_tools(tool_code);
CREATE INDEX idx_workspace_tools_status ON workspace_tools(status);
CREATE TRIGGER trg_tools_updated BEFORE UPDATE ON workspace_tools
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 3. kols
CREATE TABLE kols (
  id           BIGSERIAL PRIMARY KEY,
  name         VARCHAR(128)  NOT NULL,
  category     VARCHAR(64),
  platform     VARCHAR(32)   DEFAULT 'douyin',
  external_id  VARCHAR(128),
  douyin_id    VARCHAR(128),
  avatar_url   TEXT,
  persona      TEXT,
  content_plan TEXT,
  style_notes  TEXT,
  owner_id     BIGINT        REFERENCES users(id),
  status       VARCHAR(32)   NOT NULL DEFAULT 'active',
  created_by   BIGINT        REFERENCES users(id),
  created_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
  deleted_at   TIMESTAMPTZ
);
CREATE INDEX idx_kols_status ON kols(status) WHERE deleted_at IS NULL;
CREATE TRIGGER trg_kols_updated BEFORE UPDATE ON kols
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 4. tool_sessions
CREATE TABLE tool_sessions (
  id           BIGSERIAL PRIMARY KEY,
  tool_code    VARCHAR(64)   NOT NULL,
  current_step VARCHAR(64),
  context      JSONB,
  drafts       JSONB,
  messages     JSONB,
  status       VARCHAR(32)   NOT NULL DEFAULT 'draft',
  created_by   BIGINT        NOT NULL REFERENCES users(id),
  created_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX idx_tool_sessions_user ON tool_sessions(created_by, status);
CREATE TRIGGER trg_sessions_updated BEFORE UPDATE ON tool_sessions
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 5. task_jobs
CREATE TABLE task_jobs (
  id             BIGSERIAL PRIMARY KEY,
  task_no        VARCHAR(64)   NOT NULL,
  tool_code      VARCHAR(64)   NOT NULL,
  tool_name      VARCHAR(128)  NOT NULL,
  status         VARCHAR(32)   NOT NULL DEFAULT 'pending',
  input_payload  JSONB,
  result_summary JSONB,
  error_code     VARCHAR(128),
  error_message  TEXT,
  session_id     BIGINT        REFERENCES tool_sessions(id),
  output_id      BIGINT,
  created_by     BIGINT        NOT NULL REFERENCES users(id),
  started_at     TIMESTAMPTZ,
  finished_at    TIMESTAMPTZ,
  duration_ms    INT,
  created_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX idx_task_jobs_no ON task_jobs(task_no);
CREATE INDEX idx_task_jobs_created_by ON task_jobs(created_by);
CREATE INDEX idx_task_jobs_tool_status ON task_jobs(tool_code, status);
CREATE INDEX idx_task_jobs_created_at ON task_jobs(created_at DESC);
CREATE TRIGGER trg_task_jobs_updated BEFORE UPDATE ON task_jobs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 6. task_logs
CREATE TABLE task_logs (
  id         BIGSERIAL PRIMARY KEY,
  task_id    BIGINT        NOT NULL REFERENCES task_jobs(id) ON DELETE CASCADE,
  step_code  VARCHAR(64)   NOT NULL,
  step_name  VARCHAR(128)  NOT NULL,
  status     VARCHAR(32)   NOT NULL,
  message    TEXT,
  payload    JSONB,
  created_at TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX idx_task_logs_task_id ON task_logs(task_id);

-- 7. outputs
CREATE TABLE outputs (
  id           BIGSERIAL PRIMARY KEY,
  title        VARCHAR(255)  NOT NULL,
  tool_code    VARCHAR(64)   NOT NULL,
  tool_name    VARCHAR(128)  NOT NULL,
  task_id      BIGINT        REFERENCES task_jobs(id),
  content      TEXT,
  content_json JSONB,
  word_count   INT,
  file_id      BIGINT,
  created_by   BIGINT        NOT NULL REFERENCES users(id),
  created_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
  deleted_at   TIMESTAMPTZ
);
CREATE INDEX idx_outputs_created_by ON outputs(created_by);
CREATE INDEX idx_outputs_created_at ON outputs(created_at DESC);
CREATE TRIGGER trg_outputs_updated BEFORE UPDATE ON outputs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 8. files
CREATE TABLE files (
  id           BIGSERIAL PRIMARY KEY,
  filename     VARCHAR(255)  NOT NULL,
  file_type    VARCHAR(64),
  file_size    BIGINT,
  oss_key      TEXT          NOT NULL,
  content_type VARCHAR(128),
  output_id    BIGINT        REFERENCES outputs(id),
  task_id      BIGINT        REFERENCES task_jobs(id),
  created_by   BIGINT        NOT NULL REFERENCES users(id),
  created_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
  deleted_at   TIMESTAMPTZ
);
CREATE INDEX idx_files_created_by ON files(created_by);
CREATE INDEX idx_files_output_id ON files(output_id);

-- 9. operation_logs
CREATE TABLE operation_logs (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT        REFERENCES users(id),
  username    VARCHAR(64),
  role        VARCHAR(32),
  action      VARCHAR(128)  NOT NULL,
  target_type VARCHAR(64),
  target_id   BIGINT,
  detail      JSONB,
  ip          VARCHAR(64),
  user_agent  TEXT,
  created_at  TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX idx_op_logs_user_id ON operation_logs(user_id);
CREATE INDEX idx_op_logs_action ON operation_logs(action);
CREATE INDEX idx_op_logs_created_at ON operation_logs(created_at DESC);

-- 10. external_service_logs
CREATE TABLE external_service_logs (
  id             BIGSERIAL PRIMARY KEY,
  service        VARCHAR(64)   NOT NULL,
  action         VARCHAR(128)  NOT NULL,
  task_id        BIGINT        REFERENCES task_jobs(id),
  credential_id  BIGINT,
  request_body   JSONB,
  response_body  JSONB,
  tokens_in      INT,
  tokens_out     INT,
  credits        NUMERIC,
  audio_seconds  INT,
  duration_ms    INT,
  status         VARCHAR(32)   NOT NULL,
  error_code     VARCHAR(128),
  error_message  TEXT,
  request_hash   VARCHAR(128),
  created_at     TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX idx_external_logs_service ON external_service_logs(service);
CREATE INDEX idx_external_logs_task_id ON external_service_logs(task_id);
CREATE INDEX idx_external_logs_created_at ON external_service_logs(created_at DESC);

-- 11. service_credentials
CREATE TABLE service_credentials (
  id             BIGSERIAL PRIMARY KEY,
  provider       VARCHAR(64)   NOT NULL,
  label          VARCHAR(128)  NOT NULL,
  secret_enc     TEXT          NOT NULL,
  secret_tail    VARCHAR(16)   NOT NULL,
  status         VARCHAR(32)   NOT NULL DEFAULT 'enabled',
  weight         INT           NOT NULL DEFAULT 1,
  quota_limit    BIGINT,
  quota_used     BIGINT        DEFAULT 0,
  fail_count     INT           NOT NULL DEFAULT 0,
  cooldown_until TIMESTAMPTZ,
  created_by     BIGINT        REFERENCES users(id),
  created_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX idx_cred_provider_status ON service_credentials(provider, status);
CREATE TRIGGER trg_credentials_updated BEFORE UPDATE ON service_credentials
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE external_service_logs ADD CONSTRAINT fk_ext_logs_credential
  FOREIGN KEY (credential_id) REFERENCES service_credentials(id);

-- SEED：workspace_tools 初始数据
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, tags, sort_order) VALUES
  ('persona-writer', '人设脚本仿写', '脚本创作', '选择达人 → 对标验证 → 智能仿写 → 导出文档', 'online',  '["智能生成","视频解析","文档导出"]'::jsonb, 1),
  ('benchmark',      '对标分析助手', '选题分析', '拆解对标视频结构与爆点节奏',                 'dev',     '["智能生成"]'::jsonb,                     2),
  ('qianchuan',      '千川工具组',   '投放',     '千川投放辅助工具',                           'dev',     '[]'::jsonb,                               3),
  ('review',         '复盘工具组',   '数据复盘', '内容复盘与数据分析',                         'dev',     '[]'::jsonb,                               4),
  ('subtitle',       '字幕提取',     '素材处理', '音视频字幕自动提取',                         'dev',     '[]'::jsonb,                               5);
```

执行后验证（应看到 11 张表）：
```bash
D:\ProtgreSQL\bin\psql.exe -U postgres -h localhost -d mcn_m1 -c "\dt"
```

---

## Step 2：SQLAlchemy ORM 模型（`app/models/`）

每张表一个文件，字段名与建表 SQL 完全一致：

| 文件 | 模型 | 对应表 |
|---|---|---|
| `models/user.py` | `User` | users |
| `models/workspace.py` | `WorkspaceTool` | workspace_tools |
| `models/kol.py` | `Kol` | kols |
| `models/task.py` | `TaskJob` + `TaskLog` | task_jobs / task_logs |
| `models/output.py` | `Output` | outputs |
| `models/file.py` | `File` | files |
| `models/log.py` | `OperationLog` + `ExternalServiceLog` | operation_logs / external_service_logs |
| `models/credential.py` | `ServiceCredential` | service_credentials |
| `models/session.py` | `ToolSession` | tool_sessions |

---

## Step 3：JWT 鉴权

**`app/core/security.py`：**
- `create_access_token(user_id, username, role, token_version) → str`
  - HS256，payload 含 `sub/username/role/token_version/exp`
  - 过期时间读 `config.JWT_EXPIRE_HOURS`
- `verify_token(token: str) → dict`
  - 失败抛 `HTTPException(401, AUTH_TOKEN_EXPIRED)`

**`app/middlewares/auth.py`：**
- `get_current_user(token = Depends(oauth2_scheme)) → User`
  - token_version 不符 → `AUTH_TOKEN_EXPIRED`
  - 用户不存在/已删除 → `AUTH_TOKEN_MISSING`
  - status=disabled → `AUTH_USER_DISABLED`
- `require_admin(current_user = Depends(get_current_user)) → User`
  - role != admin → `PERMISSION_DENIED`
- `require_password_changed(current_user = Depends(get_current_user)) → User`
  - `password_changed_at IS NULL` → `AUTH_FORCE_CHANGE_PASSWORD`
  - 白名单（不经此依赖）：`/api/auth/me`、`/api/auth/change-password`、`/api/auth/logout`

---

## Step 4：认证 API（`app/routers/auth.py`）

严格遵守 `MCN_M1_Base_API` 第 5 节：

| 接口 | 方法 | 权限 | 关键逻辑 |
|---|---|---|---|
| `/api/auth/login` | POST | PUBLIC | bcrypt 校验，返回 token + must_change_password，写 operation_logs，更新 last_login_at |
| `/api/auth/me` | GET | 需登录 | 返回当前用户信息（含 must_change_password） |
| `/api/auth/change-password` | POST | 需登录 | 校验旧密码，更新 password_hash/password_changed_at，token_version+=1，写 operation_logs |
| `/api/auth/logout` | POST | 需登录 | token_version+=1，写 operation_logs |

---

## Step 5：用户管理 API（`app/routers/admin_users.py`）

全部需要 admin 权限，严格遵守 `MCN_M1_Base_API` 第 6 节：

| 接口 | 方法 | 关键逻辑 |
|---|---|---|
| `/api/admin/users` | GET | 分页+筛选（keyword/status/role），只返回 deleted_at IS NULL |
| `/api/admin/users` | POST | 随机生成初始密码，password_changed_at=NULL，initial_password 只在响应中返回一次 |
| `/api/admin/users/{id}` | GET | 用户详情 |
| `/api/admin/users/{id}` | PATCH | 可更新 real_name/role/status |
| `/api/admin/users/{id}/reset-password` | POST | 随机新密码，token_version+=1 |
| `/api/admin/users/{id}/enable` | POST | status=enabled |
| `/api/admin/users/{id}/disable` | POST | status=disabled |
| `/api/admin/users/{id}` | DELETE | 软删除，deleted_at=now() |

所有操作写 `operation_logs`。

---

## Step 6：初始 Admin Seed（`app/core/seed.py`）

```python
async def seed_initial_data():
    # 若 users 表无 admin 账号，自动创建
    # username 读 INITIAL_ADMIN_USERNAME（默认 admin）
    # 密码读 INITIAL_ADMIN_PASSWORD（默认 Admin@123456），bcrypt 加密
    # password_changed_at = NULL（首次登录强制改密）
```

在 `main.py` startup 事件中调用。

---

## 不做什么

- 不实现 workspace/tasks/outputs/files/logs/credentials API（Sprint 2-3）
- 不实现 AI/TikHub/OSS 真实调用
- 不修改 `mcn_platform` 数据库

---

## 验收标准

1. `\dt` 可见 11 张表
2. `GET /api/health` 中 `database=ok`
3. `POST /api/auth/login` 成功返回 token + must_change_password
4. operator Token 调 `/api/admin/users` 返回 `PERMISSION_DENIED`
5. `password_changed_at=null` 账号调业务接口返回 `AUTH_FORCE_CHANGE_PASSWORD`
6. `POST /api/admin/users` 返回 `initial_password`
7. `DELETE /api/admin/users/{id}` 后 `deleted_at` 有值，记录未物理删除
8. 关键操作在 `operation_logs` 有记录

---

## 完成后输出格式

```
# 后端 Claude 执行结果 — M1 Sprint 1
## 1. 本次任务
## 2. 完成内容
## 3. 新增 / 修改 API 清单（含路径、方法、权限）
## 4. 修改文件清单
## 5. 数据表变更情况（\dt 输出结果）
## 6. 权限校验说明
## 7. 自测结果（每个接口的 curl 命令 + 实际响应）
## 8. 未完成事项
## 9. 需要 PM 决策的问题
## 10. 建议下一步
```

> ⚠️ 字段命名必须与建表 SQL 完全一致，不得自行改名。  
> ⚠️ 如需新增 `MCN_M1_Base_API` 未定义的接口，必须先停下回传 PM。
