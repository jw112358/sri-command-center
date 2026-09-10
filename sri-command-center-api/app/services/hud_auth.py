"""Short-lived pairing codes and signed Citadel HUD device credentials."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Header, HTTPException

from app.config import settings


@dataclass(frozen=True)
class HudDevicePrincipal:
    device_id: str
    expires_at: int


_pairing_codes: dict[str, tuple[int, str]] = {}
_pairing_lock = threading.RLock()


def hud_auth_enabled() -> bool:
    return len(settings.citadel_hud_signing_secret) >= 32


def create_pairing_code() -> tuple[str, str]:
    if not hud_auth_enabled():
        raise ValueError("Citadel HUD authentication is not configured")
    code = f"{secrets.randbelow(100_000_000):08d}"
    expires_at = int(time.time()) + settings.citadel_hud_pairing_ttl_seconds
    with _pairing_lock:
        _purge_expired_codes()
        _pairing_codes[_hash_code(code)] = (expires_at, secrets.token_urlsafe(12))
    return code, _iso(expires_at)


def exchange_pairing_code(code: str) -> tuple[str, str, str]:
    if not hud_auth_enabled():
        raise ValueError("Citadel HUD authentication is not configured")
    normalized = "".join(character for character in code if character.isdigit())
    with _pairing_lock:
        _purge_expired_codes()
        record = _pairing_codes.pop(_hash_code(normalized), None)
    if not record:
        raise ValueError("Pairing code is invalid or expired")
    _, device_id = record
    now = int(time.time())
    expires_at = now + settings.citadel_hud_device_ttl_seconds
    payload = {
        "aud": "citadel-command-hud",
        "device_id": device_id,
        "exp": expires_at,
        "iat": now,
    }
    encoded = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = _sign(encoded)
    return f"hud1.{encoded}.{signature}", device_id, _iso(expires_at)


def require_hud_device(
    authorization: str | None = Header(default=None),
) -> HudDevicePrincipal:
    if not hud_auth_enabled():
        raise HTTPException(503, "Citadel HUD authentication is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Citadel HUD authentication required")
    try:
        return verify_device_token(authorization.removeprefix("Bearer "))
    except ValueError as exc:
        raise HTTPException(401, "Citadel HUD authentication required") from exc


def verify_device_token(token: str) -> HudDevicePrincipal:
    try:
        version, encoded, signature = token.split(".", 2)
    except ValueError as exc:
        raise ValueError("Malformed HUD token") from exc
    if version != "hud1" or not hmac.compare_digest(signature, _sign(encoded)):
        raise ValueError("Invalid HUD token")
    try:
        payload = json.loads(_b64url_decode(encoded))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed HUD token payload") from exc
    if payload.get("aud") != "citadel-command-hud":
        raise ValueError("Invalid HUD token audience")
    expires_at = int(payload.get("exp", 0))
    if expires_at <= int(time.time()):
        raise ValueError("HUD token expired")
    device_id = str(payload.get("device_id", ""))
    if not device_id:
        raise ValueError("HUD token device missing")
    return HudDevicePrincipal(device_id=device_id, expires_at=expires_at)


def _purge_expired_codes() -> None:
    now = int(time.time())
    for digest, (expires_at, _) in list(_pairing_codes.items()):
        if expires_at <= now:
            _pairing_codes.pop(digest, None)


def _hash_code(code: str) -> str:
    return hmac.new(
        settings.citadel_hud_signing_secret.encode(),
        code.encode(),
        hashlib.sha256,
    ).hexdigest()


def _sign(encoded: str) -> str:
    digest = hmac.new(
        settings.citadel_hud_signing_secret.encode(),
        encoded.encode(),
        hashlib.sha256,
    ).digest()
    return _b64url(digest)


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _iso(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
