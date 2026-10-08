from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import check_database, close_database, initialize_database
from app.routes import analysis, projects, results
from app.routes import files


@asynccontextmanager
async def lifespan(app: FastAPI):
    await initialize_database()
    yield
    await close_database()

app = FastAPI(title="Coding Validation Gateway", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    await check_database()
    return {"status": "ok", "service": settings.service_name, "database": "connected"}


app.include_router(projects.router)
app.include_router(projects.api_router)
app.include_router(files.router)
app.include_router(analysis.router)
app.include_router(analysis.api_router)
app.include_router(results.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)