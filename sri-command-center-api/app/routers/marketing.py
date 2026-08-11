"""Marketing OS launch-console endpoints."""
from fastapi import APIRouter, Depends, HTTPException

from app.models import (
    MarketingApprovalRequest,
    MarketingDashboard,
    MarketingMeasurement,
    MarketingMeasurementRequest,
    MarketingPublication,
    MarketingRoute,
    MarketingScheduleRequest,
)
from app.routers.legal import require_operator
from app.services.dashboard_state import DashboardStateUnavailable, get_dashboard_store
from app.services.marketing import approval_ids, approval_map, get_dashboard
from app.services.marketing_automation import MarketingAutomationService
from app.services.orchestrator_auth import require_operator_or_worker

router = APIRouter(prefix="/api/marketing", tags=["marketing"])


@router.get("/dashboard", response_model=MarketingDashboard, dependencies=[Depends(require_operator)])
def marketing_dashboard():
    try:
        return get_dashboard(get_dashboard_store())
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post(
    "/routes/{platform}/verify",
    response_model=MarketingRoute,
    dependencies=[Depends(require_operator)],
)
def verify_route(platform: str):
    try:
        return MarketingAutomationService(get_dashboard_store()).verify_route(platform)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post(
    "/approvals/{approval_id}/schedule",
    response_model=MarketingPublication,
    dependencies=[Depends(require_operator)],
)
def schedule_approval(approval_id: str, body: MarketingScheduleRequest):
    store = get_dashboard_store()
    approval = approval_map(store).get(approval_id)
    if not approval:
        raise HTTPException(404, "Marketing approval item not found")
    try:
        return MarketingAutomationService(store).schedule(
            packet_id="gtd-v2-daily-briefing-launch-001",
            approval=approval,
            request=body,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post(
    "/worker/run",
    response_model=list[MarketingPublication],
    dependencies=[Depends(require_operator_or_worker)],
)
def run_worker_once():
    store = get_dashboard_store()
    try:
        return MarketingAutomationService(store).run_once(approval_map(store))
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get(
    "/agent/work",
    dependencies=[Depends(require_operator_or_worker)],
)
def agent_work():
    store = get_dashboard_store()
    service = MarketingAutomationService(store)
    service.refresh_due_measurements()
    publications = list(store.list_marketing_publications().values())
    measurements = list(store.list_marketing_measurements().values())
    return {
        "publishingAgent": [
            item
            for item in publications
            if item.get("status") in {"queued", "submitting", "scheduled"}
        ],
        "analyticsAgent": [
            item for item in measurements if item.get("status") == "due"
        ],
        "learningAgent": list(store.list_marketing_learning().values()),
    }


@router.post(
    "/publications/{publication_id}/measurements",
    response_model=MarketingMeasurement,
    dependencies=[Depends(require_operator_or_worker)],
)
def record_measurement(publication_id: str, body: MarketingMeasurementRequest):
    try:
        return MarketingAutomationService(get_dashboard_store()).record_measurement(
            publication_id, body
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/approvals/{approval_id}", response_model=MarketingDashboard, dependencies=[Depends(require_operator)])
def set_approval(approval_id: str, body: MarketingApprovalRequest):
    if approval_id not in approval_ids():
        raise HTTPException(404, "Marketing approval item not found")
    store = get_dashboard_store()
    try:
        if not body.approved:
            MarketingAutomationService(store).revoke_approval(approval_id)
        store.set_marketing_approval(
            approval_id,
            approved=body.approved,
            approved_by="Jeffery Williams",
        )
        return get_dashboard(store)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
