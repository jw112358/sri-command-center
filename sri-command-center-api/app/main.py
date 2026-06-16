"""app/main.py — SRI OS Command Center API

FastAPI application entry point.

Architecture:
  - REST endpoints in app/routers/
  - Data from Google Drive (app/services/drive.py) + GitHub (app/services/github.py)
  - Live updates via WebSocket /ws  (app/services/ws_manager.py)
  - Background polling loop broadcasts Drive diffs over WS every DRIVE_POLL_INTERVAL seconds
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import agents, events, graph, notes, os, projects
from app.services.ws_manager import manager, drive_poll_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
log = logging.getLogger(__name__)


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="SRI OS Command Center API",
        description="Backend for the SRI OS operator dashboard — Drive + GitHub data, WebSocket live streams.",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── REST routers ─────────────────────────────────────────────────────────
    app.include_router(os.router)
    app.include_router(agents.router)
    app.include_router(projects.router)
    app.include_router(notes.router)
    app.include_router(graph.router)
    app.include_router(events.router)

    # ── WebSocket ─────────────────────────────────────────────────────────────
    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await manager.connect(ws)
        try:
            while True:
                # Keep connection alive; handle incoming operator messages
                data = await ws.receive_text()
                # Client can send: { "type": "ping" } or operator interact messages
                import json
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "ping":
                        await manager.send_to(ws, {"type": "pong"})
                except Exception:
                    pass
        except WebSocketDisconnect:
            await manager.disconnect(ws)

    # ── Startup / shutdown ────────────────────────────────────────────────────
    @app.on_event("startup")
    async def startup():
        log.info("SRI OS Command Center API starting up")
        log.info(f"Drive enabled: {settings.drive_enabled}")
        log.info(f"GitHub enabled: {settings.github_enabled}")
        if settings.drive_enabled:
            asyncio.create_task(drive_poll_loop(settings.drive_poll_interval))
            log.info(f"Drive poll loop started (interval={settings.drive_poll_interval}s)")

    @app.on_event("shutdown")
    async def shutdown():
        log.info("SRI OS Command Center API shutting down")

    return app


app = create_app()
