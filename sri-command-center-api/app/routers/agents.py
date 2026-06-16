"""app/routers/agents.py — Agent endpoints"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

from app.models import Agent, LogLine, MessageAgentRequest
from app.services import drive
from app.services.ws_manager import broadcast_agent_updated, broadcast_agent_stopped

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("", response_model=List[Agent])
def list_agents(status: Optional[str] = Query(None, description="Filter by status, e.g. running")):
    agents = drive.get_agents(status_filter=status)
    # Merge in GitHub CI agents for builder OS
    try:
        from app.services.github import get_github_agents
        gh_agents = get_github_agents()
        existing_ids = {a.id for a in agents}
        agents += [a for a in gh_agents if a.id not in existing_ids]
    except Exception:
        pass
    return agents


@router.get("/{agent_id}", response_model=Agent)
def get_agent(agent_id: str):
    agent = drive.get_agent(agent_id)
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    return agent


@router.get("/{agent_id}/log", response_model=List[LogLine])
def get_agent_log(agent_id: str, limit: int = Query(80, ge=1, le=500)):
    return drive.get_agent_log(agent_id, limit=limit)


@router.get("/{agent_id}/transcript")
def get_transcript(agent_id: str):
    # Full transcript — Drive log file or empty
    lines = drive.get_agent_log(agent_id, limit=500)
    return {"agentId": agent_id, "lines": lines}


@router.post("/{agent_id}/pause", status_code=202)
async def pause_agent(agent_id: str):
    agent = drive.get_agent(agent_id)
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    drive.write_signal(agent.os, "agent-pause", {"agent_id": agent_id, "status": "PAUSED"})
    updated = agent.model_copy(update={"status": "PAUSED"})
    await broadcast_agent_updated(updated.model_dump())
    return {"status": "accepted"}


@router.post("/{agent_id}/stop", status_code=202)
async def stop_agent(agent_id: str):
    agent = drive.get_agent(agent_id)
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    drive.write_signal(agent.os, "agent-stop", {"agent_id": agent_id, "status": "STOPPED"})
    await broadcast_agent_stopped(agent_id)
    return {"status": "accepted"}


@router.post("/{agent_id}/restart", status_code=202)
async def restart_agent(agent_id: str):
    agent = drive.get_agent(agent_id)
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    drive.write_signal(agent.os, "agent-restart", {"agent_id": agent_id, "status": "RUNNING"})
    updated = agent.model_copy(update={"status": "RUNNING"})
    await broadcast_agent_updated(updated.model_dump())
    return {"status": "accepted"}


@router.post("/{agent_id}/message", status_code=202)
async def message_agent(agent_id: str, body: MessageAgentRequest):
    """INTERACT channel — write operator message as a signal, echo to WS log."""
    agent = drive.get_agent(agent_id)
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found")

    drive.write_signal(agent.os, "agent-message", {
        "agent_id": agent_id,
        "operator_message": body.text,
    })

    # Echo to WS log stream immediately
    from app.services.ws_manager import broadcast_log_line
    await broadcast_log_line(agent_id, f"‹ operator: {body.text}")
    await broadcast_log_line(agent_id, "→ acknowledged · adjusting plan …")

    return {"status": "accepted"}
