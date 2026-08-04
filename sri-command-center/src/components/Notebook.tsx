import { useState, useEffect, useRef } from 'react';
import type { Note, SessionBrief, Task } from '../types';
import {
  approveTaskForShipping,
  createNote,
  createTask,
  deleteNote,
  deleteTask,
  getDashboardCapabilities,
  getNote,
  getNotes,
  getSessionBriefs,
  getTasks,
  patchNote,
  requeueTask,
  onOperatorSessionChanged,
} from '../api/client';

// ─── Markdown renderer (inline, no external dep) ──────────────────────────────
function renderMarkdown(src: string): React.ReactNode[] {
  const lines = src.split('\n');
  const out: React.ReactNode[] = [];
  let list: React.ReactNode[] | null = null;
  let key = 0;

  const inline = (t: string) => {
    let s = t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    return s;
  };

  const flush = () => {
    if (list) { out.push(<ul key={key++}>{list}</ul>); list = null; }
  };

  lines.forEach(raw => {
    const l = raw.replace(/\s+$/, '');
    if      (/^#\s+/.test(l))  { flush(); out.push(<h1 key={key++} dangerouslySetInnerHTML={{ __html: inline(l.slice(2)) }} />); }
    else if (/^##\s+/.test(l)) { flush(); out.push(<h2 key={key++} dangerouslySetInnerHTML={{ __html: inline(l.slice(3)) }} />); }
    else if (/^>\s?/.test(l))  { flush(); out.push(<blockquote key={key++} dangerouslySetInnerHTML={{ __html: inline(l.replace(/^>\s?/, '')) }} />); }
    else if (/^[-*]\s+\[[ xX]\]\s+/.test(l)) {
      const done = /\[[xX]\]/.test(l);
      const txt  = l.replace(/^[-*]\s+\[[ xX]\]\s+/, '');
      if (!list) list = [];
      list.push(
        <li key={key++}>
          <span className={'chk' + (done ? '' : ' off')}>{done ? '✓ ' : '▢ '}</span>
          <span dangerouslySetInnerHTML={{ __html: inline(txt) }} />
        </li>
      );
    } else if (/^[-*]\s+/.test(l) || /^\d+\.\s+/.test(l)) {
      const txt = l.replace(/^([-*]|\d+\.)\s+/, '');
      if (!list) list = [];
      list.push(<li key={key++} dangerouslySetInnerHTML={{ __html: inline(txt) }} />);
    } else if (l.trim() === '') {
      flush();
    } else {
      flush();
      out.push(<p key={key++} dangerouslySetInnerHTML={{ __html: inline(l) }} />);
    }
  });
  flush();
  return out;
}

// ─── Timestamp helpers ────────────────────────────────────────────────────────
function nowStamp(): string {
  const now = new Date();
  return (
    now.toLocaleString('en-US', { month: 'short', day: 'numeric' }) +
    ' · ' +
    now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
  );
}

function fmtISO(iso: string): string {
  const d = new Date(iso);
  return (
    d.toLocaleString('en-US', { month: 'short', day: 'numeric' }) +
    ' · ' +
    d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
  );
}

// ─── TasksPanel ───────────────────────────────────────────────────────────────
function TasksPanel() {
  const [tasks, setTasks]   = useState<Task[]>([]);
  const [input, setInput]   = useState('');
  const [project, setProject] = useState('Master Builder');
  const [filter, setFilter] = useState<'all' | 'active' | 'review' | 'done'>('all');
  const [status, setStatus] = useState<'ready' | 'saving' | 'error'>('ready');
  const [runnerReady, setRunnerReady] = useState(false);
  const [maxConcurrent, setMaxConcurrent] = useState(4);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let mounted = true;
    const refresh = () => {
      Promise.allSettled([getTasks(), getDashboardCapabilities()]).then(([taskResult, capabilityResult]) => {
        if (!mounted) return;
        if (taskResult.status === 'fulfilled') {
          setTasks(taskResult.value);
          setStatus('ready');
        } else {
          setStatus('error');
        }
        if (capabilityResult.status === 'fulfilled') {
          setRunnerReady(capabilityResult.value.taskOrchestrationEnabled);
          setMaxConcurrent(capabilityResult.value.maxConcurrentTasks);
        }
      });
    };
    refresh();
    const interval = window.setInterval(refresh, 10_000);
    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, []);

  const addTask = () => {
    const text = input.trim();
    if (!text) return;
    setStatus('saving');
    createTask({ text, project: project.trim() || 'Master Builder' }).then(task => {
      setTasks(current => [task, ...current]);
      setInput('');
      setStatus('ready');
      inputRef.current?.focus();
    }).catch(() => setStatus('error'));
  };

  const approveAndShip = (task: Task) => {
    if (!window.confirm(
      `Approve the reviewed action for “${task.text}” and authorize its production/external shipping step?`,
    )) return;
    setStatus('saving');
    approveTaskForShipping(task.id).then(updated => {
      setTasks(current => current.map(item => item.id === task.id ? updated : item));
      setStatus('ready');
    }).catch(() => setStatus('error'));
  };

  const requeue = (task: Task) => {
    setStatus('saving');
    requeueTask(task.id).then(updated => {
      setTasks(current => current.map(item => item.id === task.id ? updated : item));
      setStatus('ready');
    }).catch(() => setStatus('error'));
  };

  const remove = (id: string) => {
    setStatus('saving');
    deleteTask(id).then(() => {
      setTasks(current => current.filter(item => item.id !== id));
      setStatus('ready');
    }).catch(() => setStatus('error'));
  };

  const visible = tasks.filter(task => {
    if (filter === 'all') return true;
    if (filter === 'active') return ['queued', 'running', 'shipping'].includes(task.status);
    if (filter === 'review') return ['review_ready', 'blocked'].includes(task.status);
    return task.status === 'completed';
  });

  const activeCount = tasks.filter(task => (
    ['running', 'review_ready', 'shipping'].includes(task.status)
  )).length;
  const queuedCount = tasks.filter(task => task.status === 'queued').length;
  const reviewCount = tasks.filter(task => task.status === 'review_ready').length;

  return (
    <div className="tasks-panel">
      {/* Header row */}
      <div className="tasks-head">
        <span className="tasks-title">TASKS</span>
        <span className="badge ACTIVE"><span className="bd"></span>{activeCount} / {maxConcurrent} ACTIVE</span>
        <span className="badge IDLE"><span className="bd"></span>{queuedCount} QUEUED</span>
        <span className="badge BLOCKED"><span className="bd"></span>{reviewCount} REVIEW READY</span>
        <div className="tasks-filters">
          {(['all', 'active', 'review', 'done'] as const).map(f => (
            <button
              key={f}
              className={'btn sm' + (filter === f ? ' solid' : '')}
              onClick={() => setFilter(f)}
            >
              {f.toUpperCase()}
            </button>
          ))}
        </div>
        <span className={'nb-save-state ' + status}>
          {status === 'saving'
            ? 'SAVING…'
            : status === 'error'
              ? 'SIGN IN / STORAGE REQUIRED'
              : runnerReady
                ? 'ORCHESTRATOR ONLINE'
                : 'QUEUE READY · RUNNER NOT CONNECTED'}
        </span>
      </div>

      {/* Add task input */}
      <div className="tasks-add">
        <input
          className="tasks-project-input"
          value={project}
          onChange={event => setProject(event.target.value)}
          placeholder="Project / build"
          aria-label="Project or build"
        />
        <input
          ref={inputRef}
          className="tasks-input"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && addTask()}
          placeholder="Describe the outcome to build and ship…"
        />
        <button className="btn solid sm" onClick={addTask}>+ QUEUE TASK</button>
      </div>
      {!runnerReady && (
        <div className="tasks-runner-notice">
          Tasks can be recorded, but autonomous pickup remains paused until the trusted
          SRI Orchestrator runner token is connected.
        </div>
      )}

      {/* Task list */}
      <div className="tasks-list">
        {visible.length === 0 && (
          <div className="empty" style={{ padding: '24px 0', textAlign: 'center' }}>— NO TASKS —</div>
        )}
        {visible.map(t => (
          <div className={'task-row status-' + t.status + (t.done ? ' done' : '')} key={t.id}>
            <span className={'task-state task-state-' + t.status}>
              {t.status.replace(/_/g, ' ').toUpperCase()}
            </span>
            <div className="task-body">
              <span className="task-project">{t.project}</span>
              <span className="task-text">{t.text}</span>
              <div className="task-meta">
                <span className="task-ts">Added {fmtISO(t.createdAt)}</span>
                {t.assignedAgent && <span className="task-ts"> · {t.assignedAgent}</span>}
                {t.status === 'completed' && t.completedAt && (
                  <span className="task-ts done-ts"> · Done {fmtISO(t.completedAt)}</span>
                )}
              </div>
              {t.lastError && <p className="task-error">{t.lastError}</p>}
              <div className="task-links">
                {t.reviewUrl && (
                  <a className="btn sm" href={t.reviewUrl} target="_blank" rel="noreferrer">
                    OPEN REVIEW ↗
                  </a>
                )}
                {t.summaryId && <span>SESSION SUMMARY FILED</span>}
                {t.status === 'review_ready' && (
                  <button className="btn solid sm" onClick={() => approveAndShip(t)}>
                    APPROVE &amp; SHIP
                  </button>
                )}
                {t.status === 'blocked' && (
                  <button className="btn sm" onClick={() => requeue(t)}>REQUEUE</button>
                )}
              </div>
            </div>
            {['queued', 'blocked', 'completed'].includes(t.status) && (
              <button
                className="btn sm danger task-del"
                onClick={() => remove(t.id)}
                title="Delete"
              >✕</button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── SessionBriefsPanel ──────────────────────────────────────────────────────
function SessionBriefsPanel() {
  const [briefs, setBriefs] = useState<SessionBrief[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [writeReady, setWriteReady] = useState(false);

  useEffect(() => {
    let mounted = true;
    const refresh = () => {
      Promise.allSettled([getSessionBriefs(), getDashboardCapabilities()]).then(([briefResult, capabilityResult]) => {
        if (!mounted) return;
        if (briefResult.status === 'fulfilled') {
          const items = briefResult.value;
          setBriefs(items);
          setSelectedId(current => items.some(item => item.id === current) ? current : items[0]?.id ?? '');
          setError('');
        } else {
          const message = briefResult.reason instanceof Error ? briefResult.reason.message : '';
          setError(
            /authorization|authentication|not configured|session expired/i.test(message)
              ? 'SIGN IN ON LEGAL AGENT OS TO VIEW PRIVATE SESSION BRIEFS'
              : 'SESSION BRIEFS ARE TEMPORARILY UNAVAILABLE',
          );
        }
        if (capabilityResult.status === 'fulfilled') {
          setWriteReady(capabilityResult.value.sessionSummaryWriteEnabled);
        }
        setLoading(false);
      });
    };
    refresh();
    const interval = window.setInterval(refresh, 60_000);
    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, []);

  const normalizedQuery = query.trim().toLowerCase();
  const visible = briefs.filter(brief => (
    !normalizedQuery
    || brief.project.toLowerCase().includes(normalizedQuery)
    || brief.title.toLowerCase().includes(normalizedQuery)
    || brief.summary.toLowerCase().includes(normalizedQuery)
  ));
  const selected = visible.find(item => item.id === selectedId) ?? visible[0];

  return (
    <div className="session-briefs">
      <section className="panel session-brief-list-panel">
        <div className="panel-h">
          <span className="t">SESSION BRIEFS</span>
          <span className="corner">
            {briefs.length} INDEXED · {writeReady ? 'AUTO-INGEST READY' : 'INGEST SETUP REQUIRED'}
          </span>
        </div>
        {!writeReady && (
          <div className="session-ingest-notice">
            The index is readable, but new cross-surface summaries cannot be filed until
            the Drive write grant is enabled.
          </div>
        )}
        <div className="session-brief-search">
          <input
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="Search projects, builds, or outcomes…"
          />
        </div>
        <div className="session-brief-list">
          {visible.map(brief => (
            <button
              type="button"
              key={brief.id}
              className={'session-brief-item' + (selected?.id === brief.id ? ' selected' : '')}
              onClick={() => setSelectedId(brief.id)}
            >
              <strong>{brief.project}</strong>
              <span>{brief.title}</span>
              <small>{brief.date} · {brief.surface}</small>
            </button>
          ))}
          {!loading && visible.length === 0 && (
            <div className="empty">{error || '— NO SESSION BRIEFS FOUND —'}</div>
          )}
          {loading && <div className="empty">READING PLATFORM SUMMARIES…</div>}
        </div>
      </section>

      <section className="panel session-brief-detail">
        {selected ? (
          <>
            <div className="panel-h">
              <span className="t">{selected.project.toUpperCase()}</span>
              <span className="corner">{selected.sessionId}</span>
            </div>
            <div className="session-brief-body">
              <div className="session-brief-meta">
                <span>{selected.date}</span>
                <span>{selected.surface}</span>
                <span>{selected.status.replace(/-/g, ' ')}</span>
                {selected.taskId && <span>{selected.taskId}</span>}
              </div>
              <h2>{selected.title}</h2>
              <div className="session-brief-section">
                <span>CONCISE OUTCOME</span>
                <p>{selected.summary}</p>
              </div>
              {selected.currentState && (
                <div className="session-brief-section">
                  <span>CURRENT STATE</span>
                  <p>{selected.currentState}</p>
                </div>
              )}
              <div className="session-next-start">
                <span>BEGIN NEXT SESSION HERE</span>
                <p>{selected.nextStart}</p>
              </div>
              <a
                className="btn solid session-source-link"
                href={selected.sourceUrl}
                target="_blank"
                rel="noreferrer"
              >
                OPEN FULL DRIVE SUMMARY ↗
              </a>
            </div>
          </>
        ) : (
          <div className="empty session-brief-empty">
            {error || 'Session briefs appear when the canonical Platform summary folder is connected.'}
          </div>
        )}
      </section>
    </div>
  );
}

// ─── Notebook ─────────────────────────────────────────────────────────────────
export function Notebook() {
  const [tab, setTab]         = useState<'notes' | 'tasks' | 'briefs'>('notes');
  const [notes, setNotes]     = useState<Note[]>([]);
  const [selId, setSelId]     = useState('');
  const [saveState, setSaveState] = useState<'saved' | 'saving' | 'error'>('saved');
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [authVersion, setAuthVersion] = useState(0);

  useEffect(() => onOperatorSessionChanged(
    () => setAuthVersion(current => current + 1),
  ), []);

  const sel = notes.find(n => n.id === selId) ?? notes[0];

  // ── Live notes: Legal OS lifecycle notes arrive through the API ─────────
  useEffect(() => {
    let mounted = true;
    const refresh = () => {
      getNotes().then(ns => {
        if (!mounted) return;
        setNotes(previous => ns.map(note => {
          const existing = previous.find(item => item.id === note.id);
          return {
            ...existing,
            ...note,
            body: note.body ?? existing?.body ?? '',
          };
        }));
        setSelId(current => ns.some(note => note.id === current) ? current : ns[0]?.id ?? '');
      }).catch(() => { /* keep current notes */ });
    };
    refresh();
    const interval = window.setInterval(refresh, 5_000);
    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, [authVersion]);

  // ── When selection changes, load full body from API ─────────────────────
  useEffect(() => {
    if (!selId) return;
    const current = notes.find(n => n.id === selId);
    if (current?.body) return;
    let mounted = true;
    getNote(selId).then(full => {
      if (!mounted || !full) return;
      setNotes(prev => prev.map(n => n.id === selId ? { ...n, ...full } : n));
    }).catch(() => {});
    return () => { mounted = false; };
  }, [selId]);

  // ── Local update + debounced API patch ────────────────────────────────────
  const update = (patch: Partial<Note>) => {
    setNotes(ns => ns.map(n => n.id === selId ? { ...n, ...patch, updated: nowStamp() } : n));
    setSaveState('saving');
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      patchNote(selId, patch)
        .then(updated => {
          setNotes(current => current.map(note => note.id === selId ? { ...note, ...updated } : note));
          setSaveState('saved');
        })
        .catch(() => setSaveState('error'));
    }, 500);
  };

  // ── New note ──────────────────────────────────────────────────────────────
  const newNote = () => {
    const stamp = nowStamp();
    setSaveState('saving');
    createNote({ title: 'Untitled', tag: 'note', body: '# Untitled\n\n' })
      .then(created => {
        setNotes(prev => [{ ...created, updated: stamp }, ...prev]);
        setSelId(created.id);
        setSaveState('saved');
      })
      .catch(() => setSaveState('error'));
  };

  const readOnlyActivity = sel?.tag === 'legal-os';

  const removeSelectedNote = () => {
    if (!sel || readOnlyActivity) return;
    setSaveState('saving');
    deleteNote(sel.id).then(() => {
      setNotes(current => current.filter(note => note.id !== sel.id));
      setSelId(current => current === sel.id ? '' : current);
      setSaveState('saved');
    }).catch(() => setSaveState('error'));
  };

  return (
    <div className="nb">
      {/* ── Tab bar ──────────────────────────────────────────────────────── */}
      <div className="nb-tabs">
        <button
          className={'nb-tab' + (tab === 'notes' ? ' active' : '')}
          onClick={() => setTab('notes')}
        >
          ≣ NOTES
        </button>
        <button
          className={'nb-tab' + (tab === 'tasks' ? ' active' : '')}
          onClick={() => setTab('tasks')}
        >
          ✓ TASKS
        </button>
        <button
          className={'nb-tab' + (tab === 'briefs' ? ' active' : '')}
          onClick={() => setTab('briefs')}
        >
          ↻ SESSION BRIEFS
        </button>
      </div>

      {/* ── TASKS tab ────────────────────────────────────────────────────── */}
      {tab === 'tasks' && (
        <div className="nb-tasks-wrap">
          <TasksPanel key={`tasks-${authVersion}`} />
        </div>
      )}

      {tab === 'briefs' && <SessionBriefsPanel key={`briefs-${authVersion}`} />}

      {/* ── NOTES tab ────────────────────────────────────────────────────── */}
      {tab === 'notes' && (
        <div className="nb-notes-row">
          {/* Sidebar */}
          <section className="panel nb-sidebar-panel" style={{ overflow: 'hidden' }}>
            <div className="panel-h">
              <span className="t">NOTEBOOK</span>
              <span className="corner">{notes.length} NOTES</span>
            </div>
            <div className="panel-body">
              <div className="nb-sidebar">
                <button className="btn solid nb-new" onClick={newNote}>+ NEW NOTE</button>
                {notes.map(n => (
                  <div
                    className={'note-item' + (n.id === selId ? ' sel' : '')}
                    key={n.id}
                    onClick={() => setSelId(n.id)}
                  >
                    <div className="nti">{n.title || 'Untitled'}</div>
                    <div className="ntm">
                      <span className="ntag">#{n.tag}</span>
                      <span className="ntime">
                        {n.updated ?? (n.updatedAt ? fmtISO(n.updatedAt) : '—')}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* Editor */}
          {sel && (
            <section className="panel nb-editor">
              <div className="nb-toolbar">
                <input
                  className="nb-title-input"
                  value={sel.title}
                  onChange={e => {
                    if (!readOnlyActivity) update({ title: e.target.value });
                  }}
                  readOnly={readOnlyActivity}
                  placeholder="Untitled"
                />
                <span className="flabel" style={{ color: 'var(--muted-2)', fontSize: 9, letterSpacing: 2 }}>
                  {readOnlyActivity
                    ? 'AUTOMATED · READ ONLY'
                    : saveState === 'saving'
                      ? 'SAVING TO DRIVE…'
                      : saveState === 'error'
                        ? 'SIGN IN / STORAGE REQUIRED'
                        : 'DRIVE SYNCED'}
                </span>
                <input
                  className="nb-tag-input"
                  value={sel.tag}
                  onChange={e => {
                    if (!readOnlyActivity) update({ tag: e.target.value.replace(/^#/, '') });
                  }}
                  readOnly={readOnlyActivity}
                  placeholder="tag"
                />
                {!readOnlyActivity && (
                  <button
                    type="button"
                    className="btn sm danger"
                    onClick={removeSelectedNote}
                  >
                    DELETE
                  </button>
                )}
              </div>
              <div className="nb-split">
                <textarea
                  className="nb-text"
                  value={sel.body ?? ''}
                  onChange={e => {
                    if (!readOnlyActivity) update({ body: e.target.value });
                  }}
                  readOnly={readOnlyActivity}
                  spellCheck={false}
                />
                <div className="nb-preview">{renderMarkdown(sel.body ?? '')}</div>
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
