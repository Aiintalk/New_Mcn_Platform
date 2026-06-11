# MCN_Backend_Agent — M1 Sprint 3 任务指令

> 角色：MCN_Backend_Agent（后端开发 Claude）  
> 工作目录：`backend/`  
> PM 生成时间：2026-06-06（已更新：含 Key Pool + 真实 AI/TikHub 接入）  
> 前置条件：Sprint 2 验收通过，工作台 API 已就绪  
> 完成后：回传 PM，等待联调与测试 Claude 介入

---

## 必读文档

1. `../MCN_M1_Base_基层文档包/MCN_M1_Base_API_utf8_bom.md` ← 最高优先级
2. `../MCN_M1_Base_基层文档包/MCN_M1_Base_Permission_utf8_bom.md` ← 权限/数据隔离规则

---

## ⚠️ Sprint 2 热修复（先确认）

`GET /api/workspace/tools` 已改为返回 `status IN ('online', 'dev')` 的工具。
请确认修改已生效：`GET /api/workspace/tools` 应返回 persona-writer(online) + benchmark/qianchuan/review/subtitle(dev)，共 5 条。

---

## Step 0：数据库 Schema 变更

在执行任何业务逻辑前，先对数据库执行以下 DDL（在 `mcn_m1` 数据库执行）：

```sql
-- 为 service_credentials 表增加 config 字段（存储每个 Key 的模型/端点等配置）
ALTER TABLE service_credentials ADD COLUMN IF NOT EXISTS config JSONB;

-- 为 kols 表增加 tikhub_raw 字段（存储 TikHub API 原始响应）
ALTER TABLE kols ADD COLUMN IF NOT EXISTS tikhub_raw JSONB;
```

**config JSONB 示例（按 provider 类型）：**
```json
// provider = "ai"
{"model": "claude-haiku-4-5-20251001", "base_url": "https://yunwu.ai/v1", "max_tokens": 4096, "temperature": 0.7}

// provider = "tikhub"  
{"base_url": "https://api.tikhub.io"}

// provider = "oss"（结构预留，本 Sprint 不实现真实调用）
{"bucket": "your-bucket", "endpoint": "oss-cn-hangzhou.aliyuncs.com", "region": "cn-hangzhou"}
```

---

## Step 1：CredentialSelector 服务（`app/services/credential_selector.py`）

**新建文件**，实现通用 Key 池选择逻辑，供 AI / TikHub / OSS adapter 复用：

```python
"""
app/services/credential_selector.py

通用 Key 池选择器：
- 按 provider 过滤，选取状态可用、未超限、未冷却的 Key
- 加权随机选择（weight 字段）
- 成功时：fail_count 归零，quota_used += 1
- 失败时：fail_count += 1；累计 3 次后冷却 5 分钟
"""
import random
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import ServiceCredential
from app.database import AsyncSessionLocal


async def pick_credential(
    provider: str,
    db: AsyncSession,
    model: str = None,
) -> ServiceCredential:
    """
    从 Key 池中选择一个可用的 Credential。
    
    Args:
        provider: 服务提供商标识，如 "ai" / "tikhub" / "oss"
        db: AsyncSession
        model: 仅 provider="ai" 时使用，匹配 config->>'model'
    
    Returns:
        ServiceCredential 对象
    
    Raises:
        RuntimeError: 无可用 Key 时抛出
    """
    now = datetime.now(timezone.utc)
    
    # 查询可用 Key：status=enabled，cooldown 未到期，quota 未超限
    result = await db.execute(
        text("""
            SELECT * FROM service_credentials
            WHERE provider = :provider
              AND status = 'enabled'
              AND (cooldown_until IS NULL OR cooldown_until < :now)
              AND (quota_limit IS NULL OR quota_used < quota_limit)
            ORDER BY weight DESC
        """),
        {"provider": provider, "now": now},
    )
    rows = result.fetchall()
    
    # model 过滤（仅 AI provider）
    if model and rows:
        filtered = [r for r in rows if r.config and r.config.get("model") == model]
        if filtered:
            rows = filtered
    
    if not rows:
        raise RuntimeError(f"No available credential for provider={provider}")
    
    # 加权随机选择
    weights = [max(r.weight or 1, 1) for r in rows]
    selected = random.choices(rows, weights=weights, k=1)[0]
    return selected


async def report_success(credential_id: int, db: AsyncSession) -> None:
    """调用成功：fail_count 归零，quota_used += 1"""
    await db.execute(
        text("""
            UPDATE service_credentials
            SET fail_count = 0,
                quota_used = COALESCE(quota_used, 0) + 1,
                updated_at = NOW()
            WHERE id = :id
        """),
        {"id": credential_id},
    )
    await db.commit()


async def report_failure(credential_id: int, db: AsyncSession) -> None:
    """
    调用失败：fail_count += 1；
    累计 >= 3 次时冷却 5 分钟（cooldown_until = now + 5min）
    """
    result = await db.execute(
        text("SELECT fail_count FROM service_credentials WHERE id = :id"),
        {"id": credential_id},
    )
    row = result.fetchone()
    new_fail_count = (row.fail_count or 0) + 1
    
    cooldown_until = None
    if new_fail_count >= 3:
        cooldown_until = datetime.now(timezone.utc) + timedelta(minutes=5)
    
    await db.execute(
        text("""
            UPDATE service_credentials
            SET fail_count = :fail_count,
                cooldown_until = :cooldown_until,
                updated_at = NOW()
            WHERE id = :id
        """),
        {"id": credential_id, "fail_count": new_fail_count, "cooldown_until": cooldown_until},
    )
    await db.commit()
```

---

## Step 2：AI Adapter（`app/adapters/ai.py`）

**新建文件**，真实调用 OpenAI 兼容代理（yunwu.ai），使用 Key 池：

```python
"""
app/adapters/ai.py

AI 服务适配器：
- 使用 Key 池选取 Credential（provider="ai"）
- 直接 httpx POST，不依赖 OpenAI SDK
- 并发限制 Semaphore(3)（全局）
- 超时 120s
- 成功/失败后回报 CredentialSelector
"""
import asyncio
import time
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.credential_selector import pick_credential, report_success, report_failure
from app.database import AsyncSessionLocal

# 全局并发限制
_semaphore = asyncio.Semaphore(3)


async def chat(
    messages: list[dict],
    db: AsyncSession,
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """
    调用 AI 接口，返回 assistant 消息内容。
    
    Args:
        messages: OpenAI 格式的消息列表，如 [{"role": "user", "content": "..."}]
        db: AsyncSession（用于 Key 池）
        model: 可选，默认从 Key 的 config 中读取
        temperature: 采样温度
        max_tokens: 最大 token 数
    
    Returns:
        str: AI 返回的文本内容
    
    Raises:
        RuntimeError: 无可用 Key 或调用失败
    """
    credential = await pick_credential(provider="ai", db=db, model=model)
    
    config = credential.config or {}
    actual_model = model or config.get("model", "claude-haiku-4-5-20251001")
    base_url = config.get("base_url", "https://yunwu.ai/v1")
    api_key = credential.secret_enc  # 注意：secret_enc 此处存储解密后的明文（或在查询时解密）
    
    # 若 secret_enc 是加密存储，需先解密（调用 decrypt_secret 工具函数）
    # from app.utils.crypto import decrypt_secret
    # api_key = decrypt_secret(credential.secret_enc)
    
    payload = {
        "model": actual_model,
        "messages": messages,
        "temperature": config.get("temperature", temperature),
        "max_tokens": config.get("max_tokens", max_tokens),
    }
    
    async with _semaphore:
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                await report_success(credential.id, db)
                return content
        except Exception as e:
            await report_failure(credential.id, db)
            raise RuntimeError(f"AI call failed: {e}") from e


async def test_connection(db: AsyncSession) -> dict:
    """
    测试 AI 连通性。
    
    Returns:
        {"status": "ok", "model": "...", "latency_ms": 123, "reply": "..."}
    """
    start = time.monotonic()
    try:
        reply = await chat(
            messages=[{"role": "user", "content": "Say 'hello' in one word."}],
            db=db,
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        # 获取实际使用的 Key 信息
        credential = await pick_credential(provider="ai", db=db)
        config = credential.config or {}
        return {
            "status": "ok",
            "model": config.get("model", "claude-haiku-4-5-20251001"),
            "latency_ms": latency_ms,
            "reply": reply,
        }
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "error",
            "latency_ms": latency_ms,
            "error": str(e),
        }
```

> ⚠️ **安全说明**：`secret_enc` 字段存储加密后的密文。如果 Sprint 2 密钥池 API 已实现 `cryptography.fernet` 加密，需在此处调用解密函数。若当前 `secret_enc` 存储明文（Sprint 3 过渡期可接受），可直接使用，但在 Sprint 4 前必须统一加密存储。

---

## Step 3：TikHub Adapter（`app/adapters/tikhub.py`）

**新建文件**，实现 3 个真实 TikHub 接口，使用 Key 池：

```python
"""
app/adapters/tikhub.py

TikHub 服务适配器：
- 使用 Key 池选取 Credential（provider="tikhub"）
- 实现 3 个真实 Douyin API 接口
- 原始响应完整存入 kols.tikhub_raw JSONB 后再提取结构化字段
"""
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.credential_selector import pick_credential, report_success, report_failure


async def _get_client_and_key(db: AsyncSession) -> tuple[str, str]:
    """返回 (api_key, base_url)"""
    credential = await pick_credential(provider="tikhub", db=db)
    config = credential.config or {}
    base_url = config.get("base_url", "https://api.tikhub.io")
    api_key = credential.secret_enc  # 同 AI adapter，如已加密需先解密
    return credential.id, api_key, base_url


async def get_user_profile(sec_user_id: str, db: AsyncSession) -> dict:
    """
    获取抖音用户基础信息。
    
    GET /api/v1/douyin/app/v3/handler_user_profile
    参数: sec_user_id
    返回: nickname / uid / room_id / unique_id + 完整原始响应
    
    Returns:
        {
            "raw": {...},  # 完整 TikHub 响应，存入 kols.tikhub_raw
            "nickname": "...",
            "uid": "...",
            "room_id": "...",
            "unique_id": "...",
        }
    """
    cred_id, api_key, base_url = await _get_client_and_key(db)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{base_url}/api/v1/douyin/app/v3/handler_user_profile",
                params={"sec_user_id": sec_user_id},
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
            raw = response.json()
            await report_success(cred_id, db)
            
            # 提取结构化字段（路径根据实际 TikHub 响应结构调整）
            user_data = raw.get("data", {}).get("user", {})
            return {
                "raw": raw,
                "nickname": user_data.get("nickname"),
                "uid": str(user_data.get("uid", "")),
                "room_id": str(user_data.get("room_id", "")),
                "unique_id": user_data.get("unique_id"),
            }
    except Exception as e:
        await report_failure(cred_id, db)
        raise RuntimeError(f"TikHub get_user_profile failed: {e}") from e


async def get_user_fans_info(user_id: int, db: AsyncSession) -> dict:
    """
    获取抖音达人粉丝数据。
    
    POST /api/v1/douyin/index/fetch_daren_great_user_fans_info
    参数: user_id（数字型 uid）
    返回: 粉丝数相关数据 + 完整原始响应
    
    Returns:
        {
            "raw": {...},
            "fans_count": 12345,
            ...
        }
    """
    cred_id, api_key, base_url = await _get_client_and_key(db)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{base_url}/api/v1/douyin/index/fetch_daren_great_user_fans_info",
                json={"user_id": user_id},
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            raw = response.json()
            await report_success(cred_id, db)
            
            fans_data = raw.get("data", {})
            return {
                "raw": raw,
                "fans_count": fans_data.get("fans_count") or fans_data.get("follower_count"),
            }
    except Exception as e:
        await report_failure(cred_id, db)
        raise RuntimeError(f"TikHub get_user_fans_info failed: {e}") from e


async def get_live_room_products(
    room_id: str,
    author_id: str,
    db: AsyncSession,
    limit: int = 100,
) -> list:
    """
    获取直播间商品列表。
    
    GET /api/v1/douyin/web/fetch_live_room_product_result
    参数: room_id / author_id / limit
    返回: data.promotions 列表 + 完整原始响应
    
    Returns:
        [
            {"raw": {...}, "promotions": [...]},
        ]
    """
    cred_id, api_key, base_url = await _get_client_and_key(db)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{base_url}/api/v1/douyin/web/fetch_live_room_product_result",
                params={"room_id": room_id, "author_id": author_id, "limit": limit},
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
            raw = response.json()
            await report_success(cred_id, db)
            
            promotions = raw.get("data", {}).get("promotions", [])
            return {"raw": raw, "promotions": promotions}
    except Exception as e:
        await report_failure(cred_id, db)
        raise RuntimeError(f"TikHub get_live_room_products failed: {e}") from e


async def test_connection(db: AsyncSession) -> dict:
    """
    测试 TikHub 连通性（用已知测试 sec_user_id 验证）。
    
    Returns:
        {"status": "ok/error", "latency_ms": 123}
    """
    import time
    start = time.monotonic()
    # 使用抖音官方账号的 sec_user_id 做连通性测试
    TEST_SEC_USER_ID = "MS4wLjABAAAA5ZrIrbgva3dqI80CsHQMCUPAR5Q5KFBOMOrMnVKESnzNPk7sLBRKCTMSzfQkUzSZ"
    try:
        result = await get_user_profile(TEST_SEC_USER_ID, db)
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "ok",
            "latency_ms": latency_ms,
            "sample_nickname": result.get("nickname"),
        }
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "error",
            "latency_ms": latency_ms,
            "error": str(e),
        }
```

---

## Step 4：OSS Adapter 占位（`app/adapters/oss.py`）

**新建文件**，结构预留，真实调用在阿里云凭证就绪后实现：

```python
"""
app/adapters/oss.py

阿里云 OSS 适配器（M1 阶段：结构预留，真实调用待 OSS 凭证就绪后实现）

凭证配置来自 service_credentials 表（provider="oss"），
config JSONB 字段结构：
{
    "bucket": "your-bucket-name",
    "endpoint": "oss-cn-hangzhou.aliyuncs.com",
    "region": "cn-hangzhou"
}
secret_enc 存储 access_key_secret（加密）；label 中填写 access_key_id
"""
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.credential_selector import pick_credential


async def get_download_url(oss_key: str, db: AsyncSession, expires: int = 3600) -> str:
    """
    生成 OSS 文件临时下载 URL。
    
    当前返回 Mock URL；真实实现需要：
    1. pick_credential(provider="oss")
    2. oss2.Auth(access_key_id, access_key_secret)
    3. bucket.sign_url('GET', oss_key, expires)
    
    TODO: 阿里云凭证就绪后替换 Mock 实现
    """
    # Mock 实现
    return f"https://mock-oss.example.com/{oss_key}?token=mock&expires={expires}"


async def upload_file(
    oss_key: str,
    content: bytes,
    content_type: str,
    db: AsyncSession,
) -> str:
    """
    上传文件到 OSS，返回 oss_key。
    TODO: 真实实现待凭证就绪
    """
    raise NotImplementedError("OSS upload not implemented yet - waiting for credentials")
```

**同时在 `requirements.txt` 中添加 OSS SDK 依赖（不调用，仅预装）：**
```
oss2>=2.18.0
```

---

## Step 5：管理员系统测试接口（`app/routers/admin_system.py`）

**新建文件**，提供 AI 和 TikHub 连通性测试接口：

```python
"""
app/routers/admin_system.py

管理员系统维护接口：
- GET  /api/health              — 公开健康检查（已在 main.py，此处不重复）
- POST /api/admin/system/ai-test      — 测试 AI Key 池连通性
- POST /api/admin/system/tikhub-test  — 测试 TikHub Key 池连通性
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import require_admin
from app.adapters import ai as ai_adapter
from app.adapters import tikhub as tikhub_adapter
from app.utils.response import success_response

router = APIRouter(prefix="/admin/system", tags=["admin-system"])


@router.post("/ai-test")
async def test_ai_connection(
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    测试 AI Key 池连通性。
    发送一条简单消息，返回模型、延迟、回复内容。
    权限：admin + 已改密
    """
    result = await ai_adapter.test_connection(db)
    return success_response(data=result)


@router.post("/tikhub-test")
async def test_tikhub_connection(
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    测试 TikHub Key 池连通性。
    调用真实接口验证 Key 可用性。
    权限：admin + 已改密
    """
    result = await tikhub_adapter.test_connection(db)
    return success_response(data=result)
```

---

## Step 6：任务 API（`app/routers/tasks.py`）

### 运营端

**`GET /api/tasks`**（需登录 + 已改密）
- 只返回 `created_by = current_user.id` 的任务（数据隔离）
- 支持分页（page / page_size，允许 10/20/50）
- 支持筛选：`status`（pending/running/success/failed）、`tool_code`
- 按 `created_at DESC` 排序
- 返回字段：`id / task_no / tool_code / tool_name / status / created_at / finished_at / duration_ms / error_code`

**`GET /api/tasks/{task_id}`**（需登录 + 已改密）
- `created_by != current_user.id` → `PERMISSION_DENIED`（不泄露数据存在）
- 返回任务详情 + `task_logs` 列表

### 管理员端

**`GET /api/admin/tasks`**（admin + 已改密）
- 返回所有用户的任务（无 created_by 过滤）
- 支持分页 + 筛选（同上，额外支持 `user_id` 筛选）
- 额外返回 `created_by_username` 字段（JOIN users）

**`GET /api/admin/tasks/{task_id}`**（admin + 已改密）
- 返回任务详情 + task_logs

---

## Step 7：产出 API（`app/routers/outputs.py`）

### 运营端

**`GET /api/outputs`**（需登录 + 已改密）
- 只返回 `created_by = current_user.id` 且 `deleted_at IS NULL`
- 支持分页、`tool_code` 筛选
- 按 `created_at DESC` 排序
- 返回字段：`id / title / tool_code / tool_name / word_count / created_at`

**`GET /api/outputs/{output_id}`**（需登录 + 已改密）
- `created_by != current_user.id` → `PERMISSION_DENIED`
- 返回产出详情（含 content 字段）

**`DELETE /api/outputs/{output_id}`**（需登录 + 已改密）
- 软删除：`deleted_at = now()`
- 只能删除自己的产出
- 写 `operation_logs`：`action=delete_output`

### 管理员端

**`GET /api/admin/outputs`**（admin + 已改密）
- 返回所有用户产出（deleted_at IS NULL）
- 支持分页 + `user_id / tool_code` 筛选
- 额外返回 `created_by_username`

**`DELETE /api/admin/outputs/{output_id}`**（admin + 已改密）
- 软删除任意产出
- 写 `operation_logs`：`action=admin_delete_output`

---

## Step 8：文件 API（`app/routers/files.py`）

**`GET /api/files`**（需登录 + 已改密）
- 只返回 `created_by = current_user.id` 且 `deleted_at IS NULL`
- 支持分页、`output_id` 筛选

**`GET /api/files/{file_id}/download-url`**（需登录 + 已改密）
- `created_by != current_user.id` → `PERMISSION_DENIED`
- **调用 `oss.get_download_url()`**（当前返回 Mock URL，OSS 凭证就绪后自动升级为真实签名 URL）
- 返回：`{"download_url": "...", "expires_in": 3600}`

**`DELETE /api/files/{file_id}`**（需登录 + 已改密）
- 软删除：`deleted_at = now()`
- 只能删除自己的文件
- 写 `operation_logs`：`action=delete_file`

---

## Step 9：日志 API（`app/routers/admin_logs.py`）

**`GET /api/admin/logs/operation`**（admin + 已改密）
- 返回 `operation_logs` 列表
- 支持分页、`user_id / action` 筛选
- 按 `created_at DESC` 排序

**`GET /api/admin/logs/external`**（admin + 已改密）
- 返回 `external_service_logs` 列表
- 支持分页、`service / status` 筛选
- 按 `created_at DESC` 排序

---

## Step 10：密钥池 API（`app/routers/admin_credentials.py`）

**`GET /api/admin/config/credentials`**（admin + 已改密）
- 返回密钥列表，**只回显 `secret_tail`，不返回 `secret_enc`**
- 返回 `config` 字段（完整 JSONB）
- 按 `provider / created_at ASC` 排序

**`POST /api/admin/config/credentials`**（admin + 已改密）
- 入参：`provider / label / secret（明文）/ weight / quota_limit / config（JSONB，可选）`
- 后端用 `ENCRYPTION_KEY` 对 secret 加密后存入 `secret_enc`
- 截取最后 4 位存 `secret_tail`
- 写 `operation_logs`：`action=create_credential`

**`PATCH /api/admin/config/credentials/{id}`**（admin + 已改密）
- 可更新：`label / status / weight / quota_limit / config`
- 写 `operation_logs`：`action=update_credential`

**`DELETE /api/admin/config/credentials/{id}`**（admin + 已改密）
- 物理删除（密钥不做软删）
- 写 `operation_logs`：`action=delete_credential`

---

## Step 11：注册所有新路由

在 `app/main.py` 中注册：

```python
from app.routers import tasks, outputs, files, admin_logs, admin_credentials, admin_system
app.include_router(tasks.router, prefix="/api")
app.include_router(outputs.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(admin_logs.router, prefix="/api")
app.include_router(admin_credentials.router, prefix="/api")
app.include_router(admin_system.router, prefix="/api")
```

---

## Step 12：更新 `.env.example`

在 `.env.example` 中补充以下变量：

```dotenv
# ─── AI 服务（默认值，可被 DB service_credentials 覆盖）───
LLM_API_BASE=https://yunwu.ai/v1
LLM_API_KEY=your_llm_api_key_here
LLM_MODEL=claude-haiku-4-5-20251001

# ─── TikHub 服务（可被 DB service_credentials 覆盖）──────
TIKHUB_API_KEY=your_tikhub_api_key_here
TIKHUB_BASE_URL=https://api.tikhub.io

# ─── 阿里云 OSS（凭证就绪后填写）────────────────────────
# OSS_ACCESS_KEY_ID=your_access_key_id
# OSS_ACCESS_KEY_SECRET=your_access_key_secret
# OSS_BUCKET=your-bucket-name
# OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
# OSS_REGION=cn-hangzhou
```

确保 `.gitignore` 包含 `.env`（不提交真实 Key）。

---

## 不做什么

- 不实现 OSS 真实文件上传/下载（`download-url` 接口当前仍返回 Mock URL）
- 不实现 KOL 管理业务 API（kols 表字段已加，业务逻辑在后续 Sprint）
- 不实现 Alembic 迁移（继续使用 SQL 脚本，Step 0 手动执行）

---

## 验收标准

### 原有接口
1. `GET /api/tasks` operator 只能看到自己的任务，admin 调 `/api/admin/tasks` 可见全量
2. operator 调 `GET /api/tasks/{别人的task_id}` → `PERMISSION_DENIED`
3. `GET /api/outputs` operator 只能看到自己的未删除产出
4. `DELETE /api/outputs/{id}` 软删除，`deleted_at` 有值，记录保留
5. `GET /api/files/{id}/download-url` 返回 Mock URL 字符串
6. `GET /api/admin/logs/operation` 返回历史操作日志（应有 Sprint 1-2 的记录）
7. `POST /api/admin/config/credentials` 创建密钥，响应只含 `secret_tail` 不含 `secret_enc`
8. 所有 admin 接口 operator Token 调用 → `PERMISSION_DENIED`

### 新增：Key Pool + Adapter
9. `service_credentials` 表存在 `config JSONB` 字段
10. `kols` 表存在 `tikhub_raw JSONB` 字段
11. `POST /api/admin/config/credentials`（provider=ai）可携带 `config` 字段并成功存储
12. `POST /api/admin/system/ai-test` 返回 `{"status": "ok", "model": "...", "latency_ms": ...}`（需 DB 中有 provider=ai 的可用 Key）
13. `POST /api/admin/system/tikhub-test` 返回 `{"status": "ok/error", "latency_ms": ...}`（需 DB 中有 provider=tikhub 的可用 Key）
14. CredentialSelector：当某个 Key 连续失败 3 次后，`cooldown_until` 有值，该 Key 暂时不被选中

---

## 完成后输出格式

```
# 后端 Claude 执行结果 — M1 Sprint 3
## 1. 本次任务
## 2. 完成内容
## 3. 新增 API 清单（含路径、方法、权限）
## 4. 新增 Adapter/Service 文件清单
## 5. 修改文件清单
## 6. 数据隔离验证（operator 无法看到他人数据的测试结果）
## 7. 自测结果（关键接口 curl 命令 + 实际响应）
## 8. AI/TikHub 连通性测试结果
## 9. 未完成事项
## 10. 需要 PM 决策的问题
## 11. 建议下一步
```
