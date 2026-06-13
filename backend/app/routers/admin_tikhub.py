"""
app/routers/admin_tikhub.py

TikHub 独立池管理接口（10 个）：
  GET    /api/admin/tikhub/stats           — 三维统计
  GET    /api/admin/tikhub/keys            — Key 列表
  POST   /api/admin/tikhub/keys            — 新增 Key
  PUT    /api/admin/tikhub/keys/{id}       — 编辑 Key
  DELETE /api/admin/tikhub/keys/{id}       — 删除 Key
  POST   /api/admin/tikhub/keys/{id}/test  — 测试连通性
  POST   /api/admin/tikhub/keys/{id}/enable  — 启用
  POST   /api/admin/tikhub/keys/{id}/disable — 停用
  GET    /api/admin/tikhub/endpoints       — 接口统计
  GET    /api/admin/tikhub/users           — 用户调用排行
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import delete, select, update, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import ApiResponse, ErrorCode, error_response, success_response
from app.middlewares.auth import require_admin
from app.models.log import OperationLog
from app.models.tikhub_credential import TikHubCredential
from app.models.user import User

router = APIRouter(prefix="/admin/tikhub", tags=["admin-tikhub"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


def _mask_key(key: str) -> str:
    """API key 脱敏：只显示末4位"""
    if not key or len(key) <= 4:
        return "****"
    return "*" * (len(key) - 4) + key[-4:]


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class CreateTikHubKeyRequest(BaseModel):
    label: str | None = None
    api_key: str
    base_url: str | None = None
    max_concurrent: int = 5
    max_users: int = 10


class UpdateTikHubKeyRequest(BaseModel):
    label: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    max_concurrent: int | None = None
    max_users: int | None = None


# ---------------------------------------------------------------------------
# 1. GET /api/admin/tikhub/stats — 三维统计
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=ApiResponse)
async def tikhub_stats(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today - timedelta(days=7)

    # ── overview ─────────────────────────────────────────────────────────
    overview_row = (await db.execute(text("""
        SELECT
            COUNT(*)                                                  AS total_calls,
            COUNT(*) FILTER (WHERE created_at >= :today)              AS today_calls,
            ROUND(AVG(latency_ms)::NUMERIC, 1)                        AS avg_latency_ms
        FROM tikhub_call_logs
    """), {"today": today})).fetchone()

    key_row = (await db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE status = 'active')   AS active_keys,
            COUNT(*)                                     AS total_keys
        FROM tikhub_credentials
    """))).fetchone()

    # ── by endpoint ──────────────────────────────────────────────────────
    endpoint_rows = (await db.execute(text("""
        SELECT
            endpoint,
            COUNT(*)            AS calls,
            ROUND(
                COUNT(*)::NUMERIC / NULLIF(SUM(COUNT(*)) OVER (), 0) * 100,
                1
            )                   AS pct
        FROM tikhub_call_logs
        GROUP BY endpoint
        ORDER BY calls DESC
    """))).fetchall()

    # ── by user ──────────────────────────────────────────────────────────
    user_rows = (await db.execute(text("""
        SELECT
            l.user_id,
            u.username,
            COUNT(*) AS calls
        FROM tikhub_call_logs l
        LEFT JOIN users u ON u.id = l.user_id
        GROUP BY l.user_id, u.username
        ORDER BY calls DESC
        LIMIT 10
    """))).fetchall()

    # ── trend (last 7 days) ──────────────────────────────────────────────
    trend_rows = (await db.execute(text("""
        SELECT
            TO_CHAR(DATE(created_at AT TIME ZONE 'UTC'), 'MM-DD') AS date,
            COUNT(*)                                               AS calls
        FROM tikhub_call_logs
        WHERE created_at >= :week_ago
        GROUP BY DATE(created_at AT TIME ZONE 'UTC')
        ORDER BY DATE(created_at AT TIME ZONE 'UTC') ASC
    """), {"week_ago": week_ago})).fetchall()

    total_calls = int(overview_row.total_calls) if overview_row else 0

    return success_response(data={
        "overview": {
            "total_calls": total_calls,
            "today_calls": int(overview_row.today_calls) if overview_row else 0,
            "avg_latency_ms": float(overview_row.avg_latency_ms) if overview_row and overview_row.avg_latency_ms else None,
            "active_keys": int(key_row.active_keys) if key_row else 0,
            "total_keys": int(key_row.total_keys) if key_row else 0,
        },
        "endpoints": [
            {
                "endpoint": r.endpoint,
                "calls": int(r.calls),
                "percentage": float(r.pct) if r.pct else 0,
            }
            for r in endpoint_rows
        ],
        "users": [
            {
                "user_id": r.user_id,
                "username": r.username,
                "calls": int(r.calls),
            }
            for r in user_rows
        ],
        "trend": [
            {
                "date": r.date,
                "calls": int(r.calls),
            }
            for r in trend_rows
        ],
    })


# ---------------------------------------------------------------------------
# 2. GET /api/admin/tikhub/keys — Key 列表
# ---------------------------------------------------------------------------

@router.get("/keys", response_model=ApiResponse)
async def list_tikhub_keys(
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
        FROM tikhub_credentials c
        LEFT JOIN (
            SELECT credential_id, COUNT(*) AS today_calls
            FROM tikhub_call_logs
            WHERE created_at >= :today
            GROUP BY credential_id
        ) t ON t.credential_id = c.id
        LEFT JOIN (
            SELECT credential_id, COUNT(*) AS total_calls
            FROM tikhub_call_logs
            GROUP BY credential_id
        ) a ON a.credential_id = c.id
        ORDER BY c.created_at DESC
    """), {"today": today})).fetchall()

    items = [
        {
            "id": r.id,
            "provider": r.provider,
            "label": r.label,
            "api_key": _mask_key(r.api_key),
            "base_url": r.base_url,
            "status": r.status,
            "active_requests": r.active_requests,
            "max_concurrent": r.max_concurrent,
            "max_users": r.max_users,
            "last_tested_at": _ts(r.last_tested_at),
            "last_latency_ms": r.last_latency_ms,
            "today_calls": int(r.today_calls),
            "total_calls": int(r.total_calls),
            "created_at": _ts(r.created_at),
            "updated_at": _ts(r.updated_at),
        }
        for r in rows
    ]
    return success_response(data={"items": items, "total": len(items)})


# ---------------------------------------------------------------------------
# 3. POST /api/admin/tikhub/keys — 新增 Key
# ---------------------------------------------------------------------------

@router.post("/keys", response_model=ApiResponse)
async def create_tikhub_key(
    body: CreateTikHubKeyRequest,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    cred = TikHubCredential(
        label=body.label,
        api_key=body.api_key,
        base_url=body.base_url or "https://api.tikhub.io",
        max_concurrent=body.max_concurrent,
        max_users=body.max_users,
    )
    db.add(cred)
    await db.flush()
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="create_tikhub_key",
        target_type="credential",
        target_id=cred.id,
        detail={"label": body.label},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(cred)
    return success_response(
        data={
            "id": cred.id,
            "provider": cred.provider,
            "label": cred.label,
            "api_key": _mask_key(cred.api_key),
            "base_url": cred.base_url,
            "status": cred.status,
            "active_requests": cred.active_requests,
            "max_concurrent": cred.max_concurrent,
            "max_users": cred.max_users,
            "created_at": _ts(cred.created_at),
        },
        message="TikHub Key 添加成功",
    )


# ---------------------------------------------------------------------------
# 4. PUT /api/admin/tikhub/keys/{key_id} — 编辑 Key
# ---------------------------------------------------------------------------

@router.put("/keys/{key_id}", response_model=ApiResponse)
async def update_tikhub_key(
    key_id: int,
    body: UpdateTikHubKeyRequest,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    cred = (await db.execute(
        select(TikHubCredential).where(TikHubCredential.id == key_id)
    )).scalar_one_or_none()
    if cred is None:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "TikHub Key 不存在")

    values: dict = {}
    for field in ("label", "api_key", "base_url", "max_concurrent", "max_users"):
        v = getattr(body, field)
        if v is not None:
            values[field] = v
    if values:
        values["updated_at"] = datetime.now(timezone.utc)
        await db.execute(
            update(TikHubCredential).where(TikHubCredential.id == key_id).values(**values)
        )
        db.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="update_tikhub_key",
            target_type="credential",
            target_id=key_id,
            detail={k: v for k, v in values.items() if k != "updated_at"},
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent"),
        ))
        await db.commit()
        await db.refresh(cred)

    return success_response(data={
        "id": cred.id,
        "provider": cred.provider,
        "label": cred.label,
        "api_key": _mask_key(cred.api_key),
        "base_url": cred.base_url,
        "status": cred.status,
        "active_requests": cred.active_requests,
        "max_concurrent": cred.max_concurrent,
        "max_users": cred.max_users,
        "created_at": _ts(cred.created_at),
        "updated_at": _ts(cred.updated_at),
    })


# ---------------------------------------------------------------------------
# 5. DELETE /api/admin/tikhub/keys/{key_id} — 删除 Key
# ---------------------------------------------------------------------------

@router.delete("/keys/{key_id}", response_model=ApiResponse)
async def delete_tikhub_key(
    key_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    cred = (await db.execute(
        select(TikHubCredential).where(TikHubCredential.id == key_id)
    )).scalar_one_or_none()
    if cred is None:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "TikHub Key 不存在")

    await db.execute(
        delete(TikHubCredential).where(TikHubCredential.id == key_id)
    )
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="delete_tikhub_key",
        target_type="credential",
        target_id=key_id,
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data=None, message="TikHub Key 已删除")


# ---------------------------------------------------------------------------
# 6. POST /api/admin/tikhub/keys/{key_id}/test — 测试连通性
# ---------------------------------------------------------------------------

@router.post("/keys/{key_id}/test", response_model=ApiResponse)
async def test_tikhub_key(
    key_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    import time
    import httpx

    cred = (await db.execute(
        select(TikHubCredential).where(TikHubCredential.id == key_id)
    )).scalar_one_or_none()
    if cred is None:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "TikHub Key 不存在")

    TEST_SEC_USER_ID = (
        "MS4wLjABAAAA5ZrIrbgva3dqI80CsHQMCUPAR5Q5KFBOMOrMnVKESnzNPk7sLBRKCTMSzfQkUzSZ"
    )
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{cred.base_url}/api/v1/douyin/app/v3/handler_user_profile",
                params={"sec_user_id": TEST_SEC_USER_ID},
                headers={"Authorization": f"Bearer {cred.api_key}"},
            )
        latency_ms = int((time.monotonic() - start) * 1000)

        if resp.status_code == 200:
            raw = resp.json()
            user_data = (raw.get("data") or {}).get("user") or {}
            sample_nickname = user_data.get("nickname")

            await db.execute(
                update(TikHubCredential).where(TikHubCredential.id == key_id).values(
                    last_tested_at=datetime.now(timezone.utc),
                    last_latency_ms=latency_ms,
                )
            )
            db.add(OperationLog(
                user_id=current_user.id,
                username=current_user.username,
                role=current_user.role,
                action="test_tikhub_key",
                target_type="credential",
                target_id=key_id,
                detail={"status": "ok", "latency_ms": latency_ms},
                ip=_get_ip(request),
                user_agent=request.headers.get("user-agent"),
            ))
            await db.commit()
            return success_response(data={
                "status": "ok",
                "latency_ms": latency_ms,
                "sample_nickname": sample_nickname,
            })
        else:
            return success_response(data={
                "status": "error",
                "latency_ms": latency_ms,
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
            })
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        return success_response(data={
            "status": "error",
            "latency_ms": latency_ms,
            "error": str(e)[:200],
        })


# ---------------------------------------------------------------------------
# 7. POST /api/admin/tikhub/keys/{key_id}/enable — 启用
# ---------------------------------------------------------------------------

@router.post("/keys/{key_id}/enable", response_model=ApiResponse)
async def enable_tikhub_key(
    key_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    cred = (await db.execute(
        select(TikHubCredential).where(TikHubCredential.id == key_id)
    )).scalar_one_or_none()
    if cred is None:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "TikHub Key 不存在")

    await db.execute(
        update(TikHubCredential).where(TikHubCredential.id == key_id).values(
            status="active",
            updated_at=datetime.now(timezone.utc),
        )
    )
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="enable_tikhub_key",
        target_type="credential",
        target_id=key_id,
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data=None, message="TikHub Key 已启用")


# ---------------------------------------------------------------------------
# 8. POST /api/admin/tikhub/keys/{key_id}/disable — 停用
# ---------------------------------------------------------------------------

@router.post("/keys/{key_id}/disable", response_model=ApiResponse)
async def disable_tikhub_key(
    key_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    cred = (await db.execute(
        select(TikHubCredential).where(TikHubCredential.id == key_id)
    )).scalar_one_or_none()
    if cred is None:
        return error_response(ErrorCode.RESOURCE_NOT_FOUND, "TikHub Key 不存在")

    await db.execute(
        update(TikHubCredential).where(TikHubCredential.id == key_id).values(
            status="inactive",
            updated_at=datetime.now(timezone.utc),
        )
    )
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="disable_tikhub_key",
        target_type="credential",
        target_id=key_id,
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    return success_response(data=None, message="TikHub Key 已停用")


# ---------------------------------------------------------------------------
# 9. GET /api/admin/tikhub/endpoints — 接口列表和统计
# ---------------------------------------------------------------------------

@router.get("/endpoints", response_model=ApiResponse)
async def list_tikhub_endpoints(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(text("""
        SELECT
            endpoint,
            platform,
            COUNT(*)            AS calls,
            ROUND(
                COUNT(*)::NUMERIC / NULLIF(SUM(COUNT(*)) OVER (), 0) * 100,
                1
            )                   AS pct,
            ROUND(AVG(latency_ms)::NUMERIC, 1) AS avg_latency_ms,
            ROUND(
                COUNT(*) FILTER (WHERE status = 'success')::NUMERIC
                / NULLIF(COUNT(*)::NUMERIC, 0) * 100,
                1
            )                   AS success_rate
        FROM tikhub_call_logs
        GROUP BY endpoint, platform
        ORDER BY calls DESC
    """))).fetchall()

    return success_response(data=[
        {
            "endpoint": r.endpoint,
            "platform": r.platform,
            "calls": int(r.calls),
            "percentage": float(r.pct) if r.pct else 0,
            "avg_latency_ms": float(r.avg_latency_ms) if r.avg_latency_ms else None,
            "success_rate": round(float(r.success_rate) / 100, 2) if r.success_rate else None,
        }
        for r in rows
    ])


# ---------------------------------------------------------------------------
# 10. GET /api/admin/tikhub/users — 用户调用排行
# ---------------------------------------------------------------------------

@router.get("/users", response_model=ApiResponse)
async def list_tikhub_users(
    start_date: str = "",
    end_date: str = "",
    limit: int = 20,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    def _parse_date(s: str, fallback: datetime) -> datetime:
        if not s:
            return fallback
        try:
            return datetime.strptime(s, "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return fallback

    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = _parse_date(start_date, today)
    end = _parse_date(end_date, today + timedelta(days=1))
    limit = max(1, min(limit, 100))

    rows = (await db.execute(text("""
        SELECT
            l.user_id,
            u.username,
            u.role,
            COUNT(*)             AS calls,
            MAX(l.created_at)    AS last_called_at
        FROM tikhub_call_logs l
        LEFT JOIN users u ON u.id = l.user_id
        WHERE l.created_at >= :start AND l.created_at < :end
        GROUP BY l.user_id, u.username, u.role
        ORDER BY calls DESC
        LIMIT :limit
    """), {"start": start, "end": end, "limit": limit})).fetchall()

    items = [
        {
            "user_id": r.user_id,
            "username": r.username,
            "role": r.role,
            "calls": int(r.calls),
            "last_called_at": _ts(r.last_called_at),
        }
        for r in rows
    ]
    return success_response(data={"items": items, "total": len(items)})
