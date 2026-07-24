"""Gmail intake scanner for Legal Agent OS.

The runner reads only explicitly labelled messages. It creates an intake event,
copies the source and allowlisted attachments to Drive, then moves the message
to the processed label. It never sends email or delivers work product.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from email.utils import parseaddr
from typing import Any

from app.config import settings
from app.models import LegalIntakeRequest
from app.services.legal_intake import get_legal_store

log = logging.getLogger(__name__)
_gmail_service = None
_drive_service = None
_google_credentials = None


def _get_google_credentials():
    global _google_credentials
    if _google_credentials is None:
        from app.services.legal_google import load_legal_google_credentials

        _google_credentials = load_legal_google_credentials()
    return _google_credentials


def _get_gmail_service():
    global _gmail_service
    if _gmail_service is not None:
        return _gmail_service
    from googleapiclient.discovery import build

    _gmail_service = build(
        "gmail",
        "v1",
        credentials=_get_google_credentials(),
        cache_discovery=False,
    )
    return _gmail_service


def _get_drive_service():
    global _drive_service
    if _drive_service is not None:
        return _drive_service
    from googleapiclient.discovery import build

    _drive_service = build(
        "drive",
        "v3",
        credentials=_get_google_credentials(),
        cache_discovery=False,
    )
    return _drive_service


def _label_ids(service) -> dict[str, str]:
    response = service.users().labels().list(userId="me").execute()
    return {label["name"]: label["id"] for label in response.get("labels", [])}


def _headers(payload: dict[str, Any]) -> dict[str, str]:
    return {
        item.get("name", "").lower(): item.get("value", "")
        for item in payload.get("headers", [])
    }


def _plain_text(part: dict[str, Any]) -> str:
    mime_type = part.get("mimeType", "")
    body = part.get("body", {})
    data = body.get("data")
    if mime_type == "text/plain" and data:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    for child in part.get("parts", []) or []:
        text = _plain_text(child)
        if text:
            return text
    return ""


def scan_once() -> int:
    service = _get_gmail_service()
    labels = _label_ids(service)
    intake_id = labels.get(settings.legal_gmail_intake_label)
    processed_id = labels.get(settings.legal_gmail_processed_label)
    needs_review_id = labels.get(settings.legal_gmail_needs_review_label)
    error_id = labels.get(settings.legal_gmail_error_label)
    if not intake_id or not processed_id or not needs_review_id:
        raise RuntimeError("Required LegalOS Gmail labels are missing")
    drive_service = _get_drive_service()

    response = (
        service.users()
        .messages()
        .list(userId="me", labelIds=[intake_id], maxResults=25)
        .execute()
    )
    accepted = 0
    for item in response.get("messages", []):
        message_id = item["id"]
        try:
            message = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
            payload = message.get("payload", {})
            headers = _headers(payload)
            request = LegalIntakeRequest(
                channel="gmail",
                sourceId=message_id,
                threadId=message.get("threadId"),
                sender=parseaddr(headers.get("from", ""))[1] or None,
                subject=headers.get("subject", ""),
                body=_plain_text(payload) or "(No plain-text body; attachment review required.)",
                requestType="unknown",
            )
            if settings.legal_gmail_shadow_mode:
                log.info(
                    "Legal intake shadow observation: message=%s thread=%s",
                    message_id,
                    message.get("threadId", ""),
                )
                accepted += 1
                continue
            receipt = get_legal_store().ingest(request)
            from app.services.legal_artifacts import persist_gmail_source

            persist_gmail_source(
                drive_service,
                service,
                matter_id=receipt.matter.matterId,
                message=message,
                body_text=request.body,
            )
            service.users().messages().modify(
                userId="me",
                id=message_id,
                body={
                    "removeLabelIds": [intake_id],
                    "addLabelIds": [processed_id],
                },
            ).execute()
            accepted += 1
        except Exception as exc:
            from app.services.legal_artifacts import UnsafeAttachment

            if isinstance(exc, UnsafeAttachment):
                log.warning("Legal intake needs review for Gmail message %s: %s", message_id, exc)
                service.users().messages().modify(
                    userId="me",
                    id=message_id,
                    body={
                        "removeLabelIds": [intake_id],
                        "addLabelIds": [needs_review_id],
                    },
                ).execute()
                continue
            log.exception("Legal intake failed for Gmail message %s", message_id)
            if error_id:
                service.users().messages().modify(
                    userId="me",
                    id=message_id,
                    body={"addLabelIds": [error_id]},
                ).execute()
    return accepted


async def gmail_poll_loop() -> None:
    while True:
        try:
            accepted = await asyncio.to_thread(scan_once)
            if accepted:
                log.info("Legal Agent OS accepted %d Gmail intake message(s)", accepted)
        except Exception:
            log.exception("Legal Agent OS Gmail poll failed")
        await asyncio.sleep(settings.legal_gmail_poll_interval)
