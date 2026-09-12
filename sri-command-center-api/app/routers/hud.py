"""Sanitized status and governed approvals for Citadel Command on Even G2."""
from __future__ import annotations

import uuid
import hmac
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.routers.legal import require_operator
from app.services import drive
from app.services.dashboard_state import DashboardStateUnavailable, get_dashboard_store
from app.services.event_edge import EventEdgeUnavailable, get_dashboard as get_event_edge_dashboard
from app.services.hud_auth import (
    HudDevicePrincipal,
    create_pairing_code,
    exchange_pairing_code,
    require_hud_device,
)
from app.services.legal_control_plane import LegalControlPlaneError, get_legal_control_plane
from app.services.orchestrator_auth import require_orchestrator_worker
from app.services.session_briefs import list_session_briefs
from app.services.sri_projects import get_sri_projects
from app.config import settings

router = APIRouter(prefix="/api/hud", tags=["citadel-hud"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


class HudPairRequest(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class HudApprovalRequest(BaseModel):
    source: Literal["claude-code", "codex-api", "chatgpt-wrapper", "builder-os"]
    sessionId: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    detail: str = Field(min_length=1, max_length=2_000)
    action: str = Field(min_length=1, max_length=1_000)
    risk: Literal["low", "medium", "high", "critical"] = "medium"
    expiresInSeconds: int = Field(default=300, ge=30, le=3_600)


class HudDecisionRequest(BaseModel):
    decision: Literal["approve", "deny"]


class NflHudPick(BaseModel):
    rank: int = Field(ge=1, le=5)
    player: str = Field(min_length=1, max_length=100)
    team: str = Field(min_length=1, max_length=10)
    opponent: str = Field(min_length=1, max_length=10)
    category: str = Field(min_length=1, max_length=80)
    line: float | None = None
    direction: Literal["OVER", "UNDER", "NEUTRAL"] | None = None
    projection: float | None = None
    modelProbability: float | None = Field(default=None, ge=0, le=1)


class NflHudCategory(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]+$", max_length=80)
    label: str = Field(min_length=1, max_length=100)
    picks: list[NflHudPick] = Field(max_length=5)


class NflOwnerBriefSnapshot(BaseModel):
    schemaVersion: Literal["gtd-nfl-hud-v1"]
    boardId: str = Field(min_length=8, max_length=100)
    gameDate: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    briefingDate: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    publishedAt: datetime
    categories: list[NflHudCategory] = Field(min_length=1, max_length=20)
    calibrationStatus: str = Field(max_length=100)
    visibility: Literal["owner_only"] = "owner_only"


def require_hud_publisher(authorization: str | None = Header(default=None)) -> str:
    expected = settings.citadel_hud_publish_token
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not expected or not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, "Invalid HUD publisher credential")
    return "gtd-v2"


def _read_state(*, fresh: bool = False) -> dict:
    try:
        return get_dashboard_store()._load(fresh=fresh)
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


def _write_state(mutator):
    store = get_dashboard_store()
    try:
        with store._lock:
            state = store._load(fresh=True)
            result = mutator(state)
            store._save(state)
            return result
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


def _project_status(project_id: str) -> dict:
    project = next((item for item in get_sri_projects() if item.id == project_id), None)
    if not project:
        return {}
    return {
        "status": project.lane.value,
        "summary": project.notes or "No current registry update.",
        "updatedAt": project.updatedAt,
        "completionPct": project.completionPct,
        "source": "SRI governed project registry",
    }


def _gtd_status(briefs: list[dict]) -> dict:
    latest = next(
        (
            item for item in briefs
            if "gtd" in f"{item.get('project', '')} {item.get('title', '')}".lower()
        ),
        None,
    )
    if latest:
        return {
            "status": latest.get("status") or "current",
            "title": latest.get("title") or "GTD v2",
            "summary": latest.get("summary") or "No current summary.",
            "nextStart": latest.get("nextStart") or "No next action recorded.",
            "updatedAt": latest.get("updatedAt"),
            "completionPct": _project_status("gtd-v2").get("completionPct"),
            "source": "SRI Drive session summaries",
        }
    return {"title": "GTD v2", "nextStart": "No current session brief.", **_project_status("gtd-v2")}


def _event_edge_status(store) -> dict:
    fallback = _project_status("event-edge-os")
    try:
        dashboard = get_event_edge_dashboard(store)
    except EventEdgeUnavailable as exc:
        return {
            **fallback,
            "sourceStatus": "offline",
            "detail": str(exc),
            "paperOnly": True,
            "mode": "offline",
            "heartbeatStatus": "offline",
            "activeSignals": 0,
            "pendingTrades": 0,
            "settled": 0,
            "winRate": 0,
            "normalizedNet": 0,
            "generatedAt": fallback.get("updatedAt"),
        }
    return {
        **fallback,
        "sourceStatus": dashboard.sourceStatus,
        "detail": dashboard.sourceDetail,
        "paperOnly": dashboard.paperOnly,
        "mode": dashboard.automation.mode,
        "heartbeatStatus": dashboard.automation.heartbeatStatus,
        "activeSignals": sum(1 for item in dashboard.signals if item.status == "active"),
        "pendingTrades": len(dashboard.currentPaperTrades),
        "settled": dashboard.metrics.settled,
        "winRate": dashboard.metrics.winRate,
        "normalizedNet": dashboard.metrics.normalizedNet,
        "generatedAt": dashboard.generatedAt,
        "source": "Event Edge governed Drive dashboard",
    }


@router.post("/pairing-codes", dependencies=[Depends(require_operator)])
def pairing_code():
    try:
        code, expires_at = create_pairing_code()
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"code": code, "expiresAt": expires_at}


@router.post("/pair")
def pair(body: HudPairRequest):
    try:
        token, device_id, expires_at = exchange_pairing_code(body.code)
    except ValueError as exc:
        raise HTTPException(401, str(exc)) from exc
    return {"accessToken": token, "deviceId": device_id, "expiresAt": expires_at}


@router.get("/summary")
def summary(_: HudDevicePrincipal = Depends(require_hud_device)):
    state = _read_state()
    store = get_dashboard_store()
    proposals = [
        item for item in state.get("taskProposals", {}).values()
        if item.get("status") == "proposed"
    ]
    all_briefs = [brief.model_dump() for brief in list_session_briefs(limit=50)]
    briefs = all_briefs[:5]
    coding = [
        item for item in state.get("hudApprovals", {}).values()
        if item.get("status") == "pending" and item.get("expiresAt", "") > _now().isoformat()
    ]
    legal_pending = []
    try:
        for packet in get_legal_control_plane().review_packets():
            if packet.status != "awaiting_review":
                continue
            legal_pending.append({
                "packetId": packet.packetId,
                "matterId": packet.matterId,
                "riskFlags": packet.riskFlags,
                "proposedExternalAction": packet.proposedExternalAction,
                "createdAt": packet.createdAt,
            })
    except LegalControlPlaneError:
        pass
    health = drive.get_health()
    gtd = _gtd_status(all_briefs)
    nfl_snapshot = state.get("gtdNflOwnerBrief")
    if nfl_snapshot:
        gtd["nflOwnerBrief"] = nfl_snapshot
    return {
        "updatedAt": _now().isoformat(),
        "system": health,
        "counts": {
            "codingApprovals": len(coding),
            "legalApprovals": len(legal_pending),
            "builderProposals": len(proposals),
        },
        "codingApprovals": sorted(coding, key=lambda item: item["createdAt"], reverse=True),
        "legalApprovals": legal_pending,
        "builderProposals": sorted(proposals, key=lambda item: item["updatedAt"], reverse=True)[:5],
        "recentSessions": briefs,
        "gtd": gtd,
        "eventEdge": _event_edge_status(store),
    }


@router.post("/gtd/nfl-owner-brief")
def publish_nfl_owner_brief(
    body: NflOwnerBriefSnapshot,
    _: str = Depends(require_hud_publisher),
):
    """Persist the exact NFL cohort released by the owner briefing email."""
    payload = body.model_dump(mode="json")
    if any(len(category["picks"]) != 5 for category in payload["categories"]):
        raise HTTPException(422, "Every NFL category must contain exactly five picks")
    if any(
        pick["category"] != category["key"]
        for category in payload["categories"]
        for pick in category["picks"]
    ):
        raise HTTPException(422, "Pick category must match its category group")
    if any(
        [pick["rank"] for pick in category["picks"]] != [1, 2, 3, 4, 5]
        for category in payload["categories"]
    ):
        raise HTTPException(422, "NFL category ranks must be 1 through 5")

    def publish(state):
        existing = state.get("gtdNflOwnerBrief")
        if existing and existing.get("boardId") == payload["boardId"]:
            return existing
        if existing and (
            existing.get("briefingDate", ""), existing.get("gameDate", "")
        ) > (payload["briefingDate"], payload["gameDate"]):
            raise HTTPException(409, "A newer NFL owner briefing is already published")
        state["gtdNflOwnerBrief"] = payload
        return payload

    return _write_state(publish)


@router.post("/approvals", status_code=201)
def create_approval(
    body: HudApprovalRequest,
    principal: str = Depends(require_orchestrator_worker),
):
    created_at = _now()
    record = {
        "id": f"hud-approval:{uuid.uuid4().hex[:12]}",
        **body.model_dump(exclude={"expiresInSeconds"}),
        "status": "pending",
        "createdAt": created_at.isoformat(),
        "expiresAt": (created_at + timedelta(seconds=body.expiresInSeconds)).isoformat(),
        "requestedBy": principal,
        "decidedAt": None,
        "decidedBy": None,
    }

    def add(state):
        state.setdefault("hudApprovals", {})[record["id"]] = record
        return record

    return _write_state(add)


@router.get("/approvals/{approval_id}")
def approval_status(
    approval_id: str,
    _: str = Depends(require_orchestrator_worker),
):
    record = _read_state().get("hudApprovals", {}).get(approval_id)
    if not record:
        raise HTTPException(404, "Approval request not found")
    return record


@router.post("/approvals/{approval_id}/decision")
def decide_approval(
    approval_id: str,
    body: HudDecisionRequest,
    device: HudDevicePrincipal = Depends(require_hud_device),
):
    def decide(state):
        approvals = state.setdefault("hudApprovals", {})
        record = approvals.get(approval_id)
        if not record:
            raise HTTPException(404, "Approval request not found")
        if record.get("status") != "pending":
            raise HTTPException(409, "Approval request is no longer pending")
        if record.get("expiresAt", "") <= _now().isoformat():
            record["status"] = "expired"
            raise HTTPException(409, "Approval request expired")
        if body.decision == "approve" and record.get("risk") in {"high", "critical"}:
            raise HTTPException(409, "High-risk actions require desktop confirmation")
        record["status"] = "approved" if body.decision == "approve" else "denied"
        record["decidedAt"] = _now().isoformat()
        record["decidedBy"] = f"citadel-hud:{device.device_id}"
        return record

    return _write_state(decide)
