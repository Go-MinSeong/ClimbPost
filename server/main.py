import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.config.settings import CORS_ORIGINS
from server.db.database import create_tables
from server.auth.router import router as auth_router
from server.api.upload import router as upload_router
from server.api.analysis import router as analysis_router
from server.api.clips import router as clips_router
from server.push.service import router as push_router
from server.queue.worker import poll_jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    create_tables()
    task = asyncio.create_task(poll_jobs())
    yield
    # Shutdown
    task.cancel()


app = FastAPI(
    title="ClimbPost API",
    description="Auto-analyze climbing videos and prepare Instagram carousel posts",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(analysis_router)
app.include_router(clips_router)
app.include_router(push_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
