"""app/routers/events.py — System events + health"""
from fastapi import APIRouter, Depends, Query
from typing import List
from app.config import settings
from app.models import DashboardCapabilities, SystemEvent, SystemHealth
from app.routers.legal import require_operator
from app.services import drive
from app.services.orchestrator_presence import presence_status

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
    state_access = drive.probe_folder_access(settings.dashboard_state_parent_id)
    summary_access = drive.probe_folder_access(
        settings.dashboard_session_summaries_folder_id
    )
    presence = presence_status()
    write_ready = bool(
        drive_connected
        and state_access["write"]
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
            write_ready
            and settings.orchestrator_runner_token
            and presence["connected"]
        ),
        sessionSummaryWriteEnabled=bool(
            settings.dashboard_drive_write_enabled and summary_access["write"]
        ),
        maxConcurrentTasks=settings.orchestrator_max_concurrent_tasks,
        dashboardStateReadVerified=state_access["read"],
        dashboardStateWriteVerified=bool(
            settings.dashboard_drive_write_enabled and state_access["write"]
        ),
        sessionSummaryReadVerified=summary_access["read"],
        sessionSummaryWriteVerified=bool(
            settings.dashboard_drive_write_enabled and summary_access["write"]
        ),
        orchestratorConnected=presence["connected"],
        orchestratorLastSeenAt=presence["last_seen_at"],
        orchestratorWorkers=presence["workers"],
    )
