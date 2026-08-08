"""Marketing OS launch-console endpoints."""
from fastapi import APIRouter, Depends, HTTPException

from app.models import MarketingApprovalRequest, MarketingDashboard
from app.routers.legal import require_operator
from app.services.dashboard_state import DashboardStateUnavailable, get_dashboard_store
from app.services.marketing import approval_ids, get_dashboard

router = APIRouter(prefix="/api/marketing", tags=["marketing"])


@router.get("/dashboard", response_model=MarketingDashboard, dependencies=[Depends(require_operator)])
def marketing_dashboard():
    try:
        return get_dashboard(get_dashboard_store())
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/approvals/{approval_id}", response_model=MarketingDashboard, dependencies=[Depends(require_operator)])
def set_approval(approval_id: str, body: MarketingApprovalRequest):
    if approval_id not in approval_ids():
        raise HTTPException(404, "Marketing approval item not found")
    store = get_dashboard_store()
    try:
        store.set_marketing_approval(
            approval_id,
            approved=body.approved,
            approved_by="Jeffery Williams",
        )
        return get_dashboard(store)
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
