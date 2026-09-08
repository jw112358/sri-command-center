"""Agent-proposed task ingress with an operator promotion gate."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.models import Task, TaskStatus
from app.routers.legal import require_operator
from app.services.dashboard_state import DashboardStateUnavailable, get_dashboard_store
from app.services.orchestrator_auth import require_orchestrator_worker

router = APIRouter(prefix="/api/tasks/proposed", tags=["task-proposals"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskProposalRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2_000)
    project: str = Field(default="Master Builder", min_length=1, max_length=200)
    preferredSurface: Optional[str] = Field(default=None, max_length=100)
    agentId: str = Field(min_length=1, max_length=200)


class TaskProposal(BaseModel):
    id: str
    text: str
    project: str
    preferredSurface: Optional[str] = None
    status: Literal["proposed", "promoted", "rejected"]
    proposedBy: str
    authenticatedPrincipal: str
    proposedAt: str
    updatedAt: str
    promotedTaskId: Optional[str] = None
    rejectedAt: Optional[str] = None


def _proposal_from_state(item: dict) -> TaskProposal:
    return TaskProposal(**item)


@router.post("", response_model=TaskProposal, status_code=201)
def create_proposal(
    body: TaskProposalRequest,
    principal: str = Depends(require_orchestrator_worker),
):
    store = get_dashboard_store()
    now = _now()
    proposal = TaskProposal(
        id=f"proposal:{uuid.uuid4().hex[:12]}",
        text=body.text.strip(),
        project=body.project.strip(),
        preferredSurface=body.preferredSurface.strip() if body.preferredSurface else None,
        status="proposed",
        proposedBy=body.agentId.strip(),
        authenticatedPrincipal=principal,
        proposedAt=now,
        updatedAt=now,
    )
    try:
        with store._lock:
            state = store._load(fresh=True)
            proposals = state.setdefault("taskProposals", {})
            proposals[proposal.id] = proposal.model_dump(mode="json")
            store._save(state)
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return proposal


@router.get("", response_model=list[TaskProposal], dependencies=[Depends(require_operator)])
def list_proposals():
    try:
        state = get_dashboard_store()._load()
        rows = [
            _proposal_from_state(item)
            for item in state.get("taskProposals", {}).values()
        ]
        return sorted(rows, key=lambda item: item.updatedAt, reverse=True)
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post(
    "/{proposal_id}/promote",
    response_model=Task,
    dependencies=[Depends(require_operator)],
)
def promote_proposal(proposal_id: str):
    store = get_dashboard_store()
    try:
        with store._lock:
            state = store._load(fresh=True)
            proposals = state.setdefault("taskProposals", {})
            raw = proposals.get(proposal_id)
            if not raw:
                raise HTTPException(404, f"Proposal '{proposal_id}' not found")
            proposal = _proposal_from_state(raw)
            if proposal.status != "proposed":
                raise HTTPException(409, "Only proposed work can be promoted")

            now = _now()
            task = Task(
                id=f"task:{uuid.uuid4().hex[:12]}",
                text=proposal.text,
                project=proposal.project,
                preferredSurface=proposal.preferredSurface,
                status=TaskStatus.QUEUED,
                done=False,
                createdAt=now,
                updatedAt=now,
            )
            state["tasks"][task.id] = task.model_dump(mode="json")
            proposals[proposal.id] = proposal.model_copy(update={
                "status": "promoted",
                "promotedTaskId": task.id,
                "updatedAt": now,
            }).model_dump(mode="json")
            store._save(state)
            return task
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post(
    "/{proposal_id}/reject",
    response_model=TaskProposal,
    dependencies=[Depends(require_operator)],
)
def reject_proposal(proposal_id: str):
    store = get_dashboard_store()
    try:
        with store._lock:
            state = store._load(fresh=True)
            proposals = state.setdefault("taskProposals", {})
            raw = proposals.get(proposal_id)
            if not raw:
                raise HTTPException(404, f"Proposal '{proposal_id}' not found")
            proposal = _proposal_from_state(raw)
            if proposal.status != "proposed":
                raise HTTPException(409, "Only proposed work can be rejected")
            now = _now()
            updated = proposal.model_copy(update={
                "status": "rejected",
                "rejectedAt": now,
                "updatedAt": now,
            })
            proposals[proposal.id] = updated.model_dump(mode="json")
            store._save(state)
            return updated
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
