"""
Direct-call coverage tests for admin_values_writer.py。

直调 get_config / update_config，覆盖 default 不存在/存在 + insert/update 分支。
"""
import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from starlette.requests import Request

from app.models.values_writer import ValuesWriterConfig
from app.routers.admin_values_writer import ConfigIn, get_config, update_config


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(test_session):
    """清 values_writer_configs 防污染。"""
    await test_session.execute(delete(ValuesWriterConfig))
    await test_session.commit()
    yield


def _make_request() -> Request:
    return Request({"type": "http", "headers": [(b"user-agent", b"pytest")], "client": ("127.0.0.1", 0)})


@pytest.mark.asyncio
async def test_get_config_default_absent(test_session, admin_user):
    """default 不存在 → 空模板（is_active 默认 True）。"""
    resp = await get_config(db=test_session, _=admin_user)
    assert resp.data["config_key"] == "default"
    assert resp.data["is_active"] is True
    assert resp.data["model_id"] is None


@pytest.mark.asyncio
async def test_get_config_default_present(test_session, admin_user):
    """default 存在 → 真实值。"""
    test_session.add(ValuesWriterConfig(
        config_key="default", writing_prompt="hello", is_active=True,
    ))
    await test_session.commit()
    resp = await get_config(db=test_session, _=admin_user)
    assert resp.data["writing_prompt"] == "hello"


@pytest.mark.asyncio
async def test_update_config_insert_when_absent(test_session, admin_user):
    """default 不存在 → update+returning row=None → insert 新行。"""
    body = ConfigIn(writing_prompt="新", is_active=True)
    resp = await update_config(
        body=body, request=_make_request(), db=test_session, current_user=admin_user,
    )
    assert resp.data["config_key"] == "default"

    cfg = (await test_session.execute(
        select(ValuesWriterConfig)
    )).scalar_one()
    assert cfg.writing_prompt == "新"


@pytest.mark.asyncio
async def test_update_config_update_when_present(test_session, admin_user):
    """default 存在 → 走 update+returning 分支。"""
    test_session.add(ValuesWriterConfig(
        config_key="default", writing_prompt="old", is_active=True,
    ))
    await test_session.commit()
    body = ConfigIn(writing_prompt="new", is_active=False)
    resp = await update_config(
        body=body, request=_make_request(), db=test_session, current_user=admin_user,
    )
    assert resp.success is True
