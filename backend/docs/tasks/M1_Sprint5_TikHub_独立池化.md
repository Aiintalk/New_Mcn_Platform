# MCN_Backend_Agent — M1 Sprint 5 任务指令（TikHub 独立池化）

> 角色：MCN_Backend_Agent（后端开发 Claude）
> 工作目录：`backend/`
> PM 生成时间：2026-06-10
> 前置条件：M1 Sprint 2 TikHub 基础抓取功能已运行
> 完成后：回传 PM，等待前端联调

---

## M1 Sprint 5 目标

将 TikHub 从通用 Key 池（`service_credentials`）迁移到独立的专用池（类似 AI Key 池），实现：
1. 并发控制（active_requests / max_concurrent）
2. 三维统计（整体 / 接口 / 用户）
3. 完善的管理接口

---

## 一、数据库迁移

### 1.1 创建 `tikhub_credentials` 表

**文件：** `migrations/010_tikhub_credentials.sql`

```sql
-- TikHub 专用 Key 池，参考 credentials 表结构
CREATE TABLE IF NOT EXISTS tikhub_credentials (
  id              BIGSERIAL PRIMARY KEY,
  provider        VARCHAR(64)  NOT NULL DEFAULT 'tikhub',
  label           VARCHAR(128),
  api_key         TEXT         NOT NULL,
  base_url        VARCHAR(512) NOT NULL DEFAULT 'https://api.tikhub.io',
  status          VARCHAR(32)  NOT NULL DEFAULT 'active',  -- active/inactive
  active_requests INT          NOT NULL DEFAULT 0,
  max_concurrent  INT          NOT NULL DEFAULT 5,
  max_users       INT          NOT NULL DEFAULT 10,
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_tikhub_credentials_status ON tikhub_credentials(status);
CREATE INDEX IF NOT EXISTS idx_tikhub_credentials_provider ON tikhub_credentials(provider);
```

### 1.2 创建 `tikhub_call_logs` 表

**文件：** `migrations/011_tikhub_call_logs.sql`

```sql
-- TikHub 调用日志表
CREATE TABLE IF NOT EXISTS tikhub_call_logs (
  id            BIGSERIAL PRIMARY KEY,
  credential_id BIGINT       NOT NULL REFERENCES tikhub_credentials(id) ON DELETE SET NULL,
  user_id       BIGINT       NOT NULL REFERENCES users(id) ON DELETE SET NULL,
  platform      VARCHAR(64)  NOT NULL,  -- douyin/instagram/youtube 等
  endpoint      VARCHAR(64)  NOT NULL,  -- user_profile/fans_info/live_products 等
  status        VARCHAR(32)  NOT NULL,  -- success/failure
  latency_ms    INT,
  error_message TEXT,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_tikhub_call_logs_credential ON tikhub_call_logs(credential_id);
CREATE INDEX IF NOT EXISTS idx_tikhub_call_logs_user ON tikhub_call_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_tikhub_call_logs_platform ON tikhub_call_logs(platform);
CREATE INDEX IF NOT EXISTS idx_tikhub_call_logs_endpoint ON tikhub_call_logs(endpoint);
CREATE INDEX IF NOT EXISTS idx_tikhub_call_logs_created_at ON tikhub_call_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_tikhub_call_logs_status ON tikhub_call_logs(status);
```

### 1.3 数据迁移脚本

**文件：** `migrations/012_migrate_tikhub_to_dedicated_pool.sql`

```sql
-- 将现有 TikHub 配置从 service_credentials 迁移到 tikhub_credentials
DO $$
DECLARE
  sc_record RECORD;
  new_cred_id BIGINT;
BEGIN
  -- 遍历 service_credentials 中 provider='tikhub' 的记录
  FOR sc_record IN
    SELECT id, label, secret_enc AS api_key, status, weight
    FROM service_credentials
    WHERE provider = 'tikhub'
  LOOP
    -- 插入到 tikhub_credentials
    INSERT INTO tikhub_credentials (
      label, api_key, base_url, status, max_concurrent, max_users
    )
    VALUES (
      sc_record.label,
      sc_record.api_key,
      'https://api.tikhub.io',
      CASE WHEN sc_record.status = 'enabled' THEN 'active' ELSE 'inactive' END,
      5,  -- 默认最大并发
      10  -- 默认最大用户数
    )
    RETURNING id INTO new_cred_id;

    RAISE NOTICE 'Migrated TikHub credential: % (old id: %, new id: %)', sc_record.label, sc_record.id, new_cred_id;
  END LOOP;

  -- 删除 service_credentials 中的 TikHub 记录（可选，建议先手动确认后执行）
  -- DELETE FROM service_credentials WHERE provider = 'tikhub';
END $$;
```

---

## 二、TikHub 适配器改造

**文件：** `app/adapters/tikhub.py`

### 2.1 改造 `_get_key_and_url` 函数

**修改前：** 使用 `pick_credential(provider="tikhub")` 从 `service_credentials` 选

**修改后：** 实现类似 AI 的池化逻辑

```python
async def _get_key_and_url(db: AsyncSession) -> tuple[int, str, str]:
    """
    从 tikhub_credentials 选择一个可用的 Key。
    优先选择 active_requests < max_concurrent 的 Key。
    """
    from app.models.tikhub_credential import TikHubCredential

    # 查找可用的 Key（status='active' 且未超并发）
    result = await db.execute(
        select(TikHubCredential).where(
            TikHubCredential.status == 'active',
            TikHubCredential.active_requests < TikHubCredential.max_concurrent
        ).order_by(TikHubCredential.active_requests.asc())  # 优先选择并发数低的
    )
    cred = result.scalars().first()

    if not cred:
        raise RuntimeError("No available TikHub credential (all busy or inactive)")

    # 增加并发计数
    cred.active_requests += 1
    await db.commit()

    return cred.id, cred.api_key, cred.base_url
```

### 2.2 调用后释放并发

在每个接口函数中，调用完成后释放并发：

```python
async def _release_credential(cred_id: int, db: AsyncSession):
    """释放并发计数"""
    await db.execute(
        text("UPDATE tikhub_credentials SET active_requests = GREATEST(active_requests - 1, 0) WHERE id = :id"),
        {"id": cred_id}
    )
    await db.commit()

async def get_user_profile(sec_user_id: str, db: AsyncSession, user_id: int = None) -> dict:
    cred_id, api_key, base_url = await _get_key_and_url(db)
    start = time.monotonic()
    status = 'success'
    error_msg = None

    try:
        # ... 原有调用逻辑 ...
        result = { ... }
        return result
    except Exception as e:
        status = 'failure'
        error_msg = str(e)
        raise
    finally:
        latency_ms = int((time.monotonic() - start) * 1000)
        await _release_credential(cred_id, db)

        # 记录调用日志
        await db.execute(
            insert(tikhub_call_logs).values(
                credential_id=cred_id,
                user_id=user_id,
                platform='douyin',
                endpoint='user_profile',
                status=status,
                latency_ms=latency_ms,
                error_message=error_msg
            )
        )
        await db.commit()
```

### 2.3 所有接口函数添加 `user_id` 参数

- `get_user_profile(sec_user_id, db, user_id=None)`
- `get_user_fans_info(user_id, db, caller_user_id=None)`
- `get_live_room_products(room_id, author_id, db, user_id=None)`

---

## 三、管理接口

**文件：** `app/routers/admin_tikhub.py`

### 3.1 `GET /api/admin/tikhub/stats` - 三维统计数据

**JWT 鉴权：** `require_admin`

**响应：**
```json
{
  "overview": {
    "total_calls": 15234,
    "today_calls": 892,
    "avg_latency_ms": 235.6,
    "active_keys": 3,
    "total_keys": 5
  },
  "endpoints": [
    { "endpoint": "user_profile", "calls": 8923, "percentage": 58.6 },
    { "endpoint": "fans_info", "calls": 4512, "percentage": 29.6 },
    { "endpoint": "live_products", "calls": 1799, "percentage": 11.8 }
  ],
  "users": [
    { "user_id": 123, "username": "operator1", "calls": 234 },
    { "user_id": 456, "username": "operator2", "calls": 156 }
  ],
  "trend": [
    { "date": "06-04", "calls": 890 },
    { "date": "06-05", "calls": 1024 },
    { "date": "06-06", "calls": 756 },
    { "date": "06-07", "calls": 892 }
  ]
}
```

**数据来源：**
- `overview`: 聚合 `tikhub_call_logs` 表
- `endpoints`: 按 `endpoint` 分组聚合
- `users`: 按 `user_id` 分组聚合，JOIN `users` 表获取 username
- `trend`: 按 `DATE(created_at)` 分组聚合（最近7天）

### 3.2 `GET /api/admin/tikhub/keys` - Key 列表

**响应：**
```json
{
  "items": [
    {
      "id": 1,
      "label": "tikhub-main",
      "api_key": "sk-xxxx",
      "base_url": "https://api.tikhub.io",
      "status": "active",
      "active_requests": 2,
      "max_concurrent": 5,
      "today_calls": 456,
      "total_calls": 12453,
      "last_tested_at": "2026-06-10T10:30:00Z",
      "last_latency_ms": 234,
      "created_at": "2026-06-01T00:00:00Z"
    }
  ],
  "total": 5
}
```

**数据来源：**
- 基础字段：`tikhub_credentials` 表
- `today_calls`: 聚合 `tikhub_call_logs` WHERE `credential_id = id` AND `DATE(created_at) = TODAY`
- `total_calls`: 聚合 `tikhub_call_logs` WHERE `credential_id = id`
- `last_tested_at`: 从日志表获取最近一次 status='success' 的时间

### 3.3 `POST /api/admin/tikhub/keys` - 新增 Key

**请求体：**
```json
{
  "label": "tikhub-main",
  "api_key": "sk-xxxxx",
  "base_url": "https://api.tikhub.io",
  "max_concurrent": 5,
  "max_users": 10
}
```

**响应：** 创建的 Key 完整信息

### 3.4 `PUT /api/admin/tikhub/keys/:id` - 编辑 Key

**请求体：**
```json
{
  "label": "tikhub-main-updated",
  "max_concurrent": 10
}
```

**响应：** 更新后的 Key 完整信息

### 3.5 `DELETE /api/admin/tikhub/keys/:id` - 删除 Key

**响应：** `{ "success": true }`

### 3.6 `POST /api/admin/tikhub/keys/:id/test` - 测试连通性

**响应：**
```json
{
  "status": "ok",
  "latency_ms": 234,
  "sample_nickname": "抖音官方账号"
}
```

**逻辑：** 调用 `test_connection(db)` 函数（已存在）

### 3.7 `POST /api/admin/tikhub/keys/:id/enable` - 启用 Key

**响应：** `{ "success": true }`

### 3.8 `POST /api/admin/tikhub/keys/:id/disable` - 停用 Key

**响应：** `{ "success": true }`

### 3.9 `GET /api/admin/tikhub/endpoints` - 接口列表和统计

**响应：**
```json
{
  "items": [
    {
      "endpoint": "user_profile",
      "platform": "douyin",
      "calls": 8923,
      "percentage": 58.6,
      "avg_latency_ms": 245.3,
      "success_rate": 0.98
    },
    {
      "endpoint": "fans_info",
      "platform": "douyin",
      "calls": 4512,
      "percentage": 29.6,
      "avg_latency_ms": 312.7,
      "success_rate": 0.95
    }
  ]
}
```

**数据来源：** 聚合 `tikhub_call_logs` 按 `endpoint` 分组

### 3.10 `GET /api/admin/tikhub/users` - 用户调用排行

**Query 参数：**
- `start_date`: YYYYMMDD（可选，默认今日）
- `end_date`: YYYYMMDD（可选，默认明日）
- `limit`: 默认 20

**响应：**
```json
{
  "items": [
    {
      "user_id": 123,
      "username": "operator1",
      "role": "operator",
      "calls": 234,
      "last_called_at": "2026-06-10T14:30:00Z"
    }
  ],
  "total": 45
}
```

**数据来源：** 聚合 `tikhub_call_logs` JOIN `users` 表，按 `calls DESC` 排序

---

## 四、Model 定义

**文件：** `app/models/tikhub_credential.py`

```python
from sqlalchemy import Column, BigInteger, String, Integer, DateTime
from sqlalchemy.sql import func

from app.core.database import Base

class TikHubCredential(Base):
    __tablename__ = "tikhub_credentials"

    id = Column(BigInteger, primary_key=True, index=True)
    provider = Column(String(64), nullable=False, default='tikhub')
    label = Column(String(128))
    api_key = Column(String, nullable=False)
    base_url = Column(String(512), nullable=False, default='https://api.tikhub.io')
    status = Column(String(32), nullable=False, default='active')
    active_requests = Column(Integer, nullable=False, default=0)
    max_concurrent = Column(Integer, nullable=False, default=5)
    max_users = Column(Integer, nullable=False, default=10)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

**文件：** `app/models/tikhub_call_log.py`

```python
from sqlalchemy import Column, BigInteger, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.core.database import Base

class TikHubCallLog(Base):
    __tablename__ = "tikhub_call_logs"

    id = Column(BigInteger, primary_key=True, index=True)
    credential_id = Column(BigInteger, ForeignKey('tikhub_credentials.id', ondelete='SET NULL'))
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='SET NULL'))
    platform = Column(String(64), nullable=False)
    endpoint = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False)
    latency_ms = Column(Integer)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

---

## 五、注册路由

**文件：** `app/main.py`

```python
from app.routers import admin_tikhub

app.include_router(admin_tikhub.router, prefix="/api/admin/tikhub", tags=["TikHub管理"])
```

---

## 六、测试验证

### 6.1 数据库迁移测试
- 执行 010/011/012 迁移文件
- 验证 `tikhub_credentials` 表创建成功
- 验证 `tikhub_call_logs` 表创建成功
- 验证数据从 `service_credentials` 迁移到 `tikhub_credentials`

### 6.2 接口测试
- 测试 `/api/admin/tikhub/stats` 返回正确的统计数据
- 测试 Key 管理 CRUD 接口
- 测试并发控制逻辑（调用 `get_user_profile` 时 active_requests 增加）

### 6.3 日志记录测试
- 调用 TikHub 接口后，检查 `tikhub_call_logs` 表是否正确记录
- 验证 user_id、platform、endpoint、status、latency_ms 字段

---

## 七、回传 PM 内容

完成后回传以下信息：

1. ✅ 数据库迁移文件已创建（010/011/012）
2. ✅ TikHub 适配器已改造（支持并发控制 + 日志记录）
3. ✅ 管理接口已实现（10 个接口）
4. ✅ 测试验证通过

并告知：
- 迁移后 `service_credentials` 中的 TikHub 记录是否已删除
- 是否需要在前端调整前兼容旧接口

---

**PM 备注：**
- 所有接口需要 JWT 鉴权（require_admin 或 require_operator）
- 统计接口返回的百分比用 0-100 范围（不是 0-1）
- created_at 统一使用 TIMESTAMPTZ 类型
- 记得在 `app/models/__init__.py` 中导出新的 Model
