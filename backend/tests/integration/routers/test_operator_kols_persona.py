"""红人工作台七字段唯一编辑入口集成测试。"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, text

from app.models.log import OperationLog
from app.models.persona_report import PersonaReport


async def _create_kol(test_session, name="人设达人", **values):
    columns = ["name", "status", *values]
    params = {"name": name, "status": "signed", **values}
    placeholders = ", ".join(f":{column}" for column in columns)
    result = await test_session.execute(text(
        f"INSERT INTO kols ({', '.join(columns)}) VALUES ({placeholders}) RETURNING id"
    ), params)
    kol_id = result.scalar_one()
    await test_session.commit()
    return kol_id


class TestGetPersonaDetails:
    @pytest.mark.asyncio
    async def test_get_no_token(self, test_client, test_session):
        kol_id = await _create_kol(test_session)
        response = await test_client.get(f"/api/operator/kols/{kol_id}/persona-details")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_returns_all_seven_fields_and_blank_aware_count(
        self, test_client, operator_headers, test_session
    ):
        kol_id = await _create_kol(
            test_session,
            persona="完整人格",
            content_plan="内容规划",
            background="  ",
            experience="真实经历",
        )

        response = await test_client.get(
            f"/api/operator/kols/{kol_id}/persona-details", headers=operator_headers
        )

        data = response.json()["data"]
        assert {field: data[field] for field in (
            "persona", "content_plan", "background", "experience",
            "relationships", "unique_story", "extra_notes",
        )} == {
            "persona": "完整人格",
            "content_plan": "内容规划",
            "background": "  ",
            "experience": "真实经历",
            "relationships": None,
            "unique_story": None,
            "extra_notes": None,
        }
        assert data["filled_count"] == 3
        assert data["total_count"] == 7


class TestUpdatePersonaDetails:
    @pytest.mark.asyncio
    async def test_put_requires_exactly_one_field(
        self, test_client, operator_headers, test_session
    ):
        kol_id = await _create_kol(test_session)

        empty = await test_client.put(
            f"/api/operator/kols/{kol_id}/persona-details",
            json={},
            headers=operator_headers,
        )
        multiple = await test_client.put(
            f"/api/operator/kols/{kol_id}/persona-details",
            json={"persona": "人格", "content_plan": "规划"},
            headers=operator_headers,
        )

        assert empty.json()["success"] is False
        assert multiple.json()["success"] is False

    @pytest.mark.asyncio
    async def test_put_accepts_empty_string_and_logs_only_field_name(
        self, test_client, operator_headers, test_session
    ):
        kol_id = await _create_kol(test_session, persona="需要清空的完整正文")

        response = await test_client.put(
            f"/api/operator/kols/{kol_id}/persona-details",
            json={"persona": ""},
            headers=operator_headers,
        )

        assert response.json()["data"]["persona"] == ""
        log = (await test_session.execute(
            select(OperationLog).where(
                OperationLog.action == "update_kol_persona_field",
                OperationLog.target_id == kol_id,
            )
        )).scalar_one()
        assert log.detail == {"field": "persona"}
        assert "需要清空的完整正文" not in str(log.detail)


class TestFillEmptyFacts:
    @pytest.mark.asyncio
    async def test_fill_empty_uses_current_operators_latest_ready_report_and_preserves_nonempty(
        self, test_client, operator_headers, test_session, operator_user, admin_user
    ):
        kol_id = await _create_kol(test_session, background="人工基本身份")
        now = datetime.now(timezone.utc)
        own_old = PersonaReport(
            operator_id=operator_user.id,
            kol_id=kol_id,
            status="ready",
            profile_result="自己的旧报告原文",
            created_at=now - timedelta(days=1),
        )
        own_latest = PersonaReport(
            operator_id=operator_user.id,
            kol_id=kol_id,
            status="ready",
            profile_result="自己的最新报告原文",
            created_at=now,
        )
        other_newer = PersonaReport(
            operator_id=admin_user.id,
            kol_id=kol_id,
            status="ready",
            profile_result="其他运营更新的报告原文",
            created_at=now + timedelta(days=1),
        )
        test_session.add_all([own_old, own_latest, other_newer])
        await test_session.commit()

        facts = {
            "background": "报告基本身份",
            "experience": "自己的最新报告原文",
            "relationships": "",
            "unique_story": "",
            "extra_notes": "",
        }
        extractor = AsyncMock(return_value=facts)
        with patch("app.routers.admin_kols._extract_grounded_facts", new=extractor):
            response = await test_client.post(
                f"/api/operator/kols/{kol_id}/persona-details/fill-empty",
                headers=operator_headers,
            )

        assert extractor.await_args.args[0] == "自己的最新报告原文"
        assert response.json()["data"]["filled_fields"] == ["experience"]
        details = await test_client.get(
            f"/api/operator/kols/{kol_id}/persona-details", headers=operator_headers
        )
        assert details.json()["data"]["background"] == "人工基本身份"
        assert details.json()["data"]["experience"] == "自己的最新报告原文"
