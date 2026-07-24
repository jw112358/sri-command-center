"""Transactional state and intake routing for Legal Agent OS.

Only sanitized matter metadata leaves this service. Source messages, party
names, attachments, and work product remain in the protected matter store.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models import (
    LegalAssignmentSummary,
    LegalConnectorStatus,
    LegalDashboardState,
    LegalIntakeReceipt,
    LegalIntakeRequest,
    LegalMatterSummary,
    Note,
)


ACTIVE_STATES = ("researching", "drafting", "quality_review")
MATTER_ID_RE = re.compile(r"\bSC-[A-Z0-9-]+-[0-9]{4}-[A-Z0-9-]+\b", re.I)
CASE_NUMBER_RE = re.compile(
    r"\b(?:case|docket)\s*(?:no\.?|number|#)?\s*[:#-]?\s*([A-Z0-9-]{5,})\b",
    re.I,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_type(request: LegalIntakeRequest) -> str:
    if request.requestType != "unknown":
        return request.requestType
    text = f"{request.subject}\n{request.body[:2000]}".lower()
    if any(term in text for term in ("revision", "revise", "redline", "changes requested")):
        return "revision"
    if "strategy memo" in text or "strategy memorandum" in text:
        return "strategy_memo"
    if any(term in text for term in ("research memo", "legal research", "research question")):
        return "standalone_research"
    return "unknown"


def _idempotency_key(request: LegalIntakeRequest, source_id: str) -> str:
    raw = f"{request.channel}:{source_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class LegalIntakeStore:
    """SQLite-backed queue with atomic idempotency and lease enforcement."""

    def __init__(self, db_path: str, max_active: int = 4):
        self.db_path = db_path
        self.max_active = max_active
        self._lock = threading.RLock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS legal_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                INSERT OR IGNORE INTO legal_settings(key, value)
                    VALUES ('paused', '0');

                CREATE TABLE IF NOT EXISTS legal_matters (
                    matter_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    request_type TEXT NOT NULL,
                    practice_lane TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    source_channel TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    thread_id TEXT,
                    case_number TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_legal_matters_thread
                    ON legal_matters(thread_id);
                CREATE INDEX IF NOT EXISTS idx_legal_matters_case
                    ON legal_matters(case_number);

                CREATE TABLE IF NOT EXISTS legal_intake_events (
                    event_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    matter_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    request_type TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    FOREIGN KEY(matter_id) REFERENCES legal_matters(matter_id)
                );

                CREATE TABLE IF NOT EXISTS legal_leases (
                    matter_id TEXT PRIMARY KEY,
                    lease_id TEXT NOT NULL UNIQUE,
                    worker_id TEXT NOT NULL,
                    acquired_at TEXT NOT NULL,
                    heartbeat_at TEXT NOT NULL,
                    FOREIGN KEY(matter_id) REFERENCES legal_matters(matter_id)
                );

                CREATE TABLE IF NOT EXISTS legal_assignments (
                    assignment_id TEXT PRIMARY KEY,
                    matter_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    outcome_status TEXT,
                    FOREIGN KEY(matter_id) REFERENCES legal_matters(matter_id)
                );
                CREATE INDEX IF NOT EXISTS idx_legal_assignments_started
                    ON legal_assignments(started_at DESC);

                CREATE TABLE IF NOT EXISTS legal_activity_notes (
                    note_id TEXT PRIMARY KEY,
                    assignment_id TEXT NOT NULL,
                    matter_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(assignment_id) REFERENCES legal_assignments(assignment_id),
                    FOREIGN KEY(matter_id) REFERENCES legal_matters(matter_id)
                );
                CREATE INDEX IF NOT EXISTS idx_legal_activity_notes_created
                    ON legal_activity_notes(created_at DESC);

                CREATE TABLE IF NOT EXISTS legal_audit (
                    audit_id TEXT PRIMARY KEY,
                    matter_id TEXT,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def ingest(self, request: LegalIntakeRequest) -> LegalIntakeReceipt:
        source_id = request.sourceId or f"manual:{uuid.uuid4().hex}"
        key = _idempotency_key(request, source_id)
        event_id = f"intake:{uuid.uuid4().hex}"
        received_at = _now()
        resolved_type = _request_type(request)

        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                """
                SELECT e.event_id, m.*
                FROM legal_intake_events e
                JOIN legal_matters m ON m.matter_id = e.matter_id
                WHERE e.idempotency_key = ?
                """,
                (key,),
            ).fetchone()
            if existing:
                conn.execute("COMMIT")
                return LegalIntakeReceipt(
                    eventId=existing["event_id"],
                    matter=self._to_summary(existing),
                    duplicate=True,
                    revisionMatched=resolved_type == "revision",
                )

            match = self._find_revision_match(conn, request, resolved_type)
            revision_matched = match is not None
            if match:
                matter_id = match["matter_id"]
                version = int(match["version"]) + 1
                status = "revision_requested"
                conn.execute(
                    """
                    UPDATE legal_matters
                    SET request_type=?, practice_lane=?, status=?,
                        version=?, updated_at=?
                    WHERE matter_id=?
                    """,
                    (
                        resolved_type,
                        request.practiceLane,
                        status,
                        version,
                        received_at,
                        matter_id,
                    ),
                )
            else:
                matter_id = self._new_matter_id(request.practiceLane)
                version = 1
                status = "needs_operator" if resolved_type in ("unknown", "revision") else "received"
                case_number = self._case_number(request)
                conn.execute(
                    """
                    INSERT INTO legal_matters(
                        matter_id, display_name, request_type, practice_lane,
                        status, version, source_channel, source_id, thread_id,
                        case_number, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        matter_id,
                        f"MATTER {matter_id[-8:]}",
                        resolved_type,
                        request.practiceLane,
                        status,
                        version,
                        request.channel,
                        source_id,
                        request.threadId,
                        case_number,
                        received_at,
                        received_at,
                    ),
                )

            conn.execute(
                """
                INSERT INTO legal_intake_events(
                    event_id, idempotency_key, matter_id, channel, source_id,
                    request_type, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    key,
                    matter_id,
                    request.channel,
                    source_id,
                    resolved_type,
                    received_at,
                ),
            )
            conn.execute(
                """
                INSERT INTO legal_audit(
                    audit_id, matter_id, event_type, actor, detail, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"audit:{uuid.uuid4().hex}",
                    matter_id,
                    "intake.received",
                    request.channel,
                    "duplicate=false; external_action=none",
                    received_at,
                ),
            )
            row = conn.execute(
                "SELECT * FROM legal_matters WHERE matter_id=?", (matter_id,)
            ).fetchone()
            conn.execute("COMMIT")

        return LegalIntakeReceipt(
            eventId=event_id,
            matter=self._to_summary(row),
            duplicate=False,
            revisionMatched=revision_matched,
        )

    def list_matters(self) -> list[LegalMatterSummary]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM legal_matters ORDER BY updated_at DESC LIMIT 100"
            ).fetchall()
        return [self._to_summary(row) for row in rows]

    def dashboard(self) -> LegalDashboardState:
        matters = self.list_matters()
        active_count = sum(1 for matter in matters if matter.status in ACTIVE_STATES)
        awaiting = sum(1 for matter in matters if matter.status == "pending_approval")
        return LegalDashboardState(
            activeCount=active_count,
            capacity=self.max_active,
            awaitingApproval=awaiting,
            upcomingDeadlines=0,
            paused=self.is_paused(),
            matters=matters,
            connectors=[
                LegalConnectorStatus(name="GMAIL", detail="LegalOS/Intake", status="READY"),
                LegalConnectorStatus(name="DRIVE", detail="Matter system of record", status="READY"),
                LegalConnectorStatus(name="CALENDAR", detail="Tentative deadlines", status="READY"),
                LegalConnectorStatus(name="MIDPAGE", detail="Research + cite-check", status="READY"),
                LegalConnectorStatus(name="DESCRYBE", detail="Secondary research", status="READY"),
                LegalConnectorStatus(
                    name="AUTOMATION",
                    detail="Gmail runner enabled" if settings.legal_gmail_enabled else "Runner staged",
                    status="READY" if settings.legal_gmail_enabled else "STAGED",
                ),
            ],
        )

    def list_assignments(self, limit: int = 25) -> list[LegalAssignmentSummary]:
        safe_limit = max(1, min(limit, 100))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM legal_assignments
                ORDER BY
                    CASE status WHEN 'running' THEN 0 ELSE 1 END,
                    COALESCE(completed_at, started_at) DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [self._to_assignment_summary(row) for row in rows]

    def list_activity_notes(self, limit: int = 100) -> list[Note]:
        safe_limit = max(1, min(limit, 250))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT note_id, title, body, created_at
                FROM legal_activity_notes
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [
            Note(
                id=row["note_id"],
                title=row["title"],
                tag="legal-os",
                body=row["body"],
                updatedAt=row["created_at"],
            )
            for row in rows
        ]

    def get_activity_note(self, note_id: str) -> Optional[Note]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT note_id, title, body, created_at
                FROM legal_activity_notes
                WHERE note_id=?
                """,
                (note_id,),
            ).fetchone()
        if not row:
            return None
        return Note(
            id=row["note_id"],
            title=row["title"],
            tag="legal-os",
            body=row["body"],
            updatedAt=row["created_at"],
        )

    def set_paused(self, paused: bool) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE legal_settings SET value=? WHERE key='paused'",
                ("1" if paused else "0",),
            )
            conn.execute("COMMIT")

    def is_paused(self) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM legal_settings WHERE key='paused'"
            ).fetchone()
        return bool(row and row["value"] == "1")

    def acquire_lease(self, matter_id: str, worker_id: str) -> Optional[str]:
        """Atomically reserve one of four active work slots."""
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if self.is_paused():
                conn.execute("ROLLBACK")
                return None
            if conn.execute(
                "SELECT 1 FROM legal_leases WHERE matter_id=?", (matter_id,)
            ).fetchone():
                conn.execute("ROLLBACK")
                return None
            count = conn.execute("SELECT COUNT(*) AS n FROM legal_leases").fetchone()["n"]
            if count >= self.max_active:
                conn.execute("ROLLBACK")
                return None
            now = _now()
            lease_id = f"lease:{uuid.uuid4().hex}"
            conn.execute(
                """
                INSERT INTO legal_leases(
                    matter_id, lease_id, worker_id, acquired_at, heartbeat_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (matter_id, lease_id, worker_id, now, now),
            )
            conn.execute(
                """
                INSERT INTO legal_assignments(
                    assignment_id, matter_id, stage, status, started_at
                ) VALUES (?, ?, 'researching', 'running', ?)
                """,
                (lease_id, matter_id, now),
            )
            self._insert_activity_note(
                conn,
                assignment_id=lease_id,
                matter_id=matter_id,
                event_type="assignment.started",
                created_at=now,
                title=f"Legal assignment started · {matter_id}",
                body=self._assignment_note_body(
                    event="started",
                    assignment_id=lease_id,
                    matter_id=matter_id,
                    stage="researching",
                    occurred_at=now,
                ),
            )
            conn.execute(
                "UPDATE legal_matters SET status='researching', updated_at=? WHERE matter_id=?",
                (now, matter_id),
            )
            conn.execute("COMMIT")
            return lease_id

    def release_lease(self, lease_id: str, next_status: str = "queued") -> bool:
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT matter_id FROM legal_leases WHERE lease_id=?", (lease_id,)
            ).fetchone()
            if not row:
                conn.execute("ROLLBACK")
                return False
            completed_at = _now()
            conn.execute("DELETE FROM legal_leases WHERE lease_id=?", (lease_id,))
            assignment = conn.execute(
                """
                SELECT assignment_id, matter_id, stage
                FROM legal_assignments
                WHERE assignment_id=?
                """,
                (lease_id,),
            ).fetchone()
            if not assignment:
                conn.execute("ROLLBACK")
                return False
            conn.execute(
                """
                UPDATE legal_assignments
                SET status='completed', completed_at=?, outcome_status=?
                WHERE assignment_id=?
                """,
                (completed_at, next_status, lease_id),
            )
            self._insert_activity_note(
                conn,
                assignment_id=lease_id,
                matter_id=row["matter_id"],
                event_type="assignment.completed",
                created_at=completed_at,
                title=f"Legal assignment completed · {row['matter_id']}",
                body=self._assignment_note_body(
                    event="completed",
                    assignment_id=lease_id,
                    matter_id=row["matter_id"],
                    stage=assignment["stage"],
                    occurred_at=completed_at,
                    outcome_status=next_status,
                ),
            )
            conn.execute(
                "UPDATE legal_matters SET status=?, updated_at=? WHERE matter_id=?",
                (next_status, completed_at, row["matter_id"]),
            )
            conn.execute("COMMIT")
            return True

    def _find_revision_match(
        self, conn: sqlite3.Connection, request: LegalIntakeRequest, resolved_type: str
    ) -> Optional[sqlite3.Row]:
        if resolved_type != "revision":
            return None
        if request.threadId:
            row = conn.execute(
                "SELECT * FROM legal_matters WHERE thread_id=? ORDER BY updated_at DESC LIMIT 1",
                (request.threadId,),
            ).fetchone()
            if row:
                return row
        text = f"{request.subject}\n{request.body}"
        matter_match = MATTER_ID_RE.search(text)
        if matter_match:
            row = conn.execute(
                "SELECT * FROM legal_matters WHERE matter_id=?",
                (matter_match.group(0).upper(),),
            ).fetchone()
            if row:
                return row
        case_number = self._case_number(request)
        if case_number:
            return conn.execute(
                "SELECT * FROM legal_matters WHERE case_number=? ORDER BY updated_at DESC LIMIT 1",
                (case_number,),
            ).fetchone()
        return None

    @staticmethod
    def _case_number(request: LegalIntakeRequest) -> Optional[str]:
        match = CASE_NUMBER_RE.search(f"{request.subject}\n{request.body[:4000]}")
        return match.group(1).upper() if match else None

    @staticmethod
    def _new_matter_id(practice_lane: str) -> str:
        lane = "APP" if practice_lane == "appeal" else "CIV"
        year = datetime.now(timezone.utc).year
        return f"SC-{lane}-{year}-{uuid.uuid4().hex[:8].upper()}"

    @staticmethod
    def _public_assignment_id(assignment_id: str) -> str:
        return f"ASG-{assignment_id.rsplit(':', 1)[-1][-8:].upper()}"

    @classmethod
    def _assignment_note_body(
        cls,
        *,
        event: str,
        assignment_id: str,
        matter_id: str,
        stage: str,
        occurred_at: str,
        outcome_status: Optional[str] = None,
    ) -> str:
        public_id = cls._public_assignment_id(assignment_id)
        heading = "Legal assignment started" if event == "started" else "Legal assignment completed"
        time_label = "Started" if event == "started" else "Completed"
        lines = [
            f"# {heading}",
            "",
            f"- Matter: `{matter_id}`",
            f"- Assignment: `{public_id}`",
            f"- Stage: {stage.replace('_', ' ').title()}",
            f"- {time_label}: {occurred_at}",
        ]
        if outcome_status:
            lines.append(
                f"- Resulting matter state: {outcome_status.replace('_', ' ').title()}"
            )
        lines.extend([
            "",
            "> Sanitized activity log. No party names, source communications, legal analysis, or work product are included.",
        ])
        return "\n".join(lines)

    @staticmethod
    def _insert_activity_note(
        conn: sqlite3.Connection,
        *,
        assignment_id: str,
        matter_id: str,
        event_type: str,
        title: str,
        body: str,
        created_at: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO legal_activity_notes(
                note_id, assignment_id, matter_id, event_type,
                title, body, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"legal-note:{uuid.uuid4().hex}",
                assignment_id,
                matter_id,
                event_type,
                title,
                body,
                created_at,
            ),
        )

    @classmethod
    def _to_assignment_summary(cls, row: sqlite3.Row) -> LegalAssignmentSummary:
        return LegalAssignmentSummary(
            assignmentId=cls._public_assignment_id(row["assignment_id"]),
            matterId=row["matter_id"],
            stage=row["stage"],
            status=row["status"],
            startedAt=row["started_at"],
            completedAt=row["completed_at"],
            outcomeStatus=row["outcome_status"],
        )

    @staticmethod
    def _to_summary(row: sqlite3.Row) -> LegalMatterSummary:
        return LegalMatterSummary(
            matterId=row["matter_id"],
            displayName=row["display_name"],
            requestType=row["request_type"],
            practiceLane=row["practice_lane"],
            status=row["status"],
            version=row["version"],
            sourceChannel=row["source_channel"],
            createdAt=row["created_at"],
            updatedAt=row["updated_at"],
        )


_store: Optional[LegalIntakeStore] = None


def get_legal_store() -> LegalIntakeStore:
    global _store
    if _store is None:
        _store = LegalIntakeStore(
            settings.legal_state_db,
            max_active=settings.legal_max_active_matters,
        )
    return _store
