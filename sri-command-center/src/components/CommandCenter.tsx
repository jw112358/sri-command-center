import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import type {
  Agent,
  DashboardCapabilities,
  GraphNode,
  OSPlugin,
  GraphData,
  LegalAssignmentSummary,
  Selection,
  Tweaks,
  LogLine,
} from '../types';
import {
  getOSPlugins, getAgents, getAgentLog,
  pauseAgent, stopAgent, restartAgent, messageAgent,
  getDashboardCapabilities, getGraph, getLegalAssignments, launchOS, connectWS, markNodeComplete,
} from '../api/client';
import { ProjectGraph } from './Graph';

const EMPTY_CAPABILITIES: DashboardCapabilities = {
  operatorAuthConfigured: false,
  driveReadConnected: false,
  dashboardPersistenceEnabled: false,
  commandDispatchEnabled: false,
  taskOrchestrationEnabled: false,
  sessionSummaryWriteEnabled: false,
  maxConcurrentTasks: 4,
};

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

function fmtActivityTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
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
  controlsEnabled: boolean;
}

function Inspector({
  selection, agentsById, osById, elapsed,
  onInteract, interactLog, onPause, onStop, onRestart,
  onMarkComplete, onViewLog, controlsEnabled,
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
          <button
            className="btn sm"
            disabled={!controlsEnabled}
            title={controlsEnabled ? 'Mark this node complete' : 'Command adapter is not connected'}
            onClick={() => onMarkComplete(n.id)}
          >
            ✓ MARK COMPLETE
          </button>
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
        <button className="btn sm" disabled={!controlsEnabled} onClick={() => onPause(a.id)}>❚❚ PAUSE</button>
        <button className="btn sm danger" disabled={!controlsEnabled} onClick={() => onStop(a.id)}>■ STOP</button>
        <button className="btn sm" disabled={!controlsEnabled} onClick={() => onRestart(a.id)}>⟲ RESTART</button>
      </div>
      <div className="field">
        <div className="flabel">INTERACT — SEND TO RUNNING SESSION</div>
        <div className="interact">
          <input
            value={msg}
            disabled={!controlsEnabled}
            onChange={e => setMsg(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && send()}
            placeholder={`› message ${a.name} …`}
          />
          <button className="btn solid sm" disabled={!controlsEnabled} onClick={send}>SEND</button>
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
  controlsEnabled: boolean;
}

function OSRegistry({ plugins, selAgent, onLaunch, controlsEnabled }: OSRegistryProps) {
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
            <button
              className="btn sm"
              disabled={!controlsEnabled}
              title={controlsEnabled ? 'Launch this OS' : 'Command adapter is not connected'}
              onClick={() => onLaunch(os.id)}
            >
              ▶ LAUNCH
            </button>
            <button
              className="btn sm"
              type="button"
              title="Configuration becomes available when the OS exposes a verified settings adapter."
              onClick={() => window.alert(
                `${os.name} configuration is not exposed yet. No settings were changed.`,
              )}
            >
              ⚙ CONFIG STATUS
            </button>
          </div>
        </div>
      ))}
    </>
  );
}

function LegalAssignmentsPanel({ assignments }: { assignments: LegalAssignmentSummary[] }) {
  const runningCount = assignments.filter(item => item.status === 'running').length;
  return (
    <>
      <div className="panel-h">
        <span className="blip"></span>
        <span className="t">LEGAL ASSIGNMENTS</span>
        <span className="corner">{runningCount} ACTIVE · {assignments.length} RECENT</span>
      </div>
      <div className="panel-body legal-assignment-list">
        {assignments.length === 0 ? (
          <div className="legal-assignment-empty">
            NO LEGAL ASSIGNMENTS STARTED
            <small>Assignments appear here when the Legal OS acquires a work slot.</small>
          </div>
        ) : assignments.slice(0, 8).map(assignment => {
          const displayStage = (
            assignment.status === 'completed'
              ? assignment.outcomeStatus ?? assignment.stage
              : assignment.stage
          ).replace(/_/g, ' ').toUpperCase();
          const activityAt = assignment.completedAt ?? assignment.startedAt;
          return (
            <div className="legal-assignment-row" key={assignment.assignmentId}>
              <span className="legal-assignment-id">
                <strong>{assignment.matterId}</strong>
                <small>{assignment.assignmentId}</small>
              </span>
              <span className="legal-assignment-stage">{displayStage}</span>
              <span className={'badge ' + (assignment.status === 'running' ? 'RUNNING' : 'COMPLETE')}>
                <span className="bd"></span>
                {assignment.status.toUpperCase()}
              </span>
              <time dateTime={activityAt}>{fmtActivityTime(activityAt)}</time>
            </div>
          );
        })}
      </div>
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
  const [agents, setAgents]   = useState<Agent[]>([]);
  const [osPlugins, setOS]    = useState<OSPlugin[]>([]);
  const [graphData, setGraph] = useState<GraphData>({ nodes: [], links: [] });
  const [legalAssignments, setLegalAssignments] = useState<LegalAssignmentSummary[]>([]);
  const [logLines, setLogLines] = useState<string[]>([]);
  const [capabilities, setCapabilities] = useState<DashboardCapabilities>(EMPTY_CAPABILITIES);
  const [dataStatus, setDataStatus] = useState<'loading' | 'live' | 'locked'>('loading');
  const [commandNotice, setCommandNotice] = useState('');

  // ── UI state ─────────────────────────────────────────────────────────────
  const [selection, setSelection] = useState<Selection>({ type: 'none' });
  const [elapsed, setElapsed]     = useState<Record<string, number>>({});
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
    Promise.allSettled([
      getAgents(),
      getOSPlugins(),
      getGraph(),
      getLegalAssignments(),
      getDashboardCapabilities(),
    ]).then(([agentResult, osResult, graphResult, legalResult, capabilityResult]) => {
      if (!mounted) return;
      const nextAgents = agentResult.status === 'fulfilled' ? agentResult.value : [];
      setAgents(nextAgents);
      setOS(osResult.status === 'fulfilled' ? osResult.value : []);
      setGraph(
        graphResult.status === 'fulfilled'
          ? graphResult.value
          : { nodes: [], links: [] },
      );
      setLegalAssignments(legalResult.status === 'fulfilled' ? legalResult.value : []);
      setCapabilities(
        capabilityResult.status === 'fulfilled'
          ? capabilityResult.value
          : EMPTY_CAPABILITIES,
      );
      setElapsed(Object.fromEntries(nextAgents.map(a => [a.id, a.elapsed ?? 0])));
      setSelection(
        nextAgents.length > 0
          ? { type: 'agent', agent: nextAgents[0] }
          : { type: 'none' },
      );
      setDataStatus(
        agentResult.status === 'fulfilled' && graphResult.status === 'fulfilled'
          ? 'live'
          : 'locked',
      );
    });
    return () => { mounted = false; };
  }, []);

  // ── Legal assignment live feed ───────────────────────────────────────────
  useEffect(() => {
    let mounted = true;
    const refresh = () => {
      getLegalAssignments().then(items => {
        if (mounted) setLegalAssignments(items);
      }).catch(() => {});
    };
    const interval = window.setInterval(refresh, 5_000);
    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
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
        const payload = msg.line;
        const agentId =
          typeof payload === 'object' && payload
            ? (payload as Record<string, unknown>).agentId as string
            : msg.agent_id as string;
        const line =
          typeof payload === 'object' && payload
            ? (payload as Record<string, unknown>).text as string
            : payload as string;
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
        const agentId = (msg.agentId ?? msg.agent_id) as string;
        setAgents(prev => prev.map(a => a.id === agentId ? { ...a, status: 'STOPPED' } : a));
      } else if (type === 'project.updated') {
        // Graph data may have changed — refresh
        getGraph().then(gd => setGraph(gd)).catch(() => {});
      } else if (type === 'graph.node.updated') {
        const node = msg.node as GraphNode | undefined;
        const nodeId = node?.id ?? msg.node_id as string;
        const status = node?.status ?? msg.status as string;
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

  const commandError = useCallback((reason: unknown) => {
    const text = reason instanceof Error ? reason.message : '';
    if (/authorization|authentication|session expired/i.test(text)) {
      return 'SIGN IN ON LEGAL AGENT OS BEFORE USING COMMAND CONTROLS';
    }
    if (/adapter|delivered|503/i.test(text)) {
      return 'COMMAND NOT SENT · OS CONTROL ADAPTER IS NOT CONNECTED';
    }
    return 'COMMAND NOT SENT · NO EXTERNAL STATE CHANGED';
  }, []);

  const onInteract = useCallback((id: string, m: string) => {
    setCommandNotice('SENDING OPERATOR MESSAGE…');
    messageAgent(id, m).then(() => {
      setInteractLog(l => ({ ...l, [id]: [...(l[id] || []), '✓ ' + m] }));
      setLogLines(prev => [...prev, '‹ operator: ' + m, '✓ command accepted by connected adapter']);
      setCommandNotice('MESSAGE ACCEPTED BY CONNECTED ADAPTER');
    }).catch(reason => {
      const notice = commandError(reason);
      setInteractLog(l => ({ ...l, [id]: [...(l[id] || []), '✗ NOT SENT · ' + m] }));
      setCommandNotice(notice);
    });
  }, [commandError]);

  const onPause = useCallback((id: string) => {
    setCommandNotice('SENDING PAUSE COMMAND…');
    pauseAgent(id).then(() => {
      setAgents(prev => prev.map(a => a.id === id ? { ...a, status: 'PAUSED' } : a));
      setCommandNotice('PAUSE ACCEPTED BY CONNECTED ADAPTER');
    }).catch(reason => setCommandNotice(commandError(reason)));
  }, [commandError]);
  const onStop    = useCallback((id: string) => {
    setCommandNotice('SENDING STOP COMMAND…');
    stopAgent(id).then(() => {
      setAgents(prev => prev.map(a => a.id === id ? { ...a, status: 'STOPPED' } : a));
      setCommandNotice('STOP ACCEPTED BY CONNECTED ADAPTER');
    }).catch(reason => setCommandNotice(commandError(reason)));
  }, [commandError]);
  const onRestart = useCallback((id: string) => {
    setCommandNotice('SENDING RESTART COMMAND…');
    restartAgent(id).then(() => {
      setAgents(prev => prev.map(a => a.id === id ? { ...a, status: 'RUNNING' } : a));
      setCommandNotice('RESTART ACCEPTED BY CONNECTED ADAPTER');
    }).catch(reason => setCommandNotice(commandError(reason)));
  }, [commandError]);
  const onLaunch  = useCallback((id: string) => {
    setCommandNotice('SENDING LAUNCH COMMAND…');
    launchOS(id).then(() => {
      setCommandNotice('LAUNCH ACCEPTED BY CONNECTED ADAPTER');
    }).catch(reason => setCommandNotice(commandError(reason)));
  }, [commandError]);

  // MARK COMPLETE — fires API, optimistically updates graph node, broadcasts via WS
  const onMarkComplete = useCallback((nodeId: string) => {
    setCommandNotice('SENDING GRAPH UPDATE…');
    markNodeComplete(nodeId).then(() => {
      setGraph(prev => ({
        ...prev,
        nodes: prev.nodes.map(n =>
          n.id === nodeId ? { ...n, status: 'COMPLETE' as import('../types').NodeStatus } : n
        ),
      }));
      setCommandNotice('GRAPH UPDATE ACCEPTED BY CONNECTED ADAPTER');
    }).catch(reason => setCommandNotice(commandError(reason)));
  }, [commandError]);

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
          <div className={'cc-control-state ' + (capabilities.commandDispatchEnabled ? 'ready' : 'readonly')}>
            <strong>
              {capabilities.commandDispatchEnabled
                ? 'COMMAND ADAPTER CONNECTED'
                : 'LIVE MONITOR · COMMANDS READ ONLY'}
            </strong>
            <span>
              {capabilities.commandDispatchEnabled
                ? 'Jeff-only controls are available.'
                : 'Launch, stop, message, and graph changes unlock only after an OS control adapter is verified.'}
            </span>
          </div>
          {commandNotice && <div className="cc-command-notice">{commandNotice}</div>}
          <div className="registry-list">
            <OSRegistry
              plugins={osPlugins}
              selAgent={selAgent}
              onLaunch={onLaunch}
              controlsEnabled={capabilities.commandDispatchEnabled}
            />
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
              : { flex: '0 0 auto', maxHeight: '36%', overflow: 'hidden' }
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
                    <button
                      className="btn sm danger"
                      disabled={!capabilities.commandDispatchEnabled}
                      onClick={e => stopInline(e, a.id)}
                    >
                      ■ STOP
                    </button>
                  </div>
                </div>
              ))}
              {agents.length === 0 && (
                <div className="cc-private-empty">
                  {dataStatus === 'loading'
                    ? 'LOADING LIVE AGENT INDEX…'
                    : 'NO AUTHORIZED AGENT SESSIONS VISIBLE'}
                  <small>
                    {dataStatus === 'locked'
                      ? 'Sign in on Legal Agent OS to load private agent activity.'
                      : 'New sessions appear here only after a connected OS reports them.'}
                  </small>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Legal assignment activity */}
        <div
          className="panel legal-assignment-panel"
          style={
            layoutDir === 'graph'
              ? { flex: '0 0 390px', minHeight: 0, overflow: 'hidden' }
              : { flex: '0 0 auto', maxHeight: '32%', overflow: 'hidden' }
          }
        >
          <LegalAssignmentsPanel assignments={legalAssignments} />
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
            controlsEnabled={capabilities.commandDispatchEnabled}
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
          {graphData.nodes.length > 0 ? (
            <ProjectGraph
              data={graphData}
              selectedId={selectedId}
              onSelect={handleNode}
              fullscreen={graphFs}
              onToggleFs={() => setGraphFs(!graphFs)}
              tweaks={tweaks}
              pulseSet={pulseSet}
              onMarkComplete={
                capabilities.commandDispatchEnabled ? onMarkComplete : undefined
              }
              onViewLog={(node) => {
                const agent = node.agentId ? agentsById[node.agentId] : null;
                if (agent) onViewLog(agent);
                else handleNode(node);
              }}
            />
          ) : (
            <div className="cc-private-empty graph-empty">
              {dataStatus === 'loading' ? 'LOADING PRIVATE PROJECT MAP…' : 'PRIVATE PROJECT MAP LOCKED'}
              <small>Sign in on Legal Agent OS to load authorized project data.</small>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
