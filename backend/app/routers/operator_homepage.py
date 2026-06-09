"""
app/routers/operator_homepage.py

运营端首页统计接口（JWT 鉴权，operator / admin 角色）：
  GET /api/operator/homepage/stats  — 数字统计卡片 + 个人使用情况
  GET /api/operator/homepage/trend  — 最近7天内容产出趋势

时区：Asia/Shanghai（UTC+8），本周起始为周一 00:00:00
Token 用量：task_jobs 无 token_used 字段，week_token_usage 固定返回 null
"""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.middlewares.auth import get_current_user
from app.models.output import Output
from app.models.task import TaskJob
from app.models.user import User

router = APIRouter(prefix="/operator/homepage", tags=["operator-homepage"])

_CST = timezone(timedelta(hours=8))  # Asia/Shanghai


async def require_operator(current_user: User = Depends(get_current_user)) -> User:
    from fastapi import HTTPException
    if current_user.password_changed_at is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "AUTH_FORCE_CHANGE_PASSWORD", "message": "请先修改初始密码"},
        )
    if current_user.role not in ("operator", "admin"):
        raise HTTPException(
            status_code=403,
            detail={"code": "PERMISSION_DENIED", "message": "无权限访问"},
        )
    return current_user


def _week_start_cst() -> datetime:
    """返回本周一 00:00:00 CST 对应的 aware datetime（带 UTC+8 tzinfo）。"""
    today_cst = datetime.now(_CST).date()
    monday = today_cst - timedelta(days=today_cst.weekday())  # weekday(): 0=周一
    return datetime(monday.year, monday.month, monday.day, 0, 0, 0, tzinfo=_CST)


def _today_start_cst() -> datetime:
    """返回今日 00:00:00 CST。"""
    today_cst = datetime.now(_CST).date()
    return datetime(today_cst.year, today_cst.month, today_cst.day, 0, 0, 0, tzinfo=_CST)


def _format_change(current: int, prior: int) -> str | None:
    """
    计算同比变化率字符串。
    prior=0 时返回 None（前端显示「—」）。
    """
    if prior == 0:
        return None
    pct = (current - prior) / prior * 100
    if pct == 0:
        return "0%"
    return f"+{pct:.1f}%" if pct > 0 else f"{pct:.1f}%"


# ---------------------------------------------------------------------------
# GET /operator/homepage/stats
# ---------------------------------------------------------------------------

@router.get("/stats")
async def get_homepage_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    uid = current_user.id
    week_start  = _week_start_cst()
    today_start = _today_start_cst()
    yesterday_start = today_start - timedelta(days=1)
    last_week_start = week_start - timedelta(weeks=1)

    # today_outputs
    today_outputs: int = (await db.execute(
        select(func.count()).select_from(Output)
        .where(Output.created_by == uid)
        .where(Output.deleted_at.is_(None))
        .where(Output.created_at >= today_start)
    )).scalar_one()

    # yesterday_outputs（用于变化率分母）
    yesterday_outputs: int = (await db.execute(
        select(func.count()).select_from(Output)
        .where(Output.created_by == uid)
        .where(Output.deleted_at.is_(None))
        .where(Output.created_at >= yesterday_start)
        .where(Output.created_at < today_start)
    )).scalar_one()

    # week_outputs
    week_outputs: int = (await db.execute(
        select(func.count()).select_from(Output)
        .where(Output.created_by == uid)
        .where(Output.deleted_at.is_(None))
        .where(Output.created_at >= week_start)
    )).scalar_one()

    # last_week_outputs（用于变化率分母）
    last_week_outputs: int = (await db.execute(
        select(func.count()).select_from(Output)
        .where(Output.created_by == uid)
        .where(Output.deleted_at.is_(None))
        .where(Output.created_at >= last_week_start)
        .where(Output.created_at < week_start)
    )).scalar_one()

    # in_progress_tasks
    in_progress_tasks: int = (await db.execute(
        select(func.count()).select_from(TaskJob)
        .where(TaskJob.created_by == uid)
        .where(TaskJob.status == "processing")
    )).scalar_one()

    # week_tool_count（本周内 task_jobs 总数）
    week_tool_count: int = (await db.execute(
        select(func.count()).select_from(TaskJob)
        .where(TaskJob.created_by == uid)
        .where(TaskJob.created_at >= week_start)
    )).scalar_one()

    # tool_usage_breakdown — 本周 task_jobs 按 tool_code 分组，前4 + 其他
    breakdown_rows = (await db.execute(
        select(
            TaskJob.tool_code,
            TaskJob.tool_name,
            func.count().label("cnt"),
        )
        .where(TaskJob.created_by == uid)
        .where(TaskJob.created_at >= week_start)
        .group_by(TaskJob.tool_code, TaskJob.tool_name)
        .order_by(func.count().desc())
    )).all()

    tool_usage_breakdown: list[dict] = []
    if breakdown_rows:
        total = sum(r.cnt for r in breakdown_rows)
        top4 = breakdown_rows[:4]
        others_count = sum(r.cnt for r in breakdown_rows[4:])

        items = [
            {"tool_name": r.tool_name, "tool_code": r.tool_code, "count": r.cnt}
            for r in top4
        ]
        if others_count > 0:
            items.append({"tool_name": "其他", "tool_code": None, "count": others_count})

        # 计算 percentage（保留1位小数）
        for item in items:
            item["percentage"] = round(item["count"] / total * 100, 1)

        tool_usage_breakdown = items

    # recent_tools — 按 tool_code 分组，取最近 6 个
    recent_rows = (await db.execute(
        select(
            TaskJob.tool_code,
            TaskJob.tool_name,
            func.max(TaskJob.created_at).label("last_used_at"),
        )
        .where(TaskJob.created_by == uid)
        .group_by(TaskJob.tool_code, TaskJob.tool_name)
        .order_by(func.max(TaskJob.created_at).desc())
        .limit(6)
    )).all()

    recent_tools = [
        {
            "tool_name":    row.tool_name,
            "tool_code":    row.tool_code,
            "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        }
        for row in recent_rows
    ]

    # last_login_at
    last_login_at = (
        current_user.last_login_at.isoformat() if current_user.last_login_at else None
    )

    return success_response(data={
        "today_outputs":        today_outputs,
        "today_outputs_change": _format_change(today_outputs, yesterday_outputs),
        "week_outputs":         week_outputs,
        "week_outputs_change":  _format_change(week_outputs, last_week_outputs),
        "in_progress_tasks":    in_progress_tasks,
        "week_token_usage":     None,   # task_jobs 无 token_used 字段，暂不统计
        "week_tool_count":      week_tool_count,
        "tool_usage_breakdown": tool_usage_breakdown,
        "recent_tools":         recent_tools,
        "last_login_at":        last_login_at,
    })


# ---------------------------------------------------------------------------
# GET /operator/homepage/trend
# ---------------------------------------------------------------------------

@router.get("/trend")
async def get_homepage_trend(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """
    最近7天（含今天）每天的 outputs 产出数量。
    没有产出的日期 count=0，不缺项。
    date 格式：MM-DD
    """
    uid = current_user.id
    today_cst = datetime.now(_CST).date()
    # 生成最近7天日期列表（从7天前到今天）
    days = [today_cst - timedelta(days=i) for i in range(6, -1, -1)]

    # 用 generate_series 或手动 UNION 效率差不多；直接用 SQL 聚合后补零
    range_start = datetime(days[0].year, days[0].month, days[0].day, 0, 0, 0, tzinfo=_CST)
    range_end   = datetime(today_cst.year, today_cst.month, today_cst.day, 23, 59, 59, tzinfo=_CST)

    rows = (await db.execute(
        select(
            func.date(func.timezone("Asia/Shanghai", Output.created_at)).label("day"),
            func.count().label("cnt"),
        )
        .where(Output.created_by == uid)
        .where(Output.deleted_at.is_(None))
        .where(Output.created_at >= range_start)
        .where(Output.created_at <= range_end)
        .group_by(text("day"))
        .order_by(text("day"))
    )).all()

    # 建立 date → count 映射
    count_map: dict[date, int] = {row.day: row.cnt for row in rows}

    trend = [
        {
            "date":  d.strftime("%m-%d"),
            "count": count_map.get(d, 0),
        }
        for d in days
    ]

    return success_response(data={"trend": trend})
