from datetime import datetime, timezone, timedelta

from fastapi import APIRouter
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.response import ApiResponse, success_response

router = APIRouter()

_TZ_BEIJING = timezone(timedelta(hours=8))


@router.get("/health", response_model=ApiResponse)
async def health_check():
    """
    GET /api/health — 公开接口，无需鉴权。
    真实探测数据库连接；DB 未就绪时 database 字段返回 "error"，HTTP 状态仍为 200。
    """
    db_status = "ok"
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    now_iso = datetime.now(tz=_TZ_BEIJING).isoformat(timespec="seconds")

    return success_response(
        data={
            "status": "ok",
            "service": "mcn-api",
            "database": db_status,
            "time": now_iso,
        }
    )


@router.get("/version", response_model=ApiResponse)
async def version():
    """
    GET /api/version — 公开接口，无需鉴权。
    返回当前服务名称、版本号和阶段标识。
    """
    return success_response(
        data={
            "service": "mcn-api",
            "version": "0.1.0",
            "stage": "m1-base",
        }
    )
