"""Sanitized dashboard reads and protected Legal Agent OS controls."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.config import settings
from app.models import (
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
    create_operator_session,
    google_operator_auth_enabled,
    principal_expires_at,
    verify_google_credential,
    verify_operator_session,
)
from app.services.legal_intake import get_legal_store

router = APIRouter(prefix="/api/legal", tags=["legal"])


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
    if settings.legal_api_token and secrets.compare_digest(
        token, settings.legal_api_token
    ):
        return OperatorPrincipal(
            subject="server-token",
            email=settings.legal_operator_email.lower(),
            expires_at=2**31 - 1,
        )
    if google_operator_auth_enabled():
        try:
            return verify_operator_session(token)
        except ValueError:
            pass
    raise HTTPException(status_code=401, detail="Operator authentication required")


@router.get("/auth/config", response_model=LegalAuthConfig)
def auth_config():
    return LegalAuthConfig(
        enabled=google_operator_auth_enabled(),
        clientId=settings.legal_google_client_id if google_operator_auth_enabled() else "",
        sessionTtlSeconds=settings.legal_session_ttl_seconds,
        manualIntakeEnabled=(
            settings.legal_manual_intake_enabled
            and settings.legal_state_persistent
        ),
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


@router.get("/dashboard", response_model=LegalDashboardState)
def dashboard():
    """Public-safe feed: generated IDs, states, counts, and connector health only."""
    return get_legal_store().dashboard()


@router.get("/matters", response_model=list[LegalMatterSummary])
def matters():
    return get_legal_store().list_matters()


@router.post(
    "/intake",
    response_model=LegalIntakeReceipt,
    status_code=202,
    dependencies=[Depends(require_operator)],
)
def manual_intake(body: LegalIntakeRequest):
    if not settings.legal_manual_intake_enabled or not settings.legal_state_persistent:
        raise HTTPException(
            503,
            "Manual intake remains staged until persistent state is enabled",
        )
    if body.channel != "master_builder":
        raise HTTPException(400, "Manual intake channel must be master_builder")
    return get_legal_store().ingest(body)


@router.post("/pause", dependencies=[Depends(require_operator)])
def pause():
    get_legal_store().set_paused(True)
    return {"paused": True}


@router.post("/resume", dependencies=[Depends(require_operator)])
def resume():
    get_legal_store().set_paused(False)
    return {"paused": False}
