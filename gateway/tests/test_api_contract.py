from fastapi.testclient import TestClient

from app.main import app
from app.routes import analysis


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
        return FakeResponse({"project_id": "project", "status": "completed", "result": {"findings": []}})


def test_project_and_analysis_contract(monkeypatch):
    monkeypatch.setattr(analysis.httpx, "AsyncClient", FakeAsyncClient)
    client = TestClient(app)

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


def test_code_quality_adapter_forwards_to_service(monkeypatch):
    monkeypatch.setattr(analysis.httpx, "AsyncClient", FakeAsyncClient)
    client = TestClient(app)

    response = client.post("/api/agents/code-quality/analyze", json={
        "project_id": "quality-test",
        "files": [{"path": "main.py", "content": "print('ok')"}],
        "tools": ["ruff"],
    })

    assert response.status_code == 200
    assert response.json()["agent"] == "code_quality"
