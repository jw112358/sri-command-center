"""app/models.py — Pydantic models matching INTEGRATION.md entity contracts exactly."""
from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel


# ── Enumerations ──────────────────────────────────────────────────────────────

class OSStatus(str, Enum):
    ACTIVE = "ACTIVE"
    IDLE   = "IDLE"
    ERROR  = "ERROR"

class AgentStatus(str, Enum):
    RUNNING = "RUNNING"
    PAUSED  = "PAUSED"
    ERROR   = "ERROR"
    STOPPED = "STOPPED"

class Lane(str, Enum):
    PLANNING    = "PLANNING"
    IN_PROGRESS = "IN PROGRESS"
    BLOCKED     = "BLOCKED"
    COMPLETE    = "COMPLETE"

class Priority(str, Enum):
    HIGH = "HIGH"
    MED  = "MED"
    LOW  = "LOW"

class NodeKind(str, Enum):
    HUB     = "hub"
    PROJECT = "project"
    AGENT   = "agent"
    SKILL   = "skill"

class NodeStatus(str, Enum):
    ACTIVE   = "ACTIVE"
    BLOCKED  = "BLOCKED"
    COMPLETE = "COMPLETE"

class EventSeverity(str, Enum):
    INFO  = "info"
    ERROR = "error"


# ── Core entities ─────────────────────────────────────────────────────────────

class OSPlugin(BaseModel):
    id:     str
    name:   str
    status: OSStatus
    agents: int = 0
    color:  Optional[str] = None


class Agent(BaseModel):
    id:        str
    name:      str
    os:        str
    status:    AgentStatus
    task:      str
    startedAt: str           # ISO-8601
    skill:     str
    inputs:    List[str] = []
    outputs:   List[str] = []


class LogLine(BaseModel):
    agentId: str
    ts:      str
    text:    str


class Project(BaseModel):
    id:        str
    name:      str
    os:        str
    owner:     str
    priority:  Priority
    lane:      Lane
    updatedAt: Optional[str] = None      # ISO-8601 or date string
    # Completion tracking
    completionPct: Optional[float] = None  # 0-100; drives graph sphere size
    notes:         Optional[str]  = None   # human-readable status summary
    # GitHub extras (optional — populated when github_enabled)
    githubRepo:    Optional[str] = None
    githubPrCount: Optional[int] = None
    ciStatus:      Optional[str] = None  # "passing" | "failing" | "pending"


class Note(BaseModel):
    id:        str
    title:     str
    tag:       str
    body:      Optional[str] = None      # omitted in list endpoint
    updatedAt: str


class GraphNode(BaseModel):
    id:            str
    label:         str
    kind:          NodeKind
    os:            str
    status:        NodeStatus
    val:           float
    agentId:       Optional[str] = None
    completionPct: Optional[float] = None  # 0-100; drives sphere size in 3D graph


class GraphLink(BaseModel):
    source: str
    target: str


class GraphData(BaseModel):
    nodes: List[GraphNode]
    links: List[GraphLink]


class SystemEvent(BaseModel):
    id:       str
    severity: EventSeverity
    text:     str
    ts:       str


class SystemHealth(BaseModel):
    status:    str       # "NOMINAL" | "DEGRADED"
    faults:    int
    latencyMs: int


# ── Request / response bodies ─────────────────────────────────────────────────

class LaunchOSRequest(BaseModel):
    task:   Optional[str] = None
    inputs: List[str] = []

class MessageAgentRequest(BaseModel):
    text: str

class CreateProjectRequest(BaseModel):
    name:     str
    os:       str
    owner:    str
    priority: Priority = Priority.MED

class PatchProjectRequest(BaseModel):
    lane:     Optional[Lane]     = None
    priority: Optional[Priority] = None
    owner:    Optional[str]      = None
    name:     Optional[str]      = None

class CreateNoteRequest(BaseModel):
    title: str = "Untitled"
    tag:   str = "note"
    body:  str = ""

class PatchNoteRequest(BaseModel):
    title: Optional[str] = None
    tag:   Optional[str] = None
    body:  Optional[str] = None

class AddGraphLinkRequest(BaseModel):
    source: str
    target: str
