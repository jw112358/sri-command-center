import { useState, useEffect } from 'react';
import type { Project, Lane, Priority } from '../types';
import { getProjects, createProject, patchProject } from '../api/client';
import { PROJECTS as MOCK_PROJECTS, LANES, OS_REGISTRY as MOCK_OS } from '../mock/data';

export function MissionControl() {
  const [projects, setProjects] = useState<Project[]>(MOCK_PROJECTS.map(p => ({ ...p })));
  const [drag, setDrag]         = useState<string | null>(null);
  const [over, setOver]         = useState<string | null>(null);
  // Map of os.id -> os.name for quick lookup
  const [osNames, setOsNames]   = useState<Record<string, string>>(
    () => Object.fromEntries(MOCK_OS.map(o => [o.id, o.name]))
  );

  // ── Load projects from API ──────────────────────────────────────────────
  useEffect(() => {
    let mounted = true;
    getProjects().then(ps => {
      if (!mounted || ps.length === 0) return;
      setProjects(ps.map(p => ({ ...p })));
    }).catch(() => { /* keep mock */ });
    return () => { mounted = false; };
  }, []);

  // ── Move project to new lane (optimistic + API sync) ───────────────────
  const move = (pid: string, lane: Lane) => {
    setProjects(ps => ps.map(p => p.id === pid ? { ...p, lane, updated: 'just now' } : p));
    patchProject(pid, { lane }).catch(() => {
      // Revert on failure
      setProjects(ps => ps.map(p => p.id === pid ? { ...p, lane: p.lane } : p));
    });
  };

  // ── Add new project ────────────────────────────────────────────────────
  const addProject = () => {
    const osList = Object.keys(osNames);
    const osId   = osList[Math.floor(Math.random() * osList.length)] ?? 'builder-os';
    const body = { name: 'New Project', os: osId, owner: '—', priority: 'MED' as Priority };

    // Optimistic add
    const tmpId = 'tmp-' + Date.now();
    setProjects(ps => [
      { id: tmpId, ...body, lane: 'PLANNING' as Lane, updated: 'just now' },
      ...ps,
    ]);

    createProject(body)
      .then(created => {
        setProjects(ps => ps.map(p => p.id === tmpId ? created : p));
        if (created.os) setOsNames(m => ({ ...m, [created.os]: created.os }));
      })
      .catch(() => {
        // Keep the optimistic entry — user can still drag it
      });
  };

  return (
    <div className="mc">
      <div className="mc-head">
        <span className="mc-title">MISSION CONTROL</span>
        <span className="badge ACTIVE">
          <span className="bd"></span>
          {projects.filter(p => p.lane === 'IN PROGRESS').length} IN FLIGHT
        </span>
        <span className="badge BLOCKED">
          <span className="bd"></span>
          {projects.filter(p => p.lane === 'BLOCKED').length} BLOCKED
        </span>
        <button className="btn solid" style={{ marginLeft: 'auto' }} onClick={addProject}>
          + ADD PROJECT
        </button>
      </div>

      <div className="mc-board">
        {LANES.map(lane => {
          const cards = projects.filter(p => p.lane === lane);
          return (
            <section
              className={'panel mc-lane ' + lane.replace(/\s/g, '') + (over === lane ? ' drop-target' : '')}
              key={lane}
              onDragOver={e  => { e.preventDefault(); if (over !== lane) setOver(lane); }}
              onDragLeave={e => { if (e.currentTarget === e.target) setOver(null); }}
              onDrop={() => { if (drag) move(drag, lane as Lane); setOver(null); setDrag(null); }}
            >
              <div className="mc-lane-h">
                <span className="lt">{lane}</span>
                <span className="lc">{cards.length}</span>
              </div>
              <div className="mc-cards">
                {cards.map(p => {
                  const osName = osNames[p.os] ?? p.os;
                  const initials = p.owner
                    .replace(/[^A-Za-z. ]/g, '')
                    .split(/[.\s]+/)
                    .filter(Boolean)
                    .map(s => s[0])
                    .join('')
                    .slice(0, 2)
                    .toUpperCase() || '—';

                  // CI status indicator
                  const ciClass =
                    p.ciStatus === 'failure' ? 'err' :
                    p.ciStatus === 'success' ? 'dim' : '';

                  return (
                    <article
                      className={'mc-card' + (drag === p.id ? ' dragging' : '')}
                      key={p.id}
                      draggable
                      onDragStart={() => setDrag(p.id)}
                      onDragEnd={() => { setDrag(null); setOver(null); }}
                    >
                      <div className="ctop">
                        <span className="cname">{p.name}</span>
                        <span className={'prio ' + p.priority}>{p.priority}</span>
                      </div>
                      <div className="cmeta">
                        <span className="cos">{osName.replace(/ \(.*\)/, '')}</span>
                        {p.githubPrCount != null && p.githubPrCount > 0 && (
                          <span className={'cpr ' + ciClass} title={`${p.githubPrCount} open PRs · CI: ${p.ciStatus ?? 'unknown'}`}>
                            ⎇ {p.githubPrCount}
                          </span>
                        )}
                      </div>
                      <div className="cfoot">
                        <span className="cowner"><span className="av">{initials}</span>{p.owner}</span>
                        <span className="cupd">{p.updated}</span>
                      </div>
                    </article>
                  );
                })}
                {cards.length === 0 && (
                  <div className="empty" style={{ padding: 16 }}>— EMPTY —</div>
                )}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
