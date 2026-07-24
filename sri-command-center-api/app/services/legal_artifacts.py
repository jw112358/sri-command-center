"""Restricted Google Drive persistence for Legal Agent OS source material."""
from __future__ import annotations

import io
import json
import re
from datetime import datetime, timezone
from typing import Any

from googleapiclient.http import MediaIoBaseUpload

from app.config import settings


ALLOWED_ATTACHMENT_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-outlook",
    "message/rfc822",
    "text/plain",
    "text/csv",
    "image/jpeg",
    "image/png",
    "image/tiff",
}


class UnsafeAttachment(ValueError):
    pass


def _escape_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._() -]+", "_", value).strip(" .")
    return cleaned[:180] or "attachment"


def _find_folder(service, parent_id: str, name: str) -> str | None:
    query = (
        f"'{_escape_query(parent_id)}' in parents "
        "and mimeType='application/vnd.google-apps.folder' "
        f"and name='{_escape_query(name)}' and trashed=false"
    )
    response = (
        service.files()
        .list(q=query, fields="files(id)", pageSize=1)
        .execute()
    )
    files = response.get("files", [])
    return files[0]["id"] if files else None


def _ensure_folder(service, parent_id: str, name: str) -> str:
    existing = _find_folder(service, parent_id, name)
    if existing:
        return existing
    created = (
        service.files()
        .create(
            body={
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            },
            fields="id",
        )
        .execute()
    )
    return created["id"]


def _upload_bytes(
    service,
    parent_id: str,
    filename: str,
    content: bytes,
    mime_type: str,
) -> str:
    media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type, resumable=False)
    created = (
        service.files()
        .create(
            body={"name": _safe_filename(filename), "parents": [parent_id]},
            media_body=media,
            fields="id",
        )
        .execute()
    )
    return created["id"]


def persist_gmail_source(
    drive_service,
    gmail_service,
    *,
    matter_id: str,
    message: dict[str, Any],
    body_text: str,
) -> dict[str, Any]:
    """Copy the source email and allowlisted attachments to the matter folder."""
    if not settings.legal_drive_matters_folder_id:
        raise RuntimeError("LEGAL_DRIVE_MATTERS_FOLDER_ID is required for live intake")

    matter_folder = _ensure_folder(
        drive_service,
        settings.legal_drive_matters_folder_id,
        matter_id,
    )
    intake_folder = _ensure_folder(drive_service, matter_folder, "00 Intake")
    source_folder = _ensure_folder(drive_service, matter_folder, "01 Source")
    message_id = message["id"]
    recorded_at = datetime.now(timezone.utc).isoformat()
    record = {
        "matter_id": matter_id,
        "gmail_message_id": message_id,
        "gmail_thread_id": message.get("threadId"),
        "internal_date": message.get("internalDate"),
        "recorded_at": recorded_at,
        "body_text": body_text,
    }
    email_file_id = _upload_bytes(
        drive_service,
        intake_folder,
        f"gmail-message-{message_id}.json",
        json.dumps(record, indent=2, ensure_ascii=False).encode("utf-8"),
        "application/json",
    )

    attachments = []
    for part in _walk_parts(message.get("payload", {})):
        filename = part.get("filename")
        attachment_id = part.get("body", {}).get("attachmentId")
        if not filename or not attachment_id:
            continue
        mime_type = part.get("mimeType") or "application/octet-stream"
        if mime_type not in ALLOWED_ATTACHMENT_MIME_TYPES:
            raise UnsafeAttachment(
                f"Unsupported attachment type {mime_type!r} for {_safe_filename(filename)!r}"
            )
        response = (
            gmail_service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute()
        )
        import base64

        content = base64.urlsafe_b64decode(response.get("data", "") + "==")
        if len(content) > settings.legal_attachment_max_bytes:
            raise UnsafeAttachment(
                f"Attachment {_safe_filename(filename)!r} exceeds the size limit"
            )
        drive_file_id = _upload_bytes(
            drive_service,
            source_folder,
            filename,
            content,
            mime_type,
        )
        attachments.append(
            {
                "filename": _safe_filename(filename),
                "mime_type": mime_type,
                "drive_file_id": drive_file_id,
            }
        )

    manifest = {
        "matter_id": matter_id,
        "email_file_id": email_file_id,
        "attachments": attachments,
        "recorded_at": recorded_at,
    }
    manifest_id = _upload_bytes(
        drive_service,
        intake_folder,
        f"intake-manifest-{message_id}.json",
        json.dumps(manifest, indent=2).encode("utf-8"),
        "application/json",
    )
    return {
        "matter_folder_id": matter_folder,
        "email_file_id": email_file_id,
        "manifest_id": manifest_id,
        "attachment_count": len(attachments),
    }


def _walk_parts(part: dict[str, Any]):
    yield part
    for child in part.get("parts", []) or []:
        yield from _walk_parts(child)
