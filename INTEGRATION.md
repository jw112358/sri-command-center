# Integration Contract — SRI OS Command Center

This document defines the data layer the backend must provide. The prototype's **only data
seam is `data.jsx`** — it exports plain objects to `window` (`OS_REGISTRY`, `RUNNING_AGENTS`,
`AGENT_LOG_SEEDS`, `PROJECTS`, `LANES`, `NOTES`, `GRAPH_DATA`). Every component reads from
those globals. Replace that file with API/WS-backed stores and the UI ports 1:1.

## Entities

```ts
type OSStatus = "ACTIVE" | "IDLE" | "ERROR";

interface OSPlugin {
  id: string;            // "builder", "legal", ...
  name: string;          // "Builder OS"
  status: OSStatus;      // drives badge + system health pill
  agents: number;        // running-agent count (derivable)
}

type AgentStatus = "RUNNING" | "PAUSED" | "ERROR" | "STOPPED";

interface Agent {
  id: string;
  name: string;          // "scaffold-worker"
  os: string;            // OSPlugin.id
  status: AgentStatus;
  task: string;          // current task, one-line summary
  startedAt: string;     // ISO — UI derives elapsed; do NOT send a tick
  skill: string;         // "builder.scaffold_route" (skill/command being executed)
  inputs: string[];      // key=value strings shown in inspector
  outputs: string[];     // result lines; prefix "ERR:" renders red
}

interface LogLine {
  agentId: string;
  ts: string;            // ISO
  text: string;          // rendering style is derived from prefix: "✗"/"ERROR"→red, "⚠"→amber, "✓"→dim
}

type Lane = "PLANNING" | "IN PROGRESS" | "BLOCKED" | "COMPLETE";
type Priority = "HIGH" | "MED" | "LOW";

interface Project {
  id: string;
  name: string;
  os: string;            // OSPlugin.id
  owner: string;         // display name; UI derives avatar initials
  priority: Priority;
  lane: Lane;
  updatedAt: string;     // ISO; UI renders relative ("2m ago")
}

interface Note {
  id: string;
  title: string;
  tag: string;           // single tag, no "#"
  body: string;          // markdown
  updatedAt: string;
}

type NodeKind = "hub" | "project" | "agent" | "skill";
type NodeStatus = "ACTIVE" | "BLOCKED" | "COMPLETE";

interface GraphNode {
  id: string;            // namespaced: "os:builder" | "proj:p1" | "agent:a1" | "skill:builder:0"
  label: string;
  kind: NodeKind;
  os: string;            // cluster key — children orbit their OS hub
  status: NodeStatus;
  val: number;           // size weight (hub: 6 + agentCount; project 3; agent 1.6; skill 1)
  agentId?: string;      // for kind "agent" — links node selection to the inspector
}

interface GraphLink { source: string; target: string; }   // hub → child

interface SystemEvent {  // notification bell
  id: string;
  severity: "info" | "error";
  text: string;
  ts: string;
}
```

## REST endpoints

```
GET    /api/os                          → OSPlugin[]
POST   /api/os/:id/launch               → 202 (spawns an agent; appears via WS)
POST   /api/os/:id/configure            → opens config (app-defined)

GET    /api/agents?status=running       → Agent[]
GET    /api/agents/:id                  → Agent (inspector detail)
GET    /api/agents/:id/log?limit=80     → LogLine[] (backfill before streaming)
GET    /api/agents/:id/transcript       → full transcript (VIEW FULL TRANSCRIPT)
POST   /api/agents/:id/pause | /stop | /restart → 202; status change arrives via WS
POST   /api/agents/:id/message          { text } → 202   // INTERACT input

GET    /api/projects                    → Project[]
POST   /api/projects                    { name, os, owner, priority } → Project (lane=PLANNING)
PATCH  /api/projects/:id                { lane? priority? owner? name? } → Project  // kanban drop

GET    /api/notes                       → Note[] (sans body) ;  GET /api/notes/:id → Note
POST   /api/notes                       → Note ;  PATCH /api/notes/:id { title? tag? body? }

GET    /api/graph                       → { nodes: GraphNode[], links: GraphLink[] }
POST   /api/graph/links                 { source, target }            // "Add Connection"
POST   /api/graph/nodes/:id/complete                                  // "Mark Complete"

GET    /api/events?limit=20             → SystemEvent[] (bell dropdown)
GET    /api/health                      → { status: "NOMINAL"|"DEGRADED", faults: number, latencyMs: number }
```

## WebSocket events

One multiplexed socket (`/ws`) or per-channel — either works. The UI consumes:

```jsonc
// agent lifecycle — updates feed, registry counts, inspector, graph pulses
{ "type": "agent.started",  "agent": Agent }
{ "type": "agent.updated",  "agent": Agent }          // status/task/outputs changed
{ "type": "agent.stopped",  "agentId": "a1" }

// log streaming — append to the agent's buffer (UI keeps a ~200-line ring buffer,
// auto-scrolls when pinned to bottom). Prototype simulates this every 1.1–1.8s.
{ "type": "agent.log",      "line": LogLine }

// INTERACT round-trip: echo the operator message into the log stream as
// "‹ operator: <text>" followed by the agent's acknowledgement/response lines.

// graph deltas — node-in animation (expanding ring), status fades, link pulses
{ "type": "graph.node.added",   "node": GraphNode, "links": GraphLink[] }
{ "type": "graph.node.updated", "node": GraphNode }   // e.g. ACTIVE → COMPLETE (fade + drift)
{ "type": "graph.link.added",   "link": GraphLink }

// projects — move cards live when other operators/agents update them
{ "type": "project.updated", "project": Project }

// system — bell badge count, health pill, footer latency
{ "type": "system.event",   "event": SystemEvent }
{ "type": "system.health",  "status": "DEGRADED", "faults": 1, "latencyMs": 14 }
```

## UI ↔ data mapping

| UI region | Reads | Writes |
|---|---|---|
| System health pill | `/api/health`, `system.health` | — |
| Notification bell | `/api/events`, `system.event` | mark-read (optional) |
| OS Registry cards | `/api/os`, agent counts from `agent.*` | `launch`, `configure` |
| Running Agents feed | `/api/agents?status=running`, `agent.*` | `stop` |
| Agent Log terminal | `/api/agents/:id/log` + `agent.log` | — |
| Agent Inspector | `/api/agents/:id` | `pause/stop/restart`, `message`, `transcript` |
| Project Graph | `/api/graph` + `graph.*` | `links` (Add Connection), `complete` (Mark Complete); "Open OS"/"View Log" are client-side navigation |
| Notebook | `/api/notes` | `POST/PATCH` (debounce body saves ~500ms) |
| Mission Control | `/api/projects` + `project.updated` | `PATCH` lane on drop, `POST` on Add Project |

## Derivations & rules
- **System health**: `DEGRADED · n FAULT` when any OSPlugin.status === "ERROR" (n = count); else `ALL NOMINAL`.
- **Elapsed**: render `now - startedAt` as `MM:SS` (or `HhMMm` past 1h), client-ticked.
- **Graph data**: derivable server-side from OS + projects + agents + skills exactly as
  `buildGraph()` does in `data.jsx` (hubs → children links, statuses mapped:
  agent ERROR → BLOCKED, lane BLOCKED → BLOCKED, lane COMPLETE → COMPLETE, else ACTIVE).
- **Counts in panel headers** ("8 INSTALLED", "5 LIVE", "36 NODES · 28 LINKS") are derived
  from the collections — never hardcode.
- Status strings are uppercase end-to-end; the UI styles by exact value.

## Suggested implementation order
1. Port shell + styles statically (keep mock `data.jsx` temporarily).
2. Stand up `GET /api/os`, `/api/agents`, `/api/projects`, `/api/notes`, `/api/graph` and
   swap the globals for fetched stores.
3. Add the WS channel: `agent.log` first (it's the most visible "alive" signal), then agent
   lifecycle, then graph deltas.
4. Wire mutations (stop/pause/restart/message, kanban PATCH, notes CRUD, graph actions).
5. Preferences (layout direction, glow, scanlines, accent) → user settings storage.
