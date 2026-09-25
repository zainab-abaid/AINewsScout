from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import API_HOST, API_PORT, CORS_ORIGINS, FRONTEND_DIST
from backend.database import init_db
from backend.routers.admin import router as admin_router
from backend.routers.core import router as core_router
from backend.routers.ops import router as ops_router
from backend.routers.search import router as search_router
from backend.services.imap_scheduler import start_imap_daily_sync
from backend.services.jobs import resume_orphaned_jobs


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    resume_orphaned_jobs()
    start_imap_daily_sync()
    yield


app = FastAPI(title="Probe Scout", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(core_router, prefix="/api")
app.include_router(ops_router, prefix="/api")
app.include_router(search_router, prefix="/api")
app.include_router(admin_router, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True, "host": API_HOST, "port": API_PORT}


def _mount_frontend() -> None:
    """Serve the Vite production build from the same origin as the API."""
    dist = FRONTEND_DIST
    if not dist.is_dir() or not (dist / "index.html").is_file():
        return
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/")
    def spa_index():
        return FileResponse(dist / "index.html")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(404, "Not found")
        candidate = dist / full_path
        # Only serve real files under dist (e.g. vite.svg); otherwise SPA shell.
        try:
            candidate.resolve().relative_to(dist.resolve())
        except ValueError:
            raise HTTPException(404, "Not found") from None
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")


_mount_frontend()
