"""Durable operator-owned state for Notebook and Mission Control.

Google Drive remains the system of record. A single JSON control file keeps the
small, frequently edited dashboard entities together and avoids pretending that
in-process memory is durable.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from googleapiclient.http import MediaInMemoryUpload

from app.config import settings
from app.models import Lane, Note, Priority, Project, Task
from app.services import drive


class DashboardStateUnavailable(RuntimeError):
    """Raised when durable Drive state cannot be read or written."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_state() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "updatedAt": _now(),
        "notes": {},
        "tasks": {},
        "projects": {},
    }


class DashboardStateStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache: Optional[dict[str, Any]] = None
        self._cache_at = 0.0
        self._file_id: Optional[str] = None

    def available(self, *, writable: bool = False) -> bool:
        if not settings.dashboard_state_parent_id:
            return False
        if writable and not settings.dashboard_drive_write_enabled:
            return False
        return drive.get_drive_service() is not None

    def list_notes(self) -> list[Note]:
        state = self._load()
        notes = [Note(**item) for item in state["notes"].values()]
        return sorted(notes, key=lambda note: note.updatedAt, reverse=True)

    def get_note(self, note_id: str) -> Optional[Note]:
        item = self._load()["notes"].get(note_id)
        return Note(**item) if item else None

    def create_note(self, *, title: str, tag: str, body: str) -> Note:
        now = _now()
        note = Note(
            id=f"n:{uuid.uuid4().hex[:12]}",
            title=title,
            tag=tag,
            body=body,
            updatedAt=now,
        )
        with self._lock:
            state = self._load(fresh=True)
            state["notes"][note.id] = note.model_dump()
            self._save(state)
        return note

    def upsert_note(self, note: Note, patch: dict[str, Any]) -> Note:
        updated = note.model_copy(update={**patch, "updatedAt": _now()})
        with self._lock:
            state = self._load(fresh=True)
            state["notes"][updated.id] = updated.model_dump()
            self._save(state)
        return updated

    def delete_note(self, note_id: str) -> bool:
        with self._lock:
            state = self._load(fresh=True)
            if note_id not in state["notes"]:
                return False
            del state["notes"][note_id]
            self._save(state)
        return True

    def list_tasks(self) -> list[Task]:
        tasks = [Task(**item) for item in self._load()["tasks"].values()]
        return sorted(tasks, key=lambda task: task.updatedAt, reverse=True)

    def create_task(self, text: str) -> Task:
        now = _now()
        task = Task(
            id=f"task:{uuid.uuid4().hex[:12]}",
            text=text.strip(),
            createdAt=now,
            updatedAt=now,
        )
        with self._lock:
            state = self._load(fresh=True)
            state["tasks"][task.id] = task.model_dump()
            self._save(state)
        return task

    def patch_task(self, task_id: str, patch: dict[str, Any]) -> Optional[Task]:
        with self._lock:
            state = self._load(fresh=True)
            item = state["tasks"].get(task_id)
            if not item:
                return None
            task = Task(**item)
            updates = {**patch, "updatedAt": _now()}
            if patch.get("done") is True and not task.done:
                updates["completedAt"] = _now()
            elif patch.get("done") is False:
                updates["completedAt"] = None
            updated = task.model_copy(update=updates)
            state["tasks"][task_id] = updated.model_dump()
            self._save(state)
        return updated

    def delete_task(self, task_id: str) -> bool:
        with self._lock:
            state = self._load(fresh=True)
            if task_id not in state["tasks"]:
                return False
            del state["tasks"][task_id]
            self._save(state)
        return True

    def list_projects(self) -> list[Project]:
        projects = [Project(**item) for item in self._load()["projects"].values()]
        return sorted(projects, key=lambda project: project.updatedAt or "", reverse=True)

    def get_project(self, project_id: str) -> Optional[Project]:
        item = self._load()["projects"].get(project_id)
        return Project(**item) if item else None

    def create_project(
        self,
        *,
        name: str,
        os_id: str,
        owner: str,
        priority: Priority,
    ) -> Project:
        project = Project(
            id=f"p:{uuid.uuid4().hex[:12]}",
            name=name,
            os=os_id,
            owner=owner,
            priority=priority,
            lane=Lane.PLANNING,
            updatedAt=_now(),
        )
        return self.upsert_project(project)

    def upsert_project(self, project: Project) -> Project:
        updated = project.model_copy(update={"updatedAt": _now()})
        with self._lock:
            state = self._load(fresh=True)
            state["projects"][updated.id] = updated.model_dump(mode="json")
            self._save(state)
        return updated

    def delete_project(self, project_id: str) -> bool:
        with self._lock:
            state = self._load(fresh=True)
            if project_id not in state["projects"]:
                return False
            del state["projects"][project_id]
            self._save(state)
        return True

    def _load(self, *, fresh: bool = False) -> dict[str, Any]:
        with self._lock:
            if (
                not fresh
                and self._cache is not None
                and time.monotonic() - self._cache_at < 10
            ):
                return json.loads(json.dumps(self._cache))
            state = self._read_drive_state()
            for key in ("notes", "tasks", "projects"):
                state.setdefault(key, {})
            state.setdefault("schemaVersion", 1)
            self._cache = state
            self._cache_at = time.monotonic()
            return json.loads(json.dumps(state))

    def _save(self, state: dict[str, Any]) -> None:
        if not settings.dashboard_drive_write_enabled:
            raise DashboardStateUnavailable(
                "Dashboard Drive writes are disabled until operator authentication is configured"
            )
        service = drive.get_drive_service()
        parent_id = settings.dashboard_state_parent_id
        if not service or not parent_id:
            raise DashboardStateUnavailable("Google Drive state is unavailable")

        state["schemaVersion"] = 1
        state["updatedAt"] = _now()
        payload = json.dumps(state, indent=2, sort_keys=True).encode("utf-8")
        media = MediaInMemoryUpload(payload, mimetype="application/json", resumable=False)
        file_id = self._resolve_file_id(service)
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
                        "name": settings.dashboard_state_file_name,
                        "parents": [parent_id],
                        "mimeType": "application/json",
                    },
                    media_body=media,
                    fields="id,modifiedTime",
                ).execute()
                self._file_id = created["id"]
        except Exception as exc:
            raise DashboardStateUnavailable(
                "Google Drive rejected the dashboard state update"
            ) from exc

        self._cache = state
        self._cache_at = time.monotonic()

    def _read_drive_state(self) -> dict[str, Any]:
        service = drive.get_drive_service()
        if not service or not settings.dashboard_state_parent_id:
            raise DashboardStateUnavailable("Google Drive state is unavailable")
        file_id = self._resolve_file_id(service)
        if not file_id:
            return _empty_state()
        try:
            content = service.files().get_media(fileId=file_id).execute()
            if isinstance(content, bytes):
                content = content.decode("utf-8")
            return json.loads(content)
        except Exception as exc:
            raise DashboardStateUnavailable(
                "Google Drive dashboard state could not be read"
            ) from exc

    def _resolve_file_id(self, service) -> Optional[str]:
        if self._file_id:
            return self._file_id
        safe_name = settings.dashboard_state_file_name.replace("'", "\\'")
        result = service.files().list(
            q=(
                f"'{settings.dashboard_state_parent_id}' in parents "
                f"and name = '{safe_name}' and trashed = false"
            ),
            fields="files(id,modifiedTime)",
            orderBy="modifiedTime desc",
            pageSize=1,
        ).execute()
        files = result.get("files", [])
        self._file_id = files[0]["id"] if files else None
        return self._file_id


_store: Optional[DashboardStateStore] = None


def get_dashboard_store() -> DashboardStateStore:
    global _store
    if _store is None:
        _store = DashboardStateStore()
    return _store
