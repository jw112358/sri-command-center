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
  done: boolean;
  createdAt: string;
  completedAt?: string | null;
  updatedAt: string;
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

export type LegalRequestType =
  | 'new_matter'
  | 'revision'
  | 'strategy_memo'
  | 'standalone_research'
  | 'unknown';

export type LegalMatterStatus =
  | 'received'
  | 'validating'
  | 'needs_operator'
  | 'conflict_review'
  | 'queued'
  | 'researching'
  | 'drafting'
  | 'quality_review'
  | 'pending_approval'
  | 'approved'
  | 'delivering'
  | 'revision_requested'
  | 'blocked'
  | 'closed';

export interface LegalMatterSummary {
  matterId: string;
  displayName: string;
  requestType: LegalRequestType;
  practiceLane: 'civil' | 'appeal';
  status: LegalMatterStatus;
  version: number;
  sourceChannel: 'gmail' | 'master_builder';
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

export interface LegalConnectorStatus {
  name: string;
  detail: string;
  status: 'READY' | 'STAGED' | 'BLOCKED';
}

export interface LegalDashboardState {
  activeCount: number;
  capacity: number;
  awaitingApproval: number;
  upcomingDeadlines: number;
  paused: boolean;
  matters: LegalMatterSummary[];
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
