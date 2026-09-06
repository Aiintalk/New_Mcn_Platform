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

    def test_content_analysis_scheduler_is_default_off_without_system_account(self):
        s = Settings(
            database_url="postgresql+asyncpg://test",
            jwt_secret="test",
            initial_admin_password="Admin@123456",
        )
        assert s.content_analysis_scheduler_enabled is False
        assert s.content_analysis_system_user_id is None

    def test_content_analysis_runtime_values_are_loaded_from_the_standard_env_file(
        self,
        tmp_path,
    ):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "\n".join(
                [
                    "DATABASE_URL=postgresql+asyncpg://test",
                    "JWT_SECRET=test-secret",
                    "CONTENT_ANALYSIS_FEISHU_APP_ID=app-id",
                    "CONTENT_ANALYSIS_FEISHU_APP_SECRET=fake-secret",
                    "CONTENT_ANALYSIS_FEISHU_CONTENT_APP_TOKEN=content-base",
                    "CONTENT_ANALYSIS_FEISHU_CONTENT_TABLE_ID=content-table",
                    "CONTENT_ANALYSIS_FEISHU_RELATION_APP_TOKEN=relation-base",
                    "CONTENT_ANALYSIS_FEISHU_RELATION_TABLE_ID=relation-table",
                    "CONTENT_ANALYSIS_MODEL_ID=model-id",
                    "CONTENT_ANALYSIS_MODEL_PROVIDER=yunwu",
                    "CONTENT_ANALYSIS_SYSTEM_USER_ID=100",
                ]
            ),
            encoding="utf-8",
        )

        settings = Settings(_env_file=env_file)

        assert settings.content_analysis_runtime_values() == {
            "CONTENT_ANALYSIS_FEISHU_APP_ID": "app-id",
            "CONTENT_ANALYSIS_FEISHU_APP_SECRET": "fake-secret",
            "CONTENT_ANALYSIS_FEISHU_CONTENT_APP_TOKEN": "content-base",
            "CONTENT_ANALYSIS_FEISHU_CONTENT_TABLE_ID": "content-table",
            "CONTENT_ANALYSIS_FEISHU_RELATION_APP_TOKEN": "relation-base",
            "CONTENT_ANALYSIS_FEISHU_RELATION_TABLE_ID": "relation-table",
            "CONTENT_ANALYSIS_MODEL_ID": "model-id",
            "CONTENT_ANALYSIS_MODEL_PROVIDER": "yunwu",
            "CONTENT_ANALYSIS_SYSTEM_USER_ID": "100",
        }
