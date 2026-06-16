from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    jwt_secret: str
    jwt_expire_hours: int = 24
    initial_admin_username: str = "admin"
    initial_admin_password: str = "Admin@123456"
    encryption_key: str = "change-me-32-chars-encryption-key"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
