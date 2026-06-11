"""Unit tests for app.core.config — Settings loading and defaults."""
from app.core.config import Settings


class TestSettings:
    def test_settings_has_database_url(self):
        s = Settings(database_url="postgresql+asyncpg://test", jwt_secret="test-secret")
        assert s.database_url == "postgresql+asyncpg://test"

    def test_settings_has_jwt_secret(self):
        s = Settings(database_url="postgresql+asyncpg://test", jwt_secret="my-secret")
        assert s.jwt_secret == "my-secret"

    def test_settings_jwt_expire_hours_default(self):
        s = Settings(database_url="postgresql+asyncpg://test", jwt_secret="test")
        assert s.jwt_expire_hours == 24

    def test_settings_initial_admin_defaults(self):
        s = Settings(
            database_url="postgresql+asyncpg://test",
            jwt_secret="test",
            initial_admin_password="Admin@123456",  # explicit to avoid .env override
        )
        assert s.initial_admin_username == "admin"
        assert s.initial_admin_password == "Admin@123456"
