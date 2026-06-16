import { useState, useEffect, useCallback, useRef } from 'react';
import type { Tweaks, SystemEvent } from './types';
import { CommandCenter } from './components/CommandCenter';
import { Notebook } from './components/Notebook';
import { MissionControl } from './components/MissionControl';
import { getEvents, getHealth, connectWS } from './api/client';

// ─── Default tweaks ───────────────────────────────────────────────────────────
const DEFAULT_TWEAKS: Tweaks = {
  layout: 'classic',
  logSpeed: 1,
  animGraph: true,
  crtScan: false,
  glowNodes: true,
};

// ─── Clock ────────────────────────────────────────────────────────────────────
function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const iv = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(iv);
  }, []);
  const hhmm = now.toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  });
  const date = now.toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric', year: 'numeric',
  });
  return (
    <div className="clock">
      <span className="hhmm">{hhmm}</span>
      <span className="date">{date}</span>
    </div>
  );
}

// ─── Notification bell ────────────────────────────────────────────────────────
interface NotifBellProps {
  events: SystemEvent[];
}

function NotifBell({ events }: NotifBellProps) {
  const [open, setOpen] = useState(false);
  const errCount = events.filter(e => e.severity === 'error' || e.severity === 'warning').length;

  return (
    <div className="notif-wrap" style={{ position: 'relative' }}>
      <button
        className={'btn icon' + (errCount > 0 ? ' has-err' : '')}
        onClick={() => setOpen(o => !o)}
        title="Notifications"
      >
        🔔
        {errCount > 0 && <span className="badge-dot">{errCount}</span>}
      </button>
      {open && (
        <div className="notif-dropdown">
          {events.length === 0 && (
            <div className="notif-item"><span className="nt">No notifications</span></div>
          )}
          {events.map(ev => (
            <div className={'notif-item' + (ev.severity === 'error' ? ' err' : '')} key={ev.id}>
              <span className="nt">{ev.text}</span>
              <span className="ntime">
                {ev.ts ? new Date(ev.ts).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false }) : ''}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Header ───────────────────────────────────────────────────────────────────
interface HeaderProps {
  tab: number;
  setTab: (t: number) => void;
  health: string;
  events: SystemEvent[];
}

const TABS = ['COMMAND CENTER', 'NOTEBOOK', 'MISSION CONTROL'] as const;

function Header({ tab, setTab, health, events }: HeaderProps) {
  const healthBadge = health === 'NOMINAL' ? 'ACTIVE' : 'ERROR';
  const healthLabel = health === 'NOMINAL' ? 'SYSTEMS NOMINAL' : health;
  return (
    <header className="app-header">
      <div className="logo-block">
        <span className="logo-mark">◈</span>
        <span className="logo-text">SRI OS</span>
        <span className="logo-sub">COMMAND CENTER</span>
      </div>

      <nav className="tab-nav" role="tablist">
        {TABS.map((label, i) => (
          <button
            key={label}
            role="tab"
            aria-selected={tab === i}
            className={'tab-btn' + (tab === i ? ' active' : '')}
            onClick={() => setTab(i)}
          >
            {label}
          </button>
        ))}
      </nav>

      <div className="header-right">
        <span className={'sys-health badge ' + healthBadge}>
          <span className="bd"></span>
          {healthLabel}
        </span>
        <Clock />
        <NotifBell events={events} />
      </div>
    </header>
  );
}

// ─── Footer ───────────────────────────────────────────────────────────────────
function Footer({ status }: { status: string }) {
  return (
    <footer className="app-footer">
      <span className="ft-l">SRI INTELLIGENCE · OPERATOR CONSOLE v1.0.0-alpha</span>
      <span className="ft-m">{status}</span>
      <span className="ft-r">[ ? ] HELP &nbsp;·&nbsp; [ K ] SHORTCUTS</span>
    </footer>
  );
}

// ─── Keyboard shortcuts overlay ───────────────────────────────────────────────
function Shortcuts({ onClose }: { onClose: () => void }) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-box shortcuts" onClick={e => e.stopPropagation()}>
        <div className="modal-h">
          KEYBOARD SHORTCUTS
          <button className="btn sm" onClick={onClose}>✕</button>
        </div>
        <table className="shortcuts-table">
          <tbody>
            <tr><td>1 / 2 / 3</td><td>Switch tabs</td></tr>
            <tr><td>G</td><td>Toggle graph fullscreen</td></tr>
            <tr><td>?</td><td>Toggle this panel</td></tr>
            <tr><td>Esc</td><td>Close overlays</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── App root ─────────────────────────────────────────────────────────────────
export default function App() {
  const [tab, setTab]             = useState(0);
  const [tweaks]                  = useState<Tweaks>(DEFAULT_TWEAKS);
  const [graphFs, setGraphFs]     = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [pulseSet]                = useState<Set<string>>(new Set());

  // Live data from API
  const [events, setEvents]       = useState<SystemEvent[]>([]);
  const [health, setHealth]       = useState<string>('NOMINAL');
  const [apiConnected, setApiConnected] = useState(false);

  // Footer status
  const [footerStatus, setFooterStatus] = useState('INITIALIZING…');

  // WS cleanup ref
  const wsCleanup = useRef<(() => void) | null>(null);

  // ── Boot: load events + health ─────────────────────────────────────────────
  useEffect(() => {
    let mounted = true;

    (async () => {
      try {
        const [evts, hlt] = await Promise.all([getEvents(), getHealth()]);
        if (!mounted) return;
        setEvents(evts);
        setHealth(hlt.status ?? 'NOMINAL');
        setApiConnected(true);
        setFooterStatus('CONNECTED · LIVE DATA');
      } catch {
        if (!mounted) return;
        setApiConnected(false);
        setFooterStatus('API OFFLINE · MOCK DATA');
      }
    })();

    return () => { mounted = false; };
  }, []);

  // ── WebSocket connection ───────────────────────────────────────────────────
  useEffect(() => {
    if (!apiConnected) return;

    wsCleanup.current = connectWS((msg) => {
      const type = msg.type as string;

      if (type === 'agent.log' || type === 'agent.updated' || type === 'agent.stopped') {
        // CommandCenter handles these via its own WS listener — no-op here
      } else if (type === 'system.event') {
        const ev = msg.event as SystemEvent;
        if (ev) setEvents(prev => [ev, ...prev].slice(0, 50));
      } else if (type === 'health') {
        const status = msg.status as string;
        if (status) setHealth(status);
      }
    });

    return () => { wsCleanup.current?.(); };
  }, [apiConnected]);

  // ── Poll health every 60s ──────────────────────────────────────────────────
  useEffect(() => {
    const iv = setInterval(async () => {
      try {
        const hlt = await getHealth();
        setHealth(hlt.status ?? 'NOMINAL');
        setFooterStatus('CONNECTED · LIVE DATA');
      } catch {
        setFooterStatus('API OFFLINE · MOCK DATA');
      }
    }, 60_000);
    return () => clearInterval(iv);
  }, []);

  // ── Keyboard shortcuts ─────────────────────────────────────────────────────
  const onKey = useCallback(
    (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      switch (e.key) {
        case '1': setTab(0); break;
        case '2': setTab(1); break;
        case '3': setTab(2); break;
        case 'g':
        case 'G':
          if (tab === 0) setGraphFs(f => !f);
          break;
        case '?':
          setShortcutsOpen(o => !o);
          break;
        case 'Escape':
          setShortcutsOpen(false);
          if (graphFs) setGraphFs(false);
          break;
      }
    },
    [tab, graphFs]
  );

  useEffect(() => {
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onKey]);

  return (
    <div className={'app' + (tweaks.crtScan ? ' crt' : '')}>
      <Header tab={tab} setTab={setTab} health={health} events={events} />

      <main className="app-main" role="main">
        {tab === 0 && (
          <CommandCenter
            layoutDir={tweaks.layout}
            tweaks={tweaks}
            graphFs={graphFs}
            setGraphFs={setGraphFs}
            pulseSet={pulseSet}
          />
        )}
        {tab === 1 && <Notebook />}
        {tab === 2 && <MissionControl />}
      </main>

      <Footer status={footerStatus} />
      {shortcutsOpen && <Shortcuts onClose={() => setShortcutsOpen(false)} />}
    </div>
  );
}
