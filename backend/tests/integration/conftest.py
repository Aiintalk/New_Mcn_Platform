"""
Integration test conftest — FastAPI test client with dependency overrides.

Provides `test_client` fixture that overrides get_db to use the test database,
so router integration tests hit real DB + real auth middleware.
"""
import httpx
import pytest_asyncio
from app.core.database import get_db, AsyncSessionLocal
from app.main import app
from app.middlewares.auth import get_current_user, require_admin, require_password_changed


@pytest_asyncio.fixture
async def test_client(test_session):
    """
    FastAPI AsyncClient with dependency overrides.

    - get_db → yields test_session (shared test DB)
    - AsyncSessionLocal → patched so auth middleware uses test DB too
    - All requests go through real middleware and router logic
    """
    async def _override_get_db():
        yield test_session

    app.dependency_overrides[get_db] = _override_get_db

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    app.dependency_overrides.clear()
