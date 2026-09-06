"""内容分析项目库受控读取、停用/恢复和人工开头补标。"""
import asyncio
from datetime import date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.requests import Request

from app.core.response import ErrorCode
from app.models.content_analysis import ContentAnalysisLibraryItem, ContentAnalysisResult
from app.models.kol import Kol
from app.models.log import OperationLog
from app.models.material_library import KolReference
from app.models.output import Output
from app.models.task import TaskJob
from app.routers.content_analysis_library import (
    LibraryAvailabilityUpdate,
    ManualLibraryContentCreate,
    ManualOpeningUpdate,
    annotate_library_opening,
    create_manual_qianchuan_item,
    list_library_items,
    set_library_availability,
)
from app.routers.operator_material_library import (
    ReferenceUpdate,
    delete_reference,
    update_reference,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


def request():
    return Request({"type": "http", "method": "PATCH", "path": "/", "headers": []})


async def seed_item(test_session, admin_user, *, category="qianchuan"):
    suffix = uuid4().hex[:8]
    project = Kol(name=f"cov_ca_lib_{suffix}", persona="人设", content_plan="规划", status="signed", created_by=admin_user.id)
    other = Kol(name=f"cov_ca_other_{suffix}", persona="人设", content_plan="规划", status="signed", created_by=admin_user.id)
    test_session.add_all((project, other))
    await test_session.flush()
    task = TaskJob(task_no=f"ca_s28_lib_task_{suffix}", tool_code="content-analysis", tool_name="内容分析", status="success", created_by=admin_user.id)
    test_session.add(task)
    await test_session.flush()
    output = Output(title="结果", tool_code="content-analysis", tool_name="内容分析", task_id=task.id, content_json={"ok": True}, created_by=admin_user.id)
    test_session.add(output)
    await test_session.flush()
    result = ContentAnalysisResult(
        result_key=f"result-{suffix}", analysis_key=f"analysis-{suffix}", task_id=task.id,
        task_code="content_analysis_daily", run_type="auto", execution_kind="project",
        project_id=project.id, related_project_ids=[str(project.id)], business_date=date(2026, 9, 4),
        window_start=datetime(2026, 9, 2, tzinfo=SHANGHAI), window_end=datetime(2026, 9, 5, tzinfo=SHANGHAI),
        context_versions={str(project.id): "v1"}, source_receipts={}, status="success", output_id=output.id, is_test=False,
    )
    test_session.add(result)
    await test_session.flush()
    reference = KolReference(kol_id=project.id, title="匿名候选", likes=10, source="未知", type="千川爆款文案", content="匿名转写", created_by=admin_user.id)
    other_ref = KolReference(kol_id=other.id, title="其他项目", likes=10, source="未知", type="千川爆款文案", content="其他", created_by=admin_user.id)
    test_session.add_all((reference, other_ref))
    await test_session.flush()
    common = dict(
        platform="unknown", account_id="account-001", category=category,
        analysis={"opening": {"status": "unannotated"}}, project_assessment={"is_fit": True},
        latest_metrics={"like_count": 10}, confidence="medium", priority=1,
        opening_status="unannotated", availability="enabled", latest_result_id=result.id,
    )
    item = ContentAnalysisLibraryItem(kol_reference_id=reference.id, project_id=project.id, platform_content_id=f"work-{suffix}", **common)
    other_item = ContentAnalysisLibraryItem(kol_reference_id=other_ref.id, project_id=other.id, platform_content_id=f"other-{suffix}", **common)
    test_session.add_all((item, other_item))
    await test_session.commit()
    return project, other, item


@pytest.mark.asyncio
async def test_library_read_requires_project_and_filters_category_and_availability(test_session, admin_user) -> None:
    project, other, item = await seed_item(test_session, admin_user)

    response = await list_library_items(
        project_id=project.id,
        category="qianchuan",
        availability="enabled",
        page=1,
        page_size=20,
        db=test_session,
        user=admin_user,
    )

    assert response.success is True
    assert response.data["pagination"]["total"] == 1
    assert response.data["items"][0]["project_id"] == project.id
    assert response.data["items"][0]["platform"] == "unknown"
    assert response.data["items"][0]["source_platform_note"] == "来源平台未知"
    assert all(row["project_id"] != other.id for row in response.data["items"])


@pytest.mark.asyncio
async def test_generic_material_routes_cannot_mutate_content_analysis_candidate(
    test_session,
    admin_user,
) -> None:
    project, _, item = await seed_item(test_session, admin_user)

    updated = await update_reference(
        project.id,
        item.kol_reference_id,
        ReferenceUpdate(content="绕过内容分析接口修改"),
        request(),
        db=test_session,
        user=admin_user,
    )
    deleted = await delete_reference(
        project.id,
        item.kol_reference_id,
        request(),
        db=test_session,
        user=admin_user,
    )

    assert updated.success is False
    assert updated.code == ErrorCode.PERMISSION_DENIED
    assert deleted.success is False
    assert deleted.code == ErrorCode.PERMISSION_DENIED
    reference = await test_session.get(KolReference, item.kol_reference_id)
    assert reference.content == "匿名转写"
    assert reference.deleted_at is None


@pytest.mark.asyncio
async def test_manual_qianchuan_create_starts_unannotated_and_duplicate_merges_without_overwrite(
    test_session,
    admin_user,
) -> None:
    project = Kol(
        name=f"cov_ca_manual_{uuid4().hex[:8]}",
        persona="人设",
        content_plan="规划",
        status="signed",
        created_by=admin_user.id,
    )
    test_session.add(project)
    await test_session.commit()
    body = ManualLibraryContentCreate(
        project_id=project.id,
        title="人工原标题",
        transcript="人工原正文的开头",
        platform_content_id="manual-work-1",
    )

    created = await create_manual_qianchuan_item(
        body,
        request(),
        db=test_session,
        user=admin_user,
    )
    merged = await create_manual_qianchuan_item(
        ManualLibraryContentCreate(
            project_id=project.id,
            title="不应覆盖的新标题",
            transcript="不应覆盖的新正文",
            platform_content_id="manual-work-1",
            external_url="https://example.invalid/manual-work-1",
        ),
        request(),
        db=test_session,
        user=admin_user,
    )

    assert created.success is True
    assert created.data["opening_status"] == "unannotated"
    assert created.data["ingestion_source"] == "manual"
    assert merged.success is True
    assert merged.data["id"] == created.data["id"]
    item = await test_session.get(ContentAnalysisLibraryItem, created.data["id"])
    reference = await test_session.get(KolReference, item.kol_reference_id)
    assert item.external_url == "https://example.invalid/manual-work-1"
    assert item.latest_result_id is None
    assert reference.title == "人工原标题"
    assert reference.content == "人工原正文的开头"


@pytest.mark.asyncio
async def test_manual_qianchuan_create_accepts_body_without_title(
    test_session,
    admin_user,
) -> None:
    project = Kol(
        name=f"cov_ca_manual_body_{uuid4().hex[:8]}",
        persona="人设",
        content_plan="规划",
        status="signed",
        created_by=admin_user.id,
    )
    test_session.add(project)
    await test_session.commit()

    created = await create_manual_qianchuan_item(
        ManualLibraryContentCreate(
            project_id=project.id,
            transcript="可直接作为正文对标的人工内容",
        ),
        request(),
        db=test_session,
        user=admin_user,
    )

    assert created.success is True
    item = await test_session.get(ContentAnalysisLibraryItem, created.data["id"])
    reference = await test_session.get(KolReference, item.kol_reference_id)
    assert reference.title == "人工千川正文"
    assert reference.content == "可直接作为正文对标的人工内容"


@pytest.mark.asyncio
async def test_concurrent_manual_create_merges_the_same_stable_identity(
    test_engine,
    test_session,
    admin_user,
    monkeypatch,
) -> None:
    project = Kol(
        name=f"cov_ca_manual_concurrent_{uuid4().hex[:8]}",
        persona="人设",
        content_plan="规划",
        status="signed",
        created_by=admin_user.id,
    )
    test_session.add(project)
    await test_session.commit()
    project_id = project.id
    platform_content_id = f"manual-concurrent-{uuid4().hex}"
    factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    original_scalars = AsyncSession.scalars
    identity_reads_ready = asyncio.Event()
    identity_read_count = 0

    async def synchronized_scalars(session, statement, *args, **kwargs):
        nonlocal identity_read_count
        result = await original_scalars(session, statement, *args, **kwargs)
        if "content_analysis_library_items" in str(statement):
            identity_read_count += 1
            if identity_read_count == 2:
                identity_reads_ready.set()
            try:
                await asyncio.wait_for(identity_reads_ready.wait(), timeout=0.15)
            except asyncio.TimeoutError:
                pass
        return result

    monkeypatch.setattr(AsyncSession, "scalars", synchronized_scalars)

    async def create_one(title: str):
        async with factory() as session:
            return await create_manual_qianchuan_item(
                ManualLibraryContentCreate(
                    project_id=project_id,
                    title=title,
                    transcript="同一稳定身份的人工正文",
                    platform_content_id=platform_content_id,
                ),
                request(),
                db=session,
                user=admin_user,
            )

    outcomes = await asyncio.gather(
        create_one("人工标题 A"),
        create_one("人工标题 B"),
        return_exceptions=True,
    )

    assert all(not isinstance(item, BaseException) for item in outcomes), outcomes
    assert all(item.success is True for item in outcomes)
    test_session.expire_all()
    items = list(
        (
            await test_session.scalars(
                select(ContentAnalysisLibraryItem).where(
                    ContentAnalysisLibraryItem.project_id == project_id,
                    ContentAnalysisLibraryItem.platform_content_id
                    == platform_content_id,
                )
            )
        ).all()
    )
    assert len(items) == 1
    assert items[0].ingestion_source == "manual"


@pytest.mark.asyncio
async def test_content_analysis_request_validation_uses_standard_envelope(
    test_client,
    operator_headers,
) -> None:
    response = await test_client.post(
        "/api/tools/content-analysis/library",
        json={"project_id": 0, "title": "", "transcript": ""},
        headers=operator_headers,
    )

    assert response.status_code == 422
    assert response.json() == {
        "success": False,
        "code": "VALIDATION_ERROR",
        "message": "请求参数校验失败",
        "data": None,
    }


@pytest.mark.asyncio
async def test_disable_and_restore_are_project_scoped_and_write_operation_logs(test_session, admin_user) -> None:
    project, other, item = await seed_item(test_session, admin_user)

    disabled = await set_library_availability(
        item.id,
        LibraryAvailabilityUpdate(project_id=project.id, availability="disabled"),
        request(),
        test_session,
        admin_user,
    )
    wrong_project = await set_library_availability(
        item.id,
        LibraryAvailabilityUpdate(project_id=other.id, availability="enabled"),
        request(),
        test_session,
        admin_user,
    )
    restored = await set_library_availability(
        item.id,
        LibraryAvailabilityUpdate(project_id=project.id, availability="enabled"),
        request(),
        test_session,
        admin_user,
    )

    assert disabled.data["availability"] == "disabled"
    assert wrong_project.success is False
    assert restored.data["availability"] == "enabled"
    assert await test_session.scalar(
        select(func.count()).select_from(OperationLog).where(
            OperationLog.target_type == "content_analysis_library_item",
            OperationLog.target_id == item.id,
        )
    ) == 2


@pytest.mark.asyncio
async def test_manual_qianchuan_opening_annotation_keeps_fragment_in_same_record(test_session, admin_user) -> None:
    project, other, item = await seed_item(test_session, admin_user)

    response = await annotate_library_opening(
        item.id,
        ManualOpeningUpdate(
            project_id=project.id,
            status="available",
            fragment="匿名转写",
            unavailable_reason=None,
        ),
        request(),
        test_session,
        admin_user,
    )

    await test_session.refresh(item)
    assert response.success is True
    assert item.opening_status == "available"
    assert item.opening_fragment == "匿名转写"
    assert item.analysis["opening"] == {
        "status": "available",
        "kind": "language",
        "fragment": "匿名转写",
        "source": "manual",
    }
