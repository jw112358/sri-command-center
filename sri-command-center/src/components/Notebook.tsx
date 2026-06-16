import { useState, useEffect, useRef } from 'react';
import type { Note } from '../types';
import { getNotes, getNote, createNote, patchNote } from '../api/client';
import { NOTES as MOCK_NOTES } from '../mock/data';

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

// ─── Timestamp helper ─────────────────────────────────────────────────────────
function nowStamp(): string {
  const now = new Date();
  return (
    now.toLocaleString('en-US', { month: 'short', day: 'numeric' }) +
    ' · ' +
    now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
  );
}

// ─── Notebook ─────────────────────────────────────────────────────────────────
export function Notebook() {
  const [notes, setNotes] = useState<Note[]>(MOCK_NOTES.map(n => ({ ...n })));
  const [selId, setSelId] = useState(MOCK_NOTES[0]?.id ?? '');
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const sel = notes.find(n => n.id === selId) ?? notes[0];

  // ── Boot: load from API ─────────────────────────────────────────────────
  useEffect(() => {
    let mounted = true;
    getNotes().then(ns => {
      if (!mounted || ns.length === 0) return;
      setNotes(ns.map(n => ({ ...n })));
      setSelId(ns[0].id);
    }).catch(() => { /* keep mock */ });
    return () => { mounted = false; };
  }, []);

  // ── When selection changes, load full body from API ─────────────────────
  useEffect(() => {
    if (!selId) return;
    // Only fetch if body is missing (list endpoint omits body)
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

    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      patchNote(selId, patch).catch(() => {});
    }, 500);
  };

  // ── New note ──────────────────────────────────────────────────────────────
  const newNote = () => {
    const stamp = nowStamp();
    createNote({ title: 'Untitled', tag: 'note', body: '# Untitled\n\n' })
      .then(created => {
        setNotes(prev => [{ ...created, updated: stamp }, ...prev]);
        setSelId(created.id);
      })
      .catch(() => {
        // Optimistic local fallback
        const id = 'n' + Date.now();
        const note: Note = { id, title: 'Untitled', tag: 'note', updated: stamp, body: '# Untitled\n\n' };
        setNotes(prev => [note, ...prev]);
        setSelId(id);
      });
  };

  if (!sel) return <div className="nb"><div className="empty">Loading notes…</div></div>;

  return (
    <div className="nb">
      {/* ── Sidebar ─────────────────────────────────────────────────────── */}
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
                  <span className="ntime">{n.updated}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Editor ──────────────────────────────────────────────────────── */}
      <section className="panel nb-editor">
        <div className="nb-toolbar">
          <input
            className="nb-title-input"
            value={sel.title}
            onChange={e => update({ title: e.target.value })}
            placeholder="Untitled"
          />
          <span className="flabel" style={{ color: 'var(--muted-2)', fontSize: 9, letterSpacing: 2 }}>
            {sel.updated}
          </span>
          <input
            className="nb-tag-input"
            value={sel.tag}
            onChange={e => update({ tag: e.target.value.replace(/^#/, '') })}
            placeholder="tag"
          />
        </div>
        <div className="nb-split">
          <textarea
            className="nb-text"
            value={sel.body ?? ''}
            onChange={e => update({ body: e.target.value })}
            spellCheck={false}
          />
          <div className="nb-preview">{renderMarkdown(sel.body ?? '')}</div>
        </div>
      </section>
    </div>
  );
}
