"""Read-only, concise index of canonical Platform session summaries."""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import frontmatter
from googleapiclient.http import MediaInMemoryUpload

from app.config import settings
from app.models import CreateSessionSummaryRequest, SessionBrief
from app.services import drive

_cache: list[SessionBrief] = []
_cache_at = 0.0
_lock = threading.RLock()
_CACHE_FILE = Path(__file__).parent.parent.parent / "data" / "session-briefs-cache.json"


def list_session_briefs(limit: int = 50) -> list[SessionBrief]:
    global _cache, _cache_at
    safe_limit = max(1, min(limit, 100))
    with _lock:
        if _cache and time.monotonic() - _cache_at < 60:
            return _cache[:safe_limit]
        service = drive.get_drive_service()
        folder_id = settings.dashboard_session_summaries_folder_id
        if not service or not folder_id:
            return _load_bundled_cache()[:safe_limit]
        briefs: list[SessionBrief] = []
        try:
            result = service.files().list(
                q=(
                    f"'{folder_id}' in parents and trashed = false "
                    "and mimeType != 'application/vnd.google-apps.folder'"
                ),
                fields="files(id,name,createdTime,modifiedTime,webViewLink,mimeType)",
                orderBy="modifiedTime desc",
                pageSize=safe_limit,
            ).execute()
            for item in result.get("files", []):
                if not item.get("name", "").lower().endswith((".md", ".markdown", ".txt")):
                    continue
                try:
                    content = service.files().get_media(fileId=item["id"]).execute()
                    if isinstance(content, bytes):
                        content = content.decode("utf-8")
                    briefs.append(parse_session_summary(item, content))
                except Exception:
                    continue
        except Exception:
            briefs = []
        if not briefs:
            briefs = _load_bundled_cache()
        _cache = briefs
        _cache_at = time.monotonic()
        return briefs[:safe_limit]


def create_session_summary(body: CreateSessionSummaryRequest) -> SessionBrief:
    """File one material, cross-surface handoff in the canonical Drive folder."""
    if not body.materialChange:
        raise ValueError("Only sessions that materially change a project are filed")
    service = drive.get_drive_service()
    folder_id = settings.dashboard_session_summaries_folder_id
    if (
        not service
        or not folder_id
        or not settings.dashboard_drive_write_enabled
    ):
        raise RuntimeError("Session summary Drive writes are not configured")

    now = datetime.now(timezone.utc)
    session_id = f"platform-session-{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
    safe_project = re.sub(r"[^a-z0-9]+", "-", body.project.lower()).strip("-")
    filename = f"{session_id}_{safe_project or 'project'}.md"
    raw = _render_session_summary(session_id, now, body)
    media = MediaInMemoryUpload(
        raw.encode("utf-8"),
        mimetype="text/markdown",
        resumable=False,
    )
    created = service.files().create(
        body={
            "name": filename,
            "parents": [folder_id],
            "mimeType": "text/markdown",
        },
        media_body=media,
        fields="id,name,createdTime,modifiedTime,webViewLink,mimeType",
    ).execute()
    created.setdefault("createdTime", now.isoformat())
    created.setdefault("modifiedTime", now.isoformat())
    created.setdefault(
        "webViewLink",
        f"https://drive.google.com/file/d/{created['id']}/view",
    )
    invalidate_session_brief_cache()
    return parse_session_summary(created, raw)


def invalidate_session_brief_cache() -> None:
    global _cache, _cache_at
    with _lock:
        _cache = []
        _cache_at = 0.0


def _render_session_summary(
    session_id: str,
    now: datetime,
    body: CreateSessionSummaryRequest,
) -> str:
    metadata = {
        "session_id": session_id,
        "date": now.date().isoformat(),
        "project": body.project,
        "surface": body.surface,
        "status": body.status,
        "material_change": True,
    }
    if body.taskId:
        metadata["task_id"] = body.taskId
    front_matter = "\n".join(
        f"{key}: {json.dumps(value)}" for key, value in metadata.items()
    )
    evidence = "\n".join(f"- {url}" for url in body.evidenceUrls)
    evidence_section = f"\n\n## Verification Evidence\n\n{evidence}" if evidence else ""
    return (
        f"---\n{front_matter}\n---\n"
        f"# {body.title.strip()}\n\n"
        f"## Material Outcome\n\n{body.summary.strip()}\n\n"
        f"## Current State\n\n{body.currentState.strip()}"
        f"{evidence_section}\n\n"
        f"## Begin Next Session Here\n\n{body.nextStart.strip()}\n"
    )


def parse_session_summary(file_meta: dict[str, Any], raw: str) -> SessionBrief:
    post = frontmatter.loads(raw)
    metadata = dict(post.metadata)
    body = post.content
    heading = _first_heading(body) or file_meta.get("name", "Session summary")
    session_id = str(
        metadata.get("session_id")
        or metadata.get("session")
        or file_meta.get("id")
    )
    date = str(metadata.get("date") or "") or _date_part(
        file_meta.get("modifiedTime") or file_meta.get("createdTime") or ""
    )
    project = str(metadata.get("project") or _infer_project(heading))
    surface = str(
        metadata.get("surface")
        or metadata.get("source_surface")
        or metadata.get("owner_os")
        or "SRI Agent Platform"
    )
    summary = _section_excerpt(
        body,
        ["Result", "Completed", "Outcome", "Summary", "Work Completed"],
        max_words=90,
    )
    if not summary:
        summary = _opening_excerpt(body, max_words=90)
    current_state = _section_excerpt(
        body,
        ["Current Platform State", "Current State", "Current Evidence", "Status"],
        max_words=65,
    )
    next_start = _section_excerpt(
        body,
        [
            "Begin Next Session Here",
            "Resume Instruction",
            "Next Session Opening List",
            "Next Pickup",
            "Next Session",
            "Next Steps",
            "Next Step",
            "Follow-up",
        ],
        max_words=95,
    )
    if not next_start:
        next_start = (
            "Open the full source summary, confirm the latest evidence, and begin "
            "with its first unfinished action."
        )
    modified = (
        file_meta.get("modifiedTime")
        or file_meta.get("createdTime")
        or datetime.now(timezone.utc).isoformat()
    )
    source_url = (
        file_meta.get("webViewLink")
        or f"https://drive.google.com/file/d/{file_meta['id']}/view"
    )
    return SessionBrief(
        id=f"brief:{file_meta['id']}",
        sessionId=session_id,
        date=date,
        title=_clean_text(heading),
        project=project,
        surface=surface,
        status=str(metadata.get("status") or "complete"),
        summary=summary,
        currentState=current_state or None,
        nextStart=next_start,
        sourceUrl=source_url,
        updatedAt=modified,
        taskId=str(metadata.get("task_id")) if metadata.get("task_id") else None,
    )


def _first_heading(body: str) -> str:
    match = re.search(r"^#\s+(.+)$", body, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _section_excerpt(body: str, headings: list[str], *, max_words: int) -> str:
    for heading in headings:
        pattern = re.compile(
            rf"^##+\s+{re.escape(heading)}\s*$\n(.*?)(?=^##+\s+|\Z)",
            flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
        )
        match = pattern.search(body)
        if match:
            cleaned = _clean_section(match.group(1))
            if cleaned:
                return _clip_words(cleaned, max_words)
    return ""


def _opening_excerpt(body: str, *, max_words: int) -> str:
    without_heading = re.sub(r"^#\s+.+$", "", body, count=1, flags=re.MULTILINE)
    without_sections = re.sub(r"^##+\s+.+$", "", without_heading, flags=re.MULTILINE)
    return _clip_words(_clean_section(without_sections), max_words)


def _clean_section(value: str) -> str:
    value = re.sub(r"```.*?```", " ", value, flags=re.DOTALL)
    value = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"^\s*[-*]\s+", "• ", value, flags=re.MULTILINE)
    value = re.sub(r"^\s*\d+\.\s+", "• ", value, flags=re.MULTILINE)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"[*_>#|]", " ", value)
    value = re.sub(r"\s*•\s*", " · ", value)
    return _clean_text(value).strip(" ·")


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _clip_words(value: str, max_words: int) -> str:
    words = value.split()
    if len(words) <= max_words:
        return value
    return " ".join(words[:max_words]).rstrip(".,;:") + "…"


def _date_part(value: str) -> str:
    return value[:10] if len(value) >= 10 else value


def _infer_project(title: str) -> str:
    lowered = title.lower()
    known = [
        ("master builder", "Master Builder"),
        ("legal agent", "Legal Agent OS"),
        ("command center", "SRI Command Center"),
        ("event edge", "Event Edge OS"),
        ("gtd-v2", "GTD-v2"),
        ("commerce scout", "Commerce Scout OS"),
        ("marketing", "Marketing OS"),
        ("builder os", "Builder OS"),
        ("jk author", "JK Author OS"),
    ]
    for needle, label in known:
        if needle in lowered:
            return label
    return "Cross-platform"


def _load_bundled_cache() -> list[SessionBrief]:
    try:
        data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        return [SessionBrief(**item) for item in data.get("briefs", [])]
    except Exception:
        return []
