import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.kol import Kol
from app.models.log import OperationLog
from app.models.output import Output
from app.models.persona_report import PersonaReport
from app.routers.persona import (
    SyncDecisionsRequest,
    _finalize_report,
    submit_sync_decisions,
)


pytestmark = pytest.mark.asyncio


class _LockSignalSession:
    """测试代理：只在 SELECT FOR UPDATE 前后发事件，不改变数据库行为。"""

    def __init__(
        self,
        session: AsyncSession,
        *,
        before_lock: asyncio.Event | None = None,
        after_lock: asyncio.Event | None = None,
        release_after_lock: asyncio.Event | None = None,
    ):
        self._session = session
        self._before_lock = before_lock
        self._after_lock = after_lock
        self._release_after_lock = release_after_lock

    async def __aenter__(self):
        await self._session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return await self._session.__aexit__(exc_type, exc, traceback)

    async def execute(self, statement, *args, **kwargs):
        is_for_update = getattr(statement, "_for_update_arg", None) is not None
        if is_for_update and self._before_lock is not None:
            self._before_lock.set()
        result = await self._session.execute(statement, *args, **kwargs)
        if is_for_update and self._after_lock is not None:
            self._after_lock.set()
            if self._release_after_lock is not None:
                await self._release_after_lock.wait()
        return result

    def __getattr__(self, name):
        return getattr(self._session, name)


def _request() -> MagicMock:
    request = MagicMock()
    request.client.host = "127.0.0.1"
    request.headers = {}
    return request


async def _make_report(test_session, operator_user, **kol_values):
    kol = Kol(name="同步测试达人", **kol_values)
    test_session.add(kol)
    await test_session.flush()
    report = PersonaReport(
        operator_id=operator_user.id,
        kol_id=kol.id,
        douyin_nickname="同步测试达人",
        status="generating",
    )
    test_session.add(report)
    await test_session.commit()
    return kol.id, report.id


async def _finalize(report_id, operator_user, facts=None):
    facts = facts or {
        "background": "",
        "experience": "",
        "relationships": "",
        "unique_story": "",
        "extra_notes": "",
    }
    request = MagicMock()
    request.client.host = "127.0.0.1"
    request.headers = {}
    with patch("app.routers.persona.generate_persona_docx", return_value="/tmp/report.docx"), patch(
        "app.routers.persona._extract_grounded_facts",
        new=AsyncMock(return_value=facts),
    ):
        await _finalize_report(
            report_id,
            "# 同步测试达人 · 人格档案\n报告人格===SPLIT===报告规划",
            operator_user,
            request,
        )


async def _make_ready_report(
    test_session, operator_user, *, persona: str | None,
) -> tuple[int, int]:
    kol_id, report_id = await _make_report(
        test_session,
        operator_user,
        persona=persona,
        content_plan="报告规划",
    )
    report = await test_session.get(PersonaReport, report_id)
    report.status = "ready"
    report.profile_result = "报告人格"
    report.plan_result = "报告规划"
    await test_session.commit()
    return kol_id, report_id


async def test_finalize_auto_writes_empty_positioning_and_only_empty_grounded_facts(
    test_session, operator_user
):
    kol_id, report_id = await _make_report(
        test_session,
        operator_user,
        background="人工基本身份",
        extra_notes="  ",
    )

    await _finalize(report_id, operator_user, {
        "background": "报告基本身份",
        "experience": "报告真实经历",
        "relationships": "",
        "unique_story": "",
        "extra_notes": "报告其他补充",
    })

    test_session.expire_all()
    kol = await test_session.get(Kol, kol_id)
    report = await test_session.get(PersonaReport, report_id)
    assert report.status == "ready"
    assert kol.persona.startswith("# 同步测试达人")
    assert kol.content_plan == "报告规划"
    assert kol.background == "人工基本身份"
    assert kol.experience == "报告真实经历"
    assert kol.extra_notes == "报告其他补充"

    output = (await test_session.execute(
        select(Output).where(
            Output.tool_code == "persona-positioning",
            Output.content_json["report_id"].astext == str(report_id),
        )
    )).scalar_one()
    assert output.content_json["kol_id"] == kol_id

    logs = (await test_session.execute(
        select(OperationLog).where(OperationLog.target_id == report_id)
    )).scalars().all()
    details = [log.detail for log in logs if log.detail]
    assert any(detail.get("fields", {}).get("persona") == "auto_written" for detail in details)
    assert all("报告人格" not in str(detail) for detail in details)
    assert all("报告真实经历" not in str(detail) for detail in details)


async def test_finalize_mixed_values_keeps_existing_and_exposes_pending_overwrite(
    test_client, operator_headers, test_session, operator_user
):
    kol_id, report_id = await _make_report(
        test_session,
        operator_user,
        persona="人工人格",
        content_plan=None,
    )

    await _finalize(report_id, operator_user)

    test_session.expire_all()
    kol = await test_session.get(Kol, kol_id)
    assert kol.persona == "人工人格"
    assert kol.content_plan == "报告规划"

    response = await test_client.get(
        f"/api/persona/reports/{report_id}", headers=operator_headers
    )
    data = response.json()["data"]
    assert data["sync_result"] == {
        "persona": "pending",
        "content_plan": "auto_written",
    }
    assert [item["field"] for item in data["pending_overwrites"]] == ["persona"]
    assert data["pending_overwrites"][0]["current_summary"] == "人工人格"


async def test_sync_decisions_default_keep_and_independent_overwrite_are_idempotent(
    test_client, operator_headers, test_session, operator_user
):
    kol_id, report_id = await _make_report(
        test_session,
        operator_user,
        persona="人工人格",
        content_plan="人工规划",
    )
    await _finalize(report_id, operator_user)

    response = await test_client.post(
        f"/api/persona/reports/{report_id}/sync-decisions",
        headers=operator_headers,
        json={"decisions": {"content_plan": "overwrite"}},
    )
    assert response.json()["data"]["fields"] == {
        "persona": "kept",
        "content_plan": "overwritten",
    }
    test_session.expire_all()
    kol = await test_session.get(Kol, kol_id)
    assert kol.persona == "人工人格"
    assert kol.content_plan == "报告规划"

    first_count = (await test_session.execute(
        select(func.count()).select_from(OperationLog).where(
            OperationLog.action == "persona_sync_decisions",
            OperationLog.target_id == report_id,
        )
    )).scalar_one()
    repeated = await test_client.post(
        f"/api/persona/reports/{report_id}/sync-decisions",
        headers=operator_headers,
        json={"decisions": {"content_plan": "overwrite"}},
    )
    assert repeated.json()["data"]["fields"]["content_plan"] == "unchanged"
    second_count = (await test_session.execute(
        select(func.count()).select_from(OperationLog).where(
            OperationLog.action == "persona_sync_decisions",
            OperationLog.target_id == report_id,
        )
    )).scalar_one()
    assert second_count == first_count


async def test_sync_decisions_recomputes_after_concurrent_workspace_edit(
    test_engine, test_session, operator_user
):
    kol_id, report_id = await _make_ready_report(
        test_session, operator_user, persona=""
    )
    session_factory = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )
    sync_waiting_for_lock = asyncio.Event()

    def sync_session_factory():
        return _LockSignalSession(
            session_factory(), before_lock=sync_waiting_for_lock
        )

    async with session_factory() as workspace_db:
        kol = (await workspace_db.execute(
            select(Kol).where(Kol.id == kol_id).with_for_update()
        )).scalar_one()
        kol.persona = "工作台最新人工编辑"
        await workspace_db.flush()

        with patch("app.routers.persona.AsyncSessionLocal", sync_session_factory):
            sync_task = asyncio.create_task(submit_sync_decisions(
                report_id,
                SyncDecisionsRequest(decisions={}),
                operator_user,
                _request(),
            ))
            await asyncio.wait_for(sync_waiting_for_lock.wait(), timeout=5)
            await workspace_db.commit()
            response = await asyncio.wait_for(sync_task, timeout=5)

    assert response.data["fields"]["persona"] == "kept"
    async with session_factory() as verification_db:
        kol = await verification_db.get(Kol, kol_id)
        assert kol.persona == "工作台最新人工编辑"


async def test_concurrent_overwrite_recomputes_and_logs_only_first_effective_write(
    test_engine, test_session, operator_user
):
    kol_id, report_id = await _make_ready_report(
        test_session, operator_user, persona="人工旧人格"
    )
    session_factory = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )
    first_has_lock = asyncio.Event()
    release_first = asyncio.Event()
    second_waiting_for_lock = asyncio.Event()
    call_count = 0

    def ordered_sync_session_factory():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _LockSignalSession(
                session_factory(),
                after_lock=first_has_lock,
                release_after_lock=release_first,
            )
        return _LockSignalSession(
            session_factory(), before_lock=second_waiting_for_lock
        )

    with patch("app.routers.persona.AsyncSessionLocal", ordered_sync_session_factory):
        first_task = asyncio.create_task(submit_sync_decisions(
            report_id,
            SyncDecisionsRequest(decisions={"persona": "overwrite"}),
            operator_user,
            _request(),
        ))
        await asyncio.wait_for(first_has_lock.wait(), timeout=5)
        second_task = asyncio.create_task(submit_sync_decisions(
            report_id,
            SyncDecisionsRequest(decisions={"persona": "overwrite"}),
            operator_user,
            _request(),
        ))
        await asyncio.wait_for(second_waiting_for_lock.wait(), timeout=5)
        release_first.set()
        first_response, second_response = await asyncio.wait_for(
            asyncio.gather(first_task, second_task), timeout=5
        )

    assert first_response.data["fields"]["persona"] == "overwritten"
    assert second_response.data["fields"]["persona"] == "unchanged"
    async with session_factory() as verification_db:
        kol = await verification_db.get(Kol, kol_id)
        assert kol.persona == "报告人格"
        log_count = (await verification_db.execute(
            select(func.count()).select_from(OperationLog).where(
                OperationLog.action == "persona_sync_decisions",
                OperationLog.target_id == report_id,
            )
        )).scalar_one()
        assert log_count == 1


async def test_empty_decisions_model_modal_close_as_keep(
    test_client, operator_headers, test_session, operator_user
):
    kol_id, report_id = await _make_report(
        test_session,
        operator_user,
        persona="人工人格",
        content_plan="人工规划",
    )
    await _finalize(report_id, operator_user)

    response = await test_client.post(
        f"/api/persona/reports/{report_id}/sync-decisions",
        headers=operator_headers,
        json={"decisions": {}},
    )

    assert response.json()["data"]["fields"] == {
        "persona": "kept",
        "content_plan": "kept",
    }
    test_session.expire_all()
    kol = await test_session.get(Kol, kol_id)
    assert kol.persona == "人工人格"
    assert kol.content_plan == "人工规划"


async def test_deleted_kol_after_generation_keeps_failed_report_without_output_or_profile_writes(
    test_client, operator_headers, test_session, operator_user
):
    kol_id, report_id = await _make_report(test_session, operator_user)
    kol = await test_session.get(Kol, kol_id)
    kol.deleted_at = func.now()
    await test_session.commit()

    await _finalize(report_id, operator_user)

    test_session.expire_all()
    report = await test_session.get(PersonaReport, report_id)
    assert report.status == "failed"
    assert report.profile_result is None
    assert report.plan_result is None
    assert report.raw_output is None
    assert report.profile_docx_path is None
    assert report.plan_docx_path is None
    output_count = (await test_session.execute(
        select(func.count()).select_from(Output).where(
            Output.content_json["report_id"].astext == str(report_id)
        )
    )).scalar_one()
    assert output_count == 0
    kol = await test_session.get(Kol, kol_id)
    assert kol.persona is None
    assert kol.content_plan is None
    sync_log_count = (await test_session.execute(
        select(func.count()).select_from(OperationLog).where(
            OperationLog.action.in_(("persona_profile_sync", "fill_kol_persona_facts")),
            OperationLog.target_id == report_id,
        )
    )).scalar_one()
    assert sync_log_count == 0
    response = await test_client.get(
        f"/api/persona/reports/{report_id}", headers=operator_headers
    )
    assert response.json()["data"]["failure_reason"] == "kol_deleted"


async def test_interrupted_generation_never_archives_partial_output_or_syncs_profile(
    test_client, operator_headers, test_session, operator_user
):
    kol_id, report_id = await _make_report(test_session, operator_user)
    with patch("app.routers.persona.generate_persona_docx", return_value="/tmp/report.docx"):
        await _finalize_report(
            report_id,
            "# 同步测试达人 · 人格档案\n不完整内容",
            operator_user,
            _request(),
            generation_succeeded=False,
        )

    test_session.expire_all()
    report = await test_session.get(PersonaReport, report_id)
    kol = await test_session.get(Kol, kol_id)
    assert report.status == "failed"
    assert report.raw_output is None
    assert kol.persona is None
    assert kol.content_plan is None
    output_count = (await test_session.execute(
        select(func.count()).select_from(Output).where(
            Output.content_json["report_id"].astext == str(report_id)
        )
    )).scalar_one()
    assert output_count == 0
    response = await test_client.get(
        f"/api/persona/reports/{report_id}", headers=operator_headers
    )
    assert response.json()["data"]["failure_reason"] == "generation_failed"


async def test_fact_extraction_failure_does_not_change_ready_report_or_positioning_sync(
    test_client, operator_headers, test_session, operator_user
):
    kol_id, report_id = await _make_report(test_session, operator_user)
    request = MagicMock()
    request.client.host = "127.0.0.1"
    request.headers = {}
    with patch("app.routers.persona.generate_persona_docx", return_value="/tmp/report.docx"), patch(
        "app.routers.persona._extract_grounded_facts",
        new=AsyncMock(side_effect=RuntimeError("提取服务失败")),
    ):
        await _finalize_report(
            report_id,
            "报告人格===SPLIT===报告规划",
            operator_user,
            request,
        )

    test_session.expire_all()
    report = await test_session.get(PersonaReport, report_id)
    kol = await test_session.get(Kol, kol_id)
    assert report.status == "ready"
    assert kol.persona == "报告人格"
    assert kol.content_plan == "报告规划"
    failure_log = (await test_session.execute(
        select(OperationLog).where(
            OperationLog.action == "persona_fact_sync_failed",
            OperationLog.target_id == report_id,
        )
    )).scalar_one()
    assert failure_log.detail == {"kol_id": kol_id, "status": "failed"}
    response = await test_client.get(
        f"/api/persona/reports/{report_id}", headers=operator_headers
    )
    data = response.json()["data"]
    assert data["fact_sync_failed"] is True
    assert data["positioning_sync_failed"] is False


async def test_positioning_sync_failure_does_not_undo_ready_report_history(
    test_client, operator_headers, test_session, operator_user
):
    _kol_id, report_id = await _make_report(test_session, operator_user)
    request = MagicMock()
    request.client.host = "127.0.0.1"
    request.headers = {}
    with patch("app.routers.persona.generate_persona_docx", return_value="/tmp/report.docx"), patch(
        "app.routers.persona._sync_initial_positioning",
        new=AsyncMock(side_effect=RuntimeError("同步数据库暂时失败")),
    ), patch(
        "app.routers.persona._extract_grounded_facts",
        new=AsyncMock(return_value={field: "" for field in (
            "background", "experience", "relationships", "unique_story", "extra_notes"
        )}),
    ):
        await _finalize_report(
            report_id,
            "报告人格===SPLIT===报告规划",
            operator_user,
            request,
        )

    test_session.expire_all()
    report = await test_session.get(PersonaReport, report_id)
    assert report.status == "ready"
    assert report.profile_result == "报告人格"
    response = await test_client.get(
        f"/api/persona/reports/{report_id}", headers=operator_headers
    )
    data = response.json()["data"]
    assert data["positioning_sync_failed"] is True
    assert data["fact_sync_failed"] is False
    assert data["sync_result"] == {}
    assert data["pending_overwrites"] == []


async def test_sync_decisions_cannot_read_or_write_another_operators_report(
    test_client, admin_headers, test_session, operator_user
):
    _kol_id, report_id = await _make_report(
        test_session,
        operator_user,
        persona="人工人格",
        content_plan="人工规划",
    )
    await _finalize(report_id, operator_user)

    response = await test_client.post(
        f"/api/persona/reports/{report_id}/sync-decisions",
        headers=admin_headers,
        json={"decisions": {"persona": "overwrite"}},
    )

    assert response.status_code == 404
