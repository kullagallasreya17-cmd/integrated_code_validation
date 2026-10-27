import pytest
from fastapi.testclient import TestClient
from uuid import uuid4

from app.main import app
from app.routes import analysis, system


@pytest.fixture
def client():
    with TestClient(app, base_url="https://testserver") as test_client:
        registered = test_client.post("/api/auth/register", json={
            "email": f"api-test-{uuid4().hex}@example.test",
            "full_name": "API Test User",
            "password": "test-password-long-123",
        })
        assert registered.status_code == 201
        yield test_client


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
        self.text = ""

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload

    async def aread(self):
        return b""


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, json):
        if url.endswith("/analyze"):
            return FakeResponse({"agent": "code_quality", "findings": []})
        return FakeResponse({"status": "submitted", "project_id": json["project_id"]})

    async def get(self, url):
        return FakeResponse({
            "project_id": "project",
            "status": "completed",
            "result": {
                "findings": [],
                "validation_status": "pending",
                "final_report": {"project_id": "project", "validation_status": "pending"},
            },
        })


def test_project_and_analysis_contract(monkeypatch, client):
    monkeypatch.setattr(analysis.httpx, "AsyncClient", FakeAsyncClient)

    project = client.post("/api/projects", json={
        "name": "demo",
        "source_code": "print('ok')\n",
    })
    assert project.status_code == 200
    project_id = project.json()["project_id"]

    started = client.post("/api/analysis", json={"project_id": project_id})
    assert started.status_code == 200
    assert started.json()["status"] == "started"

    run_id = started.json()["run_id"]
    status = client.get(f"/api/analysis/{run_id}/status")
    assert status.status_code == 200
    assert status.json()["status"] == "completed"


def test_code_quality_adapter_forwards_to_service(monkeypatch, client):
    monkeypatch.setattr(analysis.httpx, "AsyncClient", FakeAsyncClient)

    response = client.post("/api/agents/code-quality/analyze", json={
        "project_id": "quality-test",
        "files": [{"path": "main.py", "content": "print('ok')"}],
        "tools": ["ruff"],
    })

    assert response.status_code == 200
    assert response.json()["agent"] == "code_quality"


def test_project_files_and_management_routes_persist(client):
    created = client.post("/api/projects", json={
        "name": "persisted-demo",
        "files": [{"path": "src/main.py", "content": "print('before')\n"}],
    })
    assert created.status_code == 200
    project_id = created.json()["project_id"]

    listed = client.get("/api/projects", params={"search": "persisted-demo"})
    assert listed.status_code == 200
    assert listed.json()["items"][0]["project_id"] == project_id

    files = client.get("/api/files", params={"project_id": project_id})
    assert files.json()["files"] == [{"path": "src/main.py", "content": "print('before')\n"}]

    saved = client.post("/api/files", json={
        "project_id": project_id,
        "files": [{"path": "src/main.py", "content": "print('after')\n"}],
    })
    assert saved.status_code == 200
    assert client.get("/api/files", params={"project_id": project_id}).json()["files"][0]["content"] == "print('after')\n"

    updated = client.patch(f"/api/projects/{project_id}", json={"name": "renamed-demo"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "renamed-demo"

    assert client.delete(f"/api/projects/{project_id}").status_code == 204
    assert client.get(f"/api/projects/{project_id}").status_code == 404


def test_analysis_run_is_persisted_with_restart_safe_run_id(monkeypatch, client):
    monkeypatch.setattr(analysis.httpx, "AsyncClient", FakeAsyncClient)
    project = client.post("/api/projects", json={
        "name": "persisted-analysis",
        "files": [{"path": "main.py", "content": "print('ok')\n"}],
    }).json()

    started = client.post("/analysis/run", json={
        "project_id": project["project_id"],
        "files": [{"path": "main.py", "content": "print('ok')\n"}],
        "tools": ["ruff"],
    })
    assert started.status_code == 200
    run_id = started.json()["run_id"]

    status = client.get(f"/api/analysis/{run_id}/status")
    assert status.status_code == 200
    assert status.json()["run_id"] == run_id
    assert status.json()["project_id"] == project["project_id"]

    report = client.get(f"/results/{project['project_id']}")
    assert report.status_code == 200
    assert report.json()["report"]["validation_status"] == "pending"
    report_by_run = client.get(f"/results/{run_id}")
    assert report_by_run.status_code == 200
    assert report_by_run.json()["project_id"] == project["project_id"]
    history = client.get("/api/history")
    assert history.status_code == 200
    assert any(item["run_id"] == run_id for item in history.json()["items"])


def test_public_agent_health_is_available_without_authentication(monkeypatch):
    async def healthy_service(_client, name, _url):
        return name, {"status": "healthy", "healthy": True, "details": {"service": name}}

    monkeypatch.setattr(system, "_check_service", healthy_service)
    with TestClient(app, base_url="https://testserver") as anonymous_client:
        public_response = anonymous_client.get("/api/system/public-agents")
        protected_response = anonymous_client.get("/api/system/agents")

    assert public_response.status_code == 200
    assert public_response.json()["services"]["code_quality"] is True
    assert protected_response.status_code == 401
