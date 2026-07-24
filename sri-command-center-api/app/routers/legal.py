"""Sanitized dashboard reads and protected Legal Agent OS controls."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException

from app.config import settings
from app.models import (
    LegalDashboardState,
    LegalIntakeReceipt,
    LegalIntakeRequest,
    LegalMatterSummary,
)
from app.services.legal_intake import get_legal_store

router = APIRouter(prefix="/api/legal", tags=["legal"])


def require_operator(authorization: str | None = Header(default=None)) -> None:
    """Require a server-side operator token for every mutation.

    The browser must not embed this secret. In production an authenticated
    reverse proxy or server-side session supplies the Authorization header.
    """
    if not settings.legal_api_token:
        raise HTTPException(
            status_code=503,
            detail="Legal OS operator authentication is not configured",
        )
    expected = f"Bearer {settings.legal_api_token}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Operator authentication required")


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
