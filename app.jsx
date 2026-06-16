// app.jsx — shell: header, tab nav, clock, notifications, footer, tweaks
const { useState: useStateApp, useEffect: useEffectApp, useMemo: useMemoApp } = React;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "layout": "classic",
  "glow": 1,
  "rotSpeed": 0.05,
  "scanlines": true,
  "goldTone": "#FFD700"
}/*EDITMODE-END*/;

const TABS = [
  { id: "command", label: "COMMAND CENTER" },
  { id: "notebook", label: "NOTEBOOK" },
  { id: "mission", label: "MISSION CONTROL" },
];

const NOTIFS = [
  { err: true,  t: "Brand Voice OS — voice-tuner halted (missing token)", time: "2m ago" },
  { err: false, t: "Builder OS — CI on PR #482 reached 94%", time: "5m ago" },
  { err: false, t: "Marketing-OS — 6/14 posts scheduled via Postiz", time: "9m ago" },
  { err: false, t: "JK Author OS — 2 continuity conflicts flagged", time: "14m ago" },
  { err: false, t: "Pricing Page Rewrite moved to COMPLETE", time: "1h ago" },
];

function Clock() {
  const [now, setNow] = useStateApp(new Date());
  useEffectApp(() => { const iv = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(iv); }, []);
  const time = now.toLocaleTimeString("en-US", { hour12: false });
  const date = now.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" }).toUpperCase();
  return <div className="clock"><div className="time">{time}</div><div className="date">{date}</div></div>;
}

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [tab, setTab] = useStateApp("command");
  const [collapsed, setCollapsed] = useStateApp(false);
  const [graphFs, setGraphFs] = useStateApp(false);
  const [notifOpen, setNotifOpen] = useStateApp(false);

  const pulseSet = useMemoApp(() => new Set(RUNNING_AGENTS.filter((a) => a.status === "RUNNING").map((a) => a.id)), []);
  const errCount = OS_REGISTRY.filter((o) => o.status === "ERROR").length;

  // apply visual tweaks to :root
  useEffectApp(() => {
    const r = document.documentElement.style;
    r.setProperty("--glow", String(t.glow));
    r.setProperty("--gold", t.goldTone);
    document.querySelector(".fx-scanlines").style.display = t.scanlines ? "" : "none";
  }, [t.glow, t.goldTone, t.scanlines]);

  // keyboard shortcuts
  useEffectApp(() => {
    const onKey = (e) => {
      if (e.target.matches("input, textarea")) return;
      if (e.key === "1") setTab("command");
      else if (e.key === "2") setTab("notebook");
      else if (e.key === "3") setTab("mission");
      else if (e.key === "\\") setCollapsed((c) => !c);
      else if (e.key.toLowerCase() === "g" && tab === "command") setGraphFs((f) => !f);
      else if (e.key === "Escape") { setGraphFs(false); setNotifOpen(false); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tab]);

  return (
    <div className={"shell" + (collapsed ? " collapsed" : "")}>
      {/* HEADER */}
      <header className="header">
        <div className="brand">
          <div className="brand-mark">
            <svg viewBox="0 0 40 40" fill="none">
              <path d="M20 2 L34 9 V22 C34 30 28 35 20 38 C12 35 6 30 6 22 V9 Z" stroke="var(--gold)" strokeWidth="1.5" fill="rgba(255,215,0,0.06)"/>
              <path d="M14 19 a6 4 0 1 1 12 0 a6 4 0 1 1 -12 0" stroke="var(--gold)" strokeWidth="1.3" fill="none"/>
              <circle cx="20" cy="19" r="2.4" fill="var(--gold)"/>
              <path d="M20 9 V13 M20 25 V29 M11 19 H8 M32 19 H29" stroke="var(--gold)" strokeWidth="1.2"/>
            </svg>
          </div>
          <div>
            <div className="brand-title">SRI OS COMMAND CENTER</div>
            <div className="brand-sub">CENTRAL OPS · v2.6</div>
          </div>
        </div>

        <div className={"health" + (errCount ? " warn" : "")}>
          <span className="dot"></span>
          <span className="label">SYSTEM</span>
          <span className="val">{errCount ? `DEGRADED · ${errCount} FAULT` : "ALL NOMINAL"}</span>
        </div>

        <nav className="tabs">
          {TABS.map((tb, i) => (
            <button key={tb.id} className={"tab" + (tab === tb.id ? " active" : "")} onClick={() => setTab(tb.id)}>
              <span className="idx">{String(i + 1).padStart(2, "0")}</span>{tb.label}
            </button>
          ))}
        </nav>

        <div className="header-right">
          <Clock />
          <div className="bell" onClick={() => setNotifOpen((o) => !o)} title="System events">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M6 9a6 6 0 1112 0c0 5 2 6 2 6H4s2-1 2-6z"/><path d="M10 20a2 2 0 004 0"/>
            </svg>
            <span className="badge-dot badge" style={{ display: "none" }}></span>
            <span className="badge" style={{ position: "absolute", top: -5, right: -5, minWidth: 15, height: 15, padding: "0 3px", background: "var(--gold)", color: "#1a1300", borderRadius: 8, fontSize: 9, fontWeight: 700, display: "grid", placeItems: "center", border: "none" }}>{NOTIFS.length}</span>
          </div>
        </div>

        {notifOpen && (
          <div className="notif">
            <h4>SYSTEM EVENTS · {NOTIFS.length}</h4>
            {NOTIFS.map((n, i) => (
              <div className={"notif-item" + (n.err ? " err" : "")} key={i}>
                <span className="nd"></span>
                <div><div className="nt">{n.t}</div><div className="ntime">{n.time}</div></div>
              </div>
            ))}
          </div>
        )}
      </header>

      {/* MAIN */}
      <div className="main">
        {(tab === "command" || tab === "notebook") && (
          <button className="collapse-toggle" onClick={() => setCollapsed((c) => !c)} title="Toggle sidebar (\\)">
            {collapsed ? "›" : "‹"}
          </button>
        )}
        <div className={"view" + (tab === "command" ? " active" : "")}>
          {tab === "command" && <CommandCenter layoutDir={t.layout} tweaks={t} graphFs={graphFs} setGraphFs={setGraphFs} pulseSet={pulseSet} />}
        </div>
        <div className={"view" + (tab === "notebook" ? " active" : "")}>
          {tab === "notebook" && <Notebook />}
        </div>
        <div className={"view" + (tab === "mission" ? " active" : "")}>
          {tab === "mission" && <MissionControl />}
        </div>
      </div>

      {/* FOOTER */}
      <footer className="footer">
        <span><span className="k">SRI-OS</span> · operator console</span>
        <span><kbd>1</kbd><kbd>2</kbd><kbd>3</kbd> switch view</span>
        <span><kbd>\</kbd> toggle sidebar</span>
        {tab === "command" && <span><kbd>G</kbd> graph fullscreen</span>}
        <span><kbd>Esc</kbd> close</span>
        <span className="spacer"></span>
        <span><span className="k">●</span> LINK STABLE · 14ms</span>
        <span>{RUNNING_AGENTS.filter(a=>a.status==="RUNNING").length} AGENTS LIVE</span>
      </footer>

      {/* TWEAKS */}
      <TweaksPanel>
        <TweakSection label="Command Center layout" />
        <TweakRadio label="Direction" value={t.layout}
          options={["classic", "focus", "graph"]}
          onChange={(v) => setTweak("layout", v)} />
        <TweakSection label="HUD intensity" />
        <TweakSlider label="Glow" value={t.glow} min={0} max={1.4} step={0.05}
          onChange={(v) => setTweak("glow", v)} />
        <TweakToggle label="Scanlines" value={t.scanlines} onChange={(v) => setTweak("scanlines", v)} />
        <TweakSection label="Constellation" />
        <TweakSlider label="Spin speed" value={t.rotSpeed} min={0} max={0.2} step={0.01}
          onChange={(v) => setTweak("rotSpeed", v)} />
        <TweakSection label="Accent" />
        <TweakColor label="Gold tone" value={t.goldTone}
          options={["#FFD700", "#FFB000", "#FFE45C", "#F5C518"]}
          onChange={(v) => setTweak("goldTone", v)} />
      </TweaksPanel>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
