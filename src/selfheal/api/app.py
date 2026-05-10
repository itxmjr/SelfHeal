from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import tasks, sync, system

def create_app() -> FastAPI:
    app = FastAPI(title="SelfHeal API")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(tasks.router)
    app.include_router(sync.router)
    app.include_router(system.router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
