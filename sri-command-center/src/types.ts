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
