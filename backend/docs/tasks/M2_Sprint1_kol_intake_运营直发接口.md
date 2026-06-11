# 后端任务单 · kol-intake 运营直发对话接口

> 目标：新增运营直接发起 AI 对话的接口，不依赖分享链接，用 JWT 鉴权。
>
> 复用：报告生成逻辑（intake_report.py）完全复用，仅需支持 session_id 参数。
>
> 涉及文件：
> - 新建 `backend/migrations/007_kol_intake_operator_sessions.sql`
> - 新建 `backend/app/routers/operator_intake_direct.py`
> - 修改 `backend/app/main.py`（注册新 router）

---

## 改动 1 — 新建 Migration

**文件**：`backend/migrations/007_kol_intake_operator_sessions.sql`

```sql
-- 007_kol_intake_operator_sessions.sql
-- 运营直发对话会话表（不走分享链接）

CREATE TABLE kol_intake_operator_sessions (
    id                  SERIAL PRIMARY KEY,
    operator_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kol_name            VARCHAR(200),
    messages            JSONB NOT NULL DEFAULT '[]',
    ai_report           TEXT,
    ai_report_raw       JSONB,
    report_status       VARCHAR(20) NOT NULL DEFAULT 'pending',
    report_generated_at TIMESTAMPTZ,
    docx_path           VARCHAR(500),
    pdf_path            VARCHAR(500),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_kol_intake_operator_sessions_operator
    ON kol_intake_operator_sessions(operator_id);

CREATE TRIGGER set_updated_at_kol_intake_operator_sessions
    BEFORE UPDATE ON kol_intake_operator_sessions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

---

## 改动 2 — 新建 Router

**文件**：`backend/app/routers/operator_intake_direct.py`

### 接口清单

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/operator/intake/direct/start` | 新建会话（返回 session_id） |
| `POST` | `/api/operator/intake/direct/{session_id}/chat` | 发消息，AI 返回回复 |
| `POST` | `/api/operator/intake/direct/{session_id}/submit` | 提交，触发报告生成 |
| `GET`  | `/api/operator/intake/direct/{session_id}/status` | 轮询报告状态 |
| `GET`  | `/api/operator/intake/direct/{session_id}/download` | 下载报告 |

### 接口实现参考

**POST /start**
```python
class StartSessionRequest(BaseModel):
    kol_name: str | None = None

@router.post("/start")
async def start_session(
    body: StartSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    session = KolIntakeOperatorSession(
        operator_id=current_user.id,
        kol_name=body.kol_name,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return success_response(data={
        "session_id": session.id,
        "kol_name":   session.kol_name,
    })
```

**POST /{session_id}/chat**
- 逻辑与 `intake_public.py` 的 `/chat` 完全一致
- 鉴权：`require_operator` + 验证 `session.operator_id == current_user.id`
- 保存 messages 到 `kol_intake_operator_sessions.messages`
- 返回 `{ reply: str }`

**POST /{session_id}/submit**
- 鉴权同上
- 触发 `generate_intake_report(session_id=session.id, source="operator_session")`（复用现有报告生成逻辑）
- 设置 `report_status = 'generating'`
- 返回 `{ report_status: "generating" }`

**GET /{session_id}/status**
- 返回 `{ report_status: "pending"|"generating"|"ready"|"failed" }`

**GET /{session_id}/download**
- 无下载权限限制（运营自己的会话，直接允许）
- 参数：`format=docx|pdf`
- 返回 FileResponse

---

## 改动 3 — 注册 Router

**文件**：`backend/app/main.py`

```python
from app.routers import operator_intake_direct

app.include_router(operator_intake_direct.router, prefix="/api")
```

---

## 改动汇总

| # | 文件 | 改动 |
|---|------|------|
| 1 | `migrations/007_...sql` | 新建 operator_sessions 表 |
| 2 | `routers/operator_intake_direct.py` | 新建 5 个接口 |
| 3 | `main.py` | 注册新 router |

**改动量**：约 120 行，现有代码零改动。

---

## 完成后验证

```bash
# 新建会话
POST /api/operator/intake/direct/start
Authorization: Bearer <operator_token>
{"kol_name": "测试红人"}
# 预期：{ session_id: 1 }

# 发消息
POST /api/operator/intake/direct/1/chat
{"messages": [{"role": "user", "content": "你好", "ts": "..."}]}
# 预期：{ reply: "AI回复..." }

# 提交
POST /api/operator/intake/direct/1/submit
# 预期：{ report_status: "generating" }

# 轮询
GET /api/operator/intake/direct/1/status
# 预期：{ report_status: "generating"|"ready" }
```
