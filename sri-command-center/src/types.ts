// types.ts — SRI OS Command Center entity contracts (from INTEGRATION.md)

export type OSStatus = 'ACTIVE' | 'IDLE' | 'ERROR';

export interface OSPlugin {
  id: string;
  name: string;
  status: OSStatus;
  agents: number;
  color?: string;
}

export type AgentStatus = 'RUNNING' | 'PAUSED' | 'ERROR' | 'STOPPED' | 'COMPLETE';

export interface Agent {
  id: string;
  name: string;
  os: string;           // OSPlugin.id
  status: AgentStatus;
  task: string;
  startedAt?: string;   // ISO — used server-side; elapsed derived client-side
  elapsed?: number;     // seconds, used by mock; replace with startedAt in production
  skill: string;
  inputs: string[];
  outputs: string[];
}

export interface LogLine {
  agentId: string;
  ts: string;           // ISO
  text: string;
}

export type Lane = 'PLANNING' | 'IN PROGRESS' | 'BLOCKED' | 'COMPLETE';
export type Priority = 'HIGH' | 'MED' | 'LOW';

export interface Project {
  id: string;
  name: string;
  os: string;
  owner: string;
  priority: Priority;
  lane: Lane;
  updatedAt?: string;    // ISO (server); mock uses "updated" string
  updated?: string;      // relative string used by mock
  githubRepo?: string;
  githubPrCount?: number;
  ciStatus?: 'success' | 'failure' | 'pending' | null;
  completionPct?: number;  // 0-100, passed through to graph node sphere size
  notes?: string;
}

export interface Note {
  id: string;
  title: string;
  tag: string;
  body: string;
  updatedAt?: string;   // ISO (server)
  updated?: string;     // formatted string used by mock
}

export interface Task {
  id: string;
  text: string;
  project: string;
  preferredSurface?: string | null;
  status: 'queued' | 'running' | 'review_ready' | 'shipping' | 'completed' | 'blocked';
  done: boolean;
  createdAt: string;
  startedAt?: string | null;
  reviewReadyAt?: string | null;
  approvedAt?: string | null;
  completedAt?: string | null;
  blockedAt?: string | null;
  updatedAt: string;
  assignedAgent?: string | null;
  summaryId?: string | null;
  reviewUrl?: string | null;
  evidenceUrls: string[];
  lastError?: string | null;
}

export interface SessionBrief {
  id: string;
  sessionId: string;
  date: string;
  title: string;
  project: string;
  surface: string;
  status: string;
  summary: string;
  currentState?: string | null;
  nextStart: string;
  sourceUrl: string;
  updatedAt: string;
  taskId?: string | null;
}

export type NodeKind = 'hub' | 'project' | 'agent' | 'skill';
export type NodeStatus = 'ACTIVE' | 'BLOCKED' | 'COMPLETE';

export interface GraphNode {
  id: string;
  label: string;
  kind: NodeKind;
  os: string;
  status: NodeStatus;
  val: number;
  agentId?: string;
  completionPct?: number;  // 0-100, drives sphere size in graph (higher = larger)
}

export interface GraphLink {
  source: string;
  target: string;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export type EventSeverity = 'info' | 'warning' | 'error';

export interface SystemEvent {
  id: string;
  severity: EventSeverity;
  text: string;
  ts: string;
}

export interface SystemHealth {
  status: 'NOMINAL' | 'DEGRADED';
  faults: number;
  latencyMs: number;
}

export interface DashboardCapabilities {
  operatorAuthConfigured: boolean;
  driveReadConnected: boolean;
  dashboardPersistenceEnabled: boolean;
  commandDispatchEnabled: boolean;
  taskOrchestrationEnabled: boolean;
  sessionSummaryWriteEnabled: boolean;
  maxConcurrentTasks: number;
  dashboardStateReadVerified: boolean;
  dashboardStateWriteVerified: boolean;
  sessionSummaryReadVerified: boolean;
  sessionSummaryWriteVerified: boolean;
  orchestratorConnected: boolean;
  orchestratorLastSeenAt?: string | null;
  orchestratorWorkers: string[];
}

export interface MarketingConnector {
  name: string;
  status: 'READY' | 'STAGED' | 'BLOCKED';
  detail: string;
}

export interface MarketingApproval {
  id: string;
  platform: string;
  format: string;
  content: string;
  destination: string;
  mediaUrls: string[];
  requestedAction: 'review-only' | 'publish';
  status: 'awaiting-approval' | 'approved';
  approvedAt?: string | null;
  approvedBy?: string | null;
}

export interface MarketingRoute {
  platform: string;
  provider: 'blotato';
  configured: boolean;
  verified: boolean;
  accountLabel?: string | null;
  verifiedAt?: string | null;
  detail: string;
}

export interface MarketingPublication {
  id: string;
  approvalId: string;
  packetId: string;
  platform: string;
  ownerAgent: 'Publishing Agent';
  status: 'queued' | 'submitting' | 'scheduled' | 'published' | 'failed' | 'cancelled';
  contentChecksum: string;
  destination?: string | null;
  mediaUrls: string[];
  scheduledTime?: string | null;
  useNextFreeSlot: boolean;
  publishNow: boolean;
  providerSubmissionId?: string | null;
  publicUrl?: string | null;
  error?: string | null;
  attempts: number;
  createdAt: string;
  updatedAt: string;
  publishedAt?: string | null;
}

export interface MarketingMeasurement {
  id: string;
  publicationId: string;
  window: '24h' | '72h';
  ownerAgent: 'Analytics Agent';
  status: 'pending' | 'due' | 'complete';
  dueAt: string;
  capturedAt?: string | null;
  source?: string | null;
  evidenceUrl?: string | null;
  impressions?: number | null;
  reach?: number | null;
  engagements?: number | null;
  clicks?: number | null;
  destinationSessions?: number | null;
  notes?: string | null;
}

export interface MarketingLearning {
  publicationId: string;
  ownerAgent: 'Learning Agent';
  status: 'awaiting-evidence' | 'provisional' | 'complete';
  summary: string;
  recommendation: string;
  updatedAt: string;
}

export interface MarketingDashboard {
  packetId: string;
  product: string;
  launchStage: string;
  objective: string;
  destination: string;
  productionReadiness: number;
  minimumOperationalCapability: number;
  measurementSource: string;
  currentGate: string;
  connectors: MarketingConnector[];
  approvals: MarketingApproval[];
  routes: MarketingRoute[];
  publications: MarketingPublication[];
  measurements: MarketingMeasurement[];
  learning: MarketingLearning[];
}

export interface EventEdgeSignal {
  id: string;
  family: string;
  venue: string;
  marketTicker: string;
  eventTicker: string;
  side: string;
  entryPrice: number;
  maxAcceptablePrice?: number | null;
  observedAt: string;
  expiresAt: string;
  status: 'active' | 'stale' | 'settled' | 'blocked';
  confidence: string;
  primarySignal: string;
  supportingSignals: string;
  contrarySignals: string;
  riskDecision: string;
  strategy: string;
  sourceLane: 'internal_btc' | 'polymarket_copy' | 'unknown';
  sourceTrader: string;
  lifecycleStatus: EventEdgeLifecycleStatus;
  rejectionReason: string;
}

export type EventEdgeLifecycleStatus = 'candidate' | 'rejected' | 'submitted' | 'partially_filled' | 'filled' | 'settled' | 'blocked';

export interface EventEdgeExecutionRecord {
  id: string;
  signalId?: string | null;
  family: string;
  venue: string;
  marketTicker: string;
  side: string;
  sourceLane: 'internal_btc' | 'polymarket_copy' | 'unknown';
  sourceTrader: string;
  executionMode: 'paper' | 'live';
  lifecycleStatus: EventEdgeLifecycleStatus;
  requestedContracts: number;
  filledContracts: number;
  averageFillPrice?: number | null;
  fees?: number | null;
  realizedPnl?: number | null;
  rejectionReason: string;
  updatedAt: string;
}

export interface EventEdgeAutomationState {
  mode: 'paper' | 'shadow' | 'live' | 'offline';
  heartbeatStatus: 'healthy' | 'stale' | 'offline';
  lastHeartbeatAt?: string | null;
  paused: boolean;
  killSwitchEngaged: boolean;
  controlPlaneConnected: boolean;
  ordersEnabled: boolean;
  detail: string;
}

export interface EventEdgePaperTrade {
  id: string;
  family: string;
  sequence: number;
  marketTicker: string;
  eventTicker: string;
  eventTitle: string;
  team: string;
  side: string;
  entryPrice: number;
  status: string;
  outcome: string;
  netResult: number;
  cashPnl?: number | null;
  strategy: string;
  enteredAt: string;
  expiresAt: string;
}

export interface EventEdgeManualTrade {
  id: string;
  signalId?: string | null;
  family: string;
  venue: string;
  marketTicker: string;
  side: string;
  entryPrice: number;
  quantity?: number | null;
  cashAmount?: number | null;
  notes: string;
  status: 'recorded' | 'closed' | 'cancelled';
  enteredAt: string;
  createdAt: string;
  updatedAt: string;
  executionMode: 'manual_external_record';
}

export interface EventEdgeDashboard {
  generatedAt: string;
  sourceStatus: 'live' | 'stale' | 'offline' | 'partial';
  sourceDetail: string;
  paperOnly: boolean;
  liveExecutionEnabled: boolean;
  metrics: {
    settled: number;
    pending: number;
    wins: number;
    losses: number;
    winRate: number;
    normalizedNet: number;
    maxDrawdown: number;
  };
  signals: EventEdgeSignal[];
  currentPaperTrades: EventEdgePaperTrade[];
  recentPaperTrades: EventEdgePaperTrade[];
  manualTrades: EventEdgeManualTrade[];
  executionRecords: EventEdgeExecutionRecord[];
  automation: EventEdgeAutomationState;
  marketFamilies: string[];
}

export type LegalRequestType =
  | 'new_matter'
  | 'revision'
  | 'strategy_memo'
  | 'standalone_research'
  | 'transcription'
  | 'unknown';

export type LegalMatterStatus =
  | 'received'
  | 'validating'
  | 'needs_operator'
  | 'conflict_review'
  | 'queued'
  | 'researching'
  | 'drafting'
  | 'transcribing'
  | 'quality_review'
  | 'pending_approval'
  | 'approved'
  | 'delivering'
  | 'revision_requested'
  | 'blocked'
  | 'monitoring'
  | 'dormant'
  | 'closure_review'
  | 'closed'
  | 'archived';

export interface LegalMatterSummary {
  matterId: string;
  displayName: string;
  requestType: LegalRequestType;
  practiceLane: 'civil' | 'appeal';
  status: LegalMatterStatus;
  version: number;
  currentSummary: string;
  exactNextAction: string;
  intakeCompletenessScore?: number | null;
  blockingGaps: string[];
  sourceChannel: 'gmail' | 'manual' | 'command_center' | 'master_builder';
  createdAt: string;
  updatedAt: string;
}

export interface LegalAssignmentSummary {
  assignmentId: string;
  matterId: string;
  stage: LegalMatterStatus;
  status: 'running' | 'completed';
  startedAt: string;
  completedAt?: string | null;
  outcomeStatus?: LegalMatterStatus | null;
}

export interface LegalMatterDocument {
  documentId: string;
  matterId: string;
  version: number;
  name: string;
  mimeType: string;
  sizeBytes: number;
  sha256: string;
  driveFileId: string;
  category: string;
  recordStatus: string;
  confidentiality: string;
  ingestionStatus: 'uploaded' | 'processing' | 'ready_for_review' | 'accepted' | 'excluded' | 'superseded' | 'needs_ocr' | 'failed';
  extractionMethod?: string | null;
  extractedCharacterCount: number;
  pageCount?: number | null;
  warnings: string[];
  reviewNote: string;
  acceptedAt?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface LegalDocumentExtractionPreview {
  document: LegalMatterDocument;
  textExcerpt: string;
  provenanceNotice: string;
}

export interface LegalConnectorStatus {
  name: string;
  detail: string;
  status: 'READY' | 'STAGED' | 'BLOCKED';
}

export interface LegalReviewArtifact {
  title: string;
  kind: string;
  driveFileId: string;
  sha256: string;
}

export interface LegalReviewPacket {
  packetId: string;
  matterId: string;
  matterVersion: number;
  status: 'awaiting_review' | 'approved' | 'revision_requested' | 'rejected';
  summary: string;
  artifacts: LegalReviewArtifact[];
  authorities: string[];
  citationFindings: string[];
  riskFlags: string[];
  proposedExternalAction?: string | null;
  createdAt: string;
  reviewedAt?: string | null;
  reviewedBy?: string | null;
  decisionNote?: string | null;
}

export interface LegalJobSummary {
  jobId: string;
  matterId: string;
  kind: string;
  status: 'queued' | 'leased' | 'complete' | 'failed' | 'blocked';
  attempts: number;
  lastError?: string | null;
  updatedAt: string;
  canRetry: boolean;
}

export interface LegalDashboardState {
  activeCount: number;
  capacity: number;
  awaitingApproval: number;
  upcomingDeadlines: number;
  paused: boolean;
  matters: LegalMatterSummary[];
  recentJobs: LegalJobSummary[];
  blockedJobs: number;
  connectors: LegalConnectorStatus[];
}

export interface LegalAuthConfig {
  enabled: boolean;
  provider: 'google_workspace';
  clientId: string;
  sessionTtlSeconds: number;
  manualIntakeEnabled: boolean;
}

export interface LegalOperatorSession {
  accessToken: string;
  email: string;
  expiresAt: string;
}

export interface LegalSessionStatus {
  authenticated: true;
  email: string;
  expiresAt: string;
}

export interface LegalIntakeReceipt {
  eventId: string;
  matter: LegalMatterSummary;
  duplicate: boolean;
  revisionMatched: boolean;
  acknowledgementStatus: 'draft_pending_approval';
}

// Layout preference
export type LayoutDir = 'classic' | 'focus' | 'graph';

export interface Tweaks {
  layout: LayoutDir;
  logSpeed: number;
  animGraph: boolean;
  crtScan: boolean;
  glowNodes: boolean;
}

// Selection state
export type Selection =
  | { type: 'agent'; agent: Agent }
  | { type: 'node'; node: GraphNode }
  | { type: 'none' };
