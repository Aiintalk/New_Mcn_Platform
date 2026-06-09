"""
app/routers/admin_ai.py

AI 管理模块接口：
  GET    /api/admin/ai/keys          — Key 列表（含并发状态）
  POST   /api/admin/ai/keys          — 添加 Key
  PATCH  /api/admin/ai/keys/{id}     — 编辑 / 停用 Key
  DELETE /api/admin/ai/keys/{id}     — 删除 Key

  GET    /api/admin/ai/models        — 模型列表
  POST   /api/admin/ai/models        — 添加模型
  PATCH  /api/admin/ai/models/{id}   — 编辑 / 停用模型
  DELETE /api/admin/ai/models/{id}   — 删除模型

  GET    /api/admin/ai/stats         — 使用统计（筛选：时间 / 功能 / 用户 / 模型）
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, update, delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import yunwu as yunwu_adapter
from app.core.database import get_db
from app.core.response import ApiResponse, ErrorCode, error_response, success_response
from app.middlewares.auth import require_admin
from app.models.credential import Credential, AiModel
from app.models.user import User

router = APIRouter(prefix="/admin/ai", tags=["admin-ai"])

_DEFAULT_BASE_URLS = {
    "yunwu":       "https://yunwu.ai/v1",
    "siliconflow": "https://api.siliconflow.cn/v1",
    "glm":         "https://open.bigmodel.cn/api/paas/v4",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


def _cred_to_dict(c: Credential, today_calls: int = 0) -> dict:
    return {
        "id":              c.id,
        "provider":        c.provider,
        "label":           c.label,
        "api_key":         c.api_key,
        "base_url":        c.base_url,
        "status":          c.status,
        "active_requests": c.active_requests,
        "max_concurrent":  c.max_concurrent,
        "max_users":       c.max_users,
        "today_calls":     today_calls,
        "created_at":      _ts(c.created_at),
        "updated_at":      _ts(c.updated_at),
    }


def _model_to_dict(m: AiModel, total_calls: int = 0, total_tokens: int = 0) -> dict:
    return {
        "id":           m.id,
        "name":         m.name,
        "provider":     m.provider,
        "model_id":     m.model_id,
        "status":       m.status,
        "total_calls":  total_calls,
        "total_tokens": total_tokens,
        "created_at":   _ts(m.created_at),
        "updated_at":   _ts(m.updated_at),
    }


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class CreateKeyRequest(BaseModel):
    provider:       str = "yunwu"
    label:          str | None = None
    api_key:        str
    base_url:       str | None = None
    max_concurrent: int = 5
    max_users:      int = 10


class UpdateKeyRequest(BaseModel):
    label:          str | None = None
    api_key:        str | None = None
    base_url:       str | None = None
    status:         str | None = None
    max_concurrent: int | None = None
    max_users:      int | None = None


class CreateModelRequest(BaseModel):
    name:     str
    provider: str = "yunwu"
    model_id: str


class UpdateModelRequest(BaseModel):
    name:     str | None = None
    provider: str | None = None
    status:   str | None = None


# ---------------------------------------------------------------------------
# Keys — CRUD
# ---------------------------------------------------------------------------

@router.get("/keys", response_model=ApiResponse)
async def list_keys(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (await db.execute(text("""
        SELECT
            c.id, c.provider, c.label, c.api_key, c.base_url, c.status,
            c.active_requests, c.max_concurrent, c.max_users,
            c.last_tested_at, c.last_latency_ms,
            c.created_at, c.updated_at,
            COALESCE(t.today_calls, 0)  AS today_calls,
            COALESCE(a.total_calls, 0)  AS total_calls
        FROM credentials c
        LEFT JOIN (
            SELECT credential_id, COUNT(*) AS today_calls
            FROM ai_call_logs
            WHERE created_at >= :today
            GROUP BY credential_id
        ) t ON t.credential_id = c.id
        LEFT JOIN (
            SELECT credential_id, COUNT(*) AS total_calls
            FROM ai_call_logs
            GROUP BY credential_id
        ) a ON a.credential_id = c.id
        ORDER BY c.created_at DESC
    """), {"today": today})).fetchall()

    items = []
    for r in rows:
        items.append({
            "id":              r.id,
            "provider":        r.provider,
            "label":           r.label,
            "api_key":         r.api_key,
            "base_url":        r.base_url,
            "status":          r.status,
            "active_requests": r.active_requests,
            "max_concurrent":  r.max_concurrent,
            "max_users":       r.max_users,
            "last_tested_at":  r.last_tested_at.isoformat() if r.last_tested_at else None,
            "last_latency_ms": r.last_latency_ms,
            "today_calls":     int(r.today_calls),
            "total_calls":     int(r.total_calls),
            "created_at":      r.created_at.isoformat() if r.created_at else None,
            "updated_at":      r.updated_at.isoformat() if r.updated_at else None,
        })
    return success_response(data={"items": items})


@router.post("/keys", response_model=ApiResponse)
async def create_key(
    body: CreateKeyRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    cred = Credential(
        provider=body.provider,
        label=body.label,
        api_key=body.api_key,
        base_url=body.base_url or _DEFAULT_BASE_URLS.get(body.provider),
        max_concurrent=body.max_concurrent,
        max_users=body.max_users,
    )
    db.add(cred)
    await db.commit()
    await db.refresh(cred)
    return success_response(data=_cred_to_dict(cred), message="Key 添加成功")


@router.patch("/keys/{key_id}", response_model=ApiResponse)
async def update_key(
    key_id: int,
    body: UpdateKeyRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    cred = (await db.execute(
        select(Credential).where(Credential.id == key_id)
    )).scalar_one_or_none()
    if cred is None:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "Key 不存在")

    values: dict = {}
    for field in ("label", "api_key", "base_url", "status", "max_concurrent", "max_users"):
        v = getattr(body, field)
        if v is not None:
            values[field] = v
    if values:
        values["updated_at"] = datetime.now(timezone.utc)
        await db.execute(update(Credential).where(Credential.id == key_id).values(**values))
        await db.commit()
        await db.refresh(cred)

    return success_response(data=_cred_to_dict(cred))


@router.delete("/keys/{key_id}", response_model=ApiResponse)
async def delete_key(
    key_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    cred = (await db.execute(
        select(Credential).where(Credential.id == key_id)
    )).scalar_one_or_none()
    if cred is None:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "Key 不存在")

    await db.execute(delete(Credential).where(Credential.id == key_id))
    await db.commit()
    return success_response(data=None, message="Key 已删除")


@router.post("/keys/{key_id}/test", response_model=ApiResponse)
async def test_key(
    key_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    测试 Key 连通性：GET /v1/models（不消耗 token）。
    返回 {"status": "ok"/"error", "latency_ms": int, "error": str}
    """
    import time
    import httpx

    cred = (await db.execute(
        select(Credential).where(Credential.id == key_id)
    )).scalar_one_or_none()
    if cred is None:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "Key 不存在")

    base_url = cred.base_url or _DEFAULT_BASE_URLS.get(cred.provider, "https://yunwu.ai/v1")
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {cred.api_key}"},
            )
        latency_ms = int((time.monotonic() - start) * 1000)
        if resp.status_code == 200:
            await db.execute(
                update(Credential).where(Credential.id == key_id).values(
                    last_tested_at=datetime.now(timezone.utc),
                    last_latency_ms=latency_ms,
                )
            )
            await db.commit()
            return success_response(data={"status": "ok", "latency_ms": latency_ms})
        else:
            body = resp.json()
            msg = (body.get("error") or {}).get("message") or resp.text[:200]
            return success_response(data={"status": "error", "latency_ms": latency_ms, "error": msg})
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        return success_response(data={"status": "error", "latency_ms": latency_ms, "error": str(e)[:200]})


# ---------------------------------------------------------------------------
# Models — CRUD
# ---------------------------------------------------------------------------

@router.get("/models", response_model=ApiResponse)
async def list_models(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(text("""
        SELECT
            m.id, m.name, m.provider, m.model_id, m.status,
            m.last_tested_at, m.last_latency_ms,
            m.created_at, m.updated_at,
            COALESCE(s.total_calls,  0) AS total_calls,
            COALESCE(s.total_tokens, 0) AS total_tokens
        FROM ai_models m
        LEFT JOIN (
            SELECT
                model_id,
                COUNT(*) AS total_calls,
                SUM(COALESCE(input_tokens,0) + COALESCE(output_tokens,0)) AS total_tokens
            FROM ai_call_logs
            GROUP BY model_id
        ) s ON s.model_id = m.model_id
        ORDER BY m.created_at DESC
    """))).fetchall()

    items = []
    for r in rows:
        items.append({
            "id":              r.id,
            "name":            r.name,
            "provider":        r.provider,
            "model_id":        r.model_id,
            "status":          r.status,
            "last_tested_at":  r.last_tested_at.isoformat() if r.last_tested_at else None,
            "last_latency_ms": r.last_latency_ms,
            "total_calls":     int(r.total_calls),
            "total_tokens":    int(r.total_tokens),
            "created_at":      r.created_at.isoformat() if r.created_at else None,
            "updated_at":      r.updated_at.isoformat() if r.updated_at else None,
        })
    return success_response(data={"items": items})


@router.post("/models", response_model=ApiResponse)
async def create_model(
    body: CreateModelRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(
        select(AiModel).where(AiModel.model_id == body.model_id)
    )).scalar_one_or_none()
    if existing:
        return error_response(ErrorCode.VALIDATION_ERROR, f"model_id '{body.model_id}' 已存在")

    m = AiModel(name=body.name, provider=body.provider, model_id=body.model_id)
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return success_response(data=_model_to_dict(m), message="模型添加成功")


@router.patch("/models/{model_id}", response_model=ApiResponse)
async def update_model(
    model_id: int,
    body: UpdateModelRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    m = (await db.execute(
        select(AiModel).where(AiModel.id == model_id)
    )).scalar_one_or_none()
    if m is None:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "模型不存在")

    values: dict = {}
    for field in ("name", "provider", "status"):
        v = getattr(body, field)
        if v is not None:
            values[field] = v
    if values:
        values["updated_at"] = datetime.now(timezone.utc)
        await db.execute(update(AiModel).where(AiModel.id == model_id).values(**values))
        await db.commit()
        await db.refresh(m)

    return success_response(data=_model_to_dict(m))


@router.delete("/models/{model_id}", response_model=ApiResponse)
async def delete_model(
    model_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    m = (await db.execute(
        select(AiModel).where(AiModel.id == model_id)
    )).scalar_one_or_none()
    if m is None:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "模型不存在")

    await db.execute(delete(AiModel).where(AiModel.id == model_id))
    await db.commit()
    return success_response(data=None, message="模型已删除")


@router.post("/models/{model_id}/test", response_model=ApiResponse)
async def test_model(
    model_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    测试模型可用性：固定发送 "hi" max_tokens=1，按模型的 provider 选对应 Key 池。
    返回 {"status": "ok"/"error", "latency_ms": int, "error": str}
    """
    import time

    m = (await db.execute(
        select(AiModel).where(AiModel.id == model_id)
    )).scalar_one_or_none()
    if m is None:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "模型不存在")

    start = time.monotonic()
    latency_ms = 0
    try:
        await yunwu_adapter.chat(
            messages=[{"role": "user", "content": "hi"}],
            db=db,
            model_id=m.model_id,
            provider=m.provider,
            user_id=current_user.id,
            feature="model_test",
            max_tokens=1,
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        await db.execute(
            update(AiModel).where(AiModel.id == model_id).values(
                last_tested_at=datetime.now(timezone.utc),
                last_latency_ms=latency_ms,
            )
        )
        await db.commit()
        return success_response(data={"status": "ok", "latency_ms": latency_ms})
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        await db.execute(
            update(AiModel).where(AiModel.id == model_id).values(
                last_tested_at=datetime.now(timezone.utc),
                last_latency_ms=latency_ms,
            )
        )
        await db.commit()
        return success_response(data={"status": "error", "latency_ms": latency_ms, "error": str(e)[:200]})


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=ApiResponse)
async def ai_stats(
    start_date: str = "",       # YYYYMMDD，不传则今日
    end_date:   str = "",       # YYYYMMDD，不传则明日（即今日结束）
    provider:   str = "",       # 服务商筛选（过滤 Key 汇总）
    status:     str = "",       # Key 状态筛选
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from datetime import timedelta

    def _parse_date(s: str, fallback: datetime) -> datetime:
        if not s:
            return fallback
        try:
            return datetime.strptime(s, "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return fallback

    now   = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = _parse_date(start_date, today)
    end   = _parse_date(end_date, today + timedelta(days=1))

    # ── Key 汇总（受 provider / status 筛选）────────────────────────────
    key_conditions = []
    key_params: dict = {}
    if provider:
        key_conditions.append("provider = :kp_provider")
        key_params["kp_provider"] = provider
    if status:
        key_conditions.append("status = :kp_status")
        key_params["kp_status"] = status
    key_where = ("WHERE " + " AND ".join(key_conditions)) if key_conditions else ""

    key_row = (await db.execute(text(f"""
        SELECT
            COUNT(*)                                                              AS total_keys,
            COUNT(*) FILTER (WHERE status = 'active'
                             AND active_requests < max_concurrent)                AS healthy_keys,
            COALESCE(SUM(active_requests), 0)                                     AS current_active,
            COALESCE(SUM(CASE WHEN status = 'active' THEN max_concurrent ELSE 0 END), 0) AS total_capacity
        FROM credentials
        {key_where}
    """), key_params)).fetchone()

    model_count_row = (await db.execute(text(
        "SELECT COUNT(*) FROM ai_models WHERE status = 'active'"
    ))).scalar()

    # ── 调用日志聚合（受时间范围筛选）────────────────────────────────────
    log_params: dict = {"start": start, "end": end}

    log_row = (await db.execute(text("""
        SELECT
            COALESCE(SUM(COALESCE(input_tokens,0) + COALESCE(output_tokens,0)), 0) AS total_tokens,
            ROUND(AVG(latency_ms)::NUMERIC, 1)                                     AS avg_latency_ms
        FROM ai_call_logs
        WHERE created_at >= :start AND created_at < :end
    """), log_params)).fetchone()

    # ── by_model（JOIN ai_models 获取 name / provider）──────────────────
    model_rows = (await db.execute(text("""
        SELECT
            l.model_id,
            m.name,
            m.provider,
            COUNT(*)                                                               AS requests,
            COALESCE(SUM(COALESCE(l.input_tokens,0) + COALESCE(l.output_tokens,0)), 0) AS tokens
        FROM ai_call_logs l
        LEFT JOIN ai_models m ON m.model_id = l.model_id
        WHERE l.created_at >= :start AND l.created_at < :end
        GROUP BY l.model_id, m.name, m.provider
        ORDER BY tokens DESC
    """), log_params)).fetchall()

    total_tokens = int(log_row.total_tokens) if log_row else 0

    # ── token_trend（按日聚合）────────────────────────────────────────────
    trend_rows = (await db.execute(text("""
        SELECT
            DATE(created_at AT TIME ZONE 'UTC')    AS date,
            COALESCE(SUM(input_tokens),  0)        AS input_tokens,
            COALESCE(SUM(output_tokens), 0)        AS output_tokens
        FROM ai_call_logs
        WHERE created_at >= :start AND created_at < :end
        GROUP BY DATE(created_at AT TIME ZONE 'UTC')
        ORDER BY date ASC
    """), log_params)).fetchall()

    def _float(v):
        return float(v) if v is not None else None

    current_active = int(key_row.current_active)
    total_capacity = int(key_row.total_capacity)
    queue_length   = yunwu_adapter.get_queue_length()

    if total_capacity == 0 or int(key_row.healthy_keys) == 0:
        service_status = "unavailable"
    elif queue_length > 0 or current_active >= total_capacity:
        service_status = "overloaded"
    elif int(key_row.healthy_keys) / max(int(key_row.total_keys), 1) < 0.5:
        service_status = "degraded"
    else:
        service_status = "healthy"

    return success_response(data={
        "summary": {
            "total_keys":      int(key_row.total_keys),
            "healthy_keys":    int(key_row.healthy_keys),
            "model_count":     int(model_count_row or 0),
            "total_tokens":    total_tokens,
            "avg_latency_ms":  _float(log_row.avg_latency_ms) if log_row else None,
            "service_status":  service_status,
            "queue_length":    queue_length,
            "current_active":  current_active,
            "total_capacity":  total_capacity,
        },
        "by_model": [
            {
                "model_id":   r.model_id,
                "name":       r.name,
                "provider":   r.provider,
                "requests":   int(r.requests),
                "tokens":     int(r.tokens),
                "percentage": round(int(r.tokens) / total_tokens, 4) if total_tokens else 0,
            }
            for r in model_rows
        ],
        "token_trend": [
            {
                "date":          str(r.date),
                "input_tokens":  int(r.input_tokens),
                "output_tokens": int(r.output_tokens),
            }
            for r in trend_rows
        ],
    })
