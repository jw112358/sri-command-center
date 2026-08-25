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
    LegalJobSummary,
    LegalMatterSummary,
    LegalMatterDocument,
    LegalDocumentExtractionPreview,
    LegalReviewArtifact,
    LegalReviewPacket,
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
            detail = "Canonical Legal Agent OS rejected the Command Center request"
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

    def _post_multipart(
        self,
        path: str,
        *,
        filename: str,
        content_type: str,
        content: bytes,
        fields: dict[str, str],
    ) -> Any:
        if not self.configured:
            raise LegalControlPlaneError("Canonical Legal Agent OS connection is not configured")
        try:
            response = httpx.post(
                f"{self.base_url}{path}",
                headers={"X-Operator-Token": self.operator_token},
                files={"file": (filename, content, content_type)},
                data=fields,
                timeout=max(self.timeout_seconds, 30.0),
                follow_redirects=False,
            )
        except httpx.RequestError as exc:
            raise LegalControlPlaneError("Canonical Legal Agent OS is temporarily unreachable") from exc
        if response.status_code >= 400:
            detail = "Canonical Legal Agent OS rejected the document upload"
            try:
                upstream_detail = response.json().get("detail")
                if isinstance(upstream_detail, str):
                    detail = upstream_detail
            except (ValueError, AttributeError):
                pass
            raise LegalControlPlaneError(
                detail,
                status_code=response.status_code if response.status_code in {400, 401, 403, 404, 409, 413, 422} else 502,
            )
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
    def _document(record: dict[str, Any]) -> LegalMatterDocument:
        return LegalMatterDocument(
            documentId=record["document_id"],
            matterId=record["matter_id"],
            version=record["version"],
            name=record["name"],
            mimeType=record["mime_type"],
            sizeBytes=record["size_bytes"],
            sha256=record["sha256"],
            driveFileId=record["drive_file_id"],
            category=record["category"],
            recordStatus=record["record_status"],
            confidentiality=record["confidentiality"],
            ingestionStatus=record["ingestion_status"],
            extractionMethod=record.get("extraction_method"),
            extractedCharacterCount=record.get("extracted_character_count", 0),
            pageCount=record.get("page_count"),
            warnings=record.get("warnings", []),
            reviewNote=record.get("review_note", ""),
            acceptedAt=record.get("accepted_at"),
            createdAt=record["created_at"],
            updatedAt=record["updated_at"],
        )

    @staticmethod
    def _review_packet(record: dict[str, Any]) -> LegalReviewPacket:
        return LegalReviewPacket(
            packetId=record["packet_id"],
            matterId=record["matter_id"],
            matterVersion=record["matter_version"],
            status=record["status"],
            summary=record.get("summary", ""),
            artifacts=[
                LegalReviewArtifact(
                    title=artifact["title"],
                    kind=artifact["kind"],
                    driveFileId=artifact["drive_file_id"],
                    sha256=artifact["sha256"],
                )
                for artifact in record.get("artifacts", [])
            ],
            authorities=record.get("authorities", []),
            citationFindings=record.get("citation_findings", []),
            riskFlags=record.get("risk_flags", []),
            proposedExternalAction=record.get("proposed_external_action"),
            createdAt=record["created_at"],
            reviewedAt=record.get("reviewed_at"),
            reviewedBy=record.get("reviewed_by"),
            decisionNote=record.get("decision_note"),
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
        matters_by_id = {
            record["matter_id"]: record
            for record in matter_records
            if isinstance(record, dict) and record.get("matter_id")
        }
        recent_jobs = []
        for record in state.get("recent_jobs", []):
            if not isinstance(record, dict):
                continue
            matter = matters_by_id.get(record.get("matter_id"), {})
            status = record.get("status", "queued")
            recent_jobs.append(
                LegalJobSummary(
                    jobId=record["job_id"],
                    matterId=record["matter_id"],
                    kind=record.get("kind", "unknown"),
                    status=status,
                    attempts=record.get("attempts", 0),
                    lastError=record.get("last_error"),
                    updatedAt=record.get("updated_at", record.get("created_at", "")),
                    canRetry=(
                        status in {"blocked", "failed"}
                        and bool(matter.get("drive_folder_id"))
                    ),
                )
            )
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
            recentJobs=recent_jobs,
            blockedJobs=state.get(
                "blocked_jobs",
                sum(job.status in {"blocked", "failed"} for job in recent_jobs),
            ),
            connectors=connectors,
        )

    def retry_job(self, job_id: str, operator_note: str) -> LegalJobSummary:
        record = self._post_json(
            f"/api/jobs/{job_id}/retry",
            {"operator_note": operator_note},
        )
        return LegalJobSummary(
            jobId=record["job_id"],
            matterId=record["matter_id"],
            kind=record.get("kind", "unknown"),
            status=record["status"],
            attempts=record.get("attempts", 0),
            lastError=record.get("last_error"),
            updatedAt=record.get("updated_at", record.get("created_at", "")),
            canRetry=False,
        )

    def matters(self) -> list[LegalMatterSummary]:
        records = self._request("/api/matters")
        return [self._matter(record) for record in records]

    def matter_documents(self, matter_id: str) -> list[LegalMatterDocument]:
        records = self._request(f"/api/matters/{matter_id}/documents")
        return [self._document(record) for record in records]

    def upload_matter_document(
        self,
        matter_id: str,
        *,
        filename: str,
        content_type: str,
        content: bytes,
        category: str,
        record_status: str,
        confidentiality: str,
    ) -> LegalMatterDocument:
        record = self._post_multipart(
            f"/api/matters/{matter_id}/documents",
            filename=filename,
            content_type=content_type,
            content=content,
            fields={
                "category": category,
                "record_status": record_status,
                "confidentiality": confidentiality,
            },
        )
        return self._document(record)

    def document_preview(self, matter_id: str, document_id: str) -> LegalDocumentExtractionPreview:
        record = self._request(f"/api/matters/{matter_id}/documents/{document_id}/preview")
        return LegalDocumentExtractionPreview(
            document=self._document(record["document"]),
            textExcerpt=record.get("text_excerpt", ""),
            provenanceNotice=record.get("provenance_notice", ""),
        )

    def review_document(
        self,
        matter_id: str,
        document_id: str,
        *,
        action: str,
        expected_version: int,
        note: str,
    ) -> LegalMatterDocument:
        record = self._post_json(
            f"/api/matters/{matter_id}/documents/{document_id}/review",
            {"action": action, "expected_version": expected_version, "note": note},
        )
        return self._document(record)

    def review_packets(self) -> list[LegalReviewPacket]:
        records = self._request("/api/review-packets")
        return [self._review_packet(record) for record in records]

    def decide_review_packet(
        self,
        packet_id: str,
        decision: str,
        note: str,
    ) -> LegalReviewPacket:
        record = self._post_json(
            f"/api/review-packets/{packet_id}/decision",
            {"decision": decision, "note": note},
        )
        return self._review_packet(record)

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
