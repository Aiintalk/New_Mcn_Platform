"""
Direct-call coverage tests for admin_intake.py。

直调 questions CRUD + reorder + configs（list/update + 404）+ links + submissions
（list/detail 404/ok）+ regenerate_report（404/ok，BackgroundTasks 不实际触发）。
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import delete
from starlette.background import BackgroundTasks
from starlette.requests import Request
from fastapi import HTTPException

from app.models.kol_intake import (
    KolIntakeConfig, KolIntakeLink, KolIntakeQuestion, KolIntakeSubmission,
)
from app.routers.admin_intake import (
    ConfigIn,
    QuestionIn,
    ReorderItem,
    create_question,
    delete_question,
    get_submission_detail,
    list_all_links,
    list_all_submissions,
    list_configs,
    list_questions,
    regenerate_report,
    reorder_questions,
    update_config,
    update_question,
)


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(test_session):
    """清本文件 seed 的 cov_* 行。"""
    await test_session.execute(delete(KolIntakeSubmission))
    await test_session.execute(delete(KolIntakeLink).where(KolIntakeLink.token.like("cov_%")))
    await test_session.execute(delete(KolIntakeQuestion).where(KolIntakeQuestion.category.like("cov_%")))
    await test_session.execute(delete(KolIntakeConfig).where(KolIntakeConfig.config_key.like("cov_%")))
    await test_session.commit()
    yield


def _make_request() -> Request:
    return Request({"type": "http", "headers": [(b"user-agent", b"pytest")], "client": ("127.0.0.1", 0)})


async def _seed_question(test_session, **kw) -> KolIntakeQuestion:
    defaults = dict(
        order_num=1, category=f"cov_cat_{uuid.uuid4().hex[:6]}",
        question_text="问题", question_type="text",
        is_required=True, is_active=True,
    )
    defaults.update(kw)
    q = KolIntakeQuestion(**defaults)
    test_session.add(q)
    await test_session.commit()
    await test_session.refresh(q)
    return q


# ---------------------------------------------------------------------------
# Questions CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_questions(test_session, admin_user):
    await _seed_question(test_session)
    resp = await list_questions(db=test_session, _=admin_user)
    assert any(q["category"].startswith("cov_cat_") for q in resp.data)


@pytest.mark.asyncio
async def test_create_question(test_session, admin_user):
    body = QuestionIn(order_num=10, category=f"cov_cat_{uuid.uuid4().hex[:6]}", question_text="新建")
    resp = await create_question(body=body, request=_make_request(), db=test_session, current_user=admin_user)
    assert resp.data["id"] > 0


@pytest.mark.asyncio
async def test_update_question_ok(test_session, admin_user):
    q = await _seed_question(test_session)
    body = QuestionIn(order_num=q.order_num, category=q.category, question_text="改后")
    resp = await update_question(
        question_id=q.id, body=body, request=_make_request(), db=test_session, current_user=admin_user,
    )
    assert resp.data["id"] == q.id


@pytest.mark.asyncio
async def test_update_question_not_found(test_session, admin_user):
    body = QuestionIn(order_num=1, category="cov_cat_x", question_text="x")
    with pytest.raises(HTTPException) as exc:
        await update_question(
            question_id=99999999, body=body, request=_make_request(),
            db=test_session, current_user=admin_user,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_question_ok(test_session, admin_user):
    q = await _seed_question(test_session)
    resp = await delete_question(
        question_id=q.id, request=_make_request(), db=test_session, current_user=admin_user,
    )
    assert resp.success is True


@pytest.mark.asyncio
async def test_delete_question_not_found(test_session, admin_user):
    with pytest.raises(HTTPException) as exc:
        await delete_question(
            question_id=99999999, request=_make_request(), db=test_session, current_user=admin_user,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_reorder_questions(test_session, admin_user):
    q1 = await _seed_question(test_session, order_num=1)
    q2 = await _seed_question(test_session, order_num=2)
    body = [ReorderItem(id=q1.id, order_num=5), ReorderItem(id=q2.id, order_num=4)]
    resp = await reorder_questions(
        body=body, request=_make_request(), db=test_session, current_user=admin_user,
    )
    assert resp.success is True
    await test_session.refresh(q1)
    assert q1.order_num == 5


# ---------------------------------------------------------------------------
# Configs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_configs(test_session, admin_user):
    test_session.add(KolIntakeConfig(
        config_key=f"cov_cfg_{uuid.uuid4().hex[:6]}", system_prompt="x", is_active=True,
    ))
    await test_session.commit()
    resp = await list_configs(db=test_session, _=admin_user)
    assert any(c["config_key"].startswith("cov_cfg_") for c in resp.data)


@pytest.mark.asyncio
async def test_update_config_ok(test_session, admin_user):
    key = f"cov_cfg_{uuid.uuid4().hex[:6]}"
    test_session.add(KolIntakeConfig(config_key=key, is_active=True))
    await test_session.commit()
    body = ConfigIn(system_prompt="new", is_active=False)
    resp = await update_config(
        config_key=key, body=body, request=_make_request(),
        db=test_session, current_user=admin_user,
    )
    assert resp.data["config_key"] == key


@pytest.mark.asyncio
async def test_update_config_not_found(test_session, admin_user):
    body = ConfigIn(system_prompt="x")
    with pytest.raises(HTTPException) as exc:
        await update_config(
            config_key="cov_no_such", body=body, request=_make_request(),
            db=test_session, current_user=admin_user,
        )
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Links + Submissions
# ---------------------------------------------------------------------------

async def _seed_link(test_session, operator_user) -> KolIntakeLink:
    lnk = KolIntakeLink(
        token=f"cov_tk_{uuid.uuid4().hex[:8]}",
        operator_id=operator_user.id,
        kol_name="cov_kol",
        expires_at=datetime.now(tz=timezone.utc) + timedelta(days=1),
        is_active=True,
    )
    test_session.add(lnk)
    await test_session.commit()
    await test_session.refresh(lnk)
    return lnk


@pytest.mark.asyncio
async def test_list_all_links(test_session, admin_user, operator_user):
    await _seed_link(test_session, operator_user)
    resp = await list_all_links(db=test_session, _=admin_user)
    assert any(l["token"].startswith("cov_tk_") for l in resp.data)


@pytest.mark.asyncio
async def test_list_all_submissions_and_detail(test_session, admin_user, operator_user):
    lnk = await _seed_link(test_session, operator_user)
    sub = KolIntakeSubmission(
        link_id=lnk.id, messages=[], ai_report="r", report_status="completed",
    )
    test_session.add(sub)
    await test_session.commit()
    await test_session.refresh(sub)

    resp_list = await list_all_submissions(db=test_session, _=admin_user)
    assert any(s["id"] == sub.id for s in resp_list.data)

    resp_detail = await get_submission_detail(submission_id=sub.id, db=test_session, _=admin_user)
    assert resp_detail.data["ai_report"] == "r"


@pytest.mark.asyncio
async def test_get_submission_detail_not_found(test_session, admin_user):
    with pytest.raises(HTTPException) as exc:
        await get_submission_detail(submission_id=99999999, db=test_session, _=admin_user)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_regenerate_report_not_found(test_session, admin_user):
    bg = BackgroundTasks()
    with pytest.raises(HTTPException) as exc:
        await regenerate_report(
            submission_id=99999999, background_tasks=bg, request=_make_request(),
            db=test_session, current_user=admin_user,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_regenerate_report_ok(test_session, admin_user, operator_user):
    """重置状态 + BackgroundTasks.add_task（不实际跑）。"""
    lnk = await _seed_link(test_session, operator_user)
    sub = KolIntakeSubmission(
        link_id=lnk.id, messages=[], ai_report="old", report_status="completed",
    )
    test_session.add(sub)
    await test_session.commit()
    await test_session.refresh(sub)

    bg = BackgroundTasks()
    resp = await regenerate_report(
        submission_id=sub.id, background_tasks=bg, request=_make_request(),
        db=test_session, current_user=admin_user,
    )
    assert resp.data["report_status"] == "generating"

    await test_session.refresh(sub)
    assert sub.report_status == "pending"
    assert sub.ai_report is None
