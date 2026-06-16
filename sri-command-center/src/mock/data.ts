// mock/data.ts — typed mock data layer (replace globals with API calls in Phase 2)
import type { OSPlugin, Agent, Project, Note, GraphNode, GraphLink, GraphData } from '../types';

export const OS_REGISTRY: OSPlugin[] = [
  { id: 'builder',   name: 'Builder OS',                    status: 'ACTIVE', agents: 3 },
  { id: 'legal',     name: 'Legal OS',                      status: 'IDLE',   agents: 0 },
  { id: 'marketing', name: 'Marketing OS',                  status: 'ACTIVE', agents: 2 },
  { id: 'finance',   name: 'Finance OS',                    status: 'IDLE',   agents: 0 },
  { id: 'jkauthor',  name: 'JK Author OS',                  status: 'ACTIVE', agents: 1 },
  { id: 'brand',     name: 'Brand Voice OS',                status: 'ERROR',  agents: 1 },
  { id: 'blotato',   name: 'Marketing-OS (Blotato/Postiz)', status: 'ACTIVE', agents: 2 },
  { id: 'prod',      name: 'Productivity OS',               status: 'IDLE',   agents: 0 },
];

export const OS_BY_ID: Record<string, OSPlugin> = Object.fromEntries(
  OS_REGISTRY.map((o) => [o.id, o])
);

export const RUNNING_AGENTS: Agent[] = [
  {
    id: 'a1', name: 'scaffold-worker', os: 'builder', status: 'RUNNING',
    task: 'Generating component tree for /dashboard route and wiring data hooks',
    elapsed: 184, skill: 'builder.scaffold_route',
    inputs: ['route=/dashboard', 'framework=react', 'state=zustand'],
    outputs: ['12 components emitted', 'routes/dashboard.tsx', 'hooks/useDashboard.ts (draft)'],
  },
  {
    id: 'a2', name: 'copy-smith', os: 'marketing', status: 'RUNNING',
    task: 'Drafting Q3 launch email sequence — variant B, tone: confident/direct',
    elapsed: 47, skill: 'marketing.email_sequence',
    inputs: ['campaign=Q3-launch', 'variant=B', 'audience=warm-list'],
    outputs: ['Email 1/5 drafted', 'Subject A/B pair ready'],
  },
  {
    id: 'a3', name: 'ledger-bot', os: 'blotato', status: 'RUNNING',
    task: 'Scheduling 14 posts across X, LinkedIn, Threads via Postiz queue',
    elapsed: 22, skill: 'blotato.bulk_schedule',
    inputs: ['channels=3', 'window=72h', 'posts=14'],
    outputs: ['6/14 scheduled', 'queue depth: 8'],
  },
  {
    id: 'a4', name: 'manuscript-aide', os: 'jkauthor', status: 'RUNNING',
    task: 'Continuity pass on Chapter 19 — cross-checking timeline against bible',
    elapsed: 311, skill: 'jkauthor.continuity_check',
    inputs: ['chapter=19', 'bible=v4', 'characters=7'],
    outputs: ['2 conflicts flagged', '1 timeline gap'],
  },
  {
    id: 'a5', name: 'voice-tuner', os: 'brand', status: 'ERROR',
    task: 'Re-scoring tone drift across 40 assets — halted: missing style token',
    elapsed: 8, skill: 'brand.tone_score',
    inputs: ['assets=40', 'ref=brand-voice-v2'],
    outputs: ['ERR: style token `voice.warmth` unresolved'],
  },
  {
    id: 'a6', name: 'pipe-runner', os: 'builder', status: 'RUNNING',
    task: 'Running CI on PR #482 — lint, typecheck, unit (1842 tests)',
    elapsed: 96, skill: 'builder.ci_run',
    inputs: ['pr=482', 'branch=feat/graph-view'],
    outputs: ['lint ok', 'typecheck ok', 'tests 1731/1842'],
  },
];

export const AGENT_LOG_SEEDS: Record<string, string[]> = {
  a1: [
    '[builder.scaffold_route] booting worker · session #7c41',
    '→ reading route manifest … 6 routes resolved',
    '→ target /dashboard :: layout=grid-3col',
    '✓ emitted <HeaderBar/> <TabNav/> <RegistryColumn/>',
    '✓ emitted <AgentFeed/> <TerminalLog/> <Inspector/>',
    '→ wiring useDashboard() :: 4 selectors',
    '… resolving import graph (depth 3)',
  ],
  a2: [
    '[marketing.email_sequence] campaign=Q3-launch variant=B',
    '→ loading audience segment :: warm-list (4,210)',
    '✓ subject A: "The fastest path to ship"',
    '✓ subject B: "Stop waiting on the backend"',
    '→ drafting body 1/5 … tone=confident',
  ],
  a3: [
    '[blotato.bulk_schedule] channels=[x, linkedin, threads]',
    '→ queue handshake :: Postiz OK',
    '✓ scheduled post 1 → X · 09:00',
    '✓ scheduled post 2 → LinkedIn · 11:30',
    '→ rate-limit window: 72h · depth 8',
  ],
  a4: [
    '[jkauthor.continuity_check] chapter=19 bible=v4',
    '→ indexing 7 character arcs',
    '⚠ conflict: Mara\'s location (ch18→ch19)',
    '⚠ timeline gap: 3 unaccounted days',
    '→ generating reconciliation notes …',
  ],
  a5: [
    '[brand.tone_score] assets=40 ref=brand-voice-v2',
    '→ loading style tokens …',
    '✗ ERROR style token `voice.warmth` unresolved',
    '✗ halting run · 0/40 scored',
    '→ awaiting operator input',
  ],
  a6: [
    '[builder.ci_run] pr=482 branch=feat/graph-view',
    '✓ lint · 0 errors 2 warnings',
    '✓ typecheck · 0 errors',
    '→ unit suite … 1731/1842',
    '… spec: graph/forceLayout.test.ts',
  ],
};

export const LOG_FRAGMENTS: string[] = [
  '→ resolving dependency :: {pkg}',
  '✓ committed {n} files to working tree',
  '… streaming tokens ({n}/s)',
  '→ cache hit · {pkg}',
  '✓ checkpoint saved · session ok',
  '⟳ heartbeat · latency {n}ms',
  '→ planning next step ({n} candidates)',
  '✓ tool call returned · {n}ms',
  '→ embedding batch {n} … done',
  '⚠ retry {n}/3 · transient timeout',
];

export const PROJECTS: Project[] = [
  { id: 'p1',  name: 'Graph View v2',          os: 'builder',   owner: 'A. Rao',    priority: 'HIGH', lane: 'IN PROGRESS', updated: '2m ago',    completionPct: 55 },
  { id: 'p2',  name: 'Q3 Launch Campaign',     os: 'marketing', owner: 'M. Diaz',   priority: 'HIGH', lane: 'IN PROGRESS', updated: '11m ago',   completionPct: 40 },
  { id: 'p3',  name: 'Series A Data Room',     os: 'legal',     owner: 'S. Okafor', priority: 'MED',  lane: 'PLANNING',    updated: '1h ago',    completionPct: 10 },
  { id: 'p4',  name: 'Runway Model FY26',      os: 'finance',   owner: 'J. Park',   priority: 'MED',  lane: 'PLANNING',    updated: '3h ago',    completionPct: 15 },
  { id: 'p5',  name: 'Novel — Act III edit',   os: 'jkauthor',  owner: 'J. King',   priority: 'LOW',  lane: 'IN PROGRESS', updated: '20m ago',   completionPct: 62 },
  { id: 'p6',  name: 'Brand Voice v2 Roll',    os: 'brand',     owner: 'L. Chen',   priority: 'HIGH', lane: 'BLOCKED',     updated: '5m ago',    completionPct: 30 },
  { id: 'p7',  name: 'Cross-post Engine',      os: 'blotato',   owner: 'M. Diaz',   priority: 'MED',  lane: 'IN PROGRESS', updated: 'just now',  completionPct: 48 },
  { id: 'p8',  name: 'Inbox Zero Automation',  os: 'prod',      owner: 'A. Rao',    priority: 'LOW',  lane: 'PLANNING',    updated: '6h ago',    completionPct: 5  },
  { id: 'p9',  name: 'SOC2 Evidence Pack',     os: 'legal',     owner: 'S. Okafor', priority: 'HIGH', lane: 'BLOCKED',     updated: '40m ago',   completionPct: 25 },
  { id: 'p10', name: 'Pricing Page Rewrite',   os: 'marketing', owner: 'M. Diaz',   priority: 'MED',  lane: 'COMPLETE',    updated: 'yesterday', completionPct: 100 },
  { id: 'p11', name: 'Auth Refactor',          os: 'builder',   owner: 'A. Rao',    priority: 'MED',  lane: 'COMPLETE',    updated: '2d ago',    completionPct: 100 },
  { id: 'p12', name: 'Expense Sync',           os: 'finance',   owner: 'J. Park',   priority: 'LOW',  lane: 'COMPLETE',    updated: '3d ago',    completionPct: 100 },
  // GitHub live repos — these get replaced by real API data when backend is connected
  { id: 'gh:legal-agent-os',  name: 'legal-agent-os',  os: 'builder', owner: 'sri-intel', priority: 'HIGH', lane: 'IN PROGRESS', updated: 'live', githubRepo: 'sri-intel/legal-agent-os',  completionPct: 0 },
  { id: 'gh:builder-os',      name: 'builder-os',      os: 'builder', owner: 'sri-intel', priority: 'HIGH', lane: 'IN PROGRESS', updated: 'live', githubRepo: 'sri-intel/builder-os',      completionPct: 0 },
  { id: 'gh:marketing-os',    name: 'marketing-os',    os: 'builder', owner: 'sri-intel', priority: 'MED',  lane: 'IN PROGRESS', updated: 'live', githubRepo: 'sri-intel/marketing-os',    completionPct: 0 },
];

export const LANES: string[] = ['PLANNING', 'IN PROGRESS', 'BLOCKED', 'COMPLETE'];

export const NOTES: Note[] = [
  {
    id: 'n1', title: 'Operating Doctrine', tag: 'doctrine', updated: 'Jun 11 · 09:12',
    body: `# Operating Doctrine

Every OS is a **self-contained operator**. The Command Center is the
single pane of glass — never reach into an OS directly.

## Principles
- One agent, one task, one transcript.
- **Blocked** beats *silently failing*. Surface it.
- The graph is the source of truth for what's live.

## Today
- [x] Ship Graph View v2 behind flag
- [ ] Unblock Brand Voice v2 (missing token)
- [ ] Review Series A data room scope`,
  },
  {
    id: 'n2', title: 'Brand Voice — token bug', tag: 'bug', updated: 'Jun 11 · 08:40',
    body: `# Brand Voice — token bug

\`voice-tuner\` halts on \`voice.warmth\`.

Root cause: token renamed to \`tone.warmth\` in v2 but the
scorer still references the v1 path.

> Fix: alias old → new in the token resolver, or bump the
> scorer's manifest pin to v2.

Owner: **L. Chen** · ETA today`,
  },
  {
    id: 'n3', title: 'Q3 Launch — checklist', tag: 'marketing', updated: 'Jun 10 · 17:05',
    body: `# Q3 Launch — checklist

1. Email sequence (5) — *variant B in draft*
2. Pricing page rewrite — **done**
3. Cross-post engine — wiring Postiz queue
4. Founder thread — needs JK voice pass

Target ship: **Jun 24**.`,
  },
  {
    id: 'n4', title: 'Scratch', tag: 'scratch', updated: 'Jun 10 · 14:22',
    body: `# Scratch

- graph: cluster OS hubs tighter, projects orbit hub
- idea: right-click node → "spawn agent here"
- ask finance for FY26 assumptions
- the constellation should *breathe* when idle`,
  },
];

const SKILL_NAMES = ['scaffold', 'ci', 'draft', 'schedule', 'score', 'review', 'sync', 'index'];

export function buildGraph(): GraphData {
  const nodes: GraphNode[] = [];
  const links: GraphLink[] = [];

  OS_REGISTRY.forEach((os) => {
    nodes.push({
      id: 'os:' + os.id,
      label: os.name.replace(/ \(.*\)/, ''),
      kind: 'hub',
      os: os.id,
      status: (os.status === 'ERROR' ? 'BLOCKED' : os.status === 'IDLE' ? 'ACTIVE' : os.status) as 'ACTIVE' | 'BLOCKED' | 'COMPLETE',
      val: 6 + os.agents,
    });
  });

  PROJECTS.forEach((p) => {
    const st: 'ACTIVE' | 'BLOCKED' | 'COMPLETE' =
      p.lane === 'BLOCKED' ? 'BLOCKED' : p.lane === 'COMPLETE' ? 'COMPLETE' : 'ACTIVE';
    nodes.push({
      id: 'proj:' + p.id,
      label: p.name,
      kind: 'project',
      os: p.os,
      status: st,
      val: 3,
      completionPct: p.completionPct ?? (p.lane === 'COMPLETE' ? 100 : p.lane === 'PLANNING' ? 10 : 50),
    });
    links.push({ source: 'os:' + p.os, target: 'proj:' + p.id });
  });

  RUNNING_AGENTS.forEach((a) => {
    const st: 'ACTIVE' | 'BLOCKED' = a.status === 'ERROR' ? 'BLOCKED' : 'ACTIVE';
    nodes.push({ id: 'agent:' + a.id, label: a.name, kind: 'agent', os: a.os, status: st, val: 1.6, agentId: a.id });
    links.push({ source: 'os:' + a.os, target: 'agent:' + a.id });
  });

  OS_REGISTRY.filter((o) => o.status !== 'IDLE').forEach((os, idx) => {
    for (let k = 0; k < 2; k++) {
      const id = 'skill:' + os.id + ':' + k;
      nodes.push({
        id, label: os.id + '.' + SKILL_NAMES[(idx + k) % SKILL_NAMES.length],
        kind: 'skill', os: os.id, status: 'COMPLETE', val: 1,
      });
      links.push({ source: 'os:' + os.id, target: id });
    }
  });

  return { nodes, links };
}

export const GRAPH_DATA: GraphData = buildGraph();

export const MOCK_NOTIFS = [
  { err: true,  t: 'Brand Voice OS — voice-tuner halted (missing token)', time: '2m ago' },
  { err: false, t: 'Builder OS — CI on PR #482 reached 94%', time: '5m ago' },
  { err: false, t: 'Marketing-OS — 6/14 posts scheduled via Postiz', time: '9m ago' },
  { err: false, t: 'JK Author OS — 2 continuity conflicts flagged', time: '14m ago' },
  { err: false, t: 'Pricing Page Rewrite moved to COMPLETE', time: '1h ago' },
];
