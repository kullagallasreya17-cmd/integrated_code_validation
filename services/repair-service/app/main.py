from fastapi import FastAPI

from app.api.routes import router


app = FastAPI(title="Fix and Regeneration Agent", version="1.0.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "repair-service"}


app.include_router(router)