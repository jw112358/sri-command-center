"""Authentication boundary for trusted cross-surface orchestrator workers."""
from __future__ import annotations

import secrets

from fastapi import Header, HTTPException

from app.config import settings
from app.services.legal_auth import authenticate_operator_token


def require_orchestrator_worker(
    authorization: str | None = Header(default=None),
) -> str:
    if not settings.orchestrator_runner_token:
        raise HTTPException(503, "Orchestrator runner authentication is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Orchestrator worker authentication required")
    token = authorization.removeprefix("Bearer ")
    if not secrets.compare_digest(token, settings.orchestrator_runner_token):
        raise HTTPException(401, "Orchestrator worker authentication required")
    return "orchestrator-worker"


def require_operator_or_worker(
    authorization: str | None = Header(default=None),
) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authentication required")
    token = authorization.removeprefix("Bearer ")
    if settings.orchestrator_runner_token and secrets.compare_digest(
        token,
        settings.orchestrator_runner_token,
    ):
        return "orchestrator-worker"
    try:
        principal = authenticate_operator_token(token)
        return principal.email
    except ValueError as exc:
        raise HTTPException(401, "Authentication required") from exc
