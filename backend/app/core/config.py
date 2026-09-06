from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    jwt_secret: str
    jwt_expire_hours: int = 24
    initial_admin_username: str = "admin"
    initial_admin_password: str = "Admin@123456"
    encryption_key: str = "change-me-32-chars-encryption-key"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    external_kols_api_key: str = ""
    content_analysis_scheduler_enabled: bool = False
    content_analysis_system_user_id: int | None = None
    content_analysis_feishu_app_id: str = ""
    content_analysis_feishu_app_secret: str = ""
    content_analysis_feishu_content_app_token: str = ""
    content_analysis_feishu_content_table_id: str = ""
    content_analysis_feishu_relation_app_token: str = ""
    content_analysis_feishu_relation_table_id: str = ""
    content_analysis_model_id: str = ""
    content_analysis_model_provider: str = ""

    def content_analysis_runtime_values(self) -> dict[str, str]:
        return {
            "CONTENT_ANALYSIS_FEISHU_APP_ID": self.content_analysis_feishu_app_id,
            "CONTENT_ANALYSIS_FEISHU_APP_SECRET": self.content_analysis_feishu_app_secret,
            "CONTENT_ANALYSIS_FEISHU_CONTENT_APP_TOKEN": self.content_analysis_feishu_content_app_token,
            "CONTENT_ANALYSIS_FEISHU_CONTENT_TABLE_ID": self.content_analysis_feishu_content_table_id,
            "CONTENT_ANALYSIS_FEISHU_RELATION_APP_TOKEN": self.content_analysis_feishu_relation_app_token,
            "CONTENT_ANALYSIS_FEISHU_RELATION_TABLE_ID": self.content_analysis_feishu_relation_table_id,
            "CONTENT_ANALYSIS_MODEL_ID": self.content_analysis_model_id,
            "CONTENT_ANALYSIS_MODEL_PROVIDER": self.content_analysis_model_provider,
            "CONTENT_ANALYSIS_SYSTEM_USER_ID": (
                str(self.content_analysis_system_user_id)
                if self.content_analysis_system_user_id is not None
                else ""
            ),
        }

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
