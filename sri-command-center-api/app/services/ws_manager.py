"""app/services/ws_manager.py

Multiplexed WebSocket manager.

All connected frontend clients share one broadcast channel.
The /ws endpoint registers here; background tasks push events via broadcast().

Event envelope matches INTEGRATION.md exactly:
  { "type": "agent.log",     "line": LogLine }
  { "type": "agent.started", "agent": Agent }
  { "type": "agent.updated", "agent": Agent }
  { "type": "agent.stopped", "agentId": "a1" }
  { "type": "graph.node.updated", "node": GraphNode }
  { "type": "project.updated",    "project": Project }
  { "type": "system.event",       "event": SystemEvent }
  { "type": "system.health",      "status": ..., "faults": ..., "latencyMs": ... }
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

from fastapi import WebSocket

log = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
        log.info(f"WS client connected (total={len(self._connections)})")

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)
        log.info(f"WS client disconnected (total={len(self._connections)})")

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        """Send a JSON payload to all connected clients."""
        if not self._connections:
            return
        text = json.dumps(payload, default=str)
        dead: List[WebSocket] = []
        async with self._lock:
            targets = list(self._connections)
        for ws in targets:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)

    async def send_to(self, ws: WebSocket, payload: Dict[str, Any]) -> None:
        """Send a payload to a single client."""
        try:
            await ws.send_text(json.dumps(payload, default=str))
        except Exception as e:
            log.warning(f"send_to failed: {e}")


manager = ConnectionManager()


# ── Convenience broadcast helpers ─────────────────────────────────────────────

async def broadcast_log_line(agent_id: str, text: str) -> None:
    await manager.broadcast({
        "type": "agent.log",
        "line": {
            "agentId": agent_id,
            "ts": _now_iso(),
            "text": text,
        },
    })


async def broadcast_agent_updated(agent_dict: Dict) -> None:
    await manager.broadcast({"type": "agent.updated", "agent": agent_dict})


async def broadcast_agent_stopped(agent_id: str) -> None:
    await manager.broadcast({"type": "agent.stopped", "agentId": agent_id})


async def broadcast_project_updated(project_dict: Dict) -> None:
    await manager.broadcast({"type": "project.updated", "project": project_dict})


async def broadcast_graph_node_updated(node_dict: Dict) -> None:
    await manager.broadcast({"type": "graph.node.updated", "node": node_dict})


async def broadcast_system_event(event_dict: Dict) -> None:
    await manager.broadcast({"type": "system.event", "event": event_dict})


async def broadcast_health(status: str, faults: int, latency_ms: int = 0) -> None:
    await manager.broadcast({
        "type": "system.health",
        "status": status,
        "faults": faults,
        "latencyMs": latency_ms,
    })


# ── Background polling task ────────────────────────────────────────────────────

async def drive_poll_loop(interval: int = 30) -> None:
    """
    Background task: poll Drive every `interval` seconds, diff against last
    snapshot, and broadcast any changes over WebSocket.
    """
    from app.services.drive import (
        get_agents, get_os_plugins, get_projects, get_health,
        invalidate_cache,
    )

    last_agents: Dict[str, Any] = {}
    last_projects: Dict[str, Any] = {}

    while True:
        await asyncio.sleep(interval)
        try:
            invalidate_cache()

            # ── Agents ──────────────────────────────────────────────────────
            current_agents = {a.id: a for a in get_agents()}
            for aid, agent in current_agents.items():
                old = last_agents.get(aid)
                if old is None:
                    await manager.broadcast({"type": "agent.started", "agent": agent.model_dump()})
                elif agent.status != old.status or agent.task != old.task:
                    await broadcast_agent_updated(agent.model_dump())
            for aid in set(last_agents) - set(current_agents):
                await broadcast_agent_stopped(aid)
            last_agents = current_agents

            # ── Projects ────────────────────────────────────────────────────
            current_projects = {p.id: p for p in get_projects()}
            for pid, proj in current_projects.items():
                old = last_projects.get(pid)
                if old and proj.lane != old.lane:
                    await broadcast_project_updated(proj.model_dump())
            last_projects = current_projects

            # ── Health ──────────────────────────────────────────────────────
            h = get_health()
            await broadcast_health(h["status"], h["faults"], h["latencyMs"])

        except Exception as e:
            log.warning(f"drive_poll_loop error: {e}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
