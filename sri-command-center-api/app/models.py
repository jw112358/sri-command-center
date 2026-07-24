"""app/models.py — Pydantic models matching INTEGRATION.md entity contracts exactly."""
from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


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


# ── Legal Agent OS ───────────────────────────────────────────────────────────

LegalRequestType = Literal[
    "new_matter", "revision", "strategy_memo", "standalone_research", "unknown"
]
LegalMatterStatus = Literal[
    "received", "validating", "needs_operator", "conflict_review", "queued",
    "researching", "drafting", "quality_review", "pending_approval", "approved",
    "delivering", "revision_requested", "blocked", "closed",
]


class LegalIntakeRequest(BaseModel):
    channel: Literal["gmail", "master_builder"] = "master_builder"
    requestType: LegalRequestType = "unknown"
    sourceId: Optional[str] = None
    threadId: Optional[str] = None
    sender: Optional[str] = None
    subject: str = Field(default="", max_length=500)
    body: str = Field(min_length=1, max_length=100_000)
    operatorNotes: str = Field(default="", max_length=20_000)
    practiceLane: Literal["civil", "appeal"] = "civil"


class LegalMatterSummary(BaseModel):
    matterId: str
    displayName: str
    requestType: LegalRequestType
    practiceLane: Literal["civil", "appeal"]
    status: LegalMatterStatus
    version: int
    sourceChannel: Literal["gmail", "master_builder"]
    createdAt: str
    updatedAt: str


class LegalIntakeReceipt(BaseModel):
    eventId: str
    matter: LegalMatterSummary
    duplicate: bool = False
    revisionMatched: bool = False
    acknowledgementStatus: Literal["draft_pending_approval"] = "draft_pending_approval"


class LegalAuthConfig(BaseModel):
    enabled: bool
    provider: Literal["google_workspace"] = "google_workspace"
    clientId: str = ""
    sessionTtlSeconds: int
    manualIntakeEnabled: bool


class LegalGoogleCredentialRequest(BaseModel):
    credential: str = Field(min_length=100, max_length=10_000)


class LegalOperatorSession(BaseModel):
    accessToken: str
    email: str
    expiresAt: str


class LegalSessionStatus(BaseModel):
    authenticated: Literal[True] = True
    email: str
    expiresAt: str


class LegalConnectorStatus(BaseModel):
    name: str
    detail: str
    status: Literal["READY", "STAGED", "BLOCKED"]


class LegalDashboardState(BaseModel):
    activeCount: int
    capacity: int
    awaitingApproval: int
    upcomingDeadlines: int
    paused: bool
    matters: List[LegalMatterSummary]
    connectors: List[LegalConnectorStatus]
