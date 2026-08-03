"""人格定位只使用正式达人编号，并按运营隔离入驻资料。"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.models.kol import Kol
from app.models.kol_intake import KolIntakeLink, KolIntakeOperatorSession, KolIntakeSubmission
from app.models.kol_intake import KolIntakeConfig
from app.models.log import OperationLog
from app.models.output import Output
from app.models.persona_report import PersonaReport
from app.models.user import User


async def _other_operator(test_session) -> User:
    user = User(
        username="persona_other_operator",
        real_name="其他运营",
        password_hash="unused",
        role="operator",
        status="enabled",
        password_changed_at=datetime.now(timezone.utc),
    )
    test_session.add(user)
    await test_session.commit()
    return user


class TestFormalKolIdentity:
    @pytest.mark.asyncio
    async def test_formal_kol_list_searches_and_paginates_without_session_ids(
        self, test_client, operator_headers, test_session,
    ):
        formal_kol = Kol(
            name="正式达人",
            account_name="抖音昵称",
            douyin_id="formal-douyin",
            persona="已填",
            content_plan="已填",
        )
        deleted_kol = Kol(name="已删除达人", deleted_at=datetime.now(timezone.utc))
        test_session.add_all([formal_kol, deleted_kol])
        await test_session.commit()

        for keyword in ("正式达人", "抖音昵称", "formal-douyin"):
            response = await test_client.get(
                f"/api/persona/kols?page=1&page_size=10&keyword={keyword}",
                headers=operator_headers,
            )

            assert response.status_code == 200
            data = response.json()["data"]
            assert data["pagination"] == {"page": 1, "page_size": 10, "total": 1, "total_pages": 1}
            formal_item = data["items"][0]
            assert formal_item["id"] == formal_kol.id
            assert formal_item["profile_filled_count"] == 2
            assert formal_item["profile_total"] == 7
            assert "会话_" not in response.text

    @pytest.mark.asyncio
    async def test_intake_returns_only_current_operators_latest_bound_ready_record(
        self, test_client, operator_headers, operator_user, test_session,
    ):
        formal_kol = Kol(name="目标达人")
        other_operator = await _other_operator(test_session)
        test_session.add(formal_kol)
        await test_session.flush()
        own_direct = KolIntakeOperatorSession(
            operator_id=operator_user.id,
            kol_id=formal_kol.id,
            messages=[{"role": "user", "content": "本人回答"}],
            ai_report="本人绑定报告",
            report_status="ready",
            report_generated_at=datetime.now(timezone.utc),
        )
        other_direct = KolIntakeOperatorSession(
            operator_id=other_operator.id,
            kol_id=formal_kol.id,
            messages=[{"role": "user", "content": "其他回答"}],
            ai_report="其他运营报告",
            report_status="ready",
            report_generated_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        )
        historical_unbound = KolIntakeOperatorSession(
            operator_id=operator_user.id,
            messages=[{"role": "user", "content": "历史回答"}],
            ai_report="未绑定历史报告",
            report_status="ready",
            report_generated_at=datetime.now(timezone.utc) + timedelta(minutes=2),
        )
        test_session.add_all([own_direct, other_direct, historical_unbound])
        await test_session.commit()

        response = await test_client.get(
            f"/api/persona/kols/{formal_kol.id}/intake", headers=operator_headers,
        )

        assert response.status_code == 200
        own_bound_intake = response.json()["data"]
        assert own_bound_intake["report"] == "本人绑定报告"
        assert "其他运营报告" not in response.text
        assert "未绑定历史报告" not in response.text
        assert "session_id" not in response.text

    @pytest.mark.asyncio
    async def test_intake_returns_not_found_for_missing_or_deleted_kol(
        self, test_client, operator_headers, test_session,
    ):
        deleted_kol = Kol(name="已删", deleted_at=datetime.now(timezone.utc))
        test_session.add(deleted_kol)
        await test_session.commit()

        for kol_id in (999999, deleted_kol.id):
            response = await test_client.get(
                f"/api/persona/kols/{kol_id}/intake", headers=operator_headers,
            )
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_intake_uses_newest_record_across_direct_and_share_link_sources(
        self, test_client, operator_headers, operator_user, test_session,
    ):
        formal_kol = Kol(name="双来源达人")
        test_session.add(formal_kol)
        await test_session.flush()
        completed_at = datetime.now(timezone.utc)
        direct = KolIntakeOperatorSession(
            operator_id=operator_user.id,
            kol_id=formal_kol.id,
            messages=[{"role": "user", "content": "直发回答"}],
            ai_report="较早直发报告",
            report_status="ready",
            report_generated_at=completed_at,
        )
        link = KolIntakeLink(
            token="persona-newest-share-link",
            operator_id=operator_user.id,
            kol_id=formal_kol.id,
            expires_at=completed_at + timedelta(days=1),
        )
        test_session.add_all([direct, link])
        await test_session.flush()
        submission = KolIntakeSubmission(
            link_id=link.id,
            messages=[{"role": "user", "content": "链接回答"}],
            ai_report="最新链接报告",
            report_status="ready",
            report_generated_at=completed_at + timedelta(minutes=1),
        )
        test_session.add(submission)
        await test_session.commit()

        response = await test_client.get(
            f"/api/persona/kols/{formal_kol.id}/intake", headers=operator_headers,
        )

        assert response.status_code == 200
        assert response.json()["data"]["report"] == "最新链接报告"

    @pytest.mark.asyncio
    async def test_generate_persists_formal_kol_id_to_report_output_and_log(
        self, test_client, operator_headers, operator_user, test_session,
    ):
        formal_kol = Kol(name="生成目标")
        config = KolIntakeConfig(config_key="persona_generation", system_prompt="生成")
        test_session.add_all([formal_kol, config])
        await test_session.commit()

        async def fake_stream(**_kwargs):
            yield "# 生成目标 · 人格档案\n内容===SPLIT===内容规划"

        with patch("app.routers.persona.yunwu_adapter.chat_stream", fake_stream):
            response = await test_client.post(
                "/api/persona/generate",
                headers=operator_headers,
                json={"kol_id": formal_kol.id, "influencer_info": "资料"},
            )

        assert response.status_code == 200
        report_id = int(response.headers["x-report-id"])
        generated_report = (await test_session.execute(
            select(PersonaReport).where(PersonaReport.id == report_id)
        )).scalar_one()
        output = (await test_session.execute(
            select(Output).where(Output.created_by == operator_user.id)
            .order_by(Output.id.desc())
        )).scalars().first()
        log = (await test_session.execute(
            select(OperationLog).where(OperationLog.target_id == report_id)
            .where(OperationLog.action == "persona_generate")
        )).scalar_one()
        assert generated_report.kol_id == formal_kol.id
        assert output.content_json["kol_id"] == formal_kol.id
        assert log.detail["kol_id"] == formal_kol.id
        detail_response = await test_client.get(
            f"/api/persona/reports/{report_id}", headers=operator_headers,
        )
        assert detail_response.json()["data"]["kol_id"] == formal_kol.id
