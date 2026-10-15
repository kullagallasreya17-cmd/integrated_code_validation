from fastapi.testclient import TestClient

from app.main import app
from app.routes import system


def test_public_agent_status_is_unauthenticated_and_minimal(monkeypatch):
    async def fake_check_service(client, name, url):
        configured = name != "report_recommendation"
        return name, {
            "status": "healthy",
            "healthy": True,
            "details": {"configured": configured, "service": name},
        }

    monkeypatch.setattr(system, "_check_service", fake_check_service)

    with TestClient(app, base_url="https://testserver") as client:
        response = client.get("/api/system/public-agents")

    assert response.status_code == 200
    assert response.json() == {
        "services": {
            "orchestrator": True,
            "code_quality": True,
            "security": True,
            "bug_resource": True,
            "repair": True,
            "sandbox": True,
            "validation": True,
            "report_recommendation": False,
        },
    }