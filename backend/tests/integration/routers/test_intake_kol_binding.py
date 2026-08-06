"""入驻链接和直发会话保存可选正式达人编号。"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.kol import Kol
from app.models.kol_intake import KolIntakeLink, KolIntakeOperatorSession


@pytest.mark.asyncio
async def test_link_creation_persists_valid_kol_id(
    test_client, operator_headers, operator_user, test_session,
):
    kol = Kol(name="链接绑定达人")
    test_session.add(kol)
    await test_session.commit()

    response = await test_client.post(
        "/api/operator/intake/links",
        headers=operator_headers,
        json={"kol_id": kol.id, "kol_name": "展示名"},
    )

    assert response.status_code == 200
    link_id = response.json()["data"]["id"]
    link = (await test_session.execute(
        select(KolIntakeLink).where(KolIntakeLink.id == link_id)
    )).scalar_one()
    assert link.kol_id == kol.id


@pytest.mark.asyncio
async def test_direct_session_creation_persists_valid_kol_id(
    test_client, operator_headers, test_session,
):
    kol = Kol(name="直发绑定达人")
    test_session.add(kol)
    await test_session.commit()

    response = await test_client.post(
        "/api/operator/intake/direct/start",
        headers=operator_headers,
        json={"kol_id": kol.id, "kol_name": "展示名"},
    )

    assert response.status_code == 200
    session_id = response.json()["data"]["session_id"]
    session = (await test_session.execute(
        select(KolIntakeOperatorSession).where(KolIntakeOperatorSession.id == session_id)
    )).scalar_one()
    assert session.kol_id == kol.id


@pytest.mark.asyncio
async def test_intake_creation_rejects_missing_or_deleted_kol(
    test_client, operator_headers, test_session,
):
    deleted = Kol(name="已删除绑定达人", deleted_at=datetime.now(timezone.utc))
    test_session.add(deleted)
    await test_session.commit()

    for endpoint in ("/api/operator/intake/links", "/api/operator/intake/direct/start"):
        for kol_id in (999999, deleted.id):
            response = await test_client.post(
                endpoint,
                headers=operator_headers,
                json={"kol_id": kol_id},
            )
            assert response.status_code == 404
