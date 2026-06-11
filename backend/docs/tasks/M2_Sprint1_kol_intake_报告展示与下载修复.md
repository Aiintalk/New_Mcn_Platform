# 后端任务单 · kol-intake 报告展示与下载修复

> 问题：
> 1. 下载接口 GET /download 需要 JWT，但前端用 window.open 直接打开 URL 无法带 header，导致 AUTH_TOKEN_MISSING
> 2. status 接口未返回报告内容，前端无法直接展示报告文本
>
> 涉及文件：
> - `backend/app/routers/operator_intake_direct.py`

---

## 改动 1 — status 接口返回报告内容

**文件**：`operator_intake_direct.py`

在 `GET /{session_id}/status` 的返回数据中追加 `ai_report` 字段：

```python
@router.get("/{session_id}/status")
async def session_status(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    session = await _get_own_session(session_id, current_user, db)
    return success_response(data={
        "report_status":  session.report_status,
        "download_ready": session.report_status == "ready",
        "ai_report":      session.ai_report,   # ← 新增，ready 时为报告文本，否则为 null
    })
```

---

## 改动 2 — download 接口支持 token 参数鉴权

浏览器 `window.open` 无法携带 `Authorization` header，需要支持 query string 方式传 token。

```python
from fastapi import Query
from app.core.security import verify_access_token   # 复用现有函数
from app.models.user import User
from sqlalchemy import select

@router.get("/{session_id}/download")
async def session_download(
    session_id: int,
    format: str = Query(default="docx", pattern="^(docx|pdf)$"),
    token: str | None = Query(default=None),   # ← 新增：支持 ?token=xxx
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),  # ← 改为 optional
):
    # 优先用 header token（已有逻辑），fallback 用 query string token
    user = current_user
    if user is None and token:
        payload = verify_access_token(token)
        if payload:
            user = (await db.execute(
                select(User).where(User.id == payload.get("sub"))
            )).scalar_one_or_none()

    if user is None or user.role not in ("operator", "admin"):
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_TOKEN_MISSING", "message": "缺少 Token"},
        )

    session = await _get_own_session(session_id, user, db)
    # ... 后续文件返回逻辑不变
```

同时在同文件新增 `get_current_user_optional` 依赖：

```python
from app.middlewares.auth import get_current_user_optional  # 若不存在则新增
```

若 `get_current_user_optional` 不存在，在 `middlewares/auth.py` 中新增：

```python
async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """不强制要求 token，有则解析，无则返回 None。"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        return await get_current_user(request, db)
    except HTTPException:
        return None
```

---

## 验证

```bash
# status 接口返回报告内容
GET /api/operator/intake/direct/{session_id}/status
# 预期：{ report_status: "ready", download_ready: true, ai_report: "## 报告标题\n..." }

# 带 token 参数下载（模拟 window.open）
GET /api/operator/intake/direct/{session_id}/download?format=docx&token=<jwt>
# 预期：直接返回文件流，不报 AUTH_TOKEN_MISSING
```
