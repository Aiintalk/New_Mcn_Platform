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
import uuid
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Base
from app.core.security import create_access_token
import app.models  # noqa: F401 — register all models so Base.metadata.create_all covers every table
from app.models.user import User

# ---------------------------------------------------------------------------
# Test database URL — override via TEST_DB_URL env var if needed
# ---------------------------------------------------------------------------
TEST_DB_URL = os.getenv(
    "TEST_DB_URL",
    "postgresql+asyncpg://mcn_user:admin123@localhost:5432/mcn_test",
)

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
]


# ---------------------------------------------------------------------------
# Engine & session fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Session-scoped async engine for the test database."""
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)

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
        for p in patches:
            p.stop()
        await session.close()


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
