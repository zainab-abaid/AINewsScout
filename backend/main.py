from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import API_HOST, API_PORT
from backend.database import init_db
from backend.routers.core import router as core_router
from backend.routers.ops import router as ops_router
from backend.routers.publish import router as publish_router
from backend.routers.search import router as search_router
from backend.services.gmail_sync import warmup_gmail_email
from backend.services.jobs import resume_orphaned_jobs
import threading


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    resume_orphaned_jobs()
    threading.Thread(target=warmup_gmail_email, daemon=True).start()
    yield


app = FastAPI(title="Probe Scout", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(core_router, prefix="/api")
app.include_router(ops_router, prefix="/api")
app.include_router(publish_router, prefix="/api")
app.include_router(search_router, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True, "host": API_HOST, "port": API_PORT}
