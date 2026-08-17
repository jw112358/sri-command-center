"""app/models.py — Pydantic models matching INTEGRATION.md entity contracts exactly."""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


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

class TaskStatus(str, Enum):
    QUEUED       = "queued"
    RUNNING      = "running"
    REVIEW_READY = "review_ready"
    SHIPPING     = "shipping"
    COMPLETED    = "completed"
    BLOCKED      = "blocked"


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


class Task(BaseModel):
    id: str
    text: str
    project: str = "Master Builder"
    preferredSurface: Optional[str] = None
    status: TaskStatus = TaskStatus.QUEUED
    done: bool = False
    createdAt: str
    startedAt: Optional[str] = None
    reviewReadyAt: Optional[str] = None
    approvedAt: Optional[str] = None
    completedAt: Optional[str] = None
    blockedAt: Optional[str] = None
    updatedAt: str
    assignedAgent: Optional[str] = None
    summaryId: Optional[str] = None
    reviewUrl: Optional[str] = None
    evidenceUrls: List[str] = Field(default_factory=list)
    lastError: Optional[str] = None


class SessionBrief(BaseModel):
    id: str
    sessionId: str
    date: str
    title: str
    project: str
    surface: str
    status: str
    summary: str
    currentState: Optional[str] = None
    nextStart: str
    sourceUrl: str
    updatedAt: str
    taskId: Optional[str] = None


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


class DashboardCapabilities(BaseModel):
    operatorAuthConfigured: bool
    driveReadConnected: bool
    dashboardPersistenceEnabled: bool
    commandDispatchEnabled: bool
    taskOrchestrationEnabled: bool = False
    sessionSummaryWriteEnabled: bool = False
    maxConcurrentTasks: int = 4
    dashboardStateReadVerified: bool = False
    dashboardStateWriteVerified: bool = False
    sessionSummaryReadVerified: bool = False
    sessionSummaryWriteVerified: bool = False
    orchestratorConnected: bool = False
    orchestratorLastSeenAt: Optional[str] = None
    orchestratorWorkers: List[str] = Field(default_factory=list)


class MarketingConnector(BaseModel):
    name: str
    status: Literal["READY", "STAGED", "BLOCKED"]
    detail: str


class MarketingApproval(BaseModel):
    id: str
    platform: str
    format: str
    content: str
    destination: str
    mediaUrls: List[str] = Field(default_factory=list)
    requestedAction: Literal["review-only", "publish"] = "publish"
    status: Literal["awaiting-approval", "approved"] = "awaiting-approval"
    approvedAt: Optional[str] = None
    approvedBy: Optional[str] = None


MarketingPublicationStatus = Literal[
    "queued", "submitting", "scheduled", "published", "failed", "cancelled"
]


class MarketingRoute(BaseModel):
    platform: str
    provider: Literal["blotato"] = "blotato"
    configured: bool = False
    verified: bool = False
    accountLabel: Optional[str] = None
    verifiedAt: Optional[str] = None
    detail: str


class MarketingPublication(BaseModel):
    id: str
    approvalId: str
    packetId: str
    platform: str
    ownerAgent: Literal["Publishing Agent"] = "Publishing Agent"
    status: MarketingPublicationStatus = "queued"
    contentChecksum: str
    destination: Optional[str] = None
    mediaUrls: List[str] = Field(default_factory=list)
    scheduledTime: Optional[str] = None
    useNextFreeSlot: bool = False
    publishNow: bool = False
    providerSubmissionId: Optional[str] = None
    publicUrl: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 0
    createdAt: str
    updatedAt: str
    publishedAt: Optional[str] = None


class MarketingMeasurement(BaseModel):
    id: str
    publicationId: str
    window: Literal["24h", "72h"]
    ownerAgent: Literal["Analytics Agent"] = "Analytics Agent"
    status: Literal["pending", "due", "complete"] = "pending"
    dueAt: str
    capturedAt: Optional[str] = None
    source: Optional[str] = None
    evidenceUrl: Optional[str] = None
    impressions: Optional[int] = None
    reach: Optional[int] = None
    engagements: Optional[int] = None
    clicks: Optional[int] = None
    destinationSessions: Optional[int] = None
    notes: Optional[str] = None


class MarketingLearning(BaseModel):
    publicationId: str
    ownerAgent: Literal["Learning Agent"] = "Learning Agent"
    status: Literal["awaiting-evidence", "provisional", "complete"]
    summary: str
    recommendation: str
    updatedAt: str


class MarketingDashboard(BaseModel):
    packetId: str
    product: str
    launchStage: str
    objective: str
    destination: str
    productionReadiness: int
    minimumOperationalCapability: int
    measurementSource: str
    currentGate: str
    connectors: List[MarketingConnector]
    approvals: List[MarketingApproval]
    routes: List[MarketingRoute] = Field(default_factory=list)
    publications: List[MarketingPublication] = Field(default_factory=list)
    measurements: List[MarketingMeasurement] = Field(default_factory=list)
    learning: List[MarketingLearning] = Field(default_factory=list)


class EventEdgeSignal(BaseModel):
    id: str
    family: str
    venue: str
    marketTicker: str
    eventTicker: str = ""
    side: str
    entryPrice: float
    maxAcceptablePrice: Optional[float] = None
    observedAt: str = ""
    expiresAt: str = ""
    status: Literal["active", "stale", "settled", "blocked"]
    confidence: str = ""
    primarySignal: str = ""
    supportingSignals: str = ""
    contrarySignals: str = ""
    riskDecision: str = ""
    strategy: str = ""


class EventEdgePaperTrade(BaseModel):
    id: str
    family: str
    sequence: int = 0
    marketTicker: str
    eventTicker: str = ""
    eventTitle: str = ""
    team: str = ""
    side: str
    entryPrice: float
    status: str
    outcome: str = "pending"
    netResult: float = 0.0
    cashPnl: Optional[float] = None
    strategy: str = ""
    enteredAt: str = ""
    expiresAt: str = ""


class EventEdgeManualTrade(BaseModel):
    id: str
    signalId: Optional[str] = None
    family: str
    venue: str
    marketTicker: str
    side: str
    entryPrice: float
    quantity: Optional[float] = None
    cashAmount: Optional[float] = None
    notes: str = ""
    status: Literal["recorded", "closed", "cancelled"] = "recorded"
    enteredAt: str
    createdAt: str
    updatedAt: str
    executionMode: Literal["manual_external_record"] = "manual_external_record"


class EventEdgeMetrics(BaseModel):
    settled: int = 0
    pending: int = 0
    wins: int = 0
    losses: int = 0
    winRate: float = 0.0
    normalizedNet: float = 0.0
    maxDrawdown: float = 0.0


class EventEdgeDashboard(BaseModel):
    generatedAt: str
    sourceStatus: Literal["live", "stale", "offline", "partial"]
    sourceDetail: str
    paperOnly: bool = True
    liveExecutionEnabled: bool = False
    metrics: EventEdgeMetrics
    signals: List[EventEdgeSignal] = Field(default_factory=list)
    currentPaperTrades: List[EventEdgePaperTrade] = Field(default_factory=list)
    recentPaperTrades: List[EventEdgePaperTrade] = Field(default_factory=list)
    manualTrades: List[EventEdgeManualTrade] = Field(default_factory=list)
    marketFamilies: List[str] = Field(default_factory=list)


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


class CreateTaskRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2_000)
    project: str = Field(default="Master Builder", min_length=1, max_length=200)
    preferredSurface: Optional[str] = Field(default=None, max_length=100)


class PatchTaskRequest(BaseModel):
    text: Optional[str] = Field(default=None, min_length=1, max_length=2_000)
    project: Optional[str] = Field(default=None, min_length=1, max_length=200)
    preferredSurface: Optional[str] = Field(default=None, max_length=100)


class TaskClaimRequest(BaseModel):
    workerId: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=1, ge=1, le=4)


class WorkerHeartbeatRequest(BaseModel):
    workerId: str = Field(min_length=1, max_length=200)


class TaskReviewReadyRequest(BaseModel):
    workerId: str = Field(min_length=1, max_length=200)
    surface: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=20_000)
    currentState: str = Field(min_length=1, max_length=20_000)
    nextStart: str = Field(min_length=1, max_length=10_000)
    reviewUrl: Optional[str] = Field(default=None, max_length=2_000)
    evidenceUrls: List[str] = Field(default_factory=list)


class TaskCompleteRequest(BaseModel):
    workerId: str = Field(min_length=1, max_length=200)
    finalSummary: Optional[str] = Field(default=None, max_length=20_000)
    evidenceUrls: List[str] = Field(default_factory=list)


class TaskBlockedRequest(BaseModel):
    workerId: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=10_000)
    evidenceUrls: List[str] = Field(default_factory=list)


class CreateSessionSummaryRequest(BaseModel):
    project: str = Field(min_length=1, max_length=200)
    surface: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=20_000)
    currentState: str = Field(min_length=1, max_length=20_000)
    nextStart: str = Field(min_length=1, max_length=10_000)
    materialChange: bool
    taskId: Optional[str] = Field(default=None, max_length=100)
    status: str = Field(default="complete", max_length=100)
    evidenceUrls: List[str] = Field(default_factory=list)


class MarketingApprovalRequest(BaseModel):
    approved: bool = True


class MarketingScheduleRequest(BaseModel):
    scheduledTime: Optional[str] = Field(default=None, max_length=100)
    useNextFreeSlot: bool = False
    publishNow: bool = False


class EventEdgeManualTradeRequest(BaseModel):
    signalId: Optional[str] = Field(default=None, max_length=300)
    family: str = Field(min_length=1, max_length=100)
    venue: str = Field(min_length=1, max_length=100)
    marketTicker: str = Field(min_length=1, max_length=300)
    side: str = Field(min_length=1, max_length=50)
    entryPrice: float = Field(gt=0)
    quantity: Optional[float] = Field(default=None, gt=0)
    cashAmount: Optional[float] = Field(default=None, gt=0)
    enteredAt: Optional[str] = Field(default=None, max_length=100)
    notes: str = Field(default="", max_length=5_000)

    @model_validator(mode="after")
    def require_manual_size(self):
        if self.quantity is None and self.cashAmount is None:
            raise ValueError("quantity or cashAmount is required")
        return self


class MarketingMeasurementRequest(BaseModel):
    window: Literal["24h", "72h"]
    source: str = Field(min_length=1, max_length=200)
    evidenceUrl: str = Field(min_length=1, max_length=2_000)
    impressions: Optional[int] = Field(default=None, ge=0)
    reach: Optional[int] = Field(default=None, ge=0)
    engagements: Optional[int] = Field(default=None, ge=0)
    clicks: Optional[int] = Field(default=None, ge=0)
    destinationSessions: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = Field(default=None, max_length=5_000)

    @field_validator("evidenceUrl")
    @classmethod
    def evidence_must_be_https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("evidenceUrl must use HTTPS")
        return value

    @model_validator(mode="after")
    def require_a_metric(self):
        if all(
            value is None
            for value in (
                self.impressions,
                self.reach,
                self.engagements,
                self.clicks,
                self.destinationSessions,
            )
        ):
            raise ValueError("at least one verified performance metric is required")
        return self


class AddGraphLinkRequest(BaseModel):
    source: str
    target: str


# ── Legal Agent OS ───────────────────────────────────────────────────────────

LegalRequestType = Literal[
    "new_matter", "revision", "strategy_memo", "standalone_research", "transcription", "unknown"
]
LegalMatterStatus = Literal[
    "received", "validating", "needs_operator", "conflict_review", "queued",
    "researching", "drafting", "transcribing", "quality_review", "pending_approval", "approved",
    "delivering", "revision_requested", "blocked", "monitoring", "dormant",
    "closure_review", "closed", "archived",
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
    currentSummary: str = ""
    exactNextAction: str = ""
    intakeCompletenessScore: Optional[int] = None
    blockingGaps: List[str] = Field(default_factory=list)
    sourceChannel: Literal["gmail", "manual", "command_center", "master_builder"]
    createdAt: str
    updatedAt: str


class LegalAssignmentSummary(BaseModel):
    assignmentId: str
    matterId: str
    stage: LegalMatterStatus
    status: Literal["running", "completed"]
    startedAt: str
    completedAt: Optional[str] = None
    outcomeStatus: Optional[LegalMatterStatus] = None


class LegalAssignmentStartRequest(BaseModel):
    matterId: str = Field(min_length=1, max_length=100)
    workerId: str = Field(min_length=1, max_length=200)


class LegalAssignmentStartReceipt(BaseModel):
    leaseId: str


class LegalAssignmentCompleteRequest(BaseModel):
    nextStatus: LegalMatterStatus = "pending_approval"


class LegalIntakeReceipt(BaseModel):
    eventId: str
    matter: LegalMatterSummary
    duplicate: bool = False
    revisionMatched: bool = False
    acknowledgementStatus: Literal["draft_pending_approval"] = "draft_pending_approval"


class LegalMatterClarificationRequest(BaseModel):
    expectedVersion: int = Field(ge=1)
    answers: Dict[str, str] = Field(min_length=1, max_length=100)
    operatorNote: str = Field(default="", max_length=10_000)


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


class LegalReviewArtifact(BaseModel):
    title: str
    kind: str
    driveFileId: str
    sha256: str


class LegalReviewPacket(BaseModel):
    packetId: str
    matterId: str
    matterVersion: int
    status: Literal["awaiting_review", "approved", "revision_requested", "rejected"]
    summary: str
    artifacts: List[LegalReviewArtifact]
    authorities: List[str] = Field(default_factory=list)
    citationFindings: List[str] = Field(default_factory=list)
    riskFlags: List[str] = Field(default_factory=list)
    proposedExternalAction: Optional[str] = None
    createdAt: str
    reviewedAt: Optional[str] = None
    reviewedBy: Optional[str] = None
    decisionNote: Optional[str] = None


class LegalReviewDecisionRequest(BaseModel):
    decision: Literal["approve", "request_revision", "reject"]
    note: str = Field(min_length=1, max_length=10_000)


class LegalDashboardState(BaseModel):
    activeCount: int
    capacity: int
    awaitingApproval: int
    upcomingDeadlines: int
    paused: bool
    matters: List[LegalMatterSummary]
    connectors: List[LegalConnectorStatus]
