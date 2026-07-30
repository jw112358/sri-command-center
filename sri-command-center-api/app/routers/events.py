"""app/routers/events.py — System events + health"""
from fastapi import APIRouter, Depends, Query
from typing import List
from app.config import settings
from app.models import DashboardCapabilities, SystemEvent, SystemHealth
from app.routers.legal import require_operator
from app.services import drive

router = APIRouter(tags=["system"])


@router.get(
    "/api/events",
    response_model=List[SystemEvent],
    dependencies=[Depends(require_operator)],
)
def list_events(limit: int = Query(20, ge=1, le=100)):
    return drive.get_events()[:limit]


@router.get("/api/health", response_model=SystemHealth)
def health():
    h = drive.get_health()
    return SystemHealth(**h)


@router.get("/api/capabilities", response_model=DashboardCapabilities)
def capabilities():
    drive_connected = bool(drive.get_drive_service())
    write_ready = bool(
        drive_connected
        and settings.drive_enabled
        and settings.dashboard_drive_write_enabled
    )
    return DashboardCapabilities(
        operatorAuthConfigured=bool(
            settings.legal_google_client_id and settings.legal_session_secret
        ),
        driveReadConnected=drive_connected,
        dashboardPersistenceEnabled=write_ready,
        commandDispatchEnabled=bool(
            write_ready and settings.command_dispatch_enabled
        ),
        taskOrchestrationEnabled=bool(
            write_ready and settings.orchestrator_runner_token
        ),
        sessionSummaryWriteEnabled=bool(
            write_ready and settings.dashboard_session_summaries_folder_id
        ),
        maxConcurrentTasks=settings.orchestrator_max_concurrent_tasks,
    )
