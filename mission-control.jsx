// mission-control.jsx — Tab 3: kanban board with drag between lanes
const { useState: useStateMC } = React;

function MissionControl() {
  const [projects, setProjects] = useStateMC(() => PROJECTS.map((p) => ({ ...p })));
  const [drag, setDrag] = useStateMC(null);          // project id being dragged
  const [over, setOver] = useStateMC(null);          // lane being hovered

  const move = (pid, lane) => {
    setProjects((ps) => ps.map((p) => p.id === pid ? { ...p, lane, updated: "just now" } : p));
  };
  const addProject = () => {
    const id = "p" + Date.now();
    const os = OS_REGISTRY[Math.floor(Math.random() * OS_REGISTRY.length)];
    setProjects((ps) => [{ id, name: "New Project", os: os.id, owner: "—", priority: "MED", lane: "PLANNING", updated: "just now" }, ...ps]);
  };

  return (
    <div className="mc">
      <div className="mc-head">
        <span className="mc-title">MISSION CONTROL</span>
        <span className="badge ACTIVE"><span className="bd"></span>{projects.filter(p=>p.lane==="IN PROGRESS").length} IN FLIGHT</span>
        <span className="badge BLOCKED"><span className="bd"></span>{projects.filter(p=>p.lane==="BLOCKED").length} BLOCKED</span>
        <button className="btn solid" style={{ marginLeft: "auto" }} onClick={addProject}>+ ADD PROJECT</button>
      </div>
      <div className="mc-board">
        {LANES.map((lane) => {
          const cards = projects.filter((p) => p.lane === lane);
          return (
            <section className={"panel mc-lane " + lane.replace(/\s/g, "") + (over === lane ? " drop-target" : "")} key={lane}
              onDragOver={(e) => { e.preventDefault(); if (over !== lane) setOver(lane); }}
              onDragLeave={(e) => { if (e.currentTarget === e.target) setOver(null); }}
              onDrop={() => { if (drag) move(drag, lane); setOver(null); setDrag(null); }}>
              <div className="mc-lane-h">
                <span className="lt">{lane}</span>
                <span className="lc">{cards.length}</span>
              </div>
              <div className="mc-cards">
                {cards.map((p) => {
                  const os = OS_BY_ID[p.os];
                  const initials = p.owner.replace(/[^A-Za-z. ]/g, "").split(/[.\s]+/).filter(Boolean).map(s=>s[0]).join("").slice(0,2).toUpperCase() || "—";
                  return (
                    <article className={"mc-card" + (drag === p.id ? " dragging" : "")} key={p.id}
                      draggable onDragStart={() => setDrag(p.id)} onDragEnd={() => { setDrag(null); setOver(null); }}>
                      <div className="ctop">
                        <span className="cname">{p.name}</span>
                        <span className={"prio " + p.priority}>{p.priority}</span>
                      </div>
                      <div className="cmeta"><span className="cos">{os ? os.name.replace(/ \(.*\)/, "") : p.os}</span></div>
                      <div className="cfoot">
                        <span className="cowner"><span className="av">{initials}</span>{p.owner}</span>
                        <span className="cupd">{p.updated}</span>
                      </div>
                    </article>
                  );
                })}
                {cards.length === 0 && <div className="empty" style={{ padding: 16 }}>— EMPTY —</div>}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

window.MissionControl = MissionControl;
