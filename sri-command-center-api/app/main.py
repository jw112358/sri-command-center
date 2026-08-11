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
    marketing,
    notes,
    os,
    projects,
    session_briefs,
    tasks,
)
from app.services.legal_intake import get_legal_store
from app.services.legal_auth import authenticate_operator_token
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
        version="2.1.0",
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
    app.include_router(marketing.router)
    app.include_router(tasks.router)
    app.include_router(session_briefs.router)

    # ── WebSocket ─────────────────────────────────────────────────────────────
    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        origin = ws.headers.get("origin")
        if origin and origin not in settings.cors_origins_list:
            await ws.close(code=1008)
            return
        await ws.accept()
        try:
            raw_auth = await asyncio.wait_for(ws.receive_text(), timeout=10)
            import json
            auth_message = json.loads(raw_auth)
            if auth_message.get("type") != "auth":
                raise ValueError("WebSocket authentication required")
            authenticate_operator_token(str(auth_message.get("token", "")))
            await manager.connect(ws, accepted=True)
            await manager.send_to(ws, {"type": "authenticated"})
            while True:
                # Keep connection alive; handle incoming operator messages
                data = await ws.receive_text()
                # Client can send: { "type": "ping" } or operator interact messages
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "ping":
                        await manager.send_to(ws, {"type": "pong"})
                except Exception:
                    pass
        except (WebSocketDisconnect, ValueError, asyncio.TimeoutError):
            try:
                await ws.close(code=1008)
            except Exception:
                pass
        finally:
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
        if settings.marketing_worker_enabled and settings.marketing_publishing_enabled:
            from app.services.marketing_automation import marketing_worker_loop

            asyncio.create_task(marketing_worker_loop())
            log.info(
                "Marketing OS publishing worker started "
                f"(interval={settings.marketing_worker_interval_seconds}s)"
            )

    @app.on_event("shutdown")
    async def shutdown():
        log.info("SRI OS Command Center API shutting down")

    return app


app = create_app()
