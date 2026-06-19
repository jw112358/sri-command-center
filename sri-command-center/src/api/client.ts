/**
 * api/client.ts — SRI OS Command Center API client
 *
 * All data fetching goes through this module.
 * When the API is unreachable the mock data layer is returned as fallback,
 * so the UI is always usable during local development without a running backend.
 */

import type {
  OSPlugin, Agent, LogLine, Project, Note, GraphData,
  SystemEvent, SystemHealth,
} from '../types';
import * as mock from '../mock/data';

// ── Config ────────────────────────────────────────────────────────────────────
// Vite exposes VITE_API_URL from .env; falls back to localhost:8000
const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000';
const WS_BASE  = API_BASE.replace(/^http/, 'ws');

// ── Fetch helper ──────────────────────────────────────────────────────────────
async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

// ── Reachability ──────────────────────────────────────────────────────────────
let _apiReachable: boolean | null = null;

async function isApiReachable(): Promise<boolean> {
  if (_apiReachable !== null) return _apiReachable;
  try {
    await fetch(`${API_BASE}/api/health`, { signal: AbortSignal.timeout(3000) });
    _apiReachable = true;
  } catch {
    _apiReachable = false;
    console.warn('[SRI] API unreachable — using mock data fallback');
  }
  // Re-check every 30s
  setTimeout(() => { _apiReachable = null; }, 30_000);
  return _apiReachable;
}

// ── API methods with mock fallback ────────────────────────────────────────────

export async function getOSPlugins(): Promise<OSPlugin[]> {
  if (!await isApiReachable()) return mock.OS_REGISTRY;
  return apiFetch<OSPlugin[]>('/api/os');
}

export async function getAgents(status?: string): Promise<Agent[]> {
  if (!await isApiReachable()) return mock.RUNNING_AGENTS;
  const qs = status ? `?status=${status}` : '';
  // Convert ISO startedAt → elapsed seconds for mock-compatibility
  const agents = await apiFetch<Agent[]>(`/api/agents${qs}`);
  return agents.map(normalizeAgent);
}

export async function getAgent(id: string): Promise<Agent | null> {
  if (!await isApiReachable()) return mock.RUNNING_AGENTS.find(a => a.id === id) ?? null;
  try { return normalizeAgent(await apiFetch<Agent>(`/api/agents/${id}`)); }
  catch { return null; }
}

export async function getAgentLog(id: string, limit = 80): Promise<LogLine[]> {
  if (!await isApiReachable()) return [];
  return apiFetch<LogLine[]>(`/api/agents/${id}/log?limit=${limit}`);
}

export async function pauseAgent(id: string)   { return apiFetch(`/api/agents/${id}/pause`,   { method: 'POST' }); }
export async function stopAgent(id: string)    { return apiFetch(`/api/agents/${id}/stop`,    { method: 'POST' }); }
export async function restartAgent(id: string) { return apiFetch(`/api/agents/${id}/restart`, { method: 'POST' }); }

export async function messageAgent(id: string, text: string) {
  return apiFetch(`/api/agents/${id}/message`, {
    method: 'POST',
    body: JSON.stringify({ text }),
  });
}

export async function getProjects(): Promise<Project[]> {
  if (!await isApiReachable()) return mock.PROJECTS;
  return apiFetch<Project[]>('/api/projects');
}

export async function createProject(body: { name: string; os: string; owner: string; priority: string }) {
  return apiFetch<Project>('/api/projects', { method: 'POST', body: JSON.stringify(body) });
}

export async function patchProject(id: string, patch: Partial<Project>) {
  return apiFetch<Project>(`/api/projects/${id}`, { method: 'PATCH', body: JSON.stringify(patch) });
}

export async function getNotes(): Promise<Note[]> {
  if (!await isApiReachable()) return mock.NOTES;
  return apiFetch<Note[]>('/api/notes');
}

export async function getNote(id: string): Promise<Note | null> {
  if (!await isApiReachable()) return mock.NOTES.find(n => n.id === id) ?? null;
  try { return apiFetch<Note>(`/api/notes/${id}`); }
  catch { return null; }
}

export async function createNote(body: { title?: string; tag?: string; body?: string }) {
  if (!await isApiReachable()) {
    const id = 'n' + Date.now();
    return { id, title: body.title ?? 'Untitled', tag: body.tag ?? 'note', body: body.body ?? '', updatedAt: new Date().toISOString() };
  }
  return apiFetch<Note>('/api/notes', { method: 'POST', body: JSON.stringify(body) });
}

export async function patchNote(id: string, patch: Partial<Note>) {
  if (!await isApiReachable()) return patch as Note;
  return apiFetch<Note>(`/api/notes/${id}`, { method: 'PATCH', body: JSON.stringify(patch) });
}

export async function getGraph(): Promise<GraphData> {
  if (!await isApiReachable()) return mock.GRAPH_DATA;
  return apiFetch<GraphData>('/api/graph');
}

export async function getEvents(): Promise<SystemEvent[]> {
  if (!await isApiReachable()) {
    return mock.MOCK_NOTIFS.map((n, i) => ({
      id: String(i),
      severity: n.err ? 'error' : 'info',
      text: n.t,
      ts: new Date().toISOString(),
    })) as SystemEvent[];
  }
  return apiFetch<SystemEvent[]>('/api/events');
}

export async function getHealth(): Promise<SystemHealth> {
  if (!await isApiReachable()) return { status: 'NOMINAL', faults: 0, latencyMs: 0 };
  return apiFetch<SystemHealth>('/api/health');
}

export async function launchOS(id: string, task?: string) {
  return apiFetch(`/api/os/${id}/launch`, { method: 'POST', body: JSON.stringify({ task }) });
}

export async function addGraphLink(source: string, target: string) {
  return apiFetch('/api/graph/links', { method: 'POST', body: JSON.stringify({ source, target }) });
}

export async function markNodeComplete(nodeId: string) {
  return apiFetch(`/api/graph/nodes/${nodeId}/complete`, { method: 'POST' });
}

// ── WebSocket connection ───────────────────────────────────────────────────────

export type WSHandler = (msg: Record<string, unknown>) => void;

export function connectWS(onMessage: WSHandler): () => void {
  let ws: WebSocket | null = null;
  let retryTimeout: ReturnType<typeof setTimeout> | null = null;
  let stopped = false;

  const connect = () => {
    if (stopped) return;
    try {
      ws = new WebSocket(`${WS_BASE}/ws`);

      ws.onopen = () => {
        console.info('[SRI] WebSocket connected');
        // Heartbeat
        const hb = setInterval(() => ws?.send(JSON.stringify({ type: 'ping' })), 25_000);
        ws!.addEventListener('close', () => clearInterval(hb));
      };

      ws.onmessage = (e) => {
        try { onMessage(JSON.parse(e.data)); }
        catch { /* ignore malformed */ }
      };

      ws.onclose = () => {
        if (!stopped) {
          console.info('[SRI] WebSocket closed — reconnecting in 3s');
          retryTimeout = setTimeout(connect, 3_000);
        }
      };

      ws.onerror = () => ws?.close();
    } catch {
      retryTimeout = setTimeout(connect, 5_000);
    }
  };

  connect();

  // Return cleanup function
  return () => {
    stopped = true;
    if (retryTimeout) clearTimeout(retryTimeout);
    ws?.close();
  };
}

// ── Utilities ─────────────────────────────────────────────────────────────────

/** Convert ISO startedAt to elapsed seconds for UI timer compatibility. */
function normalizeAgent(a: Agent): Agent {
  if (a.startedAt && !('elapsed' in a)) {
    const elapsed = Math.floor((Date.now() - new Date(a.startedAt).getTime()) / 1000);
    return { ...a, elapsed: Math.max(0, elapsed) };
  }
  return a;
}
