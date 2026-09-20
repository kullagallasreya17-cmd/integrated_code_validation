from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_agent_card_describes_orchestrator_skills():
    response = client.get("/.well-known/agent-card.json")

    assert response.status_code == 200
    assert response.json()["name"] == "coding-validation-orchestrator"
    assert {skill["id"] for skill in response.json()["skills"]} == {
        "workflow.start", "workflow.status", "agent.result"
    }


def test_a2a_agent_result_is_acknowledged():
    response = client.post("/a2a/v1/tasks", json={
        "task_type": "agent.result",
        "context_id": "project-a2a",
        "agent_name": "code-quality",
        "payload": {"findings_count": 1},
    })

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["result"]["agent_name"] == "code-quality"


def test_a2a_status_accepts_context_id():
    client.post("/a2a/v1/tasks", json={
        "task_type": "agent.result",
        "context_id": "project-status",
        "agent_name": "security",
        "payload": {"findings": []},
    })
    response = client.post("/a2a/v1/tasks", json={
        "task_type": "workflow.status",
        "context_id": "project-status",
    })

    assert response.status_code == 200
    assert response.json()["status"] == "completed"