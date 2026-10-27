import os
from urllib.parse import urlsplit, urlunsplit

import httpx


OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b")
OLLAMA_REQUEST_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_REQUEST_TIMEOUT_SECONDS", "600"))


async def model_status() -> tuple[bool, str | None]:
    parsed = urlsplit(OLLAMA_URL)
    path = parsed.path
    if path.endswith("/api/generate"):
        path = path[:-len("generate")] + "tags"
    else:
        path = path.rstrip("/") + "/api/tags"
    tags_url = urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(tags_url)
            response.raise_for_status()
            models = response.json().get("models", [])
    except (httpx.HTTPError, ValueError):
        return False, "Ollama is unreachable or returned an invalid model list."
    if not any(
        isinstance(model, dict)
        and OLLAMA_MODEL in {model.get("name"), model.get("model")}
        for model in models
    ):
        return False, "The configured Ollama model is not installed."
    return True, None


async def generate_code(prompt: str) -> str:
    async with httpx.AsyncClient(timeout=OLLAMA_REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "format": "json"},
        )
        response.raise_for_status()
        return response.json().get("response", "")