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
from app.models import EventEdgeManualTrade, Lane, Note, Priority, Project, Task, TaskStatus
from app.services import drive


class DashboardStateUnavailable(RuntimeError):
    """Raised when durable Drive state cannot be read or written."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_state() -> dict[str, Any]:
    return {
        "schemaVersion": 5,
        "updatedAt": _now(),
        "notes": {},
        "tasks": {},
        "projects": {},
        "marketingApprovals": {},
        "marketingRoutes": {},
        "marketingPublications": {},
        "marketingMeasurements": {},
        "marketingLearning": {},
        "eventEdgeManualTrades": {},
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
        tasks = [self._task_from_item(item) for item in self._load()["tasks"].values()]
        return sorted(tasks, key=lambda task: task.updatedAt, reverse=True)

    def get_task(self, task_id: str) -> Optional[Task]:
        item = self._load()["tasks"].get(task_id)
        return self._task_from_item(item) if item else None

    def create_task(
        self,
        text: str,
        *,
        project: str = "Master Builder",
        preferred_surface: Optional[str] = None,
    ) -> Task:
        now = _now()
        task = Task(
            id=f"task:{uuid.uuid4().hex[:12]}",
            text=text.strip(),
            project=project.strip(),
            preferredSurface=preferred_surface.strip() if preferred_surface else None,
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
            task = self._task_from_item(item)
            updates = {**patch, "updatedAt": _now()}
            updated = task.model_copy(update=updates)
            state["tasks"][task_id] = updated.model_dump(mode="json")
            self._save(state)
        return updated

    def claim_tasks(self, worker_id: str, limit: int) -> list[Task]:
        """Atomically claim queued work while enforcing the global four-slot cap."""
        with self._lock:
            state = self._load(fresh=True)
            tasks = {
                task_id: self._task_from_item(item)
                for task_id, item in state["tasks"].items()
            }
            active = sum(
                task.status in (
                    TaskStatus.RUNNING,
                    TaskStatus.REVIEW_READY,
                    TaskStatus.SHIPPING,
                )
                for task in tasks.values()
            )
            assigned = sorted(
                (
                    task for task in tasks.values()
                    if task.assignedAgent == worker_id
                    and task.status in (TaskStatus.RUNNING, TaskStatus.SHIPPING)
                ),
                key=lambda task: task.updatedAt,
            )[:limit]
            remaining = max(0, limit - len(assigned))
            available = max(
                0,
                min(remaining, settings.orchestrator_max_concurrent_tasks - active),
            )
            queued = sorted(
                (
                    task for task in tasks.values()
                    if task.status == TaskStatus.QUEUED
                ),
                key=lambda task: task.createdAt,
            )[:available]
            if not queued:
                return assigned
            now = _now()
            claimed: list[Task] = list(assigned)
            for task in queued:
                updated = task.model_copy(update={
                    "status": TaskStatus.RUNNING,
                    "done": False,
                    "assignedAgent": worker_id,
                    "startedAt": task.startedAt or now,
                    "blockedAt": None,
                    "lastError": None,
                    "updatedAt": now,
                })
                state["tasks"][task.id] = updated.model_dump(mode="json")
                claimed.append(updated)
            self._save(state)
            return claimed

    def mark_task_review_ready(
        self,
        task_id: str,
        *,
        worker_id: str,
        summary_id: str,
        review_url: Optional[str],
        evidence_urls: list[str],
    ) -> Optional[Task]:
        with self._lock:
            state = self._load(fresh=True)
            item = state["tasks"].get(task_id)
            if not item:
                return None
            task = self._task_from_item(item)
            if task.status != TaskStatus.RUNNING or task.assignedAgent != worker_id:
                raise ValueError("Only the assigned running worker can submit review-ready work")
            now = _now()
            updated = task.model_copy(update={
                "status": TaskStatus.REVIEW_READY,
                "reviewReadyAt": now,
                "summaryId": summary_id,
                "reviewUrl": review_url,
                "evidenceUrls": evidence_urls,
                "updatedAt": now,
            })
            state["tasks"][task_id] = updated.model_dump(mode="json")
            self._save(state)
            return updated

    def approve_task_for_shipping(self, task_id: str) -> Optional[Task]:
        with self._lock:
            state = self._load(fresh=True)
            item = state["tasks"].get(task_id)
            if not item:
                return None
            task = self._task_from_item(item)
            if task.status != TaskStatus.REVIEW_READY:
                raise ValueError("Only review-ready work can be approved for shipping")
            now = _now()
            updated = task.model_copy(update={
                "status": TaskStatus.SHIPPING,
                "approvedAt": now,
                "updatedAt": now,
            })
            state["tasks"][task_id] = updated.model_dump(mode="json")
            self._save(state)
            return updated

    def complete_task(
        self,
        task_id: str,
        *,
        worker_id: str,
        summary_id: str,
        evidence_urls: list[str],
    ) -> Optional[Task]:
        with self._lock:
            state = self._load(fresh=True)
            item = state["tasks"].get(task_id)
            if not item:
                return None
            task = self._task_from_item(item)
            if task.status != TaskStatus.SHIPPING or task.assignedAgent != worker_id:
                raise ValueError(
                    "Completion requires the assigned worker and prior Approve & Ship authorization"
                )
            now = _now()
            updated = task.model_copy(update={
                "status": TaskStatus.COMPLETED,
                "done": True,
                "completedAt": now,
                "summaryId": summary_id,
                "evidenceUrls": evidence_urls or task.evidenceUrls,
                "updatedAt": now,
            })
            state["tasks"][task_id] = updated.model_dump(mode="json")
            self._save(state)
            return updated

    def block_task(
        self,
        task_id: str,
        *,
        worker_id: str,
        reason: str,
        summary_id: str,
        evidence_urls: list[str],
    ) -> Optional[Task]:
        with self._lock:
            state = self._load(fresh=True)
            item = state["tasks"].get(task_id)
            if not item:
                return None
            task = self._task_from_item(item)
            if task.status == TaskStatus.COMPLETED:
                raise ValueError("Completed work cannot be marked blocked")
            if task.assignedAgent and task.assignedAgent != worker_id:
                raise ValueError("Only the assigned worker can block this task")
            now = _now()
            updated = task.model_copy(update={
                "status": TaskStatus.BLOCKED,
                "done": False,
                "assignedAgent": task.assignedAgent or worker_id,
                "blockedAt": now,
                "lastError": reason.strip(),
                "summaryId": summary_id,
                "evidenceUrls": evidence_urls or task.evidenceUrls,
                "updatedAt": now,
            })
            state["tasks"][task_id] = updated.model_dump(mode="json")
            self._save(state)
            return updated

    def requeue_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            state = self._load(fresh=True)
            item = state["tasks"].get(task_id)
            if not item:
                return None
            task = self._task_from_item(item)
            if task.status not in (TaskStatus.BLOCKED, TaskStatus.REVIEW_READY):
                raise ValueError("Only blocked or review-ready work can be requeued")
            updated = task.model_copy(update={
                "status": TaskStatus.QUEUED,
                "done": False,
                "assignedAgent": None,
                "startedAt": None,
                "reviewReadyAt": None,
                "approvedAt": None,
                "completedAt": None,
                "blockedAt": None,
                "lastError": None,
                "updatedAt": _now(),
            })
            state["tasks"][task_id] = updated.model_dump(mode="json")
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

    @staticmethod
    def _task_from_item(item: dict[str, Any]) -> Task:
        """Read schema-v1 checklist records without losing their prior state."""
        normalized = dict(item)
        if "status" not in normalized:
            normalized["status"] = (
                TaskStatus.COMPLETED if normalized.get("done") else TaskStatus.QUEUED
            )
        return Task(**normalized)

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

    def list_marketing_approvals(self) -> dict[str, dict[str, Any]]:
        return dict(self._load().get("marketingApprovals", {}))

    def list_event_edge_manual_trades(self) -> list[EventEdgeManualTrade]:
        records = [
            EventEdgeManualTrade(**item)
            for item in self._load().get("eventEdgeManualTrades", {}).values()
        ]
        return sorted(records, key=lambda item: item.enteredAt, reverse=True)

    def create_event_edge_manual_trade(
        self, record: dict[str, Any]
    ) -> EventEdgeManualTrade:
        now = _now()
        trade = EventEdgeManualTrade(
            id=f"manual-trade:{uuid.uuid4().hex[:12]}",
            createdAt=now,
            updatedAt=now,
            executionMode="manual_external_record",
            **record,
        )
        with self._lock:
            state = self._load(fresh=True)
            trades = state.setdefault("eventEdgeManualTrades", {})
            trades[trade.id] = trade.model_dump(mode="json")
            self._save(state)
        return trade

    def set_marketing_approval(
        self,
        approval_id: str,
        *,
        approved: bool,
        approved_by: str,
    ) -> dict[str, Any]:
        with self._lock:
            state = self._load(fresh=True)
            approvals = state.setdefault("marketingApprovals", {})
            record = {
                "status": "approved" if approved else "awaiting-approval",
                "approvedAt": _now() if approved else None,
                "approvedBy": approved_by if approved else None,
            }
            approvals[approval_id] = record
            self._save(state)
            return dict(record)

    def list_marketing_routes(self) -> dict[str, dict[str, Any]]:
        return dict(self._load().get("marketingRoutes", {}))

    def set_marketing_route(self, platform: str, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            state = self._load(fresh=True)
            routes = state.setdefault("marketingRoutes", {})
            routes[platform] = dict(record)
            self._save(state)
            return dict(routes[platform])

    def list_marketing_publications(self) -> dict[str, dict[str, Any]]:
        return dict(self._load().get("marketingPublications", {}))

    def upsert_marketing_publication(
        self, publication_id: str, record: dict[str, Any]
    ) -> dict[str, Any]:
        with self._lock:
            state = self._load(fresh=True)
            publications = state.setdefault("marketingPublications", {})
            publications[publication_id] = dict(record)
            self._save(state)
            return dict(publications[publication_id])

    def list_marketing_measurements(self) -> dict[str, dict[str, Any]]:
        return dict(self._load().get("marketingMeasurements", {}))

    def upsert_marketing_measurement(
        self, measurement_id: str, record: dict[str, Any]
    ) -> dict[str, Any]:
        with self._lock:
            state = self._load(fresh=True)
            measurements = state.setdefault("marketingMeasurements", {})
            measurements[measurement_id] = dict(record)
            self._save(state)
            return dict(measurements[measurement_id])

    def list_marketing_learning(self) -> dict[str, dict[str, Any]]:
        return dict(self._load().get("marketingLearning", {}))

    def upsert_marketing_learning(
        self, publication_id: str, record: dict[str, Any]
    ) -> dict[str, Any]:
        with self._lock:
            state = self._load(fresh=True)
            learning = state.setdefault("marketingLearning", {})
            learning[publication_id] = dict(record)
            self._save(state)
            return dict(learning[publication_id])

    def _load(self, *, fresh: bool = False) -> dict[str, Any]:
        with self._lock:
            if (
                not fresh
                and self._cache is not None
                and time.monotonic() - self._cache_at < 10
            ):
                return json.loads(json.dumps(self._cache))
            state = self._read_drive_state()
            for key in (
                "notes",
                "tasks",
                "projects",
                "marketingApprovals",
                "marketingRoutes",
                "marketingPublications",
                "marketingMeasurements",
                "marketingLearning",
                "eventEdgeManualTrades",
            ):
                state.setdefault(key, {})
            state.setdefault("schemaVersion", 5)
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

        state["schemaVersion"] = 5
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
