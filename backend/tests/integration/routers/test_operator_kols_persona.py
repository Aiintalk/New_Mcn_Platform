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

    @pytest.mark.parametrize(("facts", "expected_fields"), [
        ({
            "background": "",
            "experience": "报告中的真实经历",
            "relationships": "",
            "unique_story": "",
            "extra_notes": "",
        }, ["experience"]),
        ({
            "background": "",
            "experience": "",
            "relationships": "",
            "unique_story": "",
            "extra_notes": "",
        }, []),
    ])
    @pytest.mark.asyncio
    async def test_successful_retry_closes_latest_fact_failure_even_without_new_fields(
        self,
        facts,
        expected_fields,
        test_client,
        operator_headers,
        test_session,
        operator_user,
    ):
        kol_id = await _create_kol(test_session)
        report = PersonaReport(
            operator_id=operator_user.id,
            kol_id=kol_id,
            status="ready",
            profile_result="报告中的真实经历",
        )
        test_session.add(report)
        await test_session.flush()
        test_session.add(OperationLog(
            user_id=operator_user.id,
            username=operator_user.username,
            role=operator_user.role,
            action="persona_fact_sync_failed",
            target_type="persona_report",
            target_id=report.id,
            detail={"kol_id": kol_id, "status": "failed"},
            ip="127.0.0.1",
        ))
        await test_session.commit()

        with patch(
            "app.routers.admin_kols._extract_grounded_facts",
            new=AsyncMock(return_value=facts),
        ):
            response = await test_client.post(
                f"/api/operator/kols/{kol_id}/persona-details/fill-empty",
                headers=operator_headers,
            )

        assert response.json()["data"]["filled_fields"] == expected_fields
        detail = await test_client.get(
            f"/api/persona/reports/{report.id}", headers=operator_headers
        )
        assert detail.json()["data"]["fact_sync_failed"] is False
        latest_log = (await test_session.execute(
            select(OperationLog)
            .where(
                OperationLog.target_type == "persona_report",
                OperationLog.target_id == report.id,
                OperationLog.action.in_((
                    "persona_fact_sync_failed", "fill_kol_persona_facts"
                )),
            )
            .order_by(OperationLog.created_at.desc(), OperationLog.id.desc())
            .limit(1)
        )).scalar_one()
        assert latest_log.action == "fill_kol_persona_facts"
        assert latest_log.detail == {
            "kol_id": kol_id,
            "report_id": report.id,
            "fields": expected_fields,
        }
        assert "报告中的真实经历" not in str(latest_log.detail)

    @pytest.mark.asyncio
    async def test_failed_retry_becomes_latest_fact_state_without_logging_report_text(
        self, test_client, operator_headers, test_session, operator_user
    ):
        kol_id = await _create_kol(test_session)
        report = PersonaReport(
            operator_id=operator_user.id,
            kol_id=kol_id,
            status="ready",
            profile_result="不得进入日志的报告正文",
        )
        test_session.add(report)
        await test_session.flush()
        test_session.add(OperationLog(
            user_id=operator_user.id,
            username=operator_user.username,
            role=operator_user.role,
            action="persona_fact_sync_failed",
            target_type="persona_report",
            target_id=report.id,
            detail={"kol_id": kol_id, "status": "failed"},
            ip="127.0.0.1",
        ))
        await test_session.flush()
        test_session.add(OperationLog(
            user_id=operator_user.id,
            username=operator_user.username,
            role=operator_user.role,
            action="fill_kol_persona_facts",
            target_type="kol",
            target_id=kol_id,
            detail={"kol_id": kol_id, "report_id": report.id, "fields": []},
            ip="127.0.0.1",
        ))
        await test_session.commit()

        detail_before_retry = await test_client.get(
            f"/api/persona/reports/{report.id}", headers=operator_headers
        )
        assert detail_before_retry.json()["data"]["fact_sync_failed"] is False

        with patch(
            "app.routers.admin_kols._extract_grounded_facts",
            new=AsyncMock(side_effect=RuntimeError("提取失败")),
        ):
            response = await test_client.post(
                f"/api/operator/kols/{kol_id}/persona-details/fill-empty",
                headers=operator_headers,
            )

        assert response.json()["success"] is False
        detail = await test_client.get(
            f"/api/persona/reports/{report.id}", headers=operator_headers
        )
        assert detail.json()["data"]["fact_sync_failed"] is True
        latest_log = (await test_session.execute(
            select(OperationLog)
            .where(
                OperationLog.target_type == "persona_report",
                OperationLog.target_id == report.id,
                OperationLog.action.in_((
                    "persona_fact_sync_failed", "fill_kol_persona_facts"
                )),
            )
            .order_by(OperationLog.created_at.desc(), OperationLog.id.desc())
            .limit(1)
        )).scalar_one()
        assert latest_log.action == "persona_fact_sync_failed"
        assert "不得进入日志的报告正文" not in str(latest_log.detail)
