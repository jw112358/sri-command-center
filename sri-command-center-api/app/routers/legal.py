"""Sanitized dashboard reads and protected Legal Agent OS controls."""
from __future__ import annotations

from typing import Any

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
from app.services.legal_control_plane import (
    LegalControlPlaneError,
    get_legal_control_plane,
)

router = APIRouter(prefix="/api/legal", tags=["legal"])


def _manual_intake_ready() -> bool:
    return get_legal_control_plane().configured


def _canonical_error(exc: LegalControlPlaneError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


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
    try:
        return get_legal_control_plane().dashboard()
    except LegalControlPlaneError as exc:
        raise _canonical_error(exc) from exc


@router.get(
    "/matters",
    response_model=list[LegalMatterSummary],
    dependencies=[Depends(require_operator)],
)
def matters():
    try:
        return get_legal_control_plane().matters()
    except LegalControlPlaneError as exc:
        raise _canonical_error(exc) from exc


@router.get(
    "/assignments",
    response_model=list[LegalAssignmentSummary],
    dependencies=[Depends(require_operator)],
)
def assignments():
    """Jeff-only assignment activity feed."""
    try:
        return get_legal_control_plane().assignments()
    except LegalControlPlaneError as exc:
        raise _canonical_error(exc) from exc


@router.post(
    "/assignments/start",
    response_model=LegalAssignmentStartReceipt,
    dependencies=[Depends(require_operator)],
)
def start_assignment(body: LegalAssignmentStartRequest):
    raise HTTPException(
        409,
        "The retired Command Center queue cannot start canonical Legal Agent OS jobs",
    )


@router.post(
    "/assignments/{lease_id}/complete",
    dependencies=[Depends(require_operator)],
)
def complete_assignment(
    lease_id: str,
    body: LegalAssignmentCompleteRequest,
):
    raise HTTPException(
        409,
        "The retired Command Center queue cannot complete canonical Legal Agent OS jobs",
    )


@router.post(
    "/intake",
    response_model=LegalIntakeReceipt,
    status_code=202,
    dependencies=[Depends(require_operator)],
)
def manual_intake(body: dict[str, Any]):
    if not _manual_intake_ready():
        raise HTTPException(
            503,
            "Canonical Legal Agent OS intake connection is not configured",
        )
    try:
        return get_legal_control_plane().manual_intake(body)
    except LegalControlPlaneError as exc:
        raise _canonical_error(exc) from exc


@router.post("/pause", dependencies=[Depends(require_operator)])
def pause():
    try:
        return {"paused": get_legal_control_plane().set_pipeline_paused(True)}
    except LegalControlPlaneError as exc:
        raise _canonical_error(exc) from exc


@router.post("/resume", dependencies=[Depends(require_operator)])
def resume():
    try:
        return {"paused": get_legal_control_plane().set_pipeline_paused(False)}
    except LegalControlPlaneError as exc:
        raise _canonical_error(exc) from exc
