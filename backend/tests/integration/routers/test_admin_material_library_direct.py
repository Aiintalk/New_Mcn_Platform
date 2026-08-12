"""
Direct-call coverage tests for admin_material_library.py。

直调 get_configs / update_configs，覆盖空配置列表、有配置、配置不存在、
有 ai_model_id/system_prompt/is_active 三字段更新。
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete
from starlette.requests import Request

from app.models.material_library import MaterialLibraryConfig
from app.routers.admin_material_library import ConfigUpdate, get_configs, update_configs


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(test_session):
    """清 material_library_configs 防污染。"""
    await test_session.execute(delete(MaterialLibraryConfig))
    await test_session.commit()
    yield


def _make_request() -> Request:
    return Request({"type": "http", "headers": [(b"user-agent", b"pytest")], "client": ("127.0.0.1", 0)})


async def _seed_cfg(test_session, **kwargs) -> MaterialLibraryConfig:
    defaults = dict(
        config_key="soul_generator",
        system_prompt="原始 prompt",
        is_active=True,
    )
    defaults.update(kwargs)
    cfg = MaterialLibraryConfig(**defaults)
    test_session.add(cfg)
    await test_session.commit()
    await test_session.refresh(cfg)
    return cfg


@pytest.mark.asyncio
async def test_get_configs_empty(test_session, admin_user):
    """空表 → 空列表。不报错。"""
    resp = await get_configs(db=test_session, _=admin_user)
    assert resp.data == []


@pytest.mark.asyncio
async def test_get_configs_with_rows(test_session, admin_user):
    """有配置 → 列表（system_prompt 空也返回 ""）。"""
    await _seed_cfg(test_session, system_prompt=None)
    resp = await get_configs(db=test_session, _=admin_user)
    assert len(resp.data) == 1
    assert resp.data[0]["config_key"] == "soul_generator"
    assert resp.data[0]["system_prompt"] == ""  # None → ""


@pytest.mark.asyncio
async def test_update_configs_not_found(test_session, admin_user):
    """default 不存在 → success + message 提示。"""
    body = ConfigUpdate(system_prompt="new")
    resp = await update_configs(
        body=body, request=_make_request(), db=test_session, admin=admin_user,
    )
    assert resp.success is True
    assert "不存在" in resp.message


@pytest.mark.asyncio
async def test_update_configs_all_fields(test_session, admin_user):
    """更新三字段 → changes 写全（先 seed AiModel 满足 FK）。"""
    from app.models.credential import AiModel
    import uuid as _uuid
    ai = AiModel(
        name="cov_ai", provider="yunwu",
        model_id=f"cov-ai-{_uuid.uuid4().hex[:8]}", status="active",
    )
    test_session.add(ai)
    await test_session.commit()
    await test_session.refresh(ai)

    await _seed_cfg(test_session)
    body = ConfigUpdate(ai_model_id=ai.id, system_prompt="new prompt", is_active=False)
    resp = await update_configs(
        body=body, request=_make_request(), db=test_session, admin=admin_user,
    )
    assert resp.data["ai_model_id"] == ai.id
    assert resp.data["system_prompt"] == "new prompt"
    assert resp.data["is_active"] is False


@pytest.mark.asyncio
async def test_update_configs_partial(test_session, admin_user):
    """只更新一个字段 → 其他不变。"""
    await _seed_cfg(test_session, system_prompt="keep me")
    body = ConfigUpdate(system_prompt=None, ai_model_id=None, is_active=False)
    resp = await update_configs(
        body=body, request=_make_request(), db=test_session, admin=admin_user,
    )
    assert resp.data["system_prompt"] == "keep me"  # 没更新
    assert resp.data["is_active"] is False  # 更新了
