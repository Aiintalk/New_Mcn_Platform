"""
app/routers/admin_oss.py

OSS 凭证与调用统计接口（admin）：
  GET /api/admin/oss/stats       — 三维统计（overview + operations + users + trend）
  GET /api/admin/oss/operations  — 按 operation（upload/download/delete）聚合
  GET /api/admin/oss/users       — 按用户聚合调用排行

参照 admin_tikhub.py 实现，区别：
- 表名：tikhub_call_logs → oss_call_logs
- 列名：endpoint → operation（取值 upload/download/delete）
- 无 platform 维度
- 凭证池用通用 service_credentials（WHERE provider='oss'），非独立表
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import ApiResponse, success_response
from app.middlewares.auth import require_admin
from app.models.user import User

router = APIRouter(prefix="/admin/oss", tags=["admin-oss"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


# ---------------------------------------------------------------------------
# 1. GET /api/admin/oss/stats — 三维统计
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=ApiResponse)
async def oss_stats(
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
        FROM oss_call_logs
    """), {"today": today})).fetchone()

    key_row = (await db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE status = 'enabled')   AS active_keys,
            COUNT(*)                                     AS total_keys
        FROM service_credentials
        WHERE provider = 'oss'
    """))).fetchone()

    # ── by operation ─────────────────────────────────────────────────────
    operation_rows = (await db.execute(text("""
        SELECT
            operation,
            COUNT(*)            AS calls,
            ROUND(
                COUNT(*)::NUMERIC / NULLIF(SUM(COUNT(*)) OVER (), 0) * 100,
                1
            )                   AS pct
        FROM oss_call_logs
        GROUP BY operation
        ORDER BY calls DESC
    """))).fetchall()

    # ── by user (TOP 10) ─────────────────────────────────────────────────
    user_rows = (await db.execute(text("""
        SELECT
            l.user_id,
            u.username,
            COUNT(*) AS calls
        FROM oss_call_logs l
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
        FROM oss_call_logs
        WHERE created_at >= :week_ago
        GROUP BY DATE(created_at AT TIME ZONE 'UTC')
        ORDER BY DATE(created_at AT TIME ZONE 'UTC') ASC
    """), {"week_ago": week_ago})).fetchall()

    return success_response(data={
        "overview": {
            "total_calls": int(overview_row.total_calls) if overview_row and overview_row.total_calls else 0,
            "today_calls": int(overview_row.today_calls) if overview_row and overview_row.today_calls else 0,
            "avg_latency_ms": float(overview_row.avg_latency_ms) if overview_row and overview_row.avg_latency_ms else None,
            "active_keys": int(key_row.active_keys) if key_row and key_row.active_keys else 0,
            "total_keys": int(key_row.total_keys) if key_row and key_row.total_keys else 0,
        },
        "operations": [
            {
                "operation": r.operation,
                "calls": int(r.calls),
                "percentage": float(r.pct) if r.pct else 0,
            }
            for r in operation_rows
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
# 2. GET /api/admin/oss/operations — 按 operation 聚合
# ---------------------------------------------------------------------------

@router.get("/operations", response_model=ApiResponse)
async def list_oss_operations(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(text("""
        SELECT
            operation,
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
        FROM oss_call_logs
        GROUP BY operation
        ORDER BY calls DESC
    """))).fetchall()

    return success_response(data=[
        {
            "operation": r.operation,
            "calls": int(r.calls),
            "percentage": float(r.pct) if r.pct else 0,
            "avg_latency_ms": float(r.avg_latency_ms) if r.avg_latency_ms else None,
            "success_rate": round(float(r.success_rate) / 100, 2) if r.success_rate else None,
        }
        for r in rows
    ])


# ---------------------------------------------------------------------------
# 3. GET /api/admin/oss/users — 用户调用排行
# ---------------------------------------------------------------------------

@router.get("/users", response_model=ApiResponse)
async def list_oss_users(
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
        FROM oss_call_logs l
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
