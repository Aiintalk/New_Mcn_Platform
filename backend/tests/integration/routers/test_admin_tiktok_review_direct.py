"""
Direct-call coverage tests for admin_tiktok_review.py。

直调 list_configs / update_config，覆盖列表 + 更新成功 + 配置不存在 404。
"""
import pytest
import pytest_asyncio
from sqlalchemy import delete
from starlette.requests import Request
from fastapi import HTTPException

from app.models.tiktok_review import TiktokReviewConfig
from app.routers.admin_tiktok_review import ConfigIn, list_configs, update_config


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(test_session):
    """清 tiktok_review_configs 防污染。"""
    await test_session.execute(delete(TiktokReviewConfig))
    await test_session.commit()
    yield


def _make_request() -> Request:
    return Request({"type": "http", "headers": [(b"user-agent", b"pytest")], "client": ("127.0.0.1", 0)})


async def _seed(test_session, key="default") -> TiktokReviewConfig:
    cfg = TiktokReviewConfig(config_key=key, system_prompt="p", is_active=True)
    test_session.add(cfg)
    await test_session.commit()
    await test_session.refresh(cfg)
    return cfg


@pytest.mark.asyncio
async def test_list_configs(test_session, admin_user):
    """有行 → 列表返回。"""
    await _seed(test_session, key="default")
    resp = await list_configs(db=test_session, _=admin_user)
    assert len(resp.data) == 1


@pytest.mark.asyncio
async def test_update_config_ok(test_session, admin_user):
    """存在 → update+returning 走通。"""
    await _seed(test_session, key="default")
    body = ConfigIn(system_prompt="new", is_active=False)
    resp = await update_config(
        config_key="default", body=body, request=_make_request(),
        db=test_session, current_user=admin_user,
    )
    assert resp.data["config_key"] == "default"


@pytest.mark.asyncio
async def test_update_config_not_found(test_session, admin_user):
    """不存在 → HTTPException 404。"""
    body = ConfigIn(system_prompt="new")
    with pytest.raises(HTTPException) as exc:
        await update_config(
            config_key="no_such", body=body, request=_make_request(),
            db=test_session, current_user=admin_user,
        )
    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "RESOURCE_NOT_FOUND"
