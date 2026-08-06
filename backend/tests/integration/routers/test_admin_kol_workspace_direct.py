"""
Direct-call coverage tests for admin_kol_workspace.py。

test_admin_kols.py 经 test_client 跑端点对端点体覆盖不稳定；这里直接 await
端点函数，稳定记录函数体覆盖。纯测试，不改生产代码。

覆盖：
- GET  /{kol_id}/workspace-config  — 404 / 无配置（含 _DEFAULT_TABS）/ 已有配置
- PUT  /{kol_id}/workspace-config  — 404 / 新建 upsert / 更新已存在
- _get_global_prompts / _get_ip 分支
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from starlette.requests import Request

from app.models.kol import Kol
from app.models.kol_workspace_config import KolWorkspaceConfig
from app.routers.admin_kol_workspace import (
    WorkspaceConfigIn,
    _get_ip,
    _get_kol_or_404,
    get_workspace_config,
    update_workspace_config,
)
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(autouse=True)
async def _cleanup(test_session):
    """清本文件 seed 的 cov_kol_% 行（保留其他测试的 kol 数据）。"""
    from sqlalchemy import select
    cov_kol_ids = (await test_session.execute(
        select(Kol.id).where(Kol.name.like("cov_kol_%"))
    )).scalars().all()
    if cov_kol_ids:
        await test_session.execute(
            delete(KolWorkspaceConfig).where(KolWorkspaceConfig.kol_id.in_(cov_kol_ids))
        )
    await test_session.execute(delete(Kol).where(Kol.name.like("cov_kol_%")))
    await test_session.commit()
    yield


def _make_request(xff: str | None = None) -> Request:
    headers: list = [(b"user-agent", b"pytest")]
    if xff:
        headers.append((b"x-forwarded-for", xff.encode()))
    return Request({"type": "http", "headers": headers, "client": ("127.0.0.1", 0)})


async def _seed_kol(test_session, **kwargs) -> Kol:
    suffix = uuid.uuid4().hex[:8]
    kol = Kol(name=f"cov_kol_{suffix}", status="signed", **kwargs)
    test_session.add(kol)
    await test_session.commit()
    await test_session.refresh(kol)
    return kol


# ---------------------------------------------------------------------------
# _get_ip / _get_kol_or_404 单元
# ---------------------------------------------------------------------------

def test_get_ip_direct():
    """xff 存在 → 取首个。"""
    req = _make_request(xff="10.0.0.1, 10.0.0.2")
    assert _get_ip(req) == "10.0.0.1"


def test_get_ip_no_xff():
    """无 xff → client.host。"""
    req = _make_request()
    assert _get_ip(req) == "127.0.0.1"


@pytest.mark.asyncio
async def test_get_kol_or_404_missing(test_session):
    """不存在的 kol_id → HTTPException 404。"""
    with pytest.raises(HTTPException) as exc:
        await _get_kol_or_404(test_session, 99999999)
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# GET /{kol_id}/workspace-config
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_config_404(test_session, admin_user):
    """kol 不存在 → 404。"""
    with pytest.raises(HTTPException) as exc:
        await get_workspace_config(kol_id=99999999, db=test_session, current_user=admin_user)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_config_force_change_password(test_session, operator_user):
    """password_changed_at 为 None → 403。"""
    operator_user.password_changed_at = None
    await test_session.commit()

    with pytest.raises(HTTPException) as exc:
        await get_workspace_config(kol_id=1, db=test_session, current_user=operator_user)
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "AUTH_FORCE_CHANGE_PASSWORD"


@pytest.mark.asyncio
async def test_get_config_no_existing_uses_defaults(test_session, admin_user):
    """无 KolWorkspaceConfig → enabled_tabs 落到 _DEFAULT_TABS，prompt_overrides 空。"""
    kol = await _seed_kol(test_session)
    resp = await get_workspace_config(kol_id=kol.id, db=test_session, current_user=admin_user)

    assert resp.data["kol_id"] == kol.id
    assert resp.data["enabled_tabs"]  # 落到默认列表
    assert resp.data["prompt_overrides"] == {}
    assert "qianchuan-writer" in resp.data["global_prompts"]  # _get_global_prompts 走通
    assert "persona-writer" in resp.data["global_prompts"]
    assert "livestream-review" in resp.data["global_prompts"]
    assert "values-writer" in resp.data["global_prompts"]
    assert "retrospective" in resp.data["global_prompts"]


@pytest.mark.asyncio
async def test_get_config_with_existing(test_session, admin_user):
    """已有 KolWorkspaceConfig → 读出来。"""
    kol = await _seed_kol(test_session)
    test_session.add(KolWorkspaceConfig(
        kol_id=kol.id,
        enabled_tabs=["dashboard", "persona"],
        prompt_overrides={"qianchuan-writer": {"system_prompt": "ovr"}},
    ))
    await test_session.commit()

    resp = await get_workspace_config(kol_id=kol.id, db=test_session, current_user=admin_user)
    assert resp.data["enabled_tabs"] == ["dashboard", "persona"]
    assert resp.data["prompt_overrides"]["qianchuan-writer"]["system_prompt"] == "ovr"


# ---------------------------------------------------------------------------
# PUT /{kol_id}/workspace-config
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_config_404(test_session, admin_user):
    """kol 不存在 → 404。"""
    with pytest.raises(HTTPException) as exc:
        await update_workspace_config(
            kol_id=99999999,
            body=WorkspaceConfigIn(enabled_tabs=["dashboard"]),
            request=_make_request(),
            db=test_session,
            current_user=admin_user,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_config_insert_new(test_session, admin_user):
    """无配置 → insert（clean_overrides 过滤空字符串）。"""
    kol = await _seed_kol(test_session)
    body = WorkspaceConfigIn(
        enabled_tabs=["dashboard", "persona"],
        prompt_overrides={
            "qianchuan-writer": {"system_prompt": "  "},  # 空白 → 清成 None → 整 tool 不写入
            "persona-writer": {"evaluation_prompt": "real"},
        },
    )
    resp = await update_workspace_config(
        kol_id=kol.id, body=body, request=_make_request(xff="1.2.3.4"),
        db=test_session, current_user=admin_user,
    )
    assert resp.data["kol_id"] == kol.id
    assert resp.data["enabled_tabs"] == ["dashboard", "persona"]

    cfg = (await test_session.execute(
        select(KolWorkspaceConfig).where(KolWorkspaceConfig.kol_id == kol.id)
    )).scalar_one()
    # 空白 tool 应被整体移除
    assert "qianchuan-writer" not in cfg.prompt_overrides
    assert cfg.prompt_overrides["persona-writer"]["evaluation_prompt"] == "real"


@pytest.mark.asyncio
async def test_update_config_update_existing(test_session, admin_user):
    """已有配置 → 更新字段。"""
    kol = await _seed_kol(test_session)
    test_session.add(KolWorkspaceConfig(
        kol_id=kol.id, enabled_tabs=["dashboard"], prompt_overrides={},
    ))
    await test_session.commit()

    body = WorkspaceConfigIn(
        enabled_tabs=["dashboard", "persona", "film-review"],
        prompt_overrides={"livestream-writer": {"system_prompt": "new"}},
    )
    resp = await update_workspace_config(
        kol_id=kol.id, body=body, request=_make_request(),
        db=test_session, current_user=admin_user,
    )
    assert resp.data["enabled_tabs"] == ["dashboard", "persona", "film-review"]

    cfg = (await test_session.execute(
        select(KolWorkspaceConfig).where(KolWorkspaceConfig.kol_id == kol.id)
    )).scalar_one()
    assert cfg.prompt_overrides == {"livestream-writer": {"system_prompt": "new"}}


@pytest.mark.asyncio
async def test_update_config_strip_empty_keeps_tool_when_partial(test_session, admin_user):
    """一个 tool 部分键有值 → 保留该 tool，空键变 None。"""
    kol = await _seed_kol(test_session)
    body = WorkspaceConfigIn(
        enabled_tabs=["dashboard"],
        prompt_overrides={
            "persona-writer": {
                "evaluation_prompt": "",      # 空 → None
                "writing_prompt": "valid",    # 有值
            },
        },
    )
    await update_workspace_config(
        kol_id=kol.id, body=body, request=_make_request(),
        db=test_session, current_user=admin_user,
    )
    cfg = (await test_session.execute(
        select(KolWorkspaceConfig).where(KolWorkspaceConfig.kol_id == kol.id)
    )).scalar_one()
    assert cfg.prompt_overrides["persona-writer"]["writing_prompt"] == "valid"
    assert cfg.prompt_overrides["persona-writer"]["evaluation_prompt"] is None
