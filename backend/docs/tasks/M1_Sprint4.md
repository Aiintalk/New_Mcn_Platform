# MCN_Backend_Agent — M1 Sprint 4 任务指令

> 角色：MCN_Backend_Agent（后端开发 Claude）  
> 工作目录：`backend/`  
> PM 生成时间：2026-06-07  
> 前置条件：Sprint 3 验收通过，AI Key 池与基础设施就绪  
> 完成后：回传 PM，等待前端联调与测试 Claude 介入

---

## Sprint 4 目标

构建 AI 服务管理模块，实现多服务商 Key 池并发调度、模型管理与使用统计，供管理后台进行 AI 资源的全生命周期管理。

---

## 已完成功能清单

### Key 池管理

| 功能 | 状态 |
|---|---|
| credentials 表（含 base_url / active_requests / max_concurrent / max_users / last_tested_at / last_latency_ms） | ✅ 完成 |
| GET /api/admin/ai/keys — Key 列表（含今日/总调用量） | ✅ 完成 |
| POST /api/admin/ai/keys — 添加 Key（自动填充 base_url） | ✅ 完成 |
| PATCH /api/admin/ai/keys/{id} — 编辑 Key | ✅ 完成 |
| DELETE /api/admin/ai/keys/{id} — 删除 Key | ✅ 完成 |
| POST /api/admin/ai/keys/{id}/test — 连通性测试（真实调用 /v1/models） | ✅ 完成 |

### 并发调度与排队机制

| 功能 | 状态 |
|---|---|
| FOR UPDATE SKIP LOCKED 原子锁定 Key | ✅ 完成 |
| active_requests +1 / -1 并发计数（DB 级，多进程安全） | ✅ 完成 |
| GREATEST(active_requests-1, 0) 防止负数 | ✅ 完成 |
| asyncio.Queue 排队等待（无槽位时入队） | ✅ 完成 |
| 30 秒排队超时，超时后抛 RuntimeError | ✅ 完成 |
| _release() 释放后自动唤醒队列下一个等待者 | ✅ 完成 |

### 多服务商支持

| 功能 | 状态 |
|---|---|
| _pick_and_lock(db, provider) 按 provider 筛选 Key | ✅ 完成 |
| chat(provider=...) 传入 provider，云雾/硅基流动/GLM 各用各自 Key 池 | ✅ 完成 |
| _DEFAULT_BASE_URLS 内置默认地址（支持环境变量覆盖） | ✅ 完成 |

### 模型管理

| 功能 | 状态 |
|---|---|
| ai_models 表（含 last_tested_at / last_latency_ms） | ✅ 完成 |
| GET /api/admin/ai/models — 模型列表（含总调用/Token 统计） | ✅ 完成 |
| POST /api/admin/ai/models — 添加模型 | ✅ 完成 |
| PATCH /api/admin/ai/models/{id} — 编辑模型 | ✅ 完成 |
| DELETE /api/admin/ai/models/{id} — 删除模型 | ✅ 完成 |
| POST /api/admin/ai/models/{id}/test — 模型测试（按 provider 选 Key，成功/失败均写回） | ✅ 完成 |

### 使用统计

| 功能 | 状态 |
|---|---|
| ai_call_logs 表（每次调用写入） | ✅ 完成 |
| GET /api/admin/ai/stats — 汇总统计 + 按模型分布 + Token 趋势 | ✅ 完成 |
| service_status 服务状态判断（healthy / degraded / overloaded / unavailable） | ✅ 完成 |
| queue_length / current_active / total_capacity 实时字段 | ✅ 完成 |

---

## 核心逻辑说明

### app/adapters/yunwu.py — Key 池选取 + 并发控制

```
_pick_and_lock(db, provider)
  ↓ UPDATE credentials ... WHERE provider=:provider AND active_requests < max_concurrent
  ↓ FOR UPDATE SKIP LOCKED — 防止并发竞争
  ↓ RETURNING id, api_key, COALESCE(base_url, :fallback)
  
chat(messages, db, model_id, provider, ...)
  ↓ _pick_and_lock → 无槽位 → asyncio.Queue 入队等待（30s 超时）
  ↓ db.commit() 提交 +1，让其他协程可见
  ↓ httpx POST {base_url}/chat/completions
  ↓ finally: _release() → GREATEST(active_requests-1, 0)
           → 唤醒队列下一个等待者
           → AiCallLog 写入 ai_call_logs
           → db.commit()
```

**_DEFAULT_BASE_URLS（支持环境变量覆盖）：**

```python
_DEFAULT_BASE_URLS = {
    "yunwu":       os.getenv("YUNWU_BASE_URL",      "https://yunwu.ai/v1"),
    "siliconflow": os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"),
    "glm":         os.getenv("GLM_BASE_URL",         "https://open.bigmodel.cn/api/paas/v4"),
}
```

新增服务商只需在 DB 录入 Key + 在 `_DEFAULT_BASE_URLS` 加一行即可，无需改其他逻辑。

### app/services/ai_service.py（待实现）

预留位置，后续 persona-writer 等业务工具通过此层调用 yunwu_adapter.chat()，传入 feature 和 user_id 用于 ai_call_logs 分类统计。

### app/routers/admin_ai.py — 所有接口

```
GET    /api/admin/ai/keys          Key 列表（SQL JOIN ai_call_logs 统计今日/总调用）
POST   /api/admin/ai/keys          添加 Key（自动填 base_url）
PATCH  /api/admin/ai/keys/{id}     编辑 Key
DELETE /api/admin/ai/keys/{id}     删除 Key
POST   /api/admin/ai/keys/{id}/test 连通性测试（真实 GET /v1/models，写回 last_tested_at/latency）

GET    /api/admin/ai/models        模型列表（JOIN ai_call_logs 统计）
POST   /api/admin/ai/models        添加模型
PATCH  /api/admin/ai/models/{id}   编辑模型
DELETE /api/admin/ai/models/{id}   删除模型
POST   /api/admin/ai/models/{id}/test 模型测试（按 m.provider 选 Key，成功/失败均写回）

GET    /api/admin/ai/stats         汇总 + by_model + token_trend
```

**service_status 判断逻辑：**

```python
if total_capacity == 0 or healthy_keys == 0:      → "unavailable"
elif queue_length > 0 or current_active >= total_capacity: → "overloaded"
elif healthy_keys / total_keys < 0.5:              → "degraded"
else:                                               → "healthy"
```

---

## 数据库变更记录

| 迁移文件 | 内容 |
|---|---|
| `migrations/003_ai_tables.sql` | 新建 credentials / ai_models / ai_call_logs 三张表及索引 |
| `migrations/004_credentials_test_fields.sql` | credentials 表加 last_tested_at / last_latency_ms |
| `migrations/005_ai_models_test_fields.sql` | ai_models 表加 last_tested_at / last_latency_ms |

**执行顺序：** 003 → 004 → 005（003 需在 001 之后，确保 set_updated_at() 函数已存在）

---

## 验收标准

1. `GET /api/admin/ai/keys` 返回 `today_calls` / `total_calls` / `last_tested_at` / `last_latency_ms`
2. `POST /api/admin/ai/keys/{id}/test` 真实调用服务商接口，成功写回 `last_tested_at` / `last_latency_ms`
3. `POST /api/admin/ai/models/{id}/test` 按模型 provider 选 Key，成功/失败均写回
4. `GET /api/admin/ai/stats` 返回 `summary.service_status` / `queue_length` / `current_active` / `total_capacity`
5. 硅基流动 Key（provider=siliconflow）不会被云雾请求选中，各 provider Key 池独立
6. 所有并发请求走 DB 级 `FOR UPDATE SKIP LOCKED`，进程重启后 active_requests 可手动归零

---

## 未完成 / 后续事项

- `app/services/ai_service.py` 业务封装层（persona-writer 接入时实现）
- ai_call_logs `feature` 字段分类统计（依赖业务工具接入后再补 stats 筛选）
- 管理后台 stats 页面前端联调（前端已有 mock，待真实接口联调）
