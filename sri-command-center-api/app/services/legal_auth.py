"""Jeff-only authentication for Legal Agent OS operator controls."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import settings


@dataclass(frozen=True)
class OperatorPrincipal:
    subject: str
    email: str
    expires_at: int


def google_operator_auth_enabled() -> bool:
    return bool(
        settings.legal_google_client_id
        and len(settings.legal_session_secret) >= 32
    )


def verify_google_credential(credential: str) -> dict[str, Any]:
    if not settings.legal_google_client_id:
        raise ValueError("Google operator authentication is not configured")
    claims = id_token.verify_oauth2_token(
        credential,
        google_requests.Request(),
        settings.legal_google_client_id,
    )
    email = str(claims.get("email", "")).lower()
    domain = str(claims.get("hd", "")).lower()
    verified = claims.get("email_verified") in (True, "true")
    if not verified:
        raise ValueError("Google email is not verified")
    if domain != settings.legal_google_workspace_domain.lower():
        raise ValueError("Google Workspace domain is not authorized")
    if email != settings.legal_operator_email.lower():
        raise ValueError("Google account is not the Legal OS operator")
    if not claims.get("sub"):
        raise ValueError("Google account identifier is missing")
    return claims


def create_operator_session(claims: dict[str, Any]) -> tuple[str, OperatorPrincipal]:
    if not settings.legal_session_secret:
        raise ValueError("Legal OS session signing is not configured")
    now = int(time.time())
    expires_at = now + settings.legal_session_ttl_seconds
    payload = {
        "aud": "legal-agent-os",
        "email": str(claims["email"]).lower(),
        "exp": expires_at,
        "iat": now,
        "jti": secrets.token_urlsafe(16),
        "sub": str(claims["sub"]),
    }
    encoded = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = _sign(encoded)
    token = f"v1.{encoded}.{signature}"
    return token, OperatorPrincipal(
        subject=payload["sub"],
        email=payload["email"],
        expires_at=expires_at,
    )


def verify_operator_session(token: str) -> OperatorPrincipal:
    if not settings.legal_session_secret:
        raise ValueError("Legal OS session signing is not configured")
    try:
        version, encoded, signature = token.split(".", 2)
    except ValueError as exc:
        raise ValueError("Malformed operator session") from exc
    if version != "v1" or not hmac.compare_digest(signature, _sign(encoded)):
        raise ValueError("Invalid operator session signature")
    try:
        payload = json.loads(_b64url_decode(encoded))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed operator session payload") from exc
    if payload.get("aud") != "legal-agent-os":
        raise ValueError("Invalid operator session audience")
    if int(payload.get("exp", 0)) <= int(time.time()):
        raise ValueError("Operator session has expired")
    if str(payload.get("email", "")).lower() != settings.legal_operator_email.lower():
        raise ValueError("Operator session account is not authorized")
    if not payload.get("sub"):
        raise ValueError("Operator session subject is missing")
    return OperatorPrincipal(
        subject=str(payload["sub"]),
        email=str(payload["email"]).lower(),
        expires_at=int(payload["exp"]),
    )


def principal_expires_at(principal: OperatorPrincipal) -> str:
    return datetime.fromtimestamp(principal.expires_at, tz=timezone.utc).isoformat()


def _sign(encoded_payload: str) -> str:
    digest = hmac.new(
        settings.legal_session_secret.encode(),
        encoded_payload.encode(),
        hashlib.sha256,
    ).digest()
    return _b64url(digest)


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
