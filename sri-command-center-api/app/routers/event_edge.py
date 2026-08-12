"""Event Edge OS paper signals and manual external-trade records."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.models import EventEdgeDashboard, EventEdgeManualTrade, EventEdgeManualTradeRequest
from app.routers.legal import require_operator
from app.services.dashboard_state import DashboardStateUnavailable, get_dashboard_store
from app.services.event_edge import EventEdgeUnavailable, get_dashboard


router = APIRouter(prefix="/api/event-edge", tags=["event-edge"])


@router.get(
    "/dashboard",
    response_model=EventEdgeDashboard,
    dependencies=[Depends(require_operator)],
)
def event_edge_dashboard():
    try:
        return get_dashboard(get_dashboard_store())
    except (DashboardStateUnavailable, EventEdgeUnavailable) as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post(
    "/manual-trades",
    response_model=EventEdgeManualTrade,
    dependencies=[Depends(require_operator)],
)
def record_manual_trade(body: EventEdgeManualTradeRequest):
    entered_at = body.enteredAt or datetime.now(timezone.utc).isoformat()
    try:
        parsed = datetime.fromisoformat(entered_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(422, "enteredAt must be an ISO-8601 timestamp with timezone") from exc
    try:
        return get_dashboard_store().create_event_edge_manual_trade(
            {
                "signalId": body.signalId,
                "family": body.family.strip(),
                "venue": body.venue.strip(),
                "marketTicker": body.marketTicker.strip(),
                "side": body.side.strip().upper(),
                "entryPrice": body.entryPrice,
                "quantity": body.quantity,
                "cashAmount": body.cashAmount,
                "notes": body.notes.strip(),
                "status": "recorded",
                "enteredAt": entered_at,
            }
        )
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
