import asyncio

from app.services import repair_client, sandbox_client, security_client, validation_client


class StubResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class StubAsyncClient:
    def __init__(self, handler):
        self.handler = handler
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url, json):
        self.requests.append((url, json))
        return StubResponse(self.handler(url, json))


def test_security_client_adapts_per_file_scan_response(monkeypatch):
    client = StubAsyncClient(lambda _url, _body: {
        "findings": [{"type": "secret", "severity": "high", "line": 4, "description": "Secret found"}]
    })
    monkeypatch.setattr(security_client.httpx, "AsyncClient", lambda **_kwargs: client)

    result = asyncio.run(security_client.analyze("p1", {"src/main.py": "token = 'x'"}))

    assert client.requests[0][0].endswith("/scan")
    assert client.requests[0][1] == {"code": "token = 'x'", "filename": "main.py"}
    assert result["findings"][0]["file"] == "src/main.py"
    assert result["findings"][0]["category"] == "security"
    assert result["findings"][0]["line_number"] == 4


def test_sandbox_client_runs_main_file_and_reports_failed_execution(monkeypatch):
    client = StubAsyncClient(lambda _url, _body: {
        "status": "failed", "exit_code": 1, "stderr": "Traceback"
    })
    monkeypatch.setattr(sandbox_client.httpx, "AsyncClient", lambda **_kwargs: client)

    result = asyncio.run(sandbox_client.execute("p1", {
        "helper.py": "pass", "src/main.py": "raise RuntimeError()"
    }))

    assert client.requests[0][0].endswith("/execute")
    assert client.requests[0][1]["filename"] == "main.py"
    assert result["executed"] is True
    assert result["passed"] is False


def test_validation_client_maps_validity_and_findings(monkeypatch):
    client = StubAsyncClient(lambda _url, _body: {
        "valid": False,
        "findings": [{"type": "syntax", "severity": "critical", "line": 2, "message": "Invalid syntax"}],
    })
    monkeypatch.setattr(validation_client.httpx, "AsyncClient", lambda **_kwargs: client)

    result = asyncio.run(validation_client.validate("p1", {"main.py": "if:"}, []))

    assert client.requests[0][0].endswith("/validate")
    assert result["passed"] is False
    assert result["error"] is None
    assert result["findings"][0]["category"] == "code_quality"
    assert result["findings"][0]["severity"] == "critical"


def test_repair_client_adapts_finding_response(monkeypatch):
    client = StubAsyncClient(lambda _url, _body: {"fixed_code": "print('fixed')\n"})
    monkeypatch.setattr(repair_client.httpx, "AsyncClient", lambda **_kwargs: client)

    result = asyncio.run(repair_client.repair(
        "p1",
        {"main.py": "print('broken')\n"},
        [{"file": "main.py", "description": "Replace broken output", "severity": "high"}],
        1,
    ))

    assert client.requests[0][0].endswith("/analyze-fix")
    assert client.requests[0][1]["severity"] == "high"
    assert result["repaired_files"] == [{"path": "main.py", "content": "print('fixed')\n"}]