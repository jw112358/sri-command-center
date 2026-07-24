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
from app.routers import (
    agents,
    events,
    graph,
    legal,
    notes,
    os,
    projects,
    session_briefs,
    tasks,
)
from app.services.legal_intake import get_legal_store
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
    app.include_router(legal.router)
    app.include_router(tasks.router)
    app.include_router(session_briefs.router)

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
        if settings.legal_enabled:
            get_legal_store()
            log.info(
                "Legal Agent OS state initialized "
                f"(capacity={settings.legal_max_active_matters})"
            )
        if settings.legal_gmail_enabled:
            from app.services.legal_google import legal_runner_config_errors

            runner_errors = legal_runner_config_errors()
            if runner_errors:
                log.error(
                    "Legal Agent OS Gmail runner blocked: %s",
                    "; ".join(runner_errors),
                )
            else:
                from app.workers.legal_intake_runner import gmail_poll_loop

                asyncio.create_task(gmail_poll_loop())
                log.info(
                    "Legal Agent OS Gmail runner started "
                    f"(interval={settings.legal_gmail_poll_interval}s; "
                    f"shadow={settings.legal_gmail_shadow_mode})"
                )
        if settings.drive_enabled:
            asyncio.create_task(drive_poll_loop(settings.drive_poll_interval))
            log.info(f"Drive poll loop started (interval={settings.drive_poll_interval}s)")

    @app.on_event("shutdown")
    async def shutdown():
        log.info("SRI OS Command Center API shutting down")

    return app


app = create_app()
