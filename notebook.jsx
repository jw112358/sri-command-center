// notebook.jsx — Tab 2: markdown notebook with sidebar
const { useState: useStateNB } = React;

function renderMarkdown(src) {
  const lines = src.split("\n");
  const out = [];
  let list = null, key = 0;
  const inline = (t) => {
    // escape, then apply inline md
    let s = t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    return s;
  };
  const flush = () => { if (list) { out.push(<ul key={key++}>{list}</ul>); list = null; } };
  lines.forEach((raw) => {
    const l = raw.replace(/\s+$/, "");
    if (/^#\s+/.test(l)) { flush(); out.push(<h1 key={key++} dangerouslySetInnerHTML={{ __html: inline(l.slice(2)) }} />); }
    else if (/^##\s+/.test(l)) { flush(); out.push(<h2 key={key++} dangerouslySetInnerHTML={{ __html: inline(l.slice(3)) }} />); }
    else if (/^>\s?/.test(l)) { flush(); out.push(<blockquote key={key++} dangerouslySetInnerHTML={{ __html: inline(l.replace(/^>\s?/, "")) }} />); }
    else if (/^[-*]\s+\[[ xX]\]\s+/.test(l)) {
      const done = /\[[xX]\]/.test(l); const txt = l.replace(/^[-*]\s+\[[ xX]\]\s+/, "");
      if (!list) list = [];
      list.push(<li key={key++}><span className={"chk" + (done ? "" : " off")}>{done ? "✓ " : "▢ "}</span><span dangerouslySetInnerHTML={{ __html: inline(txt) }} /></li>);
    }
    else if (/^[-*]\s+/.test(l) || /^\d+\.\s+/.test(l)) {
      const txt = l.replace(/^([-*]|\d+\.)\s+/, "");
      if (!list) list = [];
      list.push(<li key={key++} dangerouslySetInnerHTML={{ __html: inline(txt) }} />);
    }
    else if (l.trim() === "") { flush(); }
    else { flush(); out.push(<p key={key++} dangerouslySetInnerHTML={{ __html: inline(l) }} />); }
  });
  flush();
  return out;
}

function Notebook() {
  const [notes, setNotes] = useStateNB(() => NOTES.map((n) => ({ ...n })));
  const [selId, setSelId] = useStateNB(NOTES[0].id);
  const sel = notes.find((n) => n.id === selId) || notes[0];

  const update = (patch) => setNotes((ns) => ns.map((n) => n.id === selId ? { ...n, ...patch } : n));
  const newNote = () => {
    const id = "n" + Date.now();
    const now = new Date();
    const stamp = now.toLocaleString("en-US", { month: "short", day: "numeric" }) + " · " +
      now.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
    const note = { id, title: "Untitled", tag: "note", updated: stamp, body: "# Untitled\n\n" };
    setNotes((ns) => [note, ...ns]); setSelId(id);
  };

  return (
    <div className="nb">
      <section className="panel nb-sidebar-panel" style={{ overflow: "hidden" }}>
        <div className="panel-h"><span className="t">NOTEBOOK</span><span className="corner">{notes.length} NOTES</span></div>
        <div className="panel-body"><div className="nb-sidebar">
          <button className="btn solid nb-new" onClick={newNote}>+ NEW NOTE</button>
          {notes.map((n) => (
            <div className={"note-item" + (n.id === selId ? " sel" : "")} key={n.id} onClick={() => setSelId(n.id)}>
              <div className="nti">{n.title || "Untitled"}</div>
              <div className="ntm"><span className="ntag">#{n.tag}</span><span className="ntime">{n.updated}</span></div>
            </div>
          ))}
        </div></div>
      </section>

      <section className="panel nb-editor">
        <div className="nb-toolbar">
          <input className="nb-title-input" value={sel.title} onChange={(e) => update({ title: e.target.value })} placeholder="Untitled" />
          <span className="flabel" style={{ color: "var(--muted-2)", fontSize: 9, letterSpacing: 2 }}>{sel.updated}</span>
          <input className="nb-tag-input" value={sel.tag} onChange={(e) => update({ tag: e.target.value.replace(/^#/, "") })} placeholder="tag" />
        </div>
        <div className="nb-split">
          <textarea className="nb-text" value={sel.body} onChange={(e) => update({ body: e.target.value })} spellCheck={false} />
          <div className="nb-preview">{renderMarkdown(sel.body)}</div>
        </div>
      </section>
    </div>
  );
}

window.Notebook = Notebook;
