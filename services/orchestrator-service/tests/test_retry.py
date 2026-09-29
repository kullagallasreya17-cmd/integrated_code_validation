import asyncio

from app.graph.nodes import should_retry
from app.config import settings
from app.graph.nodes import validate


def test_should_retry_returns_finalize_on_pass():
    state = {"validation_status": "passed", "retry_count": 0}
    assert should_retry(state) == "finalize"


def test_should_retry_returns_retry_when_under_budget():
    state = {"validation_status": "failed", "retry_count": 1}
    assert should_retry(state) == "retry"


def test_should_retry_returns_finalize_when_budget_exhausted():
    state = {"validation_status": "failed", "retry_count": settings.max_retries}
    assert should_retry(state) == "finalize"


def test_validate_does_not_call_validation_when_sandbox_fails(monkeypatch):
    from app.graph import nodes

    monkeypatch.setattr(nodes.sandbox_client, "execute", lambda *args: _failed_sandbox())

    async def fail_if_called(*args):
        raise AssertionError("validation must not run after sandbox failure")

    monkeypatch.setattr(nodes.validation_client, "validate", fail_if_called)
    result = asyncio.run(validate({"project_id": "p", "repaired_code": {"main.py": "print(1)"}}))

    assert result["validation_status"] == "failed"
    assert result["validation_results"]["passed"] is False
    assert result["agent_errors"][0]["agent"] == "sandbox"


async def _failed_sandbox():
    return {"executed": False, "error": "sandbox unavailable"}
