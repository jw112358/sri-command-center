import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import type { Agent, GraphNode, OSPlugin, GraphData, Selection, Tweaks, LogLine } from '../types';
import {
  getOSPlugins, getAgents, getAgentLog,
  pauseAgent, stopAgent, restartAgent, messageAgent,
  getGraph, launchOS, connectWS, markNodeComplete,
} from '../api/client';
import {
  RUNNING_AGENTS as MOCK_AGENTS,
  OS_REGISTRY as MOCK_OS,
  GRAPH_DATA as MOCK_GRAPH,
} from '../mock/data';
import { ProjectGraph } from './Graph';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtElapsed(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  if (h) return `${h}h${String(m).padStart(2, '0')}m`;
  return `${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}`;
}

function lineClass(ln: string): string {
  if (/ERROR|✗/.test(ln)) return 'err';
  if (/⚠/.test(ln)) return 'warn';
  if (/^✓|^→ cache|heartbeat|checkpoint/.test(ln)) return 'dim';
  return '';
}

// ─── LiveLog ──────────────────────────────────────────────────────────────────

interface LiveLogProps {
  agent: Agent | null;
  logLines: string[];
}

function LiveLog({ agent, logLines }: LiveLogProps) {
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = boxRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  });

  if (!agent) {
    return <div className="empty">SELECT A RUNNING AGENT TO STREAM OUTPUT</div>;
  }

  return (
    <div className="term" ref={boxRef}>
      {logLines.map((ln, i) => (
        <div className={'ln ' + lineClass(ln)} key={i}>{ln}</div>
      ))}
      {agent.status === 'RUNNING' && (
        <div className="ln"><span className="cursor"></span></div>
      )}
    </div>
  );
}

// ─── Inspector ────────────────────────────────────────────────────────────────

interface InspectorProps {
  selection: Selection;
  agentsById: Record<string, Agent>;
  osById: Record<string, OSPlugin>;
  elapsed: Record<string, number>;
  onInteract: (id: string, msg: string) => void;
  interactLog: Record<string, string[]>;
  onPause: (id: string) => void;
  onStop: (id: string) => void;
  onRestart: (id: string) => void;
  onMarkComplete: (nodeId: string) => void;
  onViewLog: (agent: Agent) => void;
}

function Inspector({
  selection, agentsById, osById, elapsed,
  onInteract, interactLog, onPause, onStop, onRestart,
  onMarkComplete, onViewLog,
}: InspectorProps) {
  const [msg, setMsg] = useState('');

  if (selection.type === 'none') {
    return (
      <div className="insp">
        <div className="empty">
          NO TARGET SELECTED<br /><br />
          Select an agent from the feed or a node from the graph to inspect.
        </div>
      </div>
    );
  }

  if (selection.type === 'node' && selection.node.kind !== 'agent') {
    const n = selection.node;
    const os = osById[n.os];
    return (
      <div className="insp">
        <div className="iname">{n.label}</div>
        <div className="irow">
          <span className={'badge ' + n.status}><span className="bd"></span>{n.status}</span>
          <span className="aos">{(n.kind || '').toUpperCase()} NODE</span>
        </div>
        <div className="field">
          <div className="flabel">PARENT OS</div>
          <div className="ftask">{os ? os.name : n.os}</div>
        </div>
        <div className="divider"></div>
        <div className="field">
          <div className="flabel">CONNECTED SKILLS</div>
          <ul className="io-list">
            <li>{n.os}.scaffold</li><li>{n.os}.review</li><li>{n.os}.sync</li>
          </ul>
        </div>
        <div className="insp-actions">
          <button className="btn sm" onClick={() => {
            // If this node has an agent, select it and scroll to log
            if (n.agentId && agentsById[n.agentId]) onViewLog(agentsById[n.agentId]);
          }}>≣ VIEW LOG</button>
          <button className="btn sm" onClick={() => onMarkComplete(n.id)}>✓ MARK COMPLETE</button>
        </div>
      </div>
    );
  }

  const a =
    selection.type === 'node'
      ? selection.node.agentId ? agentsById[selection.node.agentId] ?? null : null
      : selection.agent;

  if (!a) return <div className="insp"><div className="empty">AGENT NOT FOUND</div></div>;

  const os = osById[a.os];
  const myLog = interactLog[a.id] || [];

  const send = () => {
    if (!msg.trim()) return;
    onInteract(a.id, msg.trim());
    setMsg('');
  };

  return (
    <div className="insp">
      <div className="iname">{a.name}</div>
      <div className="irow">
        <span className={'badge ' + a.status}><span className="bd"></span>{a.status}</span>
        <span className="aos">{os ? os.name : a.os}</span>
        <span className="elapsed" style={{ marginLeft: 'auto' }}>
          ⏱ {fmtElapsed(elapsed[a.id] ?? a.elapsed ?? 0)}
        </span>
      </div>
      <div className="field">
        <div className="flabel">CURRENT TASK</div>
        <div className="ftask">{a.task}</div>
      </div>
      <div className="field">
        <div className="flabel">SKILL / COMMAND</div>
        <div className="skill">{a.skill}</div>
      </div>
      <div className="field">
        <div className="flabel">INPUTS PASSED</div>
        <ul className="io-list">{a.inputs.map((x, i) => <li key={i}>{x}</li>)}</ul>
      </div>
      <div className="field">
        <div className="flabel">OUTPUTS RETURNED</div>
        <ul className="io-list out">
          {a.outputs.map((x, i) => <li className={/ERR/.test(x) ? 'err' : ''} key={i}>{x}</li>)}
        </ul>
      </div>
      {myLog.length > 0 && (
        <div className="field">
          <div className="flabel">SESSION INTERACTIONS</div>
          <ul className="io-list">
            {myLog.map((m, i) => <li key={i} style={{ color: 'var(--gold)' }}>{m}</li>)}
          </ul>
        </div>
      )}
      <div className="divider"></div>
      <div className="insp-actions">
        <button className="btn sm" onClick={() => onViewLog(a)}>≣ VIEW LOG</button>
        <button className="btn sm" onClick={() => onPause(a.id)}>❚❚ PAUSE</button>
        <button className="btn sm danger" onClick={() => onStop(a.id)}>■ STOP</button>
        <button className="btn sm" onClick={() => onRestart(a.id)}>⟲ RESTART</button>
      </div>
      <div className="field">
        <div className="flabel">INTERACT — SEND TO RUNNING SESSION</div>
        <div className="interact">
          <input
            value={msg}
            onChange={e => setMsg(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && send()}
            placeholder={`› message ${a.name} …`}
          />
          <button className="btn solid sm" onClick={send}>SEND</button>
        </div>
      </div>
    </div>
  );
}

// ─── OS Registry sub-panel ────────────────────────────────────────────────────

interface OSRegistryProps {
  plugins: OSPlugin[];
  selAgent: Agent | null;
  onLaunch: (id: string) => void;
}

function OSRegistry({ plugins, selAgent, onLaunch }: OSRegistryProps) {
  return (
    <>
      {plugins.map(os => (
        <div className={'os-card' + (selAgent && selAgent.os === os.id ? ' sel' : '')} key={os.id}>
          <div className="top">
            <span className="name">{os.name}</span>
            <span className={'badge ' + os.status}><span className="bd"></span>{os.status}</span>
          </div>
          <div className="meta">
            {os.agents > 0 ? `${os.agents} AGENT${os.agents > 1 ? 'S' : ''} RUNNING` : 'NO ACTIVE AGENTS'}
          </div>
          <div className="actions">
            <button className="btn sm" onClick={() => onLaunch(os.id)}>▶ LAUNCH</button>
            <button className="btn sm">⚙ CONFIGURE</button>
          </div>
        </div>
      ))}
    </>
  );
}

// ─── CommandCenter (main export) ──────────────────────────────────────────────

export interface CommandCenterProps {
  layoutDir: string;
  tweaks: Tweaks;
  graphFs: boolean;
  setGraphFs: (v: boolean) => void;
  pulseSet: Set<string>;
}

export function CommandCenter({ layoutDir, tweaks, graphFs, setGraphFs, pulseSet }: CommandCenterProps) {
  // ── Live data state ──────────────────────────────────────────────────────
  const [agents, setAgents]   = useState<Agent[]>(MOCK_AGENTS);
  const [osPlugins, setOS]    = useState<OSPlugin[]>(MOCK_OS);
  const [graphData, setGraph] = useState<GraphData>(MOCK_GRAPH);
  const [logLines, setLogLines] = useState<string[]>([]);

  // ── UI state ─────────────────────────────────────────────────────────────
  const [selection, setSelection] = useState<Selection>({ type: 'agent', agent: MOCK_AGENTS[0] });
  const [elapsed, setElapsed]     = useState<Record<string, number>>(() =>
    Object.fromEntries(MOCK_AGENTS.map(a => [a.id, a.elapsed ?? 0]))
  );
  const [interactLog, setInteractLog] = useState<Record<string, string[]>>({});

  const agentsById = useMemo(
    () => Object.fromEntries(agents.map(a => [a.id, a])),
    [agents]
  );
  const osById = useMemo(
    () => Object.fromEntries(osPlugins.map(o => [o.id, o])),
    [osPlugins]
  );

  const selAgent: Agent | null =
    selection.type === 'agent'
      ? selection.agent
      : selection.type === 'node' && selection.node.agentId
      ? agentsById[selection.node.agentId] ?? null
      : null;

  // ── Initial data load ────────────────────────────────────────────────────
  useEffect(() => {
    let mounted = true;
    Promise.all([getAgents(), getOSPlugins(), getGraph()]).then(([ag, os, gd]) => {
      if (!mounted) return;
      setAgents(ag);
      setOS(os);
      setGraph(gd);
      setElapsed(Object.fromEntries(ag.map(a => [a.id, a.elapsed ?? 0])));
      if (ag.length > 0) setSelection({ type: 'agent', agent: ag[0] });
    }).catch(() => { /* keep mock data */ });
    return () => { mounted = false; };
  }, []);

  // ── Load agent log when selection changes ────────────────────────────────
  useEffect(() => {
    if (!selAgent) return;
    let mounted = true;
    getAgentLog(selAgent.id).then((lines: LogLine[]) => {
      if (!mounted) return;
      setLogLines(lines.map(l => l.text));
    }).catch(() => setLogLines([]));
    return () => { mounted = false; };
  }, [selAgent?.id]);

  // ── WebSocket: receive agent.log + agent.updated events ─────────────────
  useEffect(() => {
    const cleanup = connectWS(msg => {
      const type = msg.type as string;

      if (type === 'agent.log') {
        const agentId = msg.agent_id as string;
        const line    = msg.line as string;
        if (selAgent && agentId === selAgent.id) {
          setLogLines(prev => [...prev, line].slice(-80));
        }
      } else if (type === 'agent.updated') {
        const updated = msg.agent as Agent;
        if (!updated) return;
        setAgents(prev => prev.map(a => a.id === updated.id ? updated : a));
        setElapsed(prev => ({ ...prev, [updated.id]: updated.elapsed ?? prev[updated.id] ?? 0 }));
        if (selAgent?.id === updated.id) {
          setSelection({ type: 'agent', agent: updated });
        }
      } else if (type === 'agent.stopped') {
        const agentId = msg.agent_id as string;
        setAgents(prev => prev.map(a => a.id === agentId ? { ...a, status: 'COMPLETE' } : a));
      } else if (type === 'project.updated') {
        // Graph data may have changed — refresh
        getGraph().then(gd => setGraph(gd)).catch(() => {});
      } else if (type === 'graph.node.updated') {
        const nodeId = msg.node_id as string;
        const status = msg.status as string;
        if (nodeId && status) {
          setGraph(prev => ({
            ...prev,
            nodes: prev.nodes.map(n =>
              n.id === nodeId ? { ...n, status: status as import('../types').NodeStatus } : n
            ),
          }));
        }
      }
    });
    return cleanup;
  }, [selAgent?.id]);

  // ── Elapsed timer tick ────────────────────────────────────────────────────
  useEffect(() => {
    const iv = setInterval(() => {
      setElapsed(e => {
        const n = { ...e };
        agents.forEach(a => { if (a.status === 'RUNNING') n[a.id] = (n[a.id] || 0) + 1; });
        return n;
      });
    }, 1000);
    return () => clearInterval(iv);
  }, [agents]);

  // ── Actions ───────────────────────────────────────────────────────────────
  const handleNode = useCallback((node: GraphNode | null) => {
    if (!node) { setSelection({ type: 'none' }); return; }
    if (node.kind === 'agent' && node.agentId && agentsById[node.agentId]) {
      setSelection({ type: 'agent', agent: agentsById[node.agentId] });
    } else {
      setSelection({ type: 'node', node });
    }
  }, [agentsById]);

  const onInteract = useCallback((id: string, m: string) => {
    setInteractLog(l => ({ ...l, [id]: [...(l[id] || []), '› ' + m] }));
    setLogLines(prev => [...prev, '‹ operator: ' + m, '→ acknowledged · adjusting plan …']);
    messageAgent(id, m).catch(() => {});
  }, []);

  const onPause   = useCallback((id: string) => { pauseAgent(id).catch(() => {}); }, []);
  const onStop    = useCallback((id: string) => {
    stopAgent(id).catch(() => {});
    setAgents(prev => prev.map(a => a.id === id ? { ...a, status: 'COMPLETE' } : a));
  }, []);
  const onRestart = useCallback((id: string) => { restartAgent(id).catch(() => {}); }, []);
  const onLaunch  = useCallback((id: string) => { launchOS(id).catch(() => {}); }, []);

  // MARK COMPLETE — fires API, optimistically updates graph node, broadcasts via WS
  const onMarkComplete = useCallback((nodeId: string) => {
    markNodeComplete(nodeId).catch(() => {});
    setGraph(prev => ({
      ...prev,
      nodes: prev.nodes.map(n =>
        n.id === nodeId ? { ...n, status: 'COMPLETE' as import('../types').NodeStatus } : n
      ),
    }));
  }, []);

  // VIEW LOG — select the agent and scroll the terminal into view
  const logPanelRef = useRef<HTMLDivElement>(null);
  const onViewLog = useCallback((agent: Agent) => {
    setSelection({ type: 'agent', agent });
    setTimeout(() => {
      logPanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }, 50);
  }, []);

  // ── Stop button inline in feed row ────────────────────────────────────────
  const stopInline = useCallback((e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    onStop(id);
  }, [onStop]);

  const selectedId =
    selection.type === 'node'
      ? selection.node.id
      : selAgent ? 'agent:' + selAgent.id : null;

  const liveCount = agents.filter(a => a.status === 'RUNNING').length;

  return (
    <div className={'cc dir-' + layoutDir}>

      {/* ── OS REGISTRY ─────────────────────────────────────────────────── */}
      <section className="panel brackets area-registry">
        <div className="panel-h">
          <span className="blip"></span>
          <span className="t">OS REGISTRY</span>
          <span className="corner">{osPlugins.length} INSTALLED</span>
        </div>
        <div className="panel-body">
          <div className="registry-list">
            <OSRegistry plugins={osPlugins} selAgent={selAgent} onLaunch={onLaunch} />
          </div>
        </div>
      </section>

      {/* ── FEED + LOG ──────────────────────────────────────────────────── */}
      <section
        className="area-feed"
        style={{
          display: 'flex',
          flexDirection: layoutDir === 'graph' ? 'row' : 'column',
          gap: 14,
          minHeight: 0,
        }}
      >
        {/* Running agents list */}
        <div
          className="panel"
          style={
            layoutDir === 'graph'
              ? { flex: '0 0 420px', minHeight: 0, overflow: 'hidden' }
              : { flex: '0 0 auto', maxHeight: '44%', overflow: 'hidden' }
          }
        >
          <div className="panel-h">
            <span className="blip"></span>
            <span className="t">RUNNING AGENTS</span>
            <span className="corner">{liveCount} LIVE</span>
          </div>
          <div className="panel-body">
            <div className="feed-rows">
              {agents.map(a => (
                <div
                  className={'agent-row' + (selAgent?.id === a.id ? ' sel' : '') + (a.status === 'RUNNING' ? ' pulsing' : '')}
                  key={a.id}
                  onClick={() => setSelection({ type: 'agent', agent: a })}
                >
                  <div className="line1">
                    <span className="aname">{a.name}</span>
                    <span className="aos">
                      {(osById[a.os]?.name ?? a.os).replace(/ \(.*\)/, '')}
                    </span>
                    <span className={'badge ' + a.status} style={{ transform: 'scale(.92)' }}>
                      <span className="bd"></span>{a.status}
                    </span>
                  </div>
                  <div className="atask">{a.task}</div>
                  <div className="right">
                    <span className="elapsed">{fmtElapsed(elapsed[a.id] ?? a.elapsed ?? 0)}</span>
                    <button className="btn sm danger" onClick={e => stopInline(e, a.id)}>■ STOP</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Live terminal log */}
        <div className="panel" ref={logPanelRef} style={{ flex: '1 1 auto', minHeight: 0, overflow: 'hidden' }}>
          <div className="panel-h">
            <span className="blip"></span>
            <span className="t">AGENT LOG — LIVE OUTPUT</span>
            <span className="corner">{selAgent ? selAgent.name.toUpperCase() : '—'}</span>
          </div>
          <div className="term-wrap">
            <LiveLog agent={selAgent} logLines={logLines} />
          </div>
        </div>
      </section>

      {/* ── INSPECTOR ───────────────────────────────────────────────────── */}
      <section className="panel brackets area-inspector">
        <div className="panel-h">
          <span className="blip"></span>
          <span className="t">AGENT INSPECTOR</span>
        </div>
        <div className="panel-body">
          <Inspector
            selection={selection}
            agentsById={agentsById}
            osById={osById}
            elapsed={elapsed}
            onInteract={onInteract}
            interactLog={interactLog}
            onPause={onPause}
            onStop={onStop}
            onRestart={onRestart}
            onMarkComplete={onMarkComplete}
            onViewLog={onViewLog}
          />
        </div>
      </section>

      {/* ── GRAPH ───────────────────────────────────────────────────────── */}
      <section className={'panel graph-panel area-graph' + (graphFs ? ' fs' : '')}>
        <div className="panel-h">
          <span className="blip"></span>
          <span className="t">PROJECT GRAPH — LIVE DEV MAP</span>
          <span className="corner">
            {graphData.nodes.length} NODES · {graphData.links.length} LINKS
          </span>
        </div>
        <div className="panel-body" style={{ position: 'relative', overflow: 'hidden' }}>
          <ProjectGraph
            data={graphData}
            selectedId={selectedId}
            onSelect={handleNode}
            fullscreen={graphFs}
            onToggleFs={() => setGraphFs(!graphFs)}
            tweaks={tweaks}
            pulseSet={pulseSet}
            onMarkComplete={onMarkComplete}
            onViewLog={(node) => {
              // If the graph node has an agent, view its log; otherwise just select
              const agent = node.agentId ? agentsById[node.agentId] : null;
              if (agent) onViewLog(agent);
              else handleNode(node);
            }}
          />
        </div>
      </section>
    </div>
  );
}
