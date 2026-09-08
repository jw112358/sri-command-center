import { useEffect, useState } from 'react';

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000';
const LEGAL_SESSION_KEY = 'sri.legal.operator-session';

export interface TaskProposal {
  id: string;
  text: string;
  project: string;
  preferredSurface?: string | null;
  status: 'proposed' | 'promoted' | 'rejected';
  proposedBy: string;
  authenticatedPrincipal: string;
  proposedAt: string;
  updatedAt: string;
  promotedTaskId?: string | null;
  rejectedAt?: string | null;
}

function operatorToken(): string | null {
  try {
    const raw = window.localStorage.getItem(LEGAL_SESSION_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as { accessToken?: string; expiresAt?: string };
      if (parsed.accessToken && parsed.expiresAt && new Date(parsed.expiresAt).getTime() > Date.now()) {
        return parsed.accessToken;
      }
    }
    return window.sessionStorage.getItem(LEGAL_SESSION_KEY);
  } catch {
    return null;
  }
}

async function proposalFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = operatorToken();
  if (!token) throw new Error('Operator sign-in required');
  const headers = new Headers(init?.headers);
  headers.set('Authorization', `Bearer ${token}`);
  if (init?.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    let detail = '';
    try {
      const body = await response.json() as { detail?: string };
      detail = body.detail ? ` · ${body.detail}` : '';
    } catch { /* optional */ }
    throw new Error(`Proposal API ${response.status}${detail}`);
  }
  return response.json() as Promise<T>;
}

function fmt(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  });
}

export function TaskProposalsPanel() {
  const [rows, setRows] = useState<TaskProposal[]>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [message, setMessage] = useState('');

  const refresh = () => {
    setStatus('loading');
    proposalFetch<TaskProposal[]>('/api/tasks/proposed')
      .then(value => {
        setRows(value);
        setStatus('ready');
        setMessage('');
      })
      .catch(error => {
        setStatus('error');
        setMessage(error instanceof Error ? error.message : 'Proposal queue unavailable');
      });
  };

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 10_000);
    return () => window.clearInterval(timer);
  }, []);

  const act = (proposal: TaskProposal, action: 'promote' | 'reject') => {
    const verb = action === 'promote' ? 'promote this proposal into the executable queue' : 'reject this proposal';
    if (!window.confirm(`${verb}?\n\n${proposal.project}: ${proposal.text}`)) return;
    setStatus('loading');
    proposalFetch(`/api/tasks/proposed/${encodeURIComponent(proposal.id)}/${action}`, { method: 'POST' })
      .then(refresh)
      .catch(error => {
        setStatus('error');
        setMessage(error instanceof Error ? error.message : 'Proposal action failed');
      });
  };

  const pending = rows.filter(row => row.status === 'proposed');

  return (
    <section className="panel" style={{ marginBottom: 12 }}>
      <div className="panel-h">
        <span className="t">AGENT PROPOSALS</span>
        <span className="corner">{pending.length} AWAITING OPERATOR JUDGMENT</span>
      </div>
      <div className="panel-body" style={{ padding: 12 }}>
        {status === 'error' && <div className="empty">{message || 'PROPOSAL QUEUE UNAVAILABLE'}</div>}
        {status !== 'error' && pending.length === 0 && (
          <div className="empty">— NO AGENT PROPOSALS AWAITING REVIEW —</div>
        )}
        {pending.map(proposal => (
          <div className="task-row status-review_ready" key={proposal.id} style={{ marginBottom: 8 }}>
            <span className="task-state task-state-review_ready">PROPOSED</span>
            <div className="task-body">
              <span className="task-project">{proposal.project}</span>
              <span className="task-text">{proposal.text}</span>
              <div className="task-meta">
                <span className="task-ts">Proposed {fmt(proposal.proposedAt)} · {proposal.proposedBy}</span>
                {proposal.preferredSurface && <span className="task-ts"> · {proposal.preferredSurface}</span>}
              </div>
              <div className="task-links">
                <button className="btn solid sm" onClick={() => act(proposal, 'promote')}>
                  PROMOTE TO QUEUE
                </button>
                <button className="btn sm danger" onClick={() => act(proposal, 'reject')}>
                  REJECT
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
