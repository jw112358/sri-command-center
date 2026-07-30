"""Sanitized dashboard reads and protected Legal Agent OS controls."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.config import settings
from app.models import (
    LegalAssignmentCompleteRequest,
    LegalAssignmentStartReceipt,
    LegalAssignmentStartRequest,
    LegalAssignmentSummary,
    LegalAuthConfig,
    LegalDashboardState,
    LegalGoogleCredentialRequest,
    LegalIntakeReceipt,
    LegalIntakeRequest,
    LegalMatterSummary,
    LegalOperatorSession,
    LegalSessionStatus,
)
from app.services.legal_auth import (
    OperatorPrincipal,
    authenticate_operator_token,
    create_operator_session,
    google_operator_auth_enabled,
    principal_expires_at,
    verify_google_credential,
)
from app.services.legal_intake import get_legal_store

router = APIRouter(prefix="/api/legal", tags=["legal"])


def _manual_intake_ready() -> bool:
    if not settings.legal_manual_intake_enabled:
        return False
    from app.services.legal_google import legal_runner_config_errors

    return not legal_runner_config_errors()


def require_operator(
    authorization: str | None = Header(default=None),
) -> OperatorPrincipal:
    """Accept either a server-side token or a short-lived Jeff-only session."""
    if not settings.legal_api_token and not google_operator_auth_enabled():
        raise HTTPException(
            status_code=503,
            detail="Legal OS operator authentication is not configured",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Operator authentication required")
    token = authorization.removeprefix("Bearer ")
    try:
        return authenticate_operator_token(token)
    except ValueError:
        pass
    raise HTTPException(status_code=401, detail="Operator authentication required")


@router.get("/auth/config", response_model=LegalAuthConfig)
def auth_config():
    return LegalAuthConfig(
        enabled=google_operator_auth_enabled(),
        clientId=settings.legal_google_client_id if google_operator_auth_enabled() else "",
        sessionTtlSeconds=settings.legal_session_ttl_seconds,
        manualIntakeEnabled=_manual_intake_ready(),
    )


@router.post("/auth/google", response_model=LegalOperatorSession)
def google_sign_in(body: LegalGoogleCredentialRequest, request: Request):
    if not google_operator_auth_enabled():
        raise HTTPException(503, "Google operator authentication is not configured")
    origin = request.headers.get("origin")
    if origin and origin not in settings.cors_origins_list:
        raise HTTPException(403, "Origin is not authorized")
    try:
        claims = verify_google_credential(body.credential)
        token, principal = create_operator_session(claims)
    except ValueError as exc:
        raise HTTPException(401, "Google account is not authorized") from exc
    return LegalOperatorSession(
        accessToken=token,
        email=principal.email,
        expiresAt=principal_expires_at(principal),
    )


@router.get("/auth/session", response_model=LegalSessionStatus)
def session(principal: OperatorPrincipal = Depends(require_operator)):
    return LegalSessionStatus(
        email=principal.email,
        expiresAt=principal_expires_at(principal),
    )


@router.get(
    "/dashboard",
    response_model=LegalDashboardState,
    dependencies=[Depends(require_operator)],
)
def dashboard():
    """Jeff-only Legal OS state and connector health."""
    return get_legal_store().dashboard()


@router.get(
    "/matters",
    response_model=list[LegalMatterSummary],
    dependencies=[Depends(require_operator)],
)
def matters():
    return get_legal_store().list_matters()


@router.get(
    "/assignments",
    response_model=list[LegalAssignmentSummary],
    dependencies=[Depends(require_operator)],
)
def assignments():
    """Jeff-only assignment activity feed."""
    return get_legal_store().list_assignments()


@router.post(
    "/assignments/start",
    response_model=LegalAssignmentStartReceipt,
    dependencies=[Depends(require_operator)],
)
def start_assignment(body: LegalAssignmentStartRequest):
    lease_id = get_legal_store().acquire_lease(body.matterId, body.workerId)
    if not lease_id:
        raise HTTPException(
            409,
            "Assignment could not start; verify matter state, capacity, and pause status",
        )
    return LegalAssignmentStartReceipt(leaseId=lease_id)


@router.post(
    "/assignments/{lease_id}/complete",
    dependencies=[Depends(require_operator)],
)
def complete_assignment(
    lease_id: str,
    body: LegalAssignmentCompleteRequest,
):
    if not get_legal_store().release_lease(lease_id, body.nextStatus):
        raise HTTPException(404, "Active legal assignment not found")
    return {"completed": True}


@router.post(
    "/intake",
    response_model=LegalIntakeReceipt,
    status_code=202,
    dependencies=[Depends(require_operator)],
)
def manual_intake(body: LegalIntakeRequest):
    if not _manual_intake_ready():
        raise HTTPException(
            503,
            "Manual intake remains staged until durable state and Drive persistence are ready",
        )
    if body.channel != "master_builder":
        raise HTTPException(400, "Manual intake channel must be master_builder")
    store = get_legal_store()
    receipt = store.ingest(body)
    if receipt.duplicate:
        return receipt
    try:
        from app.services.legal_artifacts import persist_manual_source
        from app.services.legal_google import build_legal_drive_service

        persist_manual_source(
            build_legal_drive_service(),
            request=body,
            receipt=receipt,
        )
    except Exception as exc:
        store.block_intake_persistence_failure(
            matter_id=receipt.matter.matterId,
            event_id=receipt.eventId,
        )
        raise HTTPException(
            502,
            "Manual intake could not be preserved in Drive and was safely blocked",
        ) from exc
    return receipt


@router.post("/pause", dependencies=[Depends(require_operator)])
def pause():
    get_legal_store().set_paused(True)
    return {"paused": True}


@router.post("/resume", dependencies=[Depends(require_operator)])
def resume():
    get_legal_store().set_paused(False)
    return {"paused": False}
