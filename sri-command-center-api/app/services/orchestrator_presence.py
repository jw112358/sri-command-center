"""In-process liveness tracking for trusted orchestrator workers."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

_lock = threading.RLock()
_last_seen: dict[str, datetime] = {}
FRESH_FOR_SECONDS = 120


def record_heartbeat(worker_id: str) -> str:
    now = datetime.now(timezone.utc)
    with _lock:
        _last_seen[worker_id] = now
    return now.isoformat()


def presence_status() -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=FRESH_FOR_SECONDS)
    with _lock:
        active = {
            worker: seen for worker, seen in _last_seen.items()
            if seen >= cutoff
        }
        _last_seen.clear()
        _last_seen.update(active)
    latest = max(active.values()) if active else None
    return {
        "connected": bool(active),
        "last_seen_at": latest.isoformat() if latest else None,
        "workers": sorted(active),
    }
