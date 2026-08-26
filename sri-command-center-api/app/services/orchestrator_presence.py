"""Durable liveness tracking for trusted orchestrator workers.

Render may serve requests from more than one process. Presence therefore uses
its own small Drive record instead of process memory whenever the production
Drive identity is available. The separate file avoids heartbeat writes racing
with the operator-owned task queue state.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from googleapiclient.http import MediaInMemoryUpload

from app.config import settings
from app.services import drive

log = logging.getLogger(__name__)

_lock = threading.RLock()
_last_seen: dict[str, datetime] = {}
_cache_at = 0.0
_file_id: Optional[str] = None
FRESH_FOR_SECONDS = 120
CACHE_FOR_SECONDS = 30
PRESENCE_FILE_NAME = "sri-command-center-orchestrator-presence.json"


def record_heartbeat(worker_id: str) -> str:
    now = datetime.now(timezone.utc)
    service = drive.get_drive_service()
    parent_id = settings.dashboard_state_parent_id
    if service and parent_id and settings.dashboard_drive_write_enabled:
        with _lock:
            state = _read_drive_presence(service, parent_id)
            workers = _active_workers(state.get("workers", {}), now=now)
            workers[worker_id] = now.isoformat()
            _save_drive_presence(service, parent_id, {
                "schemaVersion": 1,
                "updatedAt": now.isoformat(),
                "workers": workers,
            })
            _set_memory_cache(workers)
        return now.isoformat()

    # Local development and unit tests may not have a Drive principal.
    with _lock:
        _last_seen[worker_id] = now
    return now.isoformat()


def presence_status() -> dict[str, Any]:
    service = drive.get_drive_service()
    parent_id = settings.dashboard_state_parent_id
    if service and parent_id:
        with _lock:
            if _cache_at == 0.0 or time.monotonic() - _cache_at >= CACHE_FOR_SECONDS:
                try:
                    state = _read_drive_presence(service, parent_id)
                    _set_memory_cache(_active_workers(state.get("workers", {})))
                except RuntimeError as exc:
                    log.warning("Durable orchestrator presence is unavailable: %s", exc)
    return _memory_presence_status()


def _memory_presence_status() -> dict[str, Any]:
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


def _active_workers(
    raw: dict[str, Any], *, now: Optional[datetime] = None
) -> dict[str, str]:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(seconds=FRESH_FOR_SECONDS)
    active: dict[str, str] = {}
    for worker, value in raw.items():
        try:
            seen = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        if seen >= cutoff:
            active[str(worker)] = seen.isoformat()
    return active


def _set_memory_cache(workers: dict[str, Any]) -> None:
    global _cache_at
    _last_seen.clear()
    for worker, value in workers.items():
        try:
            seen = datetime.fromisoformat(
                str(value).replace("Z", "+00:00")
            )
        except (TypeError, ValueError):
            continue
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        _last_seen[str(worker)] = seen
    _cache_at = time.monotonic()


def _read_drive_presence(service, parent_id: str) -> dict[str, Any]:
    file_id = _resolve_file_id(service, parent_id)
    if not file_id:
        return {"schemaVersion": 1, "workers": {}}
    try:
        content = service.files().get_media(fileId=file_id).execute()
        if isinstance(content, bytes):
            content = content.decode("utf-8")
        state = json.loads(content)
        return state if isinstance(state, dict) else {"workers": {}}
    except Exception as exc:
        raise RuntimeError("Orchestrator presence could not be read from Drive") from exc


def _save_drive_presence(service, parent_id: str, state: dict[str, Any]) -> None:
    global _file_id
    payload = json.dumps(state, indent=2, sort_keys=True).encode("utf-8")
    media = MediaInMemoryUpload(payload, mimetype="application/json", resumable=False)
    file_id = _resolve_file_id(service, parent_id)
    try:
        if file_id:
            service.files().update(
                fileId=file_id,
                media_body=media,
                fields="id,modifiedTime",
            ).execute()
        else:
            created = service.files().create(
                body={
                    "name": PRESENCE_FILE_NAME,
                    "parents": [parent_id],
                    "mimeType": "application/json",
                },
                media_body=media,
                fields="id,modifiedTime",
            ).execute()
            _file_id = created["id"]
    except Exception as exc:
        raise RuntimeError("Orchestrator presence could not be written to Drive") from exc


def _resolve_file_id(service, parent_id: str) -> Optional[str]:
    global _file_id
    if _file_id:
        return _file_id
    safe_name = PRESENCE_FILE_NAME.replace("'", "\\'")
    result = service.files().list(
        q=(
            f"'{parent_id}' in parents and name = '{safe_name}' "
            "and trashed = false"
        ),
        fields="files(id)",
        pageSize=1,
    ).execute()
    files = result.get("files", [])
    _file_id = files[0]["id"] if files else None
    return _file_id
