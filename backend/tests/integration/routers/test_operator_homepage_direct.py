"""
Direct-call coverage tests for operator_homepage.py。

直调 get_homepage_stats / get_homepage_trend，覆盖空数据 / 今日产出 / 本周 task 多 tool
聚合（含 "其他" 分桶）/ last_login_at 序列化 + 7 天 trend 补零。
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.models.output import Output
from app.models.task import TaskJob
from app.routers.operator_homepage import (
    _format_change,
    _today_start_cst,
    _week_start_cst,
    get_homepage_stats,
    get_homepage_trend,
    require_operator,
)
from fastapi import HTTPException


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(test_session):
    """清本文件 seed 的 cov_* 行（保留其他测试的 task_id=1 等）。"""
    from sqlalchemy import select
    cov_task_ids = (await test_session.execute(
        select(TaskJob.id).where(TaskJob.task_no.like("cov_%"))
    )).scalars().all()
    if cov_task_ids:
        await test_session.execute(delete(Output).where(Output.task_id.in_(cov_task_ids)))
    await test_session.execute(delete(Output).where(Output.title.like("cov_%")))
    await test_session.execute(delete(TaskJob).where(TaskJob.task_no.like("cov_%")))
    await test_session.commit()
    yield


# ---------------------------------------------------------------------------
# 纯函数
# ---------------------------------------------------------------------------

def test_format_change_prior_zero():
    assert _format_change(5, 0) is None


def test_format_change_zero():
    assert _format_change(5, 5) == "0%"


def test_format_change_positive():
    assert _format_change(6, 5) == "+20.0%"


def test_format_change_negative():
    assert _format_change(4, 5) == "-20.0%"


def test_week_start_cst_is_monday():
    """week_start 应为周一 00:00 CST。"""
    ws = _week_start_cst()
    assert ws.weekday() == 0  # 0=Monday
    assert ws.hour == 0 and ws.minute == 0


def test_today_start_cst():
    ts = _today_start_cst()
    assert ts.hour == 0 and ts.minute == 0


# ---------------------------------------------------------------------------
# require_operator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_require_operator_force_password(test_session, operator_user):
    """password_changed_at 为 None → 403。"""
    operator_user.password_changed_at = None
    await test_session.commit()
    with pytest.raises(HTTPException) as exc:
        await require_operator(current_user=operator_user)
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "AUTH_FORCE_CHANGE_PASSWORD"


@pytest.mark.asyncio
async def test_require_operator_role_denied(test_session, admin_user):
    """role 不在 operator/admin 之外 → 403 PERMISSION_DENIED（用 admin 通过；构造 viewer 角色更好）。

    这里通过手工造一个 role=viewer 的 user 触发。
    """
    from app.models.user import User
    viewer = User(
        username=f"cov_viewer_{uuid.uuid4().hex[:8]}",
        real_name="viewer",
        password_hash="x",
        role="viewer",
        status="enabled",
        password_changed_at=datetime.now(tz=timezone.utc),
    )
    test_session.add(viewer)
    await test_session.commit()
    with pytest.raises(HTTPException) as exc:
        await require_operator(current_user=viewer)
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_require_operator_admin_ok(admin_user):
    """admin 角色通过。"""
    u = await require_operator(current_user=admin_user)
    assert u.id == admin_user.id


# ---------------------------------------------------------------------------
# GET /stats
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stats_empty(test_session, operator_user):
    """无任何产出 → 全 0 + breakdown 空 + recent_tools 空。"""
    resp = await get_homepage_stats(db=test_session, current_user=operator_user)
    assert resp.data["today_outputs"] == 0
    assert resp.data["week_outputs"] == 0
    assert resp.data["in_progress_tasks"] == 0
    assert resp.data["today_outputs_change"] is None  # 昨日 0 → None
    assert resp.data["week_outputs_change"] is None
    assert resp.data["week_token_usage"] is None
    assert resp.data["tool_usage_breakdown"] == []
    assert resp.data["recent_tools"] == []
    assert resp.data["last_login_at"] is None  # operator_user 无 last_login_at


@pytest.mark.asyncio
async def test_stats_with_today_output(test_session, operator_user):
    """今天有 1 条 output → today_outputs=1，yesterday=0 → change None。"""
    cst = timezone(timedelta(hours=8))
    test_session.add(Output(
        title="cov_today",
        tool_code="qianchuan-writer", tool_name="千川",
        created_by=operator_user.id,
        created_at=datetime.now(tz=cst),
    ))
    await test_session.commit()

    resp = await get_homepage_stats(db=test_session, current_user=operator_user)
    assert resp.data["today_outputs"] == 1


@pytest.mark.asyncio
async def test_stats_breakdown_with_other_bucket(test_session, operator_user):
    """本周 6 个不同 tool_code（前 4 + "其他" 桶）。"""
    cst = timezone(timedelta(hours=8))
    now = datetime.now(tz=cst)
    for i in range(6):
        test_session.add(TaskJob(
            task_no=f"cov_b_{i}_{uuid.uuid4().hex[:6]}",
            tool_code=f"tool_{i}", tool_name=f"工具_{i}",
            status="done", created_by=operator_user.id, created_at=now,
        ))
    await test_session.commit()

    resp = await get_homepage_stats(db=test_session, current_user=operator_user)
    breakdown = resp.data["tool_usage_breakdown"]
    # 6 个 tool → top4 + "其他"
    names = [b["tool_name"] for b in breakdown]
    assert "其他" in names
    assert resp.data["week_tool_count"] == 6
    # 最近 6 个 tool（recent_tools），都有 last_used_at
    assert len(resp.data["recent_tools"]) == 6


# ---------------------------------------------------------------------------
# GET /trend
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trend_seven_days(test_session, operator_user):
    """无产出 → 7 天全 0；长度=7；date 格式 MM-DD。"""
    resp = await get_homepage_trend(db=test_session, current_user=operator_user)
    trend = resp.data["trend"]
    assert len(trend) == 7
    assert all(item["count"] == 0 for item in trend)
    assert all(len(item["date"]) == 5 for item in trend)  # MM-DD
