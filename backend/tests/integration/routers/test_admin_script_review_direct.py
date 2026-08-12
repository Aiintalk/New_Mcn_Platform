"""
Direct-call coverage tests for admin_script_review.py。

直调 get_config / update_config，覆盖 default 缺省/存在 + insert/update 分支。
"""
import pytest
import pytest_asyncio
from sqlalchemy import delete
from starlette.requests import Request

from app.models.qianchuan_script_review import QianchuanScriptReviewConfig
from app.routers.admin_script_review import ConfigIn, get_config, update_config


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(test_session):
    """清 qianchuan_script_review_configs 防污染。"""
    await test_session.execute(delete(QianchuanScriptReviewConfig))
    await test_session.commit()
    yield


def _make_request() -> Request:
    return Request({"type": "http", "headers": [(b"user-agent", b"pytest")], "client": ("127.0.0.1", 0)})


@pytest.mark.asyncio
async def test_get_config_absent(test_session, admin_user):
    """default 不存在 → 空模板。"""
    resp = await get_config(db=test_session, _=admin_user)
    assert resp.data["config_key"] == "default"
    assert resp.data["direct_prompt"] is None


@pytest.mark.asyncio
async def test_get_config_present(test_session, admin_user):
    """default 存在 → 真值。"""
    test_session.add(QianchuanScriptReviewConfig(
        config_key="default", direct_prompt="dp", value_prompt="vp", is_active=True,
    ))
    await test_session.commit()
    resp = await get_config(db=test_session, _=admin_user)
    assert resp.data["direct_prompt"] == "dp"
    assert resp.data["value_prompt"] == "vp"


@pytest.mark.asyncio
async def test_update_config_insert(test_session, admin_user):
    """default 不存在 → insert 新行。"""
    body = ConfigIn(direct_prompt="dp", is_active=True)
    resp = await update_config(
        body=body, request=_make_request(), db=test_session, current_user=admin_user,
    )
    assert resp.data["config_key"] == "default"


@pytest.mark.asyncio
async def test_update_config_update(test_session, admin_user):
    """default 存在 → update+returning 走通。"""
    test_session.add(QianchuanScriptReviewConfig(
        config_key="default", is_active=True,
    ))
    await test_session.commit()
    body = ConfigIn(value_prompt="vp", is_active=False)
    resp = await update_config(
        body=body, request=_make_request(), db=test_session, current_user=admin_user,
    )
    assert resp.success is True
