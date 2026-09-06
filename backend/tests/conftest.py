"""
Root conftest.py — shared fixtures for all backend tests.

Test database strategy:
- Unit tests use mock sessions (see tests/unit/conftest.py)
- Integration tests use a real PostgreSQL test database (see tests/integration/conftest.py)
- E2E tests (intake/, concurrent/) hit a running server — keep existing conftest.py

This file provides:
- test_engine: async engine for the test database
- test_session: async session with per-test rollback isolation
- admin_user / operator_user: pre-created test users
- admin_token / operator_token: signed JWTs
- auth_headers: ready-to-use Authorization header dict
"""
import os
import re
import uuid
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from passlib.context import CryptContext
from sqlalchemy import delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Base
from app.core.security import create_access_token
import app.models  # noqa: F401 — register all models so Base.metadata.create_all covers every table
from app.models.content_analysis import (
    ContentAnalysisAccountBaseline,
    ContentAnalysisCrossProjectOpportunity,
    ContentAnalysisDelivery,
    ContentAnalysisLibraryItem,
    ContentAnalysisResult,
)
from app.models.kol import Kol
from app.models.log import OperationLog
from app.models.material_library import KolReference
from app.models.output import Output
from app.models.task import TaskJob
from app.models.user import User

# ---------------------------------------------------------------------------
# Test database URL — override via TEST_DB_URL env var if needed
# ---------------------------------------------------------------------------
TEST_DB_URL = os.getenv(
    "TEST_DB_URL",
    "postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test",
)
TEST_DB_SCHEMA = os.getenv("TEST_DB_SCHEMA")
if TEST_DB_SCHEMA is not None and not re.fullmatch(
    r"[A-Za-z_][A-Za-z0-9_]*",
    TEST_DB_SCHEMA,
):
    raise ValueError("TEST_DB_SCHEMA 只能使用安全的数据库标识符")

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_DEFAULT_PASSWORD = "Test@123456"

# Modules that import AsyncSessionLocal directly (not via app.core.database)
# These must ALL be patched so auth middleware uses the test DB.
_SESSION_LOCAL_PATCH_TARGETS = [
    "app.core.database.AsyncSessionLocal",
    "app.middlewares.auth.AsyncSessionLocal",
    "app.routers.auth.AsyncSessionLocal",
    "app.routers.workspace.AsyncSessionLocal",
    "app.routers.tasks.AsyncSessionLocal",
    "app.routers.outputs.AsyncSessionLocal",
    "app.routers.files.AsyncSessionLocal",
    "app.routers.admin_users.AsyncSessionLocal",
    "app.routers.admin_logs.AsyncSessionLocal",
    "app.routers.admin_credentials.AsyncSessionLocal",
    "app.routers.admin_kols.AsyncSessionLocal",
    "app.routers.admin_workspace.AsyncSessionLocal",
    "app.routers.intake_public.AsyncSessionLocal",
    "app.routers.operator_intake_direct.AsyncSessionLocal",
    "app.routers.persona.AsyncSessionLocal",
    "app.core.seed.AsyncSessionLocal",
    "app.routers.health.AsyncSessionLocal",
    "app.routers.operator_tiktok_writer.AsyncSessionLocal",
    "app.routers.operator_selling_point.AsyncSessionLocal",
    "app.routers.operator_benchmark.AsyncSessionLocal",
    "app.routers.tool_chat_stream.AsyncSessionLocal",
    "app.routers.operator_livestream_writer.AsyncSessionLocal",
    "app.routers.operator_livestream_review.AsyncSessionLocal",
    "app.routers.operator_qianchuan_review.AsyncSessionLocal",
    "app.routers.operator_persona_review.AsyncSessionLocal",
    "app.routers.operator_tiktok_review.AsyncSessionLocal",
    "app.routers.operator_qianchuan_writer.AsyncSessionLocal",
    "app.routers.operator_persona_writer.AsyncSessionLocal",
    "app.routers.operator_seeding_writer.AsyncSessionLocal",
    "app.routers.operator_subtitle.AsyncSessionLocal",
    "app.routers.operator_qianchuan_products.AsyncSessionLocal",
    "app.routers.operator_workspace.AsyncSessionLocal",
    "app.routers.admin_values_writer.AsyncSessionLocal",
    "app.routers.operator_values_writer.AsyncSessionLocal",
    "app.routers.operator_script_review.AsyncSessionLocal",
    "app.routers.operator_retrospective.AsyncSessionLocal",
    "app.routers.operator_qianchuan_preview.AsyncSessionLocal",
    "app.services.agent_task_scheduler.AsyncSessionLocal",
    # AIGC 评测 Phase 3：runner 后台执行 run（持 session 写库）+ scheduler 自动/定时触发建 run
    "app.evaluation.services.runner.AsyncSessionLocal",
    "app.evaluation.services.scheduler.AsyncSessionLocal",
    # Phase 2 异步运行：worker 的 eval_case_job 开独立 session 执行 case-job（防连生产库）
    "app.evaluation.worker.AsyncSessionLocal",
]


# ---------------------------------------------------------------------------
# Engine & session fixtures
# ---------------------------------------------------------------------------


async def _cleanup_content_analysis_test_rows(
    session: AsyncSession,
    user_ids: tuple[int, ...],
) -> None:
    """只清理当前测试用户创建的 Sprint28 已提交测试数据。"""
    await session.rollback()
    if not user_ids:
        return
    task_rows = (
        await session.execute(
            select(TaskJob.id, TaskJob.input_payload).where(
                TaskJob.task_no.like("ca_s28_%"),
                TaskJob.created_by.in_(user_ids),
            )
        )
    ).all()
    task_ids = [row.id for row in task_rows]
    project_ids = list(
        (
            await session.scalars(
                select(Kol.id).where(
                    Kol.name.like("cov_ca_%"),
                    Kol.created_by.in_(user_ids),
                )
            )
        ).all()
    )
    if not task_ids and not project_ids:
        return

    result_ids = (
        list(
            (
                await session.scalars(
                    select(ContentAnalysisResult.id).where(
                        ContentAnalysisResult.task_id.in_(task_ids)
                    )
                )
            ).all()
        )
        if task_ids
        else []
    )
    item_filters = []
    if result_ids:
        item_filters.append(ContentAnalysisLibraryItem.latest_result_id.in_(result_ids))
    if project_ids:
        item_filters.append(ContentAnalysisLibraryItem.project_id.in_(project_ids))
    item_rows = (
        (
            await session.execute(
                select(
                    ContentAnalysisLibraryItem.id,
                    ContentAnalysisLibraryItem.kol_reference_id,
                ).where(or_(*item_filters))
            )
        ).all()
        if item_filters
        else []
    )
    item_ids = [row.id for row in item_rows]
    reference_ids = [row.kol_reference_id for row in item_rows]
    document_keys = []
    for row in task_rows:
        payload = row.input_payload
        if not isinstance(payload, dict):
            continue
        idempotency = payload.get("idempotency")
        if isinstance(idempotency, dict):
            document_key = idempotency.get("document_key")
            if isinstance(document_key, str) and document_key:
                document_keys.append(document_key)

    if item_ids:
        await session.execute(
            delete(OperationLog).where(
                OperationLog.target_type == "content_analysis_library_item",
                OperationLog.target_id.in_(item_ids),
            )
        )
    if result_ids:
        await session.execute(
            delete(ContentAnalysisCrossProjectOpportunity).where(
                ContentAnalysisCrossProjectOpportunity.latest_result_id.in_(result_ids)
            )
        )
        await session.execute(
            delete(ContentAnalysisAccountBaseline).where(
                ContentAnalysisAccountBaseline.latest_result_id.in_(result_ids)
            )
        )
    if item_filters:
        await session.execute(
            delete(ContentAnalysisLibraryItem).where(or_(*item_filters))
        )
    if reference_ids:
        await session.execute(
            delete(KolReference).where(KolReference.id.in_(reference_ids))
        )
    if document_keys:
        await session.execute(
            delete(ContentAnalysisDelivery).where(
                ContentAnalysisDelivery.document_key.in_(document_keys)
            )
        )
    if result_ids:
        await session.execute(
            delete(ContentAnalysisResult).where(ContentAnalysisResult.id.in_(result_ids))
        )
    if task_ids:
        await session.execute(delete(Output).where(Output.task_id.in_(task_ids)))
        await session.execute(delete(TaskJob).where(TaskJob.id.in_(task_ids)))
    if project_ids:
        await session.execute(delete(Kol).where(Kol.id.in_(project_ids)))
    await session.commit()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Session-scoped async engine for the test database."""
    if TEST_DB_SCHEMA:
        bootstrap = create_async_engine(TEST_DB_URL, poolclass=NullPool)
        async with bootstrap.begin() as conn:
            await conn.execute(
                text(f'CREATE SCHEMA IF NOT EXISTS "{TEST_DB_SCHEMA}"')
            )
        await bootstrap.dispose()
    engine = create_async_engine(
        TEST_DB_URL,
        poolclass=NullPool,
        connect_args=(
            {"server_settings": {"search_path": TEST_DB_SCHEMA}}
            if TEST_DB_SCHEMA
            else {}
        ),
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def test_session(test_engine):
    """
    Function-scoped async session with rollback isolation.
    Each test gets a clean database state.

    Patches AsyncSessionLocal in ALL modules that import it directly,
    so auth middleware and router code paths all hit the test DB.
    """
    session_factory = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )

    session = session_factory()

    patches = [patch(target, session_factory) for target in _SESSION_LOCAL_PATCH_TARGETS]
    for p in patches:
        p.start()
    try:
        yield session
    finally:
        try:
            cleanup_user_ids = tuple(
                sorted(session.info.get("content_analysis_test_user_ids", ()))
            )
            await session.close()
            async with session_factory() as cleanup_session:
                await _cleanup_content_analysis_test_rows(
                    cleanup_session,
                    cleanup_user_ids,
                )
        finally:
            for p in patches:
                p.stop()


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def admin_user(test_session) -> User:
    """Create an admin user in the test database (unique per test)."""
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"test_admin_{suffix}",
        real_name="测试管理员",
        password_hash=_pwd_context.hash(_DEFAULT_PASSWORD),
        role="admin",
        status="enabled",
        password_changed_at=datetime.now(tz=timezone.utc),
    )
    test_session.add(user)
    await test_session.commit()
    await test_session.refresh(user)
    test_session.info.setdefault("content_analysis_test_user_ids", set()).add(user.id)
    return user


@pytest_asyncio.fixture
async def operator_user(test_session) -> User:
    """Create an operator user with password already changed (unique per test)."""
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"test_operator_{suffix}",
        real_name="测试运营",
        password_hash=_pwd_context.hash(_DEFAULT_PASSWORD),
        role="operator",
        status="enabled",
        password_changed_at=datetime.now(tz=timezone.utc),
    )
    test_session.add(user)
    await test_session.commit()
    await test_session.refresh(user)
    test_session.info.setdefault("content_analysis_test_user_ids", set()).add(user.id)
    return user


# ---------------------------------------------------------------------------
# Token fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_token(admin_user: User) -> str:
    """Signed JWT for admin_user."""
    return create_access_token(
        user_id=int(admin_user.id),
        username=str(admin_user.username),
        role=str(admin_user.role),
        token_version=int(admin_user.token_version),
    )


@pytest.fixture
def operator_token(operator_user: User) -> str:
    """Signed JWT for operator_user."""
    return create_access_token(
        user_id=int(operator_user.id),
        username=str(operator_user.username),
        role=str(operator_user.role),
        token_version=int(operator_user.token_version),
    )


# ---------------------------------------------------------------------------
# Auth header helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_headers(admin_token: str) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def operator_headers(operator_token: str) -> dict:
    return {"Authorization": f"Bearer {operator_token}"}
