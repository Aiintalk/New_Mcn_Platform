"""
Direct-call coverage tests for admin_benchmark.py（Round 2）。

Round 1 的 test_admin_benchmark.py 经 test_client（ASGITransport）跑端点，
coverage 对端点函数体追踪不稳定。这里直接 await 端点函数，稳定记录函数体覆盖，
把 admin_benchmark 从 69% 拉满。纯测试，不改生产代码。
"""
import pytest
from starlette.requests import Request

from app.models.benchmark import BenchmarkAnalysis, BenchmarkConfig
from app.routers.admin_benchmark import (
    ConfigIn,
    get_analysis_detail,
    list_analyses,
    list_configs,
    regenerate_analysis,
    update_config,
)


def _make_request() -> Request:
    return Request({"type": "http", "headers": [], "client": ("127.0.0.1", 0)})


@pytest.mark.asyncio
async def test_list_configs_direct(test_session, admin_user):
    """直调 list_configs → 返回 list（含 seed 的 config）。"""
    test_session.add(BenchmarkConfig(config_key="dc_cfg_a", system_prompt="p1", is_active=True))
    test_session.add(BenchmarkConfig(config_key="dc_cfg_b", system_prompt="p2", is_active=False))
    await test_session.commit()

    resp = await list_configs(db=test_session, _=admin_user)
    keys = [c["config_key"] for c in resp.data]
    assert "dc_cfg_a" in keys and "dc_cfg_b" in keys
    sample = resp.data[0]
    for k in ("id", "config_key", "ai_model_id", "system_prompt", "is_active", "updated_at"):
        assert k in sample


@pytest.mark.asyncio
async def test_update_config_direct(test_session, admin_user):
    """直调 update_config → 更新 + 返回 config_key。"""
    test_session.add(BenchmarkConfig(config_key="dc_upd", system_prompt="old", is_active=True))
    await test_session.commit()

    resp = await update_config(
        "dc_upd",
        ConfigIn(system_prompt="new", is_active=False),
        request=_make_request(),
        db=test_session,
        current_user=admin_user,
    )
    assert resp.data["config_key"] == "dc_upd"


@pytest.mark.asyncio
async def test_list_analyses_direct(test_session, admin_user):
    """直调 list_analyses → list（含 seed）。"""
    test_session.add(BenchmarkAnalysis(account_name="dc_acct", status="completed", created_by=admin_user.id))
    await test_session.commit()

    resp = await list_analyses(db=test_session, _=admin_user)
    names = [a["account_name"] for a in resp.data]
    assert "dc_acct" in names


@pytest.mark.asyncio
async def test_get_analysis_detail_direct(test_session, admin_user):
    """直调 get_analysis_detail → 完整字段。"""
    a = BenchmarkAnalysis(account_name="dc_detail", model_used="glm-4.6", status="completed", created_by=admin_user.id)
    test_session.add(a)
    await test_session.commit()
    await test_session.refresh(a)

    resp = await get_analysis_detail(a.id, db=test_session, _=admin_user)
    assert resp.data["account_name"] == "dc_detail"
    assert resp.data["model_used"] == "glm-4.6"


@pytest.mark.asyncio
async def test_regenerate_analysis_direct(test_session, admin_user):
    """直调 regenerate_analysis → 重置 status=pending。"""
    a = BenchmarkAnalysis(account_name="dc_regen", status="completed", profile_result="x", plan_result="y", created_by=admin_user.id)
    test_session.add(a)
    await test_session.commit()
    await test_session.refresh(a)

    resp = await regenerate_analysis(a.id, request=_make_request(), db=test_session, current_user=admin_user)
    assert resp.data["status"] == "pending"
