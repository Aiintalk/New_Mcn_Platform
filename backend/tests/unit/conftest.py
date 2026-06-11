"""
Unit test conftest — mock session factory for service layer tests.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_db():
    """Mock AsyncSession for service layer unit tests."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.scalar = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    return session
