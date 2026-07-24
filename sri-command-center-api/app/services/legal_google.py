"""Google user credentials for the Legal Agent OS background runner."""
from __future__ import annotations

import json

import google.auth
from google.oauth2.credentials import Credentials

from app.config import settings


LEGAL_GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive.file",
]


def load_legal_google_credentials():
    """Load an offline user grant from a secret environment value.

    Application Default Credentials remain available only through an explicit
    local-development opt-in. This prevents a production runner from silently
    using the wrong Google identity.
    """
    if settings.legal_google_user_token_json:
        try:
            token_info = json.loads(settings.legal_google_user_token_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError("LEGAL_GOOGLE_USER_TOKEN_JSON is invalid JSON") from exc
        credentials = Credentials.from_authorized_user_info(
            token_info,
            scopes=LEGAL_GOOGLE_SCOPES,
        )
        if not credentials.refresh_token:
            raise RuntimeError("Legal Google user grant has no refresh token")
        return credentials
    if settings.legal_google_allow_adc:
        credentials, _ = google.auth.default(scopes=LEGAL_GOOGLE_SCOPES)
        return credentials
    raise RuntimeError("Legal Google user credentials are not configured")


def legal_runner_config_errors() -> list[str]:
    errors: list[str] = []
    if not settings.legal_state_persistent:
        errors.append("persistent state is not enabled")
    if not settings.legal_drive_matters_folder_id:
        errors.append("the Drive matters folder is not configured")
    if not settings.legal_google_user_token_json and not settings.legal_google_allow_adc:
        errors.append("Google user credentials are not configured")
    return errors
