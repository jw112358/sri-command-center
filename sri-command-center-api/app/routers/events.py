"""app/routers/events.py — System events + health"""
from fastapi import APIRouter, Query
from typing import List
from app.models import SystemEvent, SystemHealth
from app.services import drive

router = APIRouter(tags=["system"])


@router.get("/api/events", response_model=List[SystemEvent])
def list_events(limit: int = Query(20, ge=1, le=100)):
    return drive.get_events()[:limit]


@router.get("/api/health", response_model=SystemHealth)
def health():
    h = drive.get_health()
    return SystemHealth(**h)
