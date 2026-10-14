from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "gateway"
    host: str = "0.0.0.0"
    port: int = 8000
    orchestrator_url: str = "http://orchestrator:8000"
    quality_service_url: str = "http://code-quality:8000"
    database_url: str = "sqlite+aiosqlite:///./gateway.db"
    request_timeout_seconds: float = 120.0
    cors_origins: str = "http://localhost:5174,http://127.0.0.1:5174,http://localhost:5173,http://127.0.0.1:5173"
    auth_cookie_secure: bool = False
    local_demo_auth_enabled: bool = False
    auth_session_hours: int = 12
    auth_remember_days: int = 30
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
    bootstrap_admin_name: str = "System Administrator"

    class Config:
        env_prefix = "GATEWAY_"


settings = Settings()