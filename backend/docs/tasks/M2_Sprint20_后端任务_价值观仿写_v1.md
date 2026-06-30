# M2 Sprint20 后端任务 — 价值观仿写（values-writer）v1

> 编写时间：2026-06-26
> 分支：`feature/kol-workspace`

---

## 一、任务范围

| # | 内容 | 文件 |
|---|------|------|
| 1 | Migration 043 | `backend/migrations/043_values_writer.sql` |
| 2 | ORM 模型 | `backend/app/models/values_writer.py` |
| 3 | 管理端配置接口 | `backend/app/routers/admin_values_writer.py` |
| 4 | 运营端业务接口 | `backend/app/routers/operator_values_writer.py` |
| 5 | main.py 注册 | `backend/app/main.py` |
| 6 | conftest.py 更新 | `backend/tests/conftest.py` |
| 7 | 集成测试 | `backend/tests/integration/routers/test_operator_values_writer.py` |

---

## 二、数据库设计（Migration 043）

### 表：`values_writer_configs`

```sql
CREATE TABLE IF NOT EXISTS values_writer_configs (
    id              BIGSERIAL PRIMARY KEY,
    config_key      VARCHAR(64) NOT NULL UNIQUE,
    -- Prompt 配置
    extract_values_prompt   TEXT,     -- Step 1: 从人物档案 + 素材中提炼价值观
    emotion_direction_prompt TEXT,    -- Step 2: 推导情绪方向
    writing_prompt          TEXT,     -- Step 3: 生成价值观内容
    iteration_prompt        TEXT,     -- Step 4: 迭代优化
    -- 模型配置
    model_id        BIGINT REFERENCES ai_models(id) ON DELETE SET NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 插入默认配置
INSERT INTO values_writer_configs (config_key, is_active)
VALUES ('default', TRUE)
ON CONFLICT (config_key) DO NOTHING;
```

---

## 三、接口设计

### 3.1 管理端（admin）

**GET `/api/admin/values-writer/config`**
- 读取 `config_key='default'` 配置
- 返回：4 个 Prompt 字段 + model_id + is_active

**PUT `/api/admin/values-writer/config`**
- 更新配置（4 个 Prompt + model_id + is_active）
- 写 OperationLog（action=`admin_update_values_writer_config`）

### 3.2 运营端（operator）

**POST `/api/operator/values-writer/extract-values`**
- 请求：`{ kol_id, extra_context? }`
- 逻辑：读取 kols 表的 persona 详情字段，调 AI 提炼价值观清单
- 返回：`{ values: string[] }`（非流式，等待完成）

**POST `/api/operator/values-writer/emotion-direction`**（流式 SSE）
- 请求：`{ kol_id, selected_values: string[], tone? }`
- 逻辑：根据选中的价值观推导情绪方向，流式输出
- SSE event 格式：`data: {"delta": "..."}`

**POST `/api/operator/values-writer/write`**（流式 SSE）
- 请求：`{ kol_id, selected_values: string[], emotion_direction: string, product_context? }`
- 逻辑：生成价值观内容，流式输出
- SSE event 格式：`data: {"delta": "..."}`

**POST `/api/operator/values-writer/iterate`**（流式 SSE）
- 请求：`{ kol_id, content: string, instruction: string }`
- 逻辑：根据用户指令迭代优化内容，流式输出

---

## 四、ORM 模型

参考 `seeding_writer.py` 的 `SeedingWriterConfig` 结构，字段对应表 § 二。

---

## 五、conftest.py 需补充

```python
"app.routers.operator_values_writer.AsyncSessionLocal",
"app.routers.admin_values_writer.AsyncSessionLocal",
```

---

## 六、集成测试口径（test_operator_values_writer.py）

| 测试 | 断言 |
|------|------|
| `test_extract_values_no_auth` | 401 |
| `test_extract_values_no_kol` | success=False |
| `test_extract_values_success` | success=True, values 是 list |
| `test_emotion_direction_streaming` | SSE 响应，至少有 1 个 data: 块 |
| `test_write_streaming` | SSE 响应，至少有 1 个 data: 块 |

AI 调用在测试中 mock（`patch("app.routers.operator_values_writer.call_ai_stream")`）。

---

## 七、验收口径

1. `GET /api/admin/values-writer/config` 返回 default 配置
2. `PUT /api/admin/values-writer/config` 更新后 GET 可见变更
3. `POST /api/operator/values-writer/extract-values` 返回 values 数组
4. SSE 接口返回正确的 `text/event-stream` Content-Type
5. 全量测试 ≥ 1006 passed
