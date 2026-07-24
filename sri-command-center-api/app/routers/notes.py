"""app/routers/notes.py — Notebook endpoints"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List

from app.models import Note, CreateNoteRequest, PatchNoteRequest
from app.routers.legal import require_operator
from app.services.dashboard_state import (
    DashboardStateUnavailable,
    get_dashboard_store,
)
from app.services.legal_intake import get_legal_store
from app.services import drive

router = APIRouter(prefix="/api/notes", tags=["notes"])


@router.get(
    "",
    response_model=List[Note],
    dependencies=[Depends(require_operator)],
)
def list_notes():
    drive_notes = {n.id: n for n in drive.get_notes()}
    legal_notes = {n.id: n for n in get_legal_store().list_activity_notes()}
    try:
        dashboard_notes = {n.id: n for n in get_dashboard_store().list_notes()}
    except DashboardStateUnavailable:
        dashboard_notes = {}
    merged = {**drive_notes, **dashboard_notes, **legal_notes}
    # Return without body (per contract)
    return [
        n.model_copy(update={"body": None})
        for n in sorted(merged.values(), key=lambda note: note.updatedAt, reverse=True)
    ]


@router.get(
    "/{note_id}",
    response_model=Note,
    dependencies=[Depends(require_operator)],
)
def get_note(note_id: str):
    try:
        dashboard_note = get_dashboard_store().get_note(note_id)
    except DashboardStateUnavailable:
        dashboard_note = None
    if dashboard_note:
        return dashboard_note
    legal_note = get_legal_store().get_activity_note(note_id)
    if legal_note:
        return legal_note
    note = drive.get_note(note_id)
    if not note:
        raise HTTPException(404, f"Note '{note_id}' not found")
    return note


@router.post(
    "",
    response_model=Note,
    status_code=201,
    dependencies=[Depends(require_operator)],
)
def create_note(body: CreateNoteRequest):
    try:
        return get_dashboard_store().create_note(
            title=body.title,
            tag=body.tag,
            body=body.body,
        )
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.patch(
    "/{note_id}",
    response_model=Note,
    dependencies=[Depends(require_operator)],
)
def patch_note(note_id: str, body: PatchNoteRequest):
    if get_legal_store().get_activity_note(note_id):
        raise HTTPException(409, "Legal OS activity notes are read-only")
    try:
        note = get_dashboard_store().get_note(note_id)
    except DashboardStateUnavailable:
        note = None
    note = note or drive.get_note(note_id)
    if not note:
        raise HTTPException(404, f"Note '{note_id}' not found")

    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        return get_dashboard_store().upsert_note(note, patch)
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.delete(
    "/{note_id}",
    status_code=204,
    dependencies=[Depends(require_operator)],
)
def delete_note(note_id: str):
    if get_legal_store().get_activity_note(note_id):
        raise HTTPException(409, "Legal OS activity notes are read-only")
    try:
        if not get_dashboard_store().delete_note(note_id):
            raise HTTPException(
                409,
                "Only operator-created dashboard notes can be deleted here",
            )
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
