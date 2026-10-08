from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "gateway"
    host: str = "0.0.0.0"
    port: int = 8000
    orchestrator_url: str = "http://orchestrator:8000"
    quality_service_url: str = "http://code-quality:8000"
    database_url: str = "sqlite+aiosqlite:///./gateway.db"
    request_timeout_seconds: float = 120.0

    class Config:
        env_prefix = "GATEWAY_"


settings = Settings()