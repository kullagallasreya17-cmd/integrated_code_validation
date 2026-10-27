from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "orchestrator-service"
    host: str = "0.0.0.0"
    port: int = 8000

    # Downstream service URLs — override via env vars in docker-compose
    quality_service_url: str = "http://code-quality:8000"
    security_service_url: str = "http://security:8000"
    bug_resource_service_url: str | None = None
    repair_service_url: str = "http://repair:8000"
    sandbox_service_url: str = "http://sandbox:8000"
    validation_service_url: str = "http://validation:8000"
    report_recommendation_service_url: str = "http://report-recommendation:8000"

    agent_call_timeout_seconds: int = 60
    repair_call_timeout_seconds: int = 660
    sandbox_call_timeout_seconds: int = 60
    validation_call_timeout_seconds: int = 60
    ai_report_timeout_seconds: int = 1250

    max_retries: int = 3
    max_run_history: int = 100
    run_store_path: str = "data/workflow-runs.json"

    class Config:
        env_prefix = "ORCH_"


settings = Settings()
