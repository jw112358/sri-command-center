"""Server-side client and view adapter for the canonical Legal Agent OS API."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import settings
from app.models import (
    LegalAssignmentSummary,
    LegalConnectorStatus,
    LegalDashboardState,
    LegalIntakeReceipt,
    LegalMatterSummary,
)


class LegalControlPlaneError(RuntimeError):
    """Raised when canonical Legal Agent OS state cannot be read safely."""

    def __init__(self, message: str, *, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


class LegalControlPlane:
    JOB_STAGE = {
        "validate_intake": "validating",
        "validate_revision": "revision_requested",
        "conflict_review": "conflict_review",
        "jurisdiction_review": "validating",
        "research": "researching",
        "draft": "drafting",
        "transcribe": "transcribing",
        "quality_review": "quality_review",
        "approval_packet": "pending_approval",
    }

    def __init__(
        self,
        base_url: str | None = None,
        operator_token: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.base_url = (base_url if base_url is not None else settings.legal_os_api_url).rstrip("/")
        self.operator_token = (
            operator_token
            if operator_token is not None
            else settings.legal_os_operator_token
        )
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.operator_token)

    def _request(self, path: str) -> Any:
        if not self.configured:
            raise LegalControlPlaneError(
                "Canonical Legal Agent OS connection is not configured"
            )
        try:
            response = httpx.get(
                f"{self.base_url}{path}",
                headers={"X-Operator-Token": self.operator_token},
                timeout=self.timeout_seconds,
                follow_redirects=False,
            )
        except httpx.RequestError as exc:
            raise LegalControlPlaneError(
                "Canonical Legal Agent OS is temporarily unreachable"
            ) from exc
        if response.status_code >= 400:
            status_code = response.status_code if response.status_code in {401, 403, 404} else 502
            raise LegalControlPlaneError(
                "Canonical Legal Agent OS rejected the Command Center request",
                status_code=status_code,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise LegalControlPlaneError(
                "Canonical Legal Agent OS returned an invalid response"
            ) from exc

    def _post(self, path: str) -> Any:
        if not self.configured:
            raise LegalControlPlaneError(
                "Canonical Legal Agent OS connection is not configured"
            )
        try:
            response = httpx.post(
                f"{self.base_url}{path}",
                headers={"X-Operator-Token": self.operator_token},
                timeout=self.timeout_seconds,
                follow_redirects=False,
            )
        except httpx.RequestError as exc:
            raise LegalControlPlaneError(
                "Canonical Legal Agent OS is temporarily unreachable"
            ) from exc
        if response.status_code >= 400:
            raise LegalControlPlaneError(
                "Canonical Legal Agent OS rejected the Command Center request",
                status_code=502,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise LegalControlPlaneError(
                "Canonical Legal Agent OS returned an invalid response"
            ) from exc

    def _post_json(self, path: str, payload: dict[str, Any]) -> Any:
        if not self.configured:
            raise LegalControlPlaneError(
                "Canonical Legal Agent OS connection is not configured"
            )
        try:
            response = httpx.post(
                f"{self.base_url}{path}",
                headers={
                    "X-Operator-Token": self.operator_token,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout_seconds,
                follow_redirects=False,
            )
        except httpx.RequestError as exc:
            raise LegalControlPlaneError(
                "Canonical Legal Agent OS is temporarily unreachable"
            ) from exc
        if response.status_code >= 400:
            detail = "Canonical Legal Agent OS rejected the structured intake"
            try:
                upstream_detail = response.json().get("detail")
                if isinstance(upstream_detail, str):
                    detail = upstream_detail
            except (ValueError, AttributeError):
                pass
            status_code = response.status_code if response.status_code in {400, 401, 403, 409, 422} else 502
            raise LegalControlPlaneError(detail, status_code=status_code)
        try:
            return response.json()
        except ValueError as exc:
            raise LegalControlPlaneError(
                "Canonical Legal Agent OS returned an invalid response"
            ) from exc

    @staticmethod
    def _matter(record: dict[str, Any]) -> LegalMatterSummary:
        display_name = (
            record.get("client_name")
            or record.get("case_number")
            or record.get("current_summary")
            or record["matter_id"]
        )
        return LegalMatterSummary(
            matterId=record["matter_id"],
            displayName=str(display_name)[:300],
            requestType=record["request_type"],
            practiceLane=record.get("practice_lane", "civil"),
            status=record["status"],
            version=record.get("version", 1),
            currentSummary=record.get("current_summary", ""),
            exactNextAction=record.get("exact_next_action", ""),
            intakeCompletenessScore=record.get("intake_completeness_score"),
            blockingGaps=record.get("blocking_gaps", []),
            sourceChannel=record["source_channel"],
            createdAt=record["created_at"],
            updatedAt=record["updated_at"],
        )

    @staticmethod
    def _upcoming_deadlines(records: list[dict[str, Any]]) -> int:
        today = datetime.now(timezone.utc).date()
        cutoff = today + timedelta(days=30)
        total = 0
        for record in records:
            for raw_deadline in record.get("future_deadlines", []):
                try:
                    deadline = date.fromisoformat(str(raw_deadline))
                except ValueError:
                    continue
                if today <= deadline <= cutoff:
                    total += 1
        return total

    def dashboard(self) -> LegalDashboardState:
        state = self._request("/api/dashboard")
        automation = self._request("/api/automation/status")
        contract = self._request("/api/system/contract")
        if contract.get("control_plane") != "sri-legal-agent-os-api":
            raise LegalControlPlaneError("Unexpected Legal Agent OS control plane")
        if contract.get("command_center_local_legal_state_permitted") is not False:
            raise LegalControlPlaneError("Legal Agent OS control-plane contract is unsafe")

        matter_records = state.get("matters", [])
        connectors = [
            LegalConnectorStatus(
                name="CANONICAL API",
                detail=f"Legal Agent OS API {contract.get('api_version', 'unknown')}",
                status="READY",
            ),
            LegalConnectorStatus(
                name="MONGODB",
                detail="Authoritative operational matter and job state",
                status="READY",
            ),
            LegalConnectorStatus(
                name="DRIVE",
                detail="Private matter artifacts and durable source records",
                status="READY" if automation.get("drive_root_configured") else "BLOCKED",
            ),
            LegalConnectorStatus(
                name="GMAIL",
                detail=(
                    "Continuous scanner enabled"
                    if automation.get("gmail_scanner_enabled")
                    else "Scanner staged; continuous polling remains disabled"
                ),
                status="READY" if automation.get("gmail_scanner_enabled") else "STAGED",
            ),
            LegalConnectorStatus(
                name="AI DRAFT + QA",
                detail=(
                    f"{automation.get('ai_model', 'OpenAI')} internal worker"
                    if automation.get("ai_confidential_processing_authorized")
                    else "Confidential processing is not authorized"
                ),
                status="READY" if automation.get("ai_worker_enabled") else "STAGED",
            ),
        ]
        return LegalDashboardState(
            activeCount=state.get("active_matters", 0),
            capacity=state.get("capacity", contract.get("matter_concurrency_cap", 4)),
            awaitingApproval=state.get("awaiting_review", 0),
            upcomingDeadlines=self._upcoming_deadlines(matter_records),
            paused=bool(automation.get("pipeline_paused")),
            matters=[self._matter(record) for record in matter_records],
            connectors=connectors,
        )

    def matters(self) -> list[LegalMatterSummary]:
        records = self._request("/api/matters")
        return [self._matter(record) for record in records]

    def assignments(self) -> list[LegalAssignmentSummary]:
        jobs = self._request("/api/jobs")
        assignments: list[LegalAssignmentSummary] = []
        for job in jobs:
            if job.get("status") not in {"leased", "complete"}:
                continue
            assignments.append(
                LegalAssignmentSummary(
                    assignmentId=job["job_id"],
                    matterId=job["matter_id"],
                    stage=self.JOB_STAGE[job["kind"]],
                    status="running" if job["status"] == "leased" else "completed",
                    startedAt=job["created_at"],
                    completedAt=job.get("updated_at") if job["status"] == "complete" else None,
                    outcomeStatus=None,
                )
            )
        return assignments

    def manual_intake(self, payload: dict[str, Any]) -> LegalIntakeReceipt:
        if payload.get("schema_version") != "1.1":
            raise LegalControlPlaneError("Legal intake schema_version must be 1.1", status_code=422)
        if payload.get("channel") not in {"manual", "command_center"}:
            raise LegalControlPlaneError("Command Center intake channel is invalid", status_code=422)
        record = self._post_json("/api/intakes/manual", payload)
        matter = self._matter(record)
        return LegalIntakeReceipt(
            eventId=str(payload.get("source_id", matter.matterId)),
            matter=matter,
            duplicate=False,
            revisionMatched=bool(payload.get("request_type") == "revision"),
            acknowledgementStatus="draft_pending_approval",
        )

    def resolve_clarifications(
        self,
        matter_id: str,
        expected_version: int,
        answers: dict[str, str],
        operator_note: str,
    ) -> LegalMatterSummary:
        record = self._post_json(
            f"/api/matters/{matter_id}/clarifications",
            {
                "expected_version": expected_version,
                "answers": answers,
                "operator_note": operator_note,
            },
        )
        return self._matter(record)

    def set_pipeline_paused(self, paused: bool) -> bool:
        result = self._post(
            "/api/automation/pause" if paused else "/api/automation/resume"
        )
        if result.get("paused") is not paused:
            raise LegalControlPlaneError(
                "Canonical Legal Agent OS did not confirm the requested pipeline state"
            )
        return paused


def get_legal_control_plane() -> LegalControlPlane:
    return LegalControlPlane()
