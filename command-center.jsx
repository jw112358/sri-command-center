// command-center.jsx — Tab 1: registry · agent feed + live log · inspector · graph
const { useState: useStateCC, useEffect: useEffectCC, useRef: useRefCC, useMemo: useMemoCC } = React;

function fmtElapsed(s) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
  if (h) return `${h}h${String(m).padStart(2, "0")}m`;
  return `${String(m).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
}

function LiveLog({ agent, logRef }) {
  const boxRef = useRefCC(null);
  const [, force] = useStateCC(0);

  useEffectCC(() => {
    if (!agent) return;
    const id = agent.id;
    if (!logRef.current[id]) logRef.current[id] = (AGENT_LOG_SEEDS[id] || []).slice();
    force((n) => n + 1); // show seed lines immediately
    if (agent.status === "ERROR") { return; }
    const iv = setInterval(() => {
      const buf = logRef.current[id];
      const frag = LOG_FRAGMENTS[Math.floor(Math.random() * LOG_FRAGMENTS.length)]
        .replace("{n}", Math.floor(Math.random() * 900) + 10)
        .replace("{pkg}", ["three", "react-dom", "zod", "vite", "esbuild", "postiz-sdk"][Math.floor(Math.random()*6)]);
      buf.push(frag);
      if (buf.length > 80) buf.shift();
      force((n) => n + 1);
    }, 1100 + Math.random() * 700);
    return () => clearInterval(iv);
  }, [agent && agent.id, agent && agent.status]);

  useEffectCC(() => {
    const el = boxRef.current; if (el) el.scrollTop = el.scrollHeight;
  });

  if (!agent) return <div className="empty">SELECT A RUNNING AGENT TO STREAM OUTPUT</div>;
  const lines = logRef.current[agent.id] || [];
  return (
    <div className="term" ref={boxRef}>
      {lines.map((ln, i) => {
        const cls = /ERROR|✗/.test(ln) ? "err" : /⚠/.test(ln) ? "warn" : /^✓|^→ cache|heartbeat|checkpoint/.test(ln) ? "dim" : "";
        return <div className={"ln " + cls} key={i}>{ln}</div>;
      })}
      {agent.status !== "ERROR" && <div className="ln"><span className="cursor"></span></div>}
    </div>
  );
}

function Inspector({ selection, agentsById, elapsed, onInteract, interactLog }) {
  const [msg, setMsg] = useStateCC("");
  if (!selection) return (
    <div className="insp"><div className="empty">NO TARGET SELECTED<br/><br/>Select an agent from the feed or a node from the graph to inspect.</div></div>
  );

  if (selection.type === "node" && selection.node.kind !== "agent") {
    const n = selection.node, os = OS_BY_ID[n.os];
    return (
      <div className="insp">
        <div className="iname">{n.label}</div>
        <div className="irow"><span className={"badge " + n.status}><span className="bd"></span>{n.status}</span>
          <span className="aos">{(n.kind || "").toUpperCase()} NODE</span></div>
        <div className="field"><div className="flabel">PARENT OS</div><div className="ftask">{os ? os.name : n.os}</div></div>
        <div className="divider"></div>
        <div className="field"><div className="flabel">CONNECTED SKILLS</div>
          <ul className="io-list"><li>{n.os}.scaffold</li><li>{n.os}.review</li><li>{n.os}.sync</li></ul></div>
        <div className="insp-actions">
          <button className="btn sm">▶ OPEN</button>
          <button className="btn sm">≣ VIEW LOG</button>
          <button className="btn sm">✓ MARK COMPLETE</button>
        </div>
      </div>
    );
  }

  const a = selection.type === "node" ? agentsById[selection.node.agentId] : selection.agent;
  if (!a) return <div className="insp"><div className="empty">AGENT NOT FOUND</div></div>;
  const os = OS_BY_ID[a.os];
  const myLog = interactLog[a.id] || [];

  const send = () => { if (!msg.trim()) return; onInteract(a.id, msg.trim()); setMsg(""); };

  return (
    <div className="insp">
      <div className="iname">{a.name}</div>
      <div className="irow">
        <span className={"badge " + a.status}><span className="bd"></span>{a.status}</span>
        <span className="aos">{os ? os.name : a.os}</span>
        <span className="elapsed" style={{ marginLeft: "auto" }}>⏱ {fmtElapsed(elapsed[a.id] || a.elapsed)}</span>
      </div>

      <div className="field"><div className="flabel">CURRENT TASK</div><div className="ftask">{a.task}</div></div>
      <div className="field"><div className="flabel">SKILL / COMMAND</div><div className="skill">{a.skill}</div></div>

      <div className="field"><div className="flabel">INPUTS PASSED</div>
        <ul className="io-list">{a.inputs.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
      <div className="field"><div className="flabel">OUTPUTS RETURNED</div>
        <ul className="io-list out">{a.outputs.map((x, i) => <li className={/ERR/.test(x) ? "err" : ""} key={i}>{x}</li>)}</ul></div>

      {myLog.length > 0 && (
        <div className="field"><div className="flabel">SESSION INTERACTIONS</div>
          <ul className="io-list">{myLog.map((m, i) => <li key={i} style={{ color: "var(--gold)" }}>{m}</li>)}</ul></div>
      )}

      <div className="divider"></div>
      <div className="insp-actions">
        <button className="btn sm">≣ VIEW FULL TRANSCRIPT</button>
        <button className="btn sm">❚❚ PAUSE</button>
        <button className="btn sm danger">■ STOP</button>
        <button className="btn sm">⟲ RESTART</button>
      </div>
      <div className="field"><div className="flabel">INTERACT — SEND TO RUNNING SESSION</div>
        <div className="interact">
          <input value={msg} onChange={(e) => setMsg(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder={"› message " + a.name + " …"} />
          <button className="btn solid sm" onClick={send}>SEND</button>
        </div>
      </div>
    </div>
  );
}

function CommandCenter({ layoutDir, tweaks, graphFs, setGraphFs, pulseSet }) {
  const [selection, setSelection] = useStateCC({ type: "agent", agent: RUNNING_AGENTS[0] });
  const [elapsed, setElapsed] = useStateCC(() => Object.fromEntries(RUNNING_AGENTS.map((a) => [a.id, a.elapsed])));
  const [interactLog, setInteractLog] = useStateCC({});
  const logRef = useRefCC({});
  const agentsById = useMemoCC(() => Object.fromEntries(RUNNING_AGENTS.map((a) => [a.id, a])), []);

  // elapsed ticker
  useEffectCC(() => {
    const iv = setInterval(() => setElapsed((e) => {
      const n = { ...e };
      RUNNING_AGENTS.forEach((a) => { if (a.status === "RUNNING") n[a.id] = (n[a.id] || 0) + 1; });
      return n;
    }), 1000);
    return () => clearInterval(iv);
  }, []);

  const selAgent = selection.type === "agent" ? selection.agent
    : (selection.node && selection.node.agentId ? agentsById[selection.node.agentId] : null);

  const handleNode = (node) => {
    if (!node) { setSelection({ type: "none" }); return; }
    if (node.kind === "agent" && agentsById[node.agentId]) setSelection({ type: "agent", agent: agentsById[node.agentId] });
    else setSelection({ type: "node", node });
  };

  const onInteract = (id, m) => {
    setInteractLog((l) => ({ ...l, [id]: [...(l[id] || []), "› " + m] }));
    if (!logRef.current[id]) logRef.current[id] = (AGENT_LOG_SEEDS[id] || []).slice();
    logRef.current[id].push("‹ operator: " + m, "→ acknowledged · adjusting plan …");
  };

  return (
    <div className={"cc dir-" + layoutDir}>
      {/* REGISTRY */}
      <section className="panel brackets area-registry">
        <div className="panel-h"><span className="blip"></span><span className="t">OS REGISTRY</span><span className="corner">{OS_REGISTRY.length} INSTALLED</span></div>
        <div className="panel-body"><div className="registry-list">
          {OS_REGISTRY.map((os) => (
            <div className={"os-card" + (selAgent && selAgent.os === os.id ? " sel" : "")} key={os.id}>
              <div className="top">
                <span className="name">{os.name}</span>
                <span className={"badge " + os.status}><span className="bd"></span>{os.status}</span>
              </div>
              <div className="meta">{os.agents > 0 ? `${os.agents} AGENT${os.agents>1?"S":""} RUNNING` : "NO ACTIVE AGENTS"}</div>
              <div className="actions">
                <button className="btn sm">▶ LAUNCH</button>
                <button className="btn sm">⚙ CONFIGURE</button>
              </div>
            </div>
          ))}
        </div></div>
      </section>

      {/* FEED + LOG — vertical for classic/focus, horizontal strip for graph-first */}
      <section className="area-feed" style={{ display: "flex",
          flexDirection: layoutDir === "graph" ? "row" : "column", gap: 14, minHeight: 0 }}>
        <div className="panel" style={layoutDir === "graph"
            ? { flex: "0 0 420px", minHeight: 0 }
            : { flex: "0 0 auto", maxHeight: "44%" }}>
          <div className="panel-h"><span className="blip"></span><span className="t">RUNNING AGENTS</span>
            <span className="corner">{RUNNING_AGENTS.filter(a=>a.status==="RUNNING").length} LIVE</span></div>
          <div className="panel-body"><div className="feed-rows">
            {RUNNING_AGENTS.map((a) => (
              <div className={"agent-row" + (selAgent && selAgent.id === a.id ? " sel" : "") + (a.status === "RUNNING" ? " pulsing" : "")}
                key={a.id} onClick={() => setSelection({ type: "agent", agent: a })}>
                <div className="line1">
                  <span className="aname">{a.name}</span>
                  <span className="aos">{OS_BY_ID[a.os].name.replace(/ \(.*\)/, "")}</span>
                  <span className={"badge " + a.status} style={{ transform: "scale(.92)" }}><span className="bd"></span>{a.status}</span>
                </div>
                <div className="atask">{a.task}</div>
                <div className="right">
                  <span className="elapsed">{fmtElapsed(elapsed[a.id] || a.elapsed)}</span>
                  <button className="btn sm danger" onClick={(e) => e.stopPropagation()}>■ STOP</button>
                </div>
              </div>
            ))}
          </div></div>
        </div>
        <div className="panel" style={{ flex: "1 1 auto", minHeight: 0 }}>
          <div className="panel-h"><span className="blip"></span><span className="t">AGENT LOG — LIVE OUTPUT</span>
            <span className="corner">{selAgent ? selAgent.name.toUpperCase() : "—"}</span></div>
          <div className="term-wrap"><LiveLog agent={selAgent} logRef={logRef} /></div>
        </div>
      </section>

      {/* INSPECTOR */}
      <section className="panel brackets area-inspector">
        <div className="panel-h"><span className="blip"></span><span className="t">AGENT INSPECTOR</span></div>
        <div className="panel-body">
          <Inspector selection={selection} agentsById={agentsById} elapsed={elapsed}
            onInteract={onInteract} interactLog={interactLog} />
        </div>
      </section>

      {/* GRAPH (+ optional log when graph-first layout) */}
      <section className={"panel graph-panel area-graph" + (graphFs ? " fs" : "")}>
        <div className="panel-h"><span className="blip"></span><span className="t">PROJECT GRAPH — LIVE DEV MAP</span>
          <span className="corner">{GRAPH_DATA.nodes.length} NODES · {GRAPH_DATA.links.length} LINKS</span></div>
        <div className="panel-body" style={{ position: "relative", overflow: "hidden" }}>
          <ProjectGraph data={GRAPH_DATA} selectedId={
              selection.type === "node" ? selection.node.id
              : selAgent ? "agent:" + selAgent.id : null}
            onSelect={handleNode} fullscreen={graphFs} onToggleFs={() => setGraphFs(!graphFs)}
            tweaks={tweaks} pulseSet={pulseSet} />
        </div>
      </section>
    </div>
  );
}

window.CommandCenter = CommandCenter;
