"""app/routers/notes.py — Notebook endpoints"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from typing import List

from app.models import Note, CreateNoteRequest, PatchNoteRequest
from app.services import drive

router = APIRouter(prefix="/api/notes", tags=["notes"])

# In-memory note store — Drive is source of truth; new notes written back via signals
_local_notes: dict = {}  # note_id → Note


@router.get("", response_model=List[Note])
def list_notes():
    drive_notes = {n.id: n for n in drive.get_notes()}
    merged = {**drive_notes, **_local_notes}
    # Return without body (per contract)
    return [n.model_copy(update={"body": None}) for n in merged.values()]


@router.get("/{note_id}", response_model=Note)
def get_note(note_id: str):
    if note_id in _local_notes:
        return _local_notes[note_id]
    note = drive.get_note(note_id)
    if not note:
        raise HTTPException(404, f"Note '{note_id}' not found")
    return note


@router.post("", response_model=Note, status_code=201)
def create_note(body: CreateNoteRequest):
    note = Note(
        id=f"n:{uuid.uuid4().hex[:8]}",
        title=body.title,
        tag=body.tag,
        body=body.body,
        updatedAt=datetime.now(timezone.utc).isoformat(),
    )
    _local_notes[note.id] = note
    drive.write_signal("prod", "note-created", note.model_dump())
    return note


@router.patch("/{note_id}", response_model=Note)
def patch_note(note_id: str, body: PatchNoteRequest):
    # Try local first, then Drive
    note = _local_notes.get(note_id) or drive.get_note(note_id)
    if not note:
        raise HTTPException(404, f"Note '{note_id}' not found")

    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    patch["updatedAt"] = datetime.now(timezone.utc).isoformat()
    updated = note.model_copy(update=patch)
    _local_notes[note_id] = updated
    drive.write_signal("prod", "note-updated", updated.model_dump())
    return updated
