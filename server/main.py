from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.config.settings import CORS_ORIGINS
from server.db.database import create_tables
from server.auth.router import router as auth_router

app = FastAPI(
    title="ClimbPost API",
    description="Auto-analyze climbing videos and prepare Instagram carousel posts",
    version="0.1.0",
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


@app.on_event("startup")
def on_startup():
    create_tables()


@app.get("/health")
async def health():
    return {"status": "ok"}
